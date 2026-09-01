"""`/chat` 과 `/chat/stream` 이 같은 답을 내는지 지킨다.

저쪽 화면은 `POST /chat/stream` 을 쓰고 — **시연에서 도는 길이 이쪽이다** —
tools/check_resolve.py --execute 는 `POST /chat` 을 쓴다. 둘은 지금 같은 흐름
(`app/api/main._chat_events`)을 쓰므로 같은 답이 나온다. main.py 주석도 그렇게
적고 있다: "두 경로가 다른 답을 하면 화면과 curl 중 무엇을 믿을지가 갈린다".

**경고만 있고 지키는 장치가 없었다.** tests/ 에 "chat/stream" 을 건드리는 시험이
0건이라, 누가 한쪽만 고쳐도 아무도 안 잡았다. 그 자리를 메운다.

지키는 것은 넷이다.
  answer 가 두 길에서 같다
  commands 가 두 길에서 같다 — 지도 명령이 화면에서만 어긋나는 것을 막는다
  SSE 틀 — "data: " 접두어 · 이벤트마다 빈 줄 · 마지막 [DONE]
  ensure_ascii 가 꺼져 한글이 그대로 나간다 (main.py 가 적은 제약이다)

**진짜 서버를 띄워 부르지 않는다.** 시연 중에 pytest 가 돌면 8000 을 쓰는 저쪽
화면과 부딪히고, LLM 이 회차마다 다른 답을 내면 이 시험이 답의 내용에 흔들린다.
여기서 볼 것은 「두 길이 같은가」지 「답이 맞는가」가 아니다. 그래서 TestClient
(프로세스 안)로 진짜 창구 함수를 부르되, `_chat_events` 만 대역으로 바꾼다 —
창구 두 개의 코드(/chat 의 result 추리기 · /chat/stream 의 SSE 직렬화)는 진짜가
돌고 LLM · 온톨로지 · vendor 실행기는 안 돈다.

이벤트 모양은 tests/app/api/test_recent.py 의 `executed()` 와 같은 것을 쓴다 —
이미 있는 대역이고, 저쪽 화면이 읽는 흐름의 모양이 거기 적혀 있다.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.api import main

# 저쪽 화면이 읽는 흐름. test_recent.executed() 와 같은 모양이다.
# **한글과 좌표를 일부러 담는다** — ensure_ascii 와 commands 를 함께 보려는 것이다.
ANSWER = "\n".join(
    [
        "오송역 CCTV 를 조회했습니다.",
        "",
        "1. geo.geocode        오송역 → 충북 청주시 (127.3277, 36.6200)",
        "2. road.getCctv       minX=127.31 · minY=36.61  83건",
    ]
)

COMMANDS = [
    {"op": "moveTo", "args": {"lon": 127.3277, "lat": 36.62, "zoom": 14}},
    {"op": "addGeoJson", "args": {"geojson": {"type": "FeatureCollection", "features": []}}},
]

EVENTS = [
    {"type": "step_start", "node": "resolve", "message": "발화를 해석하고 있습니다..."},
    {"type": "step_end", "node": "resolve", "message": "SELECT recipe_019"},
    {"type": "step_start", "node": "n_cctv", "message": "road.getCctv 호출 중입니다..."},
    {"type": "step_end", "node": "n_cctv", "message": "road.getCctv 완료"},
    {"type": "result", "answer": ANSWER, "commands": COMMANDS},
]

# sessionId 를 일부러 남겨 둔다. 2026-09-01 에 세션을 걷으면서 ChatRequest 의
# 칸을 지웠으므로 이것은 이제 모르는 칸이다. 저쪽 화면(ASAP-web)은 여전히
# 보내므로, 모르는 칸이 와도 422 가 안 나는 것을 두 창구가 함께 지킨다.
BODY = {"text": "오송역 CCTV 보여줘", "sessionId": "parity", "context": {}}


@pytest.fixture
def client(monkeypatch):
    """`_chat_events` 만 대역으로 바꾼 진짜 앱.

    창구 둘은 모듈 전역으로 `_chat_events` 를 찾으므로 여기만 바꾸면 둘 다
    같은 이벤트를 받는다. **두 창구에 서로 다른 대역을 물리지 않는 것이
    이 시험의 전부다** — 같은 입력에서 같은 답이 나오는지를 보는 것이라
    입력이 갈리면 아무것도 못 잰다.
    """

    def fake_chat_events(form, model=None):
        async def events():
            for payload in EVENTS:
                yield payload

        return events()

    monkeypatch.setattr(main, "_chat_events", fake_chat_events)
    return TestClient(main.app)


def sse_result(raw: str) -> dict:
    """SSE 본문에서 result 이벤트를 꺼냄. 틀을 지키는지도 함께 봄."""
    assert raw.endswith("\n\n"), "마지막 이벤트에도 빈 줄이 붙어야 한다"
    blocks = [block for block in raw.split("\n\n") if block]

    payloads = []
    for block in blocks:
        assert block.startswith("data: "), f'"data: " 접두어가 없다 : {block!r}'
        body = block[len("data: ") :]
        if body == "[DONE]":
            continue
        payloads.append(json.loads(body))

    assert blocks[-1] == "data: [DONE]", "마지막은 [DONE] 이어야 한다"

    results = [payload for payload in payloads if payload["type"] == "result"]
    assert len(results) == 1, f"result 가 하나여야 한다 : {len(results)}개"
    return results[0]


# ================================================================ 두 길이 같은가
def test_the_two_paths_give_the_same_answer(client):
    """화면(/chat/stream)과 curl(/chat) 중 무엇을 믿을지가 갈리지 않게."""
    plain = client.post("/chat", json=BODY).json()
    streamed = sse_result(client.post("/chat/stream", json=BODY).text)

    assert plain["answer"] == streamed["answer"]
    assert plain["answer"] == ANSWER


def test_the_two_paths_give_the_same_commands(client):
    """지도 명령이 어긋나면 화면에만 안 그려진다. answer 로는 안 잡힌다."""
    plain = client.post("/chat", json=BODY).json()
    streamed = sse_result(client.post("/chat/stream", json=BODY).text)

    assert plain["commands"] == streamed["commands"]
    assert plain["commands"] == COMMANDS


def test_chat_drops_the_intermediate_events_and_gives_only_the_result(client):
    """두 길의 **의도된** 차이. 이것까지 같아지면 SSE 를 쓸 까닭이 없다."""
    plain = client.post("/chat", json=BODY).json()

    assert set(plain) == {"answer", "commands"}


# ================================================================ SSE 틀
def test_step_events_flow_in_order_and_the_last_one_is_DONE(client):
    """저쪽 화면이 진행 상황을 그리는 근거. 순서가 바뀌면 화면이 어긋난다."""
    raw = client.post("/chat/stream", json=BODY).text
    sse_result(raw)  # 틀 검사

    bodies = [
        block[len("data: ") :]
        for block in raw.split("\n\n")
        if block and block != "data: [DONE]"
    ]
    kinds = [json.loads(body)["type"] for body in bodies]

    assert kinds == [payload["type"] for payload in EVENTS]
    assert kinds[-1] == "result", "result 뒤에 다른 이벤트가 오면 안 된다"


def test_the_media_type_is_event_stream(client):
    response = client.post("/chat/stream", json=BODY)

    assert response.headers["content-type"].startswith("text/event-stream")


def test_korean_goes_out_verbatim_without_escaping(client):
    """main.py 의 제약이다 — ensure_ascii 를 켜면 저쪽 화면에서 안 읽힌다."""
    raw = client.post("/chat/stream", json=BODY).text

    assert "오송역 CCTV 를 조회했습니다." in raw
    assert "\\u" not in raw, "유니코드 이스케이프가 섞였다 — ensure_ascii 가 켜졌다"
