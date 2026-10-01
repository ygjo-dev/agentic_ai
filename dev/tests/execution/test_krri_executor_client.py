"""대상 : execution/krri_executor_client.py — 완성된 workflow 를 KRRI 실행 창구로 나르는 HTTP 손

나르기만 한다. 본문 · 헤더 모양, 이벤트를 받는 대로 내는지, 못 불렀을 때 KrriExecutorError
하나로 올리는지를 본다. 주고받는 모양은 KRRI_ASAP ASAP-orchestrator/tests/test_workflow_execute_stream.py
와 같다.

KRRI 는 부르지 않는다. httpx 의 MockTransport 가 대신 답한다.
"""

import asyncio
import copy
import json

import httpx
import pytest

from execution import krri_executor_client

ORCHESTRATOR = "http://krri-orchestrator.test:18100"

WORKFLOW = {
    "action": "call_mcp_workflow",
    "steps": [
        {"id": "s1", "server_id": "asap-mcp-core", "tool": "geo.geocode", "input": {"query": "오송역"}},
        {
            "id": "s2",
            "server_id": "asap-mcp-core",
            "tool": "road.getCctv",
            "input": {"center": ["$s1.location.0", "$s1.location.1"], "radiusMeters": 15000},
            "inputAdapter": "point_radius_to_bbox",
        },
    ],
}

USER_CONTEXT = {
    "user_id": "asap-ontology-orchestrator",
    "selected_mcp_tool_refs": ["asap-mcp-core/*", "r5-server/*", "otp-router/*"],
}

# KRRI WorkflowExecuteResponse 한 벌. 스트림의 result 이벤트가 이 칸을 그대로 갖는다.
KRRI_RESPONSE = {
    "status": "success",
    "answer": "오송역 주변 CCTV 3대를 찾았습니다.",
    "commands": [{"op": "map.draw", "args": {"layerId": "mcp-place"}}],
    "trace": [{"id": "s1", "server_id": "asap-mcp-core", "tool": "geo.geocode", "input": {}, "result": {}}],
    "errors": [],
}


# Gateway 가 KRRI_ASAP 채팅의 /chat/stream 에 넣는 여섯 값. 값은 예시다.
GATEWAY_HEADERS = {
    "X-User-ID": "guest:6f1c2d3e-4a5b-4c6d-8e7f-0a1b2c3d4e5f",
    "X-User-Name": "guest",
    "X-User-Role": "",
    "X-User-MCP-Servers": "asap-mcp-core",
    "X-User-MCP-Tools": "asap-mcp-core/geo.geocode,otp-router/*",
    "X-User-MCP-Groups": "krri-map-location,route-accessibility",
}


def sse(*events) -> str:
    """KRRI(sse-starlette)가 보내는 본문. 줄 끝이 CRLF 다."""
    return "".join(
        f"data: {event if isinstance(event, str) else json.dumps(event, ensure_ascii=False)}\r\n\r\n"
        for event in events
    )


def krri_stream(response=KRRI_RESPONSE, deltas=("오송역 주변 ", "CCTV 3대를 찾았습니다.")):
    """KRRI 스트림 한 벌. execution · 조각 · result · [DONE]."""
    execution = {"type": "execution", **{k: v for k, v in response.items() if k != "answer"}}
    return sse(execution, *({"type": "answer_delta", "text": text} for text in deltas),
               {"type": "result", **response}, "[DONE]")


def stream_response(text: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, text=text, headers={"content-type": "text/event-stream"})


def call(workflow=WORKFLOW, context=None, headers=None):
    """stream_workflow 가 낸 이벤트 전부."""

    async def pump():
        return [event async for event in krri_executor_client.stream_workflow(
            workflow,
            user_text="오송역 CCTV 보여줘",
            context=context if context is not None else {"view": {"zoom": 12}},
            headers=headers if headers is not None else krri_executor_client.identity_headers(USER_CONTEXT),
        )]

    return asyncio.run(pump())


