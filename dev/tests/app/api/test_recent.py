"""KRRI_ASAP 화면에서 넣은 회차를 기억하고 창구 하나로 읽어가는 것.

LLM 도 온톨로지도 안 부른다. `/chat/stream` 이 내는 이벤트를 가짜로 흘려 넣고
**무엇이 남고 무엇이 안 남는가** 만 본다.

여기서 지키는 것은 다섯이다.
  기록이 터져도 답은 나간다
  개수를 막는다
  since 가 새 것만 준다
  raw JSON 이 안 샌다
  단계와 실행 판정은 이벤트에서 옮겨 적는다 — 답 문장을 가르지 않는다
"""

import asyncio
import json
from collections import deque

import pytest
from fastapi.testclient import TestClient

from app.api.services.bridge import recent_service

# 머리말 · 빈 줄 · 번호 줄로 된 답. **번호 줄이 있어도 단계가 아니다** — 단계는 이벤트로 온다.
ANSWER = "\n".join(
    [
        "오송역 CCTV 를 조회했습니다.",
        "",
        "1. geo.geocode        오송역 → 충북 청주시 (127.3277, 36.6200)",
        "2. road.getCctv       minX=127.31 · minY=36.61  83건",
    ]
)

# KRRI Gemini 가 쓴 답. 번호 줄이 없다 — KRRI 답은 단계 줄 꼴을 약속하지 않는다.
KRRI_ANSWER = "오송역 주변 15km 안에서 CCTV 3대를 찾았습니다."

# 되묻기 답. 번호가 앞에 공백을 두고 붙고 마침표가 없다. 단계 줄이 아니다.
CLARIFY_ANSWER = "\n".join(
    [
        "어느 것을 보시겠습니까?",
        "  1  인구 통계 조회",
        "  2  장소 좌표 변환 -> 인구 통계 조회",
    ]
)

# 지도 명령. **좌표 배열이 통째로 들어 있다.** 이것이 새면 안 된다.
GEOJSON_COMMANDS = [
    {
        "op": "addGeoJson",
        "args": {
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[127.3277, 36.6200], [127.3281, 36.6204]]],
                        },
                        "properties": {"cctvUrl": "rtsp://10.0.0.5/stream1"},
                    }
                ],
            }
        },
    }
]


def collect(events):
    """async generator 가 낸 이벤트를 순서대로 모음."""

    async def pump():
        return [event async for event in events]

    return asyncio.run(pump())


def stream(*payloads):
    """가짜 /chat 이벤트 흐름."""

    async def events():
        for payload in payloads:
            yield payload

    return events()


def executed(answer=ANSWER, commands=None, status="success", failed_last=False):
    """단계 둘을 부르고 끝난 회차 하나의 이벤트. KRRI 가 실행한 회차의 모양."""
    last_end = "road.getCctv 실패" if failed_last else "road.getCctv 완료"
    return [
        {"type": "step_start", "node": "resolve", "message": "발화를 해석하고 있습니다..."},
        {"type": "step_end", "node": "resolve", "message": "SELECT recipe_002"},
        {"type": "step_start", "node": "n_geocode", "message": "geo.geocode 호출 중입니다..."},
        {"type": "step_end", "node": "n_geocode", "message": "geo.geocode 완료", "failed": False},
        {"type": "step_start", "node": "n_cctv", "message": "road.getCctv 호출 중입니다..."},
        {"type": "step_end", "node": "n_cctv", "message": last_end, "failed": failed_last},
        {"type": "result", "answer": answer, "commands": commands or [], "status": status},
    ]


def resolved(**overrides):
    """resolve 가 냈다고 할 값."""
    answer = {
        "status": "SELECT",
        "recipe_id": "recipe_002",
        "candidate_recipe_ids": ["recipe_002"],
        "argument": "오송역",
    }
    answer.update(overrides)
    return answer


def turn_of(text, payloads, resolve=None):
    """회차 하나를 통째로 흘려 넣음. 훔쳐보는 자리도 함께 부름.

    입력  발화 · 이벤트 목록 · resolve 가 냈다고 할 것
    출력  흘러나온 이벤트 목록
    """

    async def events():
        if resolve is not None:
            recent_service._note_resolve(resolve)
        for payload in payloads:
            yield payload

    return collect(recent_service.watched(text, events()))


@pytest.fixture(autouse=True)
def empty():
    recent_service.clear()
    yield
    recent_service.clear()


