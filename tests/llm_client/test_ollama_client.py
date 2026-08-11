"""llm_engine 검증.

call_ollama() 는 urllib.request.urlopen 을 monkeypatch 해서 검증한다.
Ollama 데몬 없이 요청 인자와 응답 처리를 그대로 볼 수 있다.
"""

import inspect
import json
import urllib.request

import pytest

from conftest import StubLLMClient
from llm_engine.client import LLMClient
from llm_engine.ollama import OLLAMA_HOST, OLLAMA_MODEL, OllamaClient, call_ollama

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"status": {"type": "string"}},
    "required": ["status"],
}


class FakeHTTPResponse:
    """urlopen() 이 돌려주는 객체 흉내. context manager + read()."""

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


@pytest.fixture
def sent_request(monkeypatch):
    """call_ollama() 가 보낸 urllib Request 를 가로챈다."""
    captured = {}

    def fake_urlopen(request, *args, **kwargs):
        captured["request"] = request
        captured["kwargs"] = kwargs
        return FakeHTTPResponse({"response": '{"status": "SELECT"}'})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return captured


def sent_body(captured):
    return json.loads(captured["request"].data.decode("utf-8"))


# ------------------------------------------------------------ 요청 구성
def test_call_ollama_posts_to_generate_endpoint(sent_request):
    call_ollama("발화", RESPONSE_SCHEMA)

    assert sent_request["request"].full_url == f"{OLLAMA_HOST}/api/generate"


def test_call_ollama_body_carries_model_prompt_and_no_stream(sent_request):
    call_ollama("승강장 CCTV 동영상으로 혼잡도를 분석해줘", RESPONSE_SCHEMA)

    body = sent_body(sent_request)

    assert body["model"] == OLLAMA_MODEL
    assert body["prompt"] == "승강장 CCTV 동영상으로 혼잡도를 분석해줘"
    assert body["stream"] is False


def test_call_ollama_passes_response_schema_as_format(sent_request):
    """구조화 출력의 핵심. schema 가 그대로 실리지 않으면 응답 형식을 강제할 수 없다."""
    call_ollama("발화", RESPONSE_SCHEMA)

    assert sent_body(sent_request)["format"] == RESPONSE_SCHEMA


def test_call_ollama_requests_deterministic_options(sent_request):
    """temperature / seed 가 고정되지 않으면 같은 발화가 다른 Recipe 로 간다."""
    call_ollama("발화", RESPONSE_SCHEMA)

    options = sent_body(sent_request)["options"]

    assert options["temperature"] == 0
    assert options["seed"] == 0
    assert options["num_ctx"] == 8192


def test_call_ollama_disables_thinking(sent_request):
    """think 가 켜지면 응답에 사고 과정이 섞여 JSON 파싱이 깨진다."""
    call_ollama("발화", RESPONSE_SCHEMA)

    assert sent_body(sent_request)["think"] is False


def test_call_ollama_sends_json_content_type(sent_request):
    call_ollama("발화", RESPONSE_SCHEMA)

    headers = {key.lower(): value for key, value in sent_request["request"].headers.items()}

    assert headers["content-type"] == "application/json"


# ------------------------------------------------------------ 응답 처리
def test_call_ollama_returns_response_field(sent_request):
    """Ollama 응답 봉투에서 ["response"] 원문만 꺼내 돌려줘야 한다."""
    result = call_ollama("발화", RESPONSE_SCHEMA)

    assert result == '{"status": "SELECT"}'


def test_ollama_client_delegates_to_call_ollama(sent_request):
    result = OllamaClient().generate("발화", RESPONSE_SCHEMA)

    assert result == '{"status": "SELECT"}'
    assert sent_body(sent_request)["prompt"] == "발화"


# ------------------------------------------------------------ LLMClient Protocol
def assert_satisfies_llm_client(instance):
    """LLMClient Protocol 이 요구하는 generate() 를 그대로 갖추었는지 본다.

    LLMClient 는 @runtime_checkable 이 아니라 isinstance 로 볼 수 없다.
    Protocol 선언부의 signature 와 직접 비교한다.
    """
    generate = getattr(instance, "generate", None)
    assert callable(generate), f"{type(instance).__name__} 에 generate() 가 없다."

    expected = list(inspect.signature(LLMClient.generate).parameters.values())[1:]  # self 제외
    actual = list(inspect.signature(generate).parameters.values())

    assert [(p.name, p.annotation) for p in actual] == [
        (p.name, p.annotation) for p in expected
    ], f"{type(instance).__name__}.generate() signature 가 Protocol 과 다르다."


def test_ollama_client_satisfies_llm_client_protocol():
    assert_satisfies_llm_client(OllamaClient())


def test_stub_llm_client_satisfies_llm_client_protocol():
    """Stub 이 Protocol 을 벗어나면 테스트가 실제와 다른 것을 검증하게 된다."""
    assert_satisfies_llm_client(StubLLMClient("{}"))