@pytest.fixture
def krri(monkeypatch):
    """KRRI 창구 대역. handler 를 갈아 끼우고, 받은 요청을 남긴다."""
    monkeypatch.setenv("ASAP_ORCHESTRATOR_URL", ORCHESTRATOR)
    state = {"requests": [], "handler": lambda request: stream_response(krri_stream())}

    def handle(request):
        state["requests"].append(request)
        return state["handler"](request)

    real = httpx.AsyncClient
    monkeypatch.setattr(
        krri_executor_client.httpx,
        "AsyncClient",
        lambda **kwargs: real(transport=httpx.MockTransport(handle), **kwargs),
    )
    return state


def test_the_workflow_goes_out_byte_for_byte(krri):
    """본문의 workflow 가 받은 그대로다. 서버 · 도구 · 차례 · raw 참조 · inputAdapter 가 안 바뀐다."""
    before = copy.deepcopy(WORKFLOW)

    call()

    (request,) = krri["requests"]
    assert request.method == "POST"
    assert str(request.url) == ORCHESTRATOR + "/workflow/execute/stream"
    body = json.loads(request.content)
    assert set(body) == {"workflow", "user_text", "context"}
    assert body["workflow"] == before == WORKFLOW
    assert body["user_text"] == "오송역 CCTV 보여줘"
    assert body["context"] == {"view": {"zoom": 12}}


def test_the_identity_goes_out_as_the_same_headers_gateway_uses(krri):
    """KRRI 는 /chat 과 같은 X-User-* 헤더로 신원과 도구 범위를 읽는다."""
    call()

    headers = krri["requests"][0].headers
    assert headers["X-User-ID"] == "asap-ontology-orchestrator"
    assert headers["X-User-MCP-Tools"] == "asap-mcp-core/*,r5-server/*,otp-router/*"


def test_the_gateway_headers_go_out_as_they_came(krri):
    """Gateway 가 준 여섯 값을 이름 · 값 그대로 싣는다. 빈 값도 빼지 않는다."""
    call(headers=GATEWAY_HEADERS)

    sent = krri["requests"][0].headers
    assert {name: sent[name] for name in GATEWAY_HEADERS} == GATEWAY_HEADERS
    assert sent.get_list("X-User-Role") == [""]


def test_a_latin1_header_value_goes_out_byte_for_byte(krri):
    """들어온 헤더는 latin-1 로 풀린 문자열이다. 같은 바이트로 되돌려 싣는다."""
    call(headers={**GATEWAY_HEADERS, "X-User-Name": "gäst"})

    raw = dict(krri["requests"][0].headers.raw)
    assert raw[b"X-User-Name"] == "gäst".encode("latin-1")


def test_the_krri_events_come_back_as_they_are_in_order(krri):
    """execution · 조각 · result 를 온 차례 그대로, 고치지 않고 낸다. [DONE] 은 안 냄."""
    events = call()

    assert [event["type"] for event in events] == ["execution", "answer_delta", "answer_delta", "result"]
    assert [event["text"] for event in events[1:3]] == ["오송역 주변 ", "CCTV 3대를 찾았습니다."]
    assert {k: v for k, v in events[-1].items() if k != "type"} == KRRI_RESPONSE


def test_a_krri_failure_is_a_result_not_an_error(krri):
    """KRRI 가 실행하다 실패한 것은 200 + status=failed 다. 실행 결과로 돌려준다."""
    failed = {**KRRI_RESPONSE, "status": "failed", "answer": "s1 단계 실패", "commands": [], "errors": ["s1 단계 실패"]}
    krri["handler"] = lambda request: stream_response(krri_stream(failed, deltas=()))

    assert {k: v for k, v in call()[-1].items() if k != "type"} == failed


def test_pings_and_unknown_events_are_skipped(krri):
    """sse-starlette 의 ping 주석 줄과 모르는 type 은 건너뛴다."""
    krri["handler"] = lambda request: stream_response(
        ": ping - 2026-10-01\r\n\r\n" + sse({"type": "앞으로_생길_것", "x": 1}) + krri_stream())

    assert [event["type"] for event in call()] == ["execution", "answer_delta", "answer_delta", "result"]


