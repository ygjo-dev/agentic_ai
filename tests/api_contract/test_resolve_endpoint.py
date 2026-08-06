"""backend/main.py 의 /resolve 엔드포인트 계약 검증.

OllamaClient 를 Stub 으로 갈아끼워 LLM 없이 검증한다.
"""

import json

import pytest
from fastapi.testclient import TestClient

import backend.main as backend_main
from conftest import SELECT, StubLLMClient
from orchestrator.route_resolver import RouteResolutionError

VALID_LLM_RESPONSE = {
    "reason": "CCTV 군중 분석과 하는 일이 같다.",
    "candidate_recipe_ids": ["recipe_002"],
    "status": SELECT,
    "recipe_id": "recipe_002",
}


class ExplodingLLMClient:
    """LLM 호출 자체가 실패하는 상황. RouteResolutionError 가 아니다."""

    def __init__(self, exc):
        self.exc = exc

    def generate(self, prompt: str, response_schema: dict) -> str:
        raise self.exc


@pytest.fixture
def client():
    return TestClient(backend_main.app)


@pytest.fixture
def use_llm_client(monkeypatch):
    """backend.main 이 쓰는 OllamaClient 를 주어진 Stub 으로 교체한다."""

    def _use(llm_client):
        monkeypatch.setattr(backend_main, "OllamaClient", lambda: llm_client)
        return llm_client

    return _use


# ------------------------------------------------------------ 정상 응답
def test_resolve_returns_200(client, use_llm_client):
    use_llm_client(StubLLMClient(json.dumps(VALID_LLM_RESPONSE)))

    response = client.post("/resolve", params={"utterance": "CCTV로 군중을 분석해줘"})

    assert response.status_code == 200


def test_resolve_body_has_contract_keys(client, use_llm_client):
    """Frontend 가 의존하는 4개 key 가 그대로 나와야 한다."""
    use_llm_client(StubLLMClient(json.dumps(VALID_LLM_RESPONSE)))

    response = client.post("/resolve", params={"utterance": "CCTV로 군중을 분석해줘"})

    assert set(response.json()) == {
        "reason",
        "candidate_recipe_ids",
        "status",
        "recipe_id",
    }


def test_resolve_passes_utterance_to_llm(client, use_llm_client):
    llm_client = use_llm_client(StubLLMClient(json.dumps(VALID_LLM_RESPONSE)))

    client.post("/resolve", params={"utterance": "CCTV로 군중을 분석해줘"})

    assert "CCTV로 군중을 분석해줘" in llm_client.prompts[0]


# ------------------------------------------------------------ 실패 응답
def test_broken_llm_response_becomes_422(client, use_llm_client):
    """RouteResolutionError 는 LLM 응답이 계약을 어긴 것이므로 422."""
    use_llm_client(StubLLMClient("이건 JSON 이 아니다"))

    response = client.post("/resolve", params={"utterance": "CCTV로 군중을 분석해줘"})

    assert response.status_code == 422


def test_unexpected_error_becomes_500(client, use_llm_client):
    """RouteResolutionError 가 아닌 예외는 서버 문제이므로 500."""
    use_llm_client(ExplodingLLMClient(ConnectionError("Ollama 에 연결할 수 없다")))

    response = client.post("/resolve", params={"utterance": "CCTV로 군중을 분석해줘"})

    assert response.status_code == 500
    assert "Internal error" in response.json()["detail"]


def test_missing_utterance_is_422(client, use_llm_client):
    """utterance 는 필수 query parameter (FastAPI 기본 동작)."""
    use_llm_client(StubLLMClient(json.dumps(VALID_LLM_RESPONSE)))

    response = client.post("/resolve")

    assert response.status_code == 422


def test_route_resolution_error_is_not_swallowed_as_500(client, use_llm_client):
    """422 와 500 이 뒤바뀌면 호출자가 재시도 여부를 판단할 수 없다."""
    use_llm_client(ExplodingLLMClient(RouteResolutionError("계약 위반")))

    response = client.post("/resolve", params={"utterance": "CCTV로 군중을 분석해줘"})

    assert response.status_code == 422
