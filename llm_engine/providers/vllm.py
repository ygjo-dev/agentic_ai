"""vLLM (OpenAI 호환) 구현체.

Solar Open2 250B 가 이 길로 간다. **요청 모양을 지어내지 않았다** — benchmark 로
검증된 request contract 그대로다 (근거는 NOTES 「백열한째」).

**Ollama 와 다른 세 가지는 전부 이 파일 안에만 있다.**

    think 끄기   Ollama 는 body 의 think=False, 여기는 reasoning_effort="none"
    schema 강제  Ollama 는 format=schema, 여기는 response_format.json_schema
                 + strict
    컨텍스트     Ollama 는 요청마다 num_ctx, 여기는 서버가 --max-model-len 으로
                 정해 둠. 그래서 body 에 안 실음

keep_alive 도 안 만든다. vLLM 은 모델을 이미 올려 둔 서버라 요청 단위로
붙들 개념이 없다.

★ /v1/completions 는 쓰지 않는다. 맨 prompt 로는 같은 response_format 을 보내도
JSON 이 안 나왔다(실측). CHAT 한 길만 둔다.
"""

import json
import os
import urllib.request
from dataclasses import dataclass

from llm_engine.model_config import get_model_config

VLLM_HOST = os.environ.get("VLLM_HOST", "http://127.0.0.1:18000")

# reason 상한(200자)에 후보 몇 개면 100 토큰 언저리다. 넉넉하되 작은 상한.
MAX_TOKENS = 1024


@dataclass(frozen=True)
class VllmConfig:
    """호출 한 번이 쓰는 설정.

    num_ctx 가 없음. 컨텍스트는 서버가 뜰 때 --max-model-len 으로 정해지고
    요청이 바꿀 수 있는 값이 아님.
    """

    model: str
    timeout: float        # 호출 하나의 상한(초)
    host: str = VLLM_HOST


def config_for(model: str | None = None, *, found=None) -> VllmConfig:
    """모델 설정을 vLLM 호출 설정으로.

    입력  모델 이름(None 이면 기본 모델) · 이미 읽어 둔 ModelConfig
    출력  VllmConfig
    규칙  host 만 환경변수에서 오고 나머지는 models.yaml 에서 옴
    """
    found = found or get_model_config(model)
    return VllmConfig(model=found.model, timeout=found.timeout)


class VllmProvider:
    def __init__(self, config: VllmConfig | None = None):
        self.config = config or config_for()

    def generate(self, prompt: str, response_schema: dict) -> str:
        return call_vllm(prompt, response_schema, config=self.config)


def call_vllm(
    prompt: str,
    response_schema: dict,
    *,
    config: VllmConfig | None = None,
) -> str:
    """CHAT 한 건 처리.

    출력  choices[0].message.content 원문 문자열
    규칙  프롬프트를 user 한 통에 통째로 실음. system 으로 안 가름. benchmark 를
          그 모양으로 쟀고 요청이 달라지면 그 측정과 못 견줌
          받은 스키마를 response_format.json_schema 로 감싸기만 함. 한 글자도
          안 고침
          reasoning_effort="none" 이 Ollama 의 think=False 자리임
    제약  응답을 파싱하지 않는다.
          provider 는 HTTP request · response envelope 까지만 앎. JSON 파싱과
          계약 검증은 부르는 쪽(orchestrator · registration)의 몫임
          /v1/completions 를 부르지 않는다.
          맨 prompt 로는 JSON 강제가 안 걸림(실측)
    """
    config = config or config_for()

    body = json.dumps(
        {
            "model": config.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "recipe_selection",
                    "schema": response_schema,
                    "strict": True,
                },
            },
            "reasoning_effort": "none",
            "temperature": 0,
            "seed": 0,
            "max_tokens": MAX_TOKENS,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        f"{config.host}/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            # vLLM 은 인증을 안 걸었지만 OpenAI 호환 클라이언트가 늘 보내는
            # 자리라 검증된 request contract 그대로 둔다.
            "Authorization": "Bearer EMPTY",
        },
    )
    with urllib.request.urlopen(request, timeout=config.timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]