# ================================================================ 기록
def test_no_event_is_lost_even_when_recording_blows_up(monkeypatch):
    """답이 먼저다. 기록은 이벤트가 다 나간 뒤에 도는 일이고 터져도 삼킨다."""

    class Broken(deque):
        def append(self, item):
            raise RuntimeError("기록이 터졌다")

    monkeypatch.setattr(recent_service, "_TURNS", Broken())

    payloads = executed()
    assert turn_of("오송역 CCTV 보여줘", payloads, resolve=resolved()) == payloads
    assert recent_service.since()["turns"] == []


def test_a_turn_that_never_saw_an_answer_is_not_kept():
    """중간에 끊긴 흐름은 남길 답이 없다."""
    turn_of("오송역 CCTV 보여줘", executed()[:4], resolve=resolved())

    assert recent_service.since()["turns"] == []


def test_exceeding_twenty_turns_evicts_the_oldest_first():
    for number in range(recent_service.MAX_TURNS + 5):
        turn_of(f"발화 {number}", executed(), resolve=resolved())

    everything = recent_service.since(0)["turns"]
    assert len(everything) == recent_service.MAX_TURNS
    assert everything[0]["utterance"] == "발화 5"
    assert everything[-1]["utterance"] == f"발화 {recent_service.MAX_TURNS + 4}"


def test_turn_numbers_only_ever_increase():
    """버려진 회차의 번호를 다시 쓰지 않는다. 화면이 이것으로 새 것을 안다."""
    for number in range(recent_service.MAX_TURNS + 5):
        turn_of(f"발화 {number}", executed(), resolve=resolved())

    assert recent_service.since()["seq"] == recent_service.MAX_TURNS + 5


# ================================================================ 창구
def test_giving_since_returns_only_what_is_greater():
    turn_of("첫 발화", executed(), resolve=resolved())
    turn_of("둘째 발화", executed(), resolve=resolved())
    turn_of("셋째 발화", executed(), resolve=resolved())

    fresh = recent_service.since(1)["turns"]

    assert [turn["utterance"] for turn in fresh] == ["둘째 발화", "셋째 발화"]


def test_since_at_the_current_number_gives_an_empty_list():
    turn_of("첫 발화", executed(), resolve=resolved())

    now = recent_service.since()

    assert recent_service.since(now["seq"])["turns"] == []


def test_with_nothing_put_in_the_number_is_0_and_the_list_is_empty():
    assert recent_service.since() == {"seq": 0, "turns": []}


def test_without_since_only_the_last_few_turns_come():
    for number in range(recent_service.TAIL + 3):
        turn_of(f"발화 {number}", executed(), resolve=resolved())

    assert len(recent_service.since()["turns"]) == recent_service.TAIL


# ================================================================ 무엇이 남는가
def test_the_candidates_and_the_argument_come_verbatim_from_the_resolve():
    turn_of("오송역 CCTV 보여줘", executed(), resolve=resolved())

    turn = recent_service.since()["turns"][-1]

    assert turn["status"] == "SELECT"
    assert turn["recipe_id"] == "recipe_002"
    assert turn["candidate_recipe_ids"] == ["recipe_002"]
    assert turn["argument"] == "오송역"


def test_a_clarify_keeps_its_candidates_verbatim_too():
    """화면이 되묻기 회차에서도 후보 경로를 강조할 수 있어야 한다."""
    turn_of(
        "오송역 인구 구성 알려줘",
        [{"type": "result", "answer": CLARIFY_ANSWER, "commands": []}],
        resolve=resolved(
            status="CLARIFY", recipe_id=None, candidate_recipe_ids=["recipe_011", "recipe_045"]
        ),
    )

    turn = recent_service.since()["turns"][-1]

    assert turn["status"] == "CLARIFY"
    assert turn["candidate_recipe_ids"] == ["recipe_011", "recipe_045"]


def test_a_resolve_called_outside_a_turn_keeps_nothing():
    """Streamlit 이 부르는 POST /resolve 는 회차가 아니다."""
    recent_service._note_resolve(resolved())

    assert recent_service.since() == {"seq": 0, "turns": []}


# ================================================================ 단계 · 실행 판정
def test_the_steps_are_the_events_in_the_order_they_came():
    """단계는 step_start · step_end 에서 옮겨 적는다. 차례 · node · 두 message 가 그대로다."""
    turn_of("오송역 CCTV 보여줘", executed(), resolve=resolved())

    steps = recent_service.since()["turns"][-1]["steps"]

    assert steps == [
        {"node": "resolve", "start_message": "발화를 해석하고 있습니다...", "end_message": "SELECT recipe_002", "failed": False},
        {"node": "n_geocode", "start_message": "geo.geocode 호출 중입니다...", "end_message": "geo.geocode 완료", "failed": False},
        {"node": "n_cctv", "start_message": "road.getCctv 호출 중입니다...", "end_message": "road.getCctv 완료", "failed": False},
    ]


