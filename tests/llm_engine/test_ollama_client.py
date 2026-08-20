"""대상 : llm_engine/ — LLM 호출을 한 곳에 가둔다

해석 엔진(orchestrator)은 어떤 LLM 을 쓰는지 모른다. `generate(prompt, schema)`
하나만 아는 객체로 이야기하고, 그 구현이 여기 있다. 모델을 바꾸려면
이 폴더만 갈아끼운다.

**응답을 파싱하지 않는다.** Ollama 응답 봉투에서 원문만 꺼내 그대로 넘긴다 —
파싱과 계약 검증은 route_resolver 의 몫이라 두 곳에 흩어지면 안 된다.

닿는지 확인하는 것도 여기 있다. 라우팅 계층이 HTTP 를 직접 던지면
"LLM 호출을 한 곳에 가둔다" 는 약속이 깨진다.

Ollama 데몬 없이 검증한다. urlopen 을 가로채 요청 인자를 그대로 본다.
"""

import inspect
import json
import urllib.request

import pytest

from conftest import StubLLMClient
from llm_engine.ollama import (
    OLLAMA_HOST,
    OllamaClient,
    OllamaConfig,
    call_ollama,
    config_for,
    make_client,
    ping,
)

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
    """call_ollama() 가 보낸 urllib Request 를 가로챔."""
    captured = {}

    def fake_urlopen(request, *args, **kwargs):
        captured["request"] = request
        captured["kwargs"] = kwargs
        return FakeHTTPResponse({"response": ANSWER})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return captured


def test_the_request_forces_a_structured_deterministic_answer(sent_request):
    """세 가지가 없으면 시연이 무너짐.

    format(schema)     없으면 LLM 이 자유 문장을 돌려주고 파싱이 깨짐
    temperature/seed 0 없으면 같은 발화가 실행할 때마다 다른 Recipe 로 감
    think=False        켜지면 응답에 사고 과정이 섞여 JSON 이 아니게 됨

    num_ctx 는 menu 전체가 들어갈 만큼이어야 함. 넘치면 응답이 잘려
    타임아웃처럼 보임.
    """
    call_ollama("발화", RESPONSE_SCHEMA)

    request = sent_request["request"]
    body = json.loads(request.data.decode("utf-8"))
    headers = {key.lower(): value for key, value in request.headers.items()}

    assert request.full_url == f"{OLLAMA_HOST}/api/generate"
    assert headers["content-type"] == "application/json"

    assert body["model"] == config_for().model
    assert body["prompt"] == "발화"
    assert body["stream"] is False
    assert body["format"] == RESPONSE_SCHEMA
    assert body["think"] is False
    assert body["options"]["temperature"] == 0
    assert body["options"]["seed"] == 0
    assert body["options"]["num_ctx"] == config_for().num_ctx

    # 시연 중 LLM 이 멎어도 화면이 영영 기다리면 안 된다.
    assert sent_request["kwargs"].get("timeout"), "타임아웃이 없다"


def test_the_raw_answer_comes_back_untouched(sent_request):
    """봉투에서 ["response"] 원문만 꺼냄. 파싱은 route_resolver 가 함.

    Stub 이 실물에서 흘러가면 registry · orchestrator 테스트가 실제와 다른
    것을 검증하면서 통과함. 그래서 실물을 기준으로 Stub 을 맞춰 봄.

    기준이 실물임. 예전에는 별도 Protocol 파일이 기준이었는데, 프로덕션
    어디서도 import 되지 않아 강제되는 것이 없었음. 지우고 실물에 맞춤.
    """
    assert call_ollama("발화", RESPONSE_SCHEMA) == ANSWER
    assert OllamaClient().generate("발화", RESPONSE_SCHEMA) == ANSWER
    assert json.loads(sent_request["request"].data.decode("utf-8"))["prompt"] == "발화"

    def parameters(instance):
        generate = getattr(instance, "generate", None)
        assert callable(generate), type(instance).__name__
        signature = inspect.signature(generate)
        return [
            (p.name, p.annotation) for p in signature.parameters.values()
        ], signature.return_annotation

    assert parameters(StubLLMClient(ANSWER)) == parameters(OllamaClient()), \
        "StubLLMClient.generate() 가 실물과 다르다"


def test_the_model_can_be_swapped_without_restarting(sent_request):
    """모델을 바꾸는 데 프로세스를 다시 띄우지 않음.

    측정은 같은 발화를 모델만 바꿔 돌리는 일이라, 모델이 다른 클라이언트가
    한 프로세스에 동시에 살아 있어야 함. 전역 상수를 읽으면 그게 안 됨.

    인자를 안 주면 기본 모델. 지금 동작이 그대로여야 함.
    """
    def sent_body():
        return json.loads(sent_request["request"].data.decode("utf-8"))

    make_client("qwen2.5:7b").generate("발화", RESPONSE_SCHEMA)
    assert sent_body()["model"] == "qwen2.5:7b"

    make_client().generate("발화", RESPONSE_SCHEMA)
    assert sent_body()["model"] == config_for().model

    # 모델과 함께 움직이는 값도 호출마다 갈아끼울 수 있어야 한다 —
    # 큰 모델은 기본 타임아웃(180초)을 넘긴다.
    call_ollama(
        "발화",
        RESPONSE_SCHEMA,
        config=OllamaConfig(model="아무거나", timeout=1, num_ctx=512),
    )
    assert sent_request["kwargs"]["timeout"] == 1
    assert sent_body()["options"]["num_ctx"] == 512


def test_reachability_is_checked_without_raising(monkeypatch):
    """시연 직전 점검용. 못 닿아도 예외를 올리지 않음.

    LLM 이 꺼져 있다는 것은 화면이 보여줘야 할 정보이지 서버가 죽을 이유가
    아님. 이유도 묻지 않음. 연결 거부든 타임아웃이든 답은 "못 닿는다" 하나.

    타임아웃이 짧음. 오래 걸리는 점검은 점검이 아님.
    """
    calls = {}

    def fake_urlopen(url, *args, **kwargs):
        calls["url"] = url
        calls["timeout"] = kwargs.get("timeout")
        return FakeHTTPResponse({"models": []})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert ping() is True
    assert calls["url"].startswith(OLLAMA_HOST)
    assert 0 < calls["timeout"] <= 5, "점검이 오래 걸리면 점검이 아니다"

    for boom in (ConnectionError("연결 거부"), TimeoutError("시간 초과")):
        def exploding(*args, _boom=boom, **kwargs):
            raise _boom

        monkeypatch.setattr(urllib.request, "urlopen", exploding)
        assert ping(timeout=0.1) is False
