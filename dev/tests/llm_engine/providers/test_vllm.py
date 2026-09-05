"""대상 : llm_engine/providers/vllm.py — Solar 가 가는 길

**요청 모양을 지어내지 않았다.** 2026-09-05 에 36발화 35/36 을 낸 그 요청을
옮긴 것이고, 이 시험이 그 계약을 붙든다. 여기 숫자가 흔들리면 그때 잰 성적을
더는 못 견준다.

Ollama 와 다른 것은 셋뿐이고 셋 다 이 파일 안에만 있다 — think 를 끄는 법,
schema 를 강제하는 법, 컨텍스트를 정하는 자리.

vLLM 서버 없이 검증한다. urlopen 을 가로채 요청 인자를 그대로 본다.
"""

import inspect
import json
import urllib.request

import pytest

from conftest import StubLLMClient
from llm_engine.providers.vllm import (
    MAX_TOKENS,
    VLLM_HOST,
    VllmConfig,
    VllmProvider,
    call_vllm,
    config_for,
)

# 저장소가 실제로 넘기는 것과 같은 모양 — union 타입과 enum 이 섞여 있다.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string", "maxLength": 200},
        "recipe_id": {"type": ["string", "null"]},
        "status": {"type": "string", "enum": ["SELECT", "CLARIFY", "NO_MATCH"]},
    },
    "required": ["reason", "recipe_id", "status"],
}
ANSWER = '{"reason": "까닭", "recipe_id": "recipe_052", "status": "SELECT"}'


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
    """call_vllm() 이 보낸 urllib Request 를 가로챔."""
    captured = {}

    def fake_urlopen(request, *args, **kwargs):
        captured["request"] = request
        captured["kwargs"] = kwargs
        return FakeHTTPResponse(
            {"choices": [{"message": {"content": ANSWER, "reasoning_content": None}}]}
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return captured


def test_the_request_is_the_one_that_measured_35_of_36(sent_request):
    """성적을 낸 요청과 같은 요청이어야 함.

    CHAT       측정이 /v1/chat/completions 로 났음
    user 한 통  프롬프트를 통째로 실었음. system 으로 가르지 않았음
    t0 · seed0  같은 발화가 같은 답으로 가야 함
    none       reasoning_effort 가 Ollama 의 think=False 자리임.
               켜지면 사고 과정이 섞여 JSON 이 아니게 됨
    strict     schema 봉투가 이 모양일 때 45발화 x 3 이 한 번도 안 깨졌음
    """
    call_vllm("발화", RESPONSE_SCHEMA)

    request = sent_request["request"]
    body = json.loads(request.data.decode("utf-8"))
    headers = {key.lower(): value for key, value in request.headers.items()}

    assert request.full_url == f"{VLLM_HOST}/v1/chat/completions"
    assert headers["content-type"] == "application/json"

    assert body["model"] == config_for().model
    assert body["messages"] == [{"role": "user", "content": "발화"}]
    assert body["temperature"] == 0
    assert body["seed"] == 0
    assert body["reasoning_effort"] == "none"
    assert body["max_tokens"] == MAX_TOKENS

    assert body["response_format"]["type"] == "json_schema"
    envelope = body["response_format"]["json_schema"]
    assert envelope["strict"] is True
    assert envelope["schema"] == RESPONSE_SCHEMA, "받은 스키마를 고치면 안 된다"

    # 시연 중 LLM 이 멎어도 화면이 영영 기다리면 안 된다.
    assert sent_request["kwargs"].get("timeout"), "타임아웃이 없다"


def test_what_ollama_sends_and_vllm_must_not(sent_request):
    """Ollama 것을 그대로 옮기면 안 되는 칸들.

    num_ctx     컨텍스트는 서버가 --max-model-len 으로 정함. 요청이 못 바꿈
    keep_alive  vLLM 은 모델을 이미 올려 둔 서버라 요청 단위 개념이 없음
    think       provider 마다 표현이 다름. 여기서는 reasoning_effort 임
    format      schema 를 맨몸으로 보내지 않음. response_format 봉투에 담음
    """
    call_vllm("발화", RESPONSE_SCHEMA)
    body = json.loads(sent_request["request"].data.decode("utf-8"))

    for absent in ("num_ctx", "keep_alive", "think", "format", "options", "stream"):
        assert absent not in body, f"{absent} 은 vLLM 요청에 없어야 한다"


def test_the_raw_answer_comes_back_untouched(sent_request):
    """봉투에서 content 원문만 꺼냄. 파싱은 route_resolver 가 함.

    Stub 이 실물에서 흘러가면 orchestrator 테스트가 실제와 다른 것을 검증하면서
    통과함. 그래서 실물을 기준으로 Stub 을 맞춰 봄. 두 provider 가 같은
    signature 라야 orchestrator 가 어느 쪽인지 몰라도 됨.
    """
    assert call_vllm("발화", RESPONSE_SCHEMA) == ANSWER
    assert VllmProvider().generate("발화", RESPONSE_SCHEMA) == ANSWER

    def parameters(instance):
        generate = getattr(instance, "generate", None)
        assert callable(generate), type(instance).__name__
        signature = inspect.signature(generate)
        return [
            (p.name, p.annotation) for p in signature.parameters.values()
        ], signature.return_annotation

    assert parameters(StubLLMClient(ANSWER)) == parameters(VllmProvider()), \
        "StubLLMClient.generate() 가 실물과 다르다"


def test_the_model_and_timeout_can_be_swapped_without_restarting(sent_request):
    """모델과 함께 움직이는 값을 호출마다 갈아끼울 수 있어야 함.

    측정은 같은 발화를 모델만 바꿔 돌리는 일이라, 모델이 다른 객체가 한
    프로세스에 동시에 살아 있어야 함.
    """
    call_vllm(
        "발화",
        RESPONSE_SCHEMA,
        config=VllmConfig(model="다른모델", timeout=1, host="http://저쪽:9"),
    )

    body = json.loads(sent_request["request"].data.decode("utf-8"))
    assert body["model"] == "다른모델"
    assert sent_request["request"].full_url == "http://저쪽:9/v1/chat/completions"
    assert sent_request["kwargs"]["timeout"] == 1