def test_a_failed_step_is_marked_from_the_event_not_from_its_message():
    """실패는 step_end 의 failed 칸이 말한다. KRRI 가 trace 에 error 를 적은 단계다."""
    turn_of("오송역 CCTV 보여줘", executed(status="failed", failed_last=True), resolve=resolved())

    steps = recent_service.since()["turns"][-1]["steps"]

    assert [step["failed"] for step in steps] == [False, False, True]


def test_the_krri_status_is_kept_as_it_came():
    for status in ("success", "failed"):
        turn_of("오송역 CCTV 보여줘", executed(status=status), resolve=resolved())

        assert recent_service.since()["turns"][-1]["execution_status"] == status


def test_a_turn_krri_never_ran_has_no_execution_status():
    """되묻기 · 실행 전에 멈춘 자리 · 창구를 못 부른 자리. result 에 status 칸이 없다."""
    turn_of(
        "오송역 인구 구성 알려줘",
        [{"type": "result", "answer": CLARIFY_ANSWER, "commands": []}],
        resolve=resolved(status="CLARIFY", recipe_id=None),
    )

    turn = recent_service.since()["turns"][-1]

    assert turn["execution_status"] is None
    assert turn["steps"] == []


def test_an_answer_without_numbered_lines_still_keeps_its_steps():
    """KRRI Gemini 답에는 "1. " 줄이 없을 수 있다. 단계가 비면 안 된다."""
    turn_of("오송역 CCTV 보여줘", executed(answer=KRRI_ANSWER), resolve=resolved())

    turn = recent_service.since()["turns"][-1]

    assert [step["node"] for step in turn["steps"]] == ["resolve", "n_geocode", "n_cctv"]
    assert turn["answer"] == KRRI_ANSWER


def test_numbered_lines_in_the_answer_are_not_taken_for_steps():
    """답의 "1. " 줄은 답의 일부다. 단계 수 · 내용이 답에서 오지 않는다."""
    turn_of("오송역 CCTV 보여줘", executed(answer=ANSWER), resolve=resolved())

    turn = recent_service.since()["turns"][-1]

    assert len(turn["steps"]) == 3
    assert all(not step["end_message"].startswith(("1. ", "2. ")) for step in turn["steps"])
    assert turn["answer"] == ANSWER


def test_a_clarify_answer_is_kept_whole():
    """번호가 붙어 있어도 도구를 부른 것이 아니다. 후보 목록이 답 그대로 남는다."""
    turn_of(
        "오송역 인구 구성 알려줘",
        [{"type": "result", "answer": CLARIFY_ANSWER, "commands": []}],
        resolve=resolved(status="CLARIFY", recipe_id=None),
    )

    assert recent_service.since()["turns"][-1]["answer"] == CLARIFY_ANSWER


# ================================================================ raw JSON
def test_geojson_never_leaks_because_commands_are_not_kept_at_all():
    """commands 를 아예 안 읽는다. 이 저장소의 계약이다.

    칸이 없는 것이 곧 안 새는 까닭이라 둘을 함께 본다.
    """
    turn_of("오송역 CCTV 보여줘", executed(commands=GEOJSON_COMMANDS), resolve=resolved())

    assert "commands" not in recent_service.since()["turns"][-1]

    body = json.dumps(recent_service.since(0), ensure_ascii=False)
    for leaked in ("geojson", "coordinates", "geometry", "FeatureCollection", "rtsp://"):
        assert leaked not in body


# ================================================================ 엔드포인트
def test_the_recent_endpoint_gives_the_current_number_together_with_the_turns():
    from app.api.main import app

    turn_of("오송역 CCTV 보여줘", executed(), resolve=resolved())

    with TestClient(app) as client:
        payload = client.get("/recent").json()

    assert payload["seq"] == 1
    assert payload["turns"][0]["utterance"] == "오송역 CCTV 보여줘"


def test_the_recent_endpoint_accepts_since():
    from app.api.main import app

    turn_of("첫 발화", executed(), resolve=resolved())
    turn_of("둘째 발화", executed(), resolve=resolved())

    with TestClient(app) as client:
        payload = client.get("/recent", params={"since": 1}).json()

    assert [turn["utterance"] for turn in payload["turns"]] == ["둘째 발화"]
