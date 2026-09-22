"""대상 : execution/krri_executor_client.py — 완성된 workflow 를 KRRI 실행 창구로 나르는 HTTP 손

나르기만 한다. 본문 · 헤더 모양과, 못 불렀을 때 KrriExecutorError 하나로 올리는지를 본다.
주고받는 JSON 모양은 KRRI_ASAP ASAP-orchestrator/tests/test_workflow_execute.py 와 같다.

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

# KRRI WorkflowExecuteResponse 한 벌.
KRRI_RESPONSE = {
    "status": "success",
    "answer": "오송역 주변 CCTV 3대를 찾았습니다.",
    "commands": [{"op": "map.draw", "args": {"layerId": "mcp-place"}}],
    "trace": [{"id": "s1", "server_id": "asap-mcp-core", "tool": "geo.geocode", "input": {}, "result": {}}],
    "errors": [],
}


def call(workflow=WORKFLOW, context=None):
    return asyncio.run(krri_executor_client.execute_workflow(
        workflow,
        user_text="오송역 CCTV 보여줘",
        context=context if context is not None else {"view": {"zoom": 12}},
        user_context=USER_CONTEXT,
    ))


@pytest.fixture
def krri(monkeypatch):
    """KRRI 창구 대역. handler 를 갈아 끼우고, 받은 요청을 남긴다."""
    monkeypatch.setenv("ASAP_ORCHESTRATOR_URL", ORCHESTRATOR)
    state = {"requests": [], "handler": lambda request: httpx.Response(200, json=KRRI_RESPONSE)}

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
    assert str(request.url) == ORCHESTRATOR + "/workflow/execute"
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


def test_the_krri_response_comes_back_as_it_is(krri):
    """answer · commands · trace · errors 를 고치지 않고 돌려준다."""
    assert call() == KRRI_RESPONSE


def test_a_krri_failure_is_a_result_not_an_error(krri):
    """KRRI 가 실행하다 실패한 것은 200 + status=failed 다. 실행 결과로 돌려준다."""
    failed = {**KRRI_RESPONSE, "status": "failed", "answer": "s1 단계 실패", "commands": [], "errors": ["s1 단계 실패"]}
    krri["handler"] = lambda request: httpx.Response(200, json=failed)

    assert call() == failed


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


@pytest.mark.parametrize("response", [
    httpx.Response(200, text="not json"),
    httpx.Response(200, json=["not", "an", "object"]),
    httpx.Response(200, json={k: v for k, v in KRRI_RESPONSE.items() if k != "answer"}),
    httpx.Response(200, json={**KRRI_RESPONSE, "trace": None}),
    httpx.Response(200, json={**KRRI_RESPONSE, "commands": "map.draw"}),
])
def test_a_malformed_response_is_raised(krri, response):
    """모양이 다른 응답은 받은 것으로 치지 않는다."""
    krri["handler"] = lambda request: response

    with pytest.raises(krri_executor_client.KrriExecutorError):
        call()


def test_a_missing_address_is_raised_before_calling(krri, monkeypatch):
    """주소가 없으면 부르지 않는다. localhost 로 돌아가지 않는다."""
    monkeypatch.delenv("ASAP_ORCHESTRATOR_URL")

    with pytest.raises(krri_executor_client.KrriExecutorError) as raised:
        call()
    assert "ASAP_ORCHESTRATOR_URL" in str(raised.value)
    assert krri["requests"] == []
