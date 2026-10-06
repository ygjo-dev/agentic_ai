"""`POST /chat/stream` 이 누구의 MCP 범위로 KRRI 를 부르는가.

두 갈래이고 섞지 않는다.
  KRRI_ASAP 채팅   Gateway 가 X-User-* 여섯 값을 넣는다. 그 사용자가 적용한 범위 밖 도구면
                   KRRI 를 안 부르고, 안이면 여섯 값을 그대로 KRRI /workflow/execute/stream 에 싣는다
  직접 호출        X-User-* 가 없다(KRRI EASY MCPs 「AI로 사용해보기」). 내 MCP과 무관하게
                   standalone 신원으로 부른다
body 의 context 는 어느 갈래에서도 범위가 아니다.

창구 · 진입점 · workflow_materializer · workflow_execution · krri_executor_client 가 진짜로 돈다.
LLM 해석과 KRRI HTTP 만 대역이다 — KRRI 는 httpx MockTransport 가 받고, 받은 요청을 남긴다.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import main
from app.api.services.bridge import recent_service
from execution import krri_executor_client, local_presentation, workflow_execution

ORCHESTRATOR = "http://krri-orchestrator.test:18100"

# 고른 recipe 는 asap-mcp-core/geo.geocode 하나를 부른다.
RESOLVED = {
    "status": "SELECT",
    "recipe_id": "recipe_001",
    "candidate_recipe_ids": ["recipe_001"],
    "reason": "장소 위치",
    "argument": "익산역",
    "paths": {},
}

KRRI_ANSWER = "익산역 위치를 표시했습니다. (KRRI)"


def gateway(tools: str) -> dict:
    """Gateway proxy 가 넣는 여섯 값. 도구 범위만 바꿔 씀."""
    return {
        "X-User-ID": "guest:6f1c2d3e-4a5b-4c6d-8e7f-0a1b2c3d4e5f",
        "X-User-Name": "guest",
        "X-User-Role": "",
        "X-User-MCP-Servers": "asap-mcp-core",
        "X-User-MCP-Tools": tools,
        "X-User-MCP-Groups": "krri-map-location",
    }


@pytest.fixture
def krri(monkeypatch):
    """해석과 KRRI 만 대역. KRRI 가 받은 요청을 남긴다."""
    monkeypatch.setenv("ASAP_ORCHESTRATOR_URL", ORCHESTRATOR)
    monkeypatch.setattr(main, "get_role_config", lambda role: object())
    monkeypatch.setattr(main, "get_llm_for", lambda role: object())
    monkeypatch.setattr(main.resolve_service, "resolve", lambda text, llm_client, role: dict(RESOLVED))
    requests = []

    def handle(request):
        requests.append(request)
        steps = json.loads(request.content)["workflow"]["steps"]
        trace = [{"id": s["id"], "server_id": s["server_id"], "tool": s["tool"], "input": {}, "result": {}} for s in steps]
        result = {"type": "result", "status": "success", "answer": KRRI_ANSWER, "commands": [],
                  "trace": trace, "errors": []}
        return httpx.Response(200, text=f"data: {json.dumps(result, ensure_ascii=False)}\r\n\r\ndata: [DONE]\r\n\r\n",
                              headers={"content-type": "text/event-stream"})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        krri_executor_client.httpx,
        "AsyncClient",
        lambda **kwargs: real(transport=httpx.MockTransport(handle), **kwargs),
    )
    recent_service.clear()
    yield requests
    recent_service.clear()


def chat(headers=None, context=None) -> dict:
    """창구를 부르고 result 이벤트를 꺼냄."""
    body = {"text": "익산역 위치 보여줘", "context": context or {}}
    raw = TestClient(main.app).post("/chat/stream", json=body, headers=headers or {}).text
    payloads = [json.loads(block[len("data: "):]) for block in raw.split("\n\n")
                if block.startswith("data: ") and block != "data: [DONE]"]
    (result,) = [p for p in payloads if p["type"] == "result"]
    return result


def test_the_selected_tool_runs_and_the_six_gateway_headers_reach_krri_as_they_came(krri):
    """CASE 1 · CASE 7 — 범위 안이면 KRRI 를 한 번 부르고, 여섯 값이 그대로 간다."""
    headers = gateway("asap-mcp-core/geo.geocode,asap-mcp-core/adminboundary.searchboundaries")

    result = chat(headers)

    (request,) = krri
    assert {name: request.headers[name] for name in headers} == headers
    assert result["answer"] == KRRI_ANSWER
    assert result["status"] == "success"


def test_a_tool_the_user_did_not_select_is_not_sent_to_krri(krri):
    """CASE 2 — 고른 범위에 부를 도구가 없으면 KRRI /workflow/execute/stream 을 안 부른다."""
    result = chat(gateway("asap-mcp-core/adminboundary.searchboundaries"))

    assert krri == []
    assert result == {"type": "result", "answer": local_presentation.TOOL_NOT_SELECTED, "commands": []}


def test_a_server_wildcard_from_the_gateway_lets_the_tool_run(krri):
    """CASE 3 — "<server>/*" 는 그 서버의 exact 도구를 허용한다."""
    chat(gateway("asap-mcp-core/*"))

    assert len(krri) == 1


def test_selected_refs_in_the_body_context_do_not_widen_the_gateway_scope(krri):
    """CASE 5 — body context 에 refs 를 넣어도 Gateway 범위는 그대로다."""
    fake = {
        "selected_mcp_tool_refs": ["asap-mcp-core/*"],
        "user_context": {"selected_mcp_tool_refs": ["asap-mcp-core/*"]},
        "X-User-MCP-Tools": "asap-mcp-core/*",
    }

    result = chat(gateway("asap-mcp-core/adminboundary.searchboundaries"), context=fake)

    assert krri == []
    assert result["answer"] == local_presentation.TOOL_NOT_SELECTED


def test_a_direct_call_without_gateway_headers_runs_with_the_standalone_identity(krri):
    """CASE 6 — X-User-* 가 없으면 범위로 막지 않고 standalone 신원으로 부른다.

    KRRI EASY MCPs 「AI로 사용해보기」가 이 길이다. body context 의 refs 는 여기서도 안 쓴다.
    """
    result = chat(context={"selected_mcp_tool_refs": ["nothing/at-all"]})

    (request,) = krri
    standalone = krri_executor_client.identity_headers(workflow_execution.STANDALONE_USER_CONTEXT)
    sent = {name: request.headers[name] for name in workflow_execution.GATEWAY_SCOPE_HEADERS if name in request.headers}
    assert sent == standalone
    assert result["answer"] == KRRI_ANSWER