def test_each_event_is_handed_over_before_the_body_ends(krri):
    """본문을 다 읽고 나서 나누지 않는다. 첫 조각을 내보낸 뒤에야 KRRI 대역이 나머지를 보낸다."""
    handed_first = asyncio.Event()

    class Gated(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield sse({"type": "execution", **{k: v for k, v in KRRI_RESPONSE.items() if k != "answer"}},
                      {"type": "answer_delta", "text": "첫 조각"}).encode()
            await asyncio.wait_for(handed_first.wait(), timeout=2)
            yield sse({"type": "answer_delta", "text": " 둘째"}, {"type": "result", **KRRI_RESPONSE}, "[DONE]").encode()

    krri["handler"] = lambda request: httpx.Response(200, stream=Gated(), headers={"content-type": "text/event-stream"})

    async def pump():
        out = []
        async for event in krri_executor_client.stream_workflow(
            WORKFLOW, user_text="", context={}, headers=krri_executor_client.identity_headers(USER_CONTEXT),
        ):
            out.append(event)
            if event.get("text") == "첫 조각":
                handed_first.set()
        return out

    events = asyncio.run(pump())
    assert [event.get("text") for event in events if event["type"] == "answer_delta"] == ["첫 조각", " 둘째"]


def test_a_stream_that_ends_without_a_result_is_raised(krri):
    """result 가 없으면 KRRI 가 끝까지 간 것을 모른다. 실행 결과로 치지 않는다."""
    krri["handler"] = lambda request: stream_response(
        sse({"type": "execution", **{k: v for k, v in KRRI_RESPONSE.items() if k != "answer"}}, "[DONE]"))

    with pytest.raises(krri_executor_client.KrriExecutorError):
        call()


def test_an_http_error_is_raised_without_the_body(krri):
    """HTTP 오류는 KrriExecutorError. 응답 본문 원문은 예외 문장에 싣지 않는다."""
    krri["handler"] = lambda request: httpx.Response(500, text="Traceback ... /app/secret.py")

    with pytest.raises(krri_executor_client.KrriExecutorError) as raised:
        call()
    assert "500" in str(raised.value)
    assert "secret" not in str(raised.value)


def test_a_rejected_workflow_is_an_error(krri):
    """KRRI 가 action 을 거절하면 422. 실행 결과가 아니다."""
    krri["handler"] = lambda request: httpx.Response(422, json={"detail": []})

    with pytest.raises(krri_executor_client.KrriExecutorError):
        call()


def test_a_connection_failure_is_raised(krri):
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    krri["handler"] = refuse

    with pytest.raises(krri_executor_client.KrriExecutorError) as raised:
        call()
    assert ORCHESTRATOR not in str(raised.value)


def test_a_timeout_is_raised(krri):
    def slow(request):
        raise httpx.ReadTimeout("timed out", request=request)

    krri["handler"] = slow

    with pytest.raises(krri_executor_client.KrriExecutorError) as raised:
        call()
    assert "시간" in str(raised.value)


@pytest.mark.parametrize("body", [
    "data: not json\r\n\r\n",
    sse(["not", "an", "object"]),
    sse({"type": "result", **{k: v for k, v in KRRI_RESPONSE.items() if k != "answer"}}),
    sse({"type": "result", **KRRI_RESPONSE, "trace": None}),
    sse({"type": "result", **KRRI_RESPONSE, "commands": "map.draw"}),
    sse({"type": "execution", "status": "success", "commands": [], "trace": {}, "errors": []}),
    sse({"type": "answer_delta", "text": None}),
])
def test_a_malformed_event_is_raised(krri, body):
    """모양이 다른 이벤트는 받은 것으로 치지 않는다."""
    krri["handler"] = lambda request: stream_response(body)

    with pytest.raises(krri_executor_client.KrriExecutorError):
        call()


def test_a_missing_address_is_raised_before_calling(krri, monkeypatch):
    """주소가 없으면 부르지 않는다. localhost 로 돌아가지 않는다."""
    monkeypatch.delenv("ASAP_ORCHESTRATOR_URL")

    with pytest.raises(krri_executor_client.KrriExecutorError) as raised:
        call()
    assert "ASAP_ORCHESTRATOR_URL" in str(raised.value)
    assert krri["requests"] == []
