"""대상 : demo/api/main.py — GET /health

demo/api/main.py 의 /health 엔드포인트 검증.

시연 직전 점검용이다. LLM 에 닿지 못하는 것은 점검 결과이지 서버 고장이
아니므로, 그때도 200 이어야 한다.
"""

import urllib.request

import pytest
from fastapi.testclient import TestClient

import demo.api.main as backend_main
from llm_engine import ollama


@pytest.fixture
def client():
    return TestClient(backend_main.app)


@pytest.fixture
def unreachable_llm(monkeypatch):
    """Ollama 에 닿지 못하는 상황."""

    def explode(*args, **kwargs):
        raise ConnectionError("Ollama 에 연결할 수 없다")

    monkeypatch.setattr(urllib.request, "urlopen", explode)


# ------------------------------------------------------------ 형태
def test_health_has_contract_keys(client):
    body = client.get("/health").json()

    assert set(body) == {"ok", "ontology_version", "llm"}
    assert set(body["llm"]) == {"reachable", "model"}


def test_health_reports_the_ontology_version(client):
    body = client.get("/health").json()

    assert body["ontology_version"] == client.get("/graph").json()["version"]


def test_health_reports_the_model_name(client):
    assert client.get("/health").json()["llm"]["model"] == ollama.OLLAMA_MODEL


# ------------------------------------------------------------ LLM 도달 실패
def test_unreachable_llm_is_still_200(client, unreachable_llm):
    """못 닿는다는 사실 자체가 응답이다. 500 을 내면 점검이 되지 않는다."""
    assert client.get("/health").status_code == 200


def test_unreachable_llm_is_reported_as_false(client, unreachable_llm):
    body = client.get("/health").json()

    assert body["ok"] is True
    assert body["llm"]["reachable"] is False
