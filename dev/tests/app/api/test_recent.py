"""KRRI_ASAP 화면에서 넣은 회차를 기억하고 창구 하나로 읽어가는 것.

LLM 도 온톨로지도 안 부른다. `/chat/stream` 이 내는 이벤트를 가짜로 흘려 넣고
**무엇이 남고 무엇이 안 남는가** 만 본다.

여기서 지키는 것은 다섯이다.
  기록이 터져도 답은 나간다
  개수를 막는다
  since 가 새 것만 준다
  raw JSON 이 안 샌다
  단계 줄을 다시 만들지 않는다
"""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.api.services.bridge import recent_service

# vendor_to_be_deleted/asap/workflow_answer 가 만든 답의 모양. 머리말 · 빈 줄 · 번호 줄이다.
ANSWER = "\n".join(
    [
        "오송역 CCTV 를 조회했습니다.",
        "",
        "1. geo.geocode        오송역 → 충북 청주시 (127.3277, 36.6200)",
        "2. road.getCctv       minX=127.31 · minY=36.61  83건",
    ]
)

# 문서 검색 답. 한 단계가 여러 줄이다 — 건수 줄 아래에 문서 조각이 붙는다.
RAG_ANSWER = "\n".join(
    [
        "철도안전법 문서를 조회했습니다.",
        "",
        "1. knowledge.query   6건",
        "   「철도안전법(법률)(제21188호)(20260303).pdf」 1쪽 · \"법제처 1 국가법령정보센터…\"",
        "   「철도안전법(법률)(제21188호)(20260303).pdf」 2쪽 · \"법제처 2 국가법령정보센터…\"",
    ]
)

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


def executed(answer=ANSWER, commands=None):
    """단계 둘을 부르고 끝난 회차 하나의 이벤트."""
    return [
        {"type": "step_start", "node": "resolve", "message": "발화를 해석하고 있습니다..."},
        {"type": "step_end", "node": "resolve", "message": "SELECT recipe_002"},
        {"type": "step_start", "node": "n_geocode", "message": "geo.geocode 호출 중입니다..."},
        {"type": "step_end", "node": "n_geocode", "message": "geo.geocode 완료"},
        {"type": "step_start", "node": "n_cctv", "message": "road.getCctv 호출 중입니다..."},
        {"type": "step_end", "node": "n_cctv", "message": "road.getCctv 완료"},
        {"type": "result", "answer": answer, "commands": commands or []},
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


def turn_of(text, payloads, resolve=None, ran=None):
    """회차 하나를 통째로 흘려 넣음. 훔쳐보는 자리도 함께 부름.

    입력  발화 · 이벤트 목록 · resolve 가 냈다고 할 것 · run 이 불렸다고 할 것
    출력  흘러나온 이벤트 목록
    """

    async def events():
        if resolve is not None:
            recent_service._note_resolve(resolve)
        if ran is not None:
            recent_service._note_run(*ran)
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

    def broken(answer, nodes):
        raise RuntimeError("기록이 터졌다")

    monkeypatch.setattr(recent_service, "_steps", broken)

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


def test_a_choice_turn_gets_its_recipe_from_run():
    """되묻기 뒤에 번호로 고르면 해석을 안 거친다. 그때는 run 만 지나간다."""
    turn_of("2번", executed(), ran=("recipe_045", "오송역"))

    turn = recent_service.since()["turns"][-1]

    assert turn["status"] == recent_service.CHOICE
    assert turn["recipe_id"] == "recipe_045"
    assert turn["argument"] == "오송역"


def test_a_resolve_called_outside_a_turn_keeps_nothing():
    """Streamlit 이 부르는 POST /resolve 는 회차가 아니다."""
    recent_service._note_resolve(resolved())

    assert recent_service.since() == {"seq": 0, "turns": []}


# ================================================================ 단계 줄
def test_step_lines_are_held_verbatim_as_written_in_the_answer():
    """요약하는 코드가 둘이 되면 한쪽이 raw JSON 을 흘린다."""
    turn_of("오송역 CCTV 보여줘", executed(), resolve=resolved())

    lines = [step["line"] for step in recent_service.since()["turns"][-1]["steps"]]

    assert lines == ANSWER.splitlines()[2:]


def test_the_node_attached_to_a_step_line_is_a_tool_step():
    """앞머리의 해석 단계(node="resolve")가 첫 줄에 붙으면 안 된다."""
    turn_of("오송역 CCTV 보여줘", executed(), resolve=resolved())

    nodes = [step["node"] for step in recent_service.since()["turns"][-1]["steps"]]

    assert nodes == ["n_geocode", "n_cctv"]


def test_a_step_of_several_lines_stays_one_block_entirely():
    """문서 조각을 떼어 내면 화면에서 「문서에서 찾아온다」가 안 보인다."""
    turn_of(
        "문서에서 철도안전법 관련 내용 찾아줘",
        [
            {"type": "step_end", "node": "resolve", "message": "SELECT recipe_013"},
            {"type": "step_end", "node": "search_documents", "message": "knowledge.query 완료"},
            {"type": "result", "answer": RAG_ANSWER, "commands": []},
        ],
        resolve=resolved(recipe_id="recipe_013"),
    )

    turn = recent_service.since()["turns"][-1]

    assert len(turn["steps"]) == 1
    assert turn["steps"][0]["node"] == "search_documents"
    assert turn["steps"][0]["line"] == "\n".join(RAG_ANSWER.splitlines()[2:])


def test_the_preamble_runs_up_to_the_first_step_line():
    turn_of(
        "문서에서 철도안전법 관련 내용 찾아줘",
        [{"type": "result", "answer": RAG_ANSWER, "commands": []}],
        resolve=resolved(recipe_id="recipe_013"),
    )

    assert recent_service.since()["turns"][-1]["head"] == "철도안전법 문서를 조회했습니다."


def test_a_clarify_answer_has_no_step_lines_so_it_is_all_preamble():
    """번호가 붙어 있어도 도구를 부른 것이 아니다.

    후보 줄을 단계로 읽으면 머리말이 첫 줄에서 잘려 무엇을 고를지가 안 보인다.
    """
    turn_of(
        "오송역 인구 구성 알려줘",
        [{"type": "result", "answer": CLARIFY_ANSWER, "commands": []}],
        resolve=resolved(status="CLARIFY", recipe_id=None),
    )

    turn = recent_service.since()["turns"][-1]

    assert turn["steps"] == []
    assert turn["head"] == CLARIFY_ANSWER


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
