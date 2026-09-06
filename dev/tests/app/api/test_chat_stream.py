"""`POST /chat/stream` 의 계약을 지킨다.

**제품 창구가 이것 하나다.** KRRI_ASAP 화면(ASAP-web)도 dev/tools/check_resolve.py
--execute 도 이쪽을 부른다.

지키는 것은 다섯이다.
  이벤트 순서 — step_start · step_end 가 짝으로, 마지막이 result
  SSE 틀 — "data: " 접두어 · 이벤트마다 빈 줄 · 마지막 [DONE]
  content-type 이 text/event-stream 이다
  ensure_ascii 가 꺼져 한글이 그대로 나간다 (main.py 가 적은 제약이다)
  모르는 칸이 와도 422 가 안 난다 — KRRI_ASAP 이 sessionId · target_documents 를
  여전히 보낸다

**진짜 서버를 띄워 부르지 않는다.** 시연 중에 pytest 가 돌면 8000 을 쓰는
KRRI_ASAP 화면과 부딪히고, LLM 이 회차마다 다른 답을 내면 이 시험이 답의 내용에 흔들린다.
여기서 볼 것은 「창구가 계약을 지키는가」지 「답이 맞는가」가 아니다. 그래서
TestClient(프로세스 안)로 진짜 창구 함수를 부르되 `_chat_events` 만 대역으로
바꾼다 — SSE 직렬화는 진짜가 돌고 LLM · 온톨로지 · vendor 실행기는 안 돈다.

이벤트 모양은 dev/tests/app/api/test_recent.py 의 `executed()` 와 같은 것을 쓴다 —
이미 있는 대역이고, KRRI_ASAP 화면이 읽는 흐름의 모양이 거기 적혀 있다.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.api import main

# KRRI_ASAP 화면이 읽는 흐름. test_recent.executed() 와 같은 모양이다.
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

# **모르는 칸을 일부러 남겨 둔다.** sessionId · target_documents 는 ChatRequest 에
# 없는데 KRRI_ASAP 화면은 둘 다 여전히 보낸다. 그것이 와도 422 가 안 나는 것을
# 이 본문이 지킨다.
BODY = {
    "text": "오송역 CCTV 보여줘",
    "sessionId": "stream",
    "target_documents": ["doc-1", "doc-2"],
    "context": {},
}


@pytest.fixture
def client(monkeypatch):
    """`_chat_events` 만 대역으로 바꾼 진짜 앱."""

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


# ================================================================ 창구가 하나다
def test_the_plain_chat_endpoint_is_gone(client):
    """창구를 /chat/stream 하나로 두기로 했다. 평범한 POST /chat 이 되살아나면 잡는다."""
    assert client.post("/chat", json=BODY).status_code == 404


# ================================================================ 답
def test_the_result_event_carries_the_answer(client):
    """KRRI_ASAP 화면이 읽는 두 칸이 마지막 이벤트에 그대로 실린다."""
    result = sse_result(client.post("/chat/stream", json=BODY).text)

    assert result["answer"] == ANSWER
    assert result["commands"] == COMMANDS


# ================================================================ SSE 틀
def test_step_events_flow_in_order_and_the_last_one_is_DONE(client):
    """KRRI_ASAP 화면이 진행 상황을 그리는 근거. 순서가 바뀌면 화면이 어긋난다."""
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
    """main.py 의 제약이다 — ensure_ascii 를 켜면 KRRI_ASAP 화면에서 안 읽힌다."""
    raw = client.post("/chat/stream", json=BODY).text

    assert "오송역 CCTV 를 조회했습니다." in raw
    assert "\\u" not in raw, "유니코드 이스케이프가 섞였다 — ensure_ascii 가 켜졌다"


# ================================================================ 모르는 칸
def test_unknown_fields_are_dropped_instead_of_rejected(client):
    """KRRI_ASAP 이 sessionId · target_documents 를 보내도 422 가 아니어야 한다.

    ChatRequest 에 그 칸이 없다. pydantic 이 모르는 칸을 그냥 버리는 것이
    「안 읽는 칸은 선언하지 않는다」의 근거이므로 여기서 실제로 지킨다.
    """
    assert client.post("/chat/stream", json=BODY).status_code == 200

    form = main.ChatRequest(**BODY)
    assert not hasattr(form, "target_documents")
    assert not hasattr(form, "sessionId")
    assert form.text == BODY["text"]
