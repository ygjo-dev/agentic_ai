"""대상 : llm_engine/ — LLM 호출을 한 곳에 가둔다

해석 엔진(orchestrator)은 어떤 LLM 을 쓰는지 모른다. `generate(prompt, schema)`
하나만 아는 Protocol 로 이야기하고, 그 구현이 여기 있다. 모델을 바꾸려면
이 폴더만 갈아끼운다.

**응답을 파싱하지 않는다.** Ollama 응답 봉투에서 원문만 꺼내 그대로 넘긴다 —
파싱과 계약 검증은 route_resolver 의 몫이라 두 곳에 흩어지면 안 된다.

Ollama 데몬 없이 검증한다. urlopen 을 가로채 요청 인자를 그대로 본다.
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
ANSWER = '{"status": "SELECT"}'


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
        return FakeHTTPResponse({"response": ANSWER})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return captured


def test_the_request_forces_a_structured_deterministic_answer(sent_request):
    """세 가지가 없으면 시연이 무너진다.

    format(schema) — 없으면 LLM 이 자유 문장을 돌려주고 파싱이 깨진다.
    temperature/seed 0 — 없으면 같은 발화가 실행할 때마다 다른 Recipe 로 간다.
    think=False — 켜지면 응답에 사고 과정이 섞여 JSON 이 아니게 된다.

    num_ctx 는 menu 전체가 들어갈 만큼이어야 한다. 넘치면 응답이 잘려
    타임아웃처럼 보인다.
    """
    call_ollama("발화", RESPONSE_SCHEMA)

    request = sent_request["request"]
    body = json.loads(request.data.decode("utf-8"))
    headers = {key.lower(): value for key, value in request.headers.items()}

    assert request.full_url == f"{OLLAMA_HOST}/api/generate"
    assert headers["content-type"] == "application/json"

    assert body["model"] == OLLAMA_MODEL
    assert body["prompt"] == "발화"
    assert body["stream"] is False
    assert body["format"] == RESPONSE_SCHEMA
    assert body["think"] is False
    assert body["options"]["temperature"] == 0
    assert body["options"]["seed"] == 0
    assert body["options"]["num_ctx"] == 8192

    # 시연 중 LLM 이 멎어도 화면이 영영 기다리면 안 된다.
    assert sent_request["kwargs"].get("timeout"), "타임아웃이 없다"


def test_the_raw_answer_comes_back_untouched(sent_request):
    """봉투에서 ["response"] 원문만 꺼낸다. 파싱은 route_resolver 가 한다.

    Protocol 을 벗어나면 orchestrator 가 구현을 갈아끼울 수 없고, 테스트의
    Stub 도 실제와 다른 것을 검증하게 된다. 그래서 실물과 Stub 둘 다 본다.
    """
    assert call_ollama("발화", RESPONSE_SCHEMA) == ANSWER
    assert OllamaClient().generate("발화", RESPONSE_SCHEMA) == ANSWER
    assert json.loads(sent_request["request"].data.decode("utf-8"))["prompt"] == "발화"

    expected = list(inspect.signature(LLMClient.generate).parameters.values())[1:]
    for instance in (OllamaClient(), StubLLMClient(ANSWER)):
        generate = getattr(instance, "generate", None)
        assert callable(generate), type(instance).__name__

        actual = list(inspect.signature(generate).parameters.values())
        assert [(p.name, p.annotation) for p in actual] == [
            (p.name, p.annotation) for p in expected
        ], f"{type(instance).__name__}.generate() 가 Protocol 과 다르다"
