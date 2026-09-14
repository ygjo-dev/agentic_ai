"""대상 : llm_engine/providers/ollama.py — qwen 이 가는 길

해석 엔진(orchestrator)은 어떤 LLM 을 쓰는지 모른다. `generate(prompt, schema)`
하나만 아는 객체로 이야기하고, 그 구현이 여기 있다. 모델을 바꾸려면
이 폴더만 갈아끼운다.

**응답을 파싱하지 않는다.** Ollama response JSON 에서 원문만 꺼내 그대로 넘긴다 —
파싱과 계약 검증은 부르는 쪽(orchestrator · registration)의 몫이라 두 곳에
흩어지면 안 된다.

닿는지 확인하는 것도 여기 있다. 라우팅 계층이 HTTP 를 직접 던지면
"LLM 호출을 한 곳에 가둔다" 는 약속이 깨진다.

Ollama 데몬 없이 검증한다. urlopen 을 가로채 요청 인자를 그대로 본다.
"""

import inspect
import json
import urllib.request

import pytest

from conftest import TEST_ENDPOINTS, StubLLMClient, fake_role
from llm_engine.llm_selector import get_llm_for
from llm_engine.providers.ollama import (
    OllamaConfig,
    OllamaProvider,
    call_ollama,
    config_for,
    ping,
)

# Ollama 로 가는 역할 한 벌. 실물 역할의 이름을 안 적는다 — 역할이 provider 를
# 옮기면 여기가 상관없이 빨개진다.
ROLE = fake_role(provider="ollama", model="시험모델", inference={"num_ctx": 32768, "timeout": 900})

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
    call_ollama("발화", RESPONSE_SCHEMA, config=config_for(ROLE))

    request = sent_request["request"]
    body = json.loads(request.data.decode("utf-8"))
    headers = {key.lower(): value for key, value in request.headers.items()}

    assert request.full_url == f"{TEST_ENDPOINTS['OLLAMA_URL']}/api/generate"
    assert headers["content-type"] == "application/json"

    assert body["model"] == ROLE.model
    assert body["prompt"] == "발화"
    assert body["stream"] is False
    assert body["format"] == RESPONSE_SCHEMA
    assert body["think"] is False
    assert body["options"]["temperature"] == 0
    assert body["options"]["seed"] == 0
    assert body["options"]["num_ctx"] == ROLE.inference["num_ctx"]

    # 시연 중 LLM 이 멎어도 화면이 영영 기다리면 안 된다.
    assert sent_request["kwargs"]["timeout"] == ROLE.inference["timeout"], "역할의 타임아웃이 안 갔다"


def test_the_raw_answer_comes_back_untouched(sent_request):
    """response JSON 의 ["response"] 원문만 꺼냄. 파싱은 부르는 쪽이 함.

    Stub 이 실물에서 흘러가면 registry · orchestrator 테스트가 실제와 다른
    것을 검증하면서 통과함. 그래서 기준을 실물로 두고 Stub 을 맞춰 봄.
    """
    설정 = config_for(ROLE)
    assert call_ollama("발화", RESPONSE_SCHEMA, config=설정) == ANSWER
    assert OllamaProvider(설정).generate("발화", RESPONSE_SCHEMA) == ANSWER
    assert json.loads(sent_request["request"].data.decode("utf-8"))["prompt"] == "발화"

    def parameters(instance):
        generate = getattr(instance, "generate", None)
        assert callable(generate), type(instance).__name__
        signature = inspect.signature(generate)
        return [
            (p.name, p.annotation) for p in signature.parameters.values()
        ], signature.return_annotation

    assert parameters(StubLLMClient(ANSWER)) == parameters(OllamaProvider(설정)), \
        "StubLLMClient.generate() 가 실물과 다르다"


def test_clients_of_different_roles_live_side_by_side(sent_request):
    """역할마다 모델과 값이 다른 클라이언트가 한 프로세스에 함께 삶.

    resolve 와 node_registration 이 한 서버에서 서로 다른 모델 · num_ctx ·
    timeout 으로 돔. 전역 상수를 읽으면 나중에 만든 쪽 값이 앞의 것을 덮음.
    """
    def sent_body():
        return json.loads(sent_request["request"].data.decode("utf-8"))

    작은_쪽 = get_llm_for(
        fake_role(provider="ollama", model="작은모델", inference={"num_ctx": 512, "timeout": 1})
    )
    큰_쪽 = get_llm_for(ROLE)

    작은_쪽.generate("발화", RESPONSE_SCHEMA)
    assert sent_body()["model"] == "작은모델"
    assert sent_body()["options"]["num_ctx"] == 512
    assert sent_request["kwargs"]["timeout"] == 1

    큰_쪽.generate("발화", RESPONSE_SCHEMA)
    assert sent_body()["model"] == ROLE.model
    assert sent_body()["options"]["num_ctx"] == ROLE.inference["num_ctx"]
    assert sent_request["kwargs"]["timeout"] == ROLE.inference["timeout"]

    # 호출 설정은 역할을 안 거치고도 만들 수 있다. provider 는 역할 파일을 모른다.
    call_ollama(
        "발화",
        RESPONSE_SCHEMA,
        config=OllamaConfig(
            model="아무거나",
            timeout=2,
            num_ctx=256,
            host=TEST_ENDPOINTS["OLLAMA_URL"],
        ),
    )
    assert sent_request["kwargs"]["timeout"] == 2
    assert sent_body()["options"]["num_ctx"] == 256


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
    assert calls["url"].startswith(TEST_ENDPOINTS["OLLAMA_URL"])
    assert 0 < calls["timeout"] <= 5, "점검이 오래 걸리면 점검이 아니다"

    for boom in (ConnectionError("연결 거부"), TimeoutError("시간 초과")):
        def exploding(*args, _boom=boom, **kwargs):
            raise _boom

        monkeypatch.setattr(urllib.request, "urlopen", exploding)
        assert ping(timeout=0.1) is False
