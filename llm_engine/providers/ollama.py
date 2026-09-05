"""Ollama 구현체.

qwen 이 이 길로 간다. 요청 한 건에 model · prompt · schema 를 실어 보내고
응답 봉투에서 원문만 꺼낸다. 파싱은 route_resolver 의 몫이다.
"""

import json
import os
import urllib.request
from dataclasses import dataclass

from llm_engine.model_config import get_model_config

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


@dataclass(frozen=True)
class OllamaConfig:
    """호출 한 번이 쓰는 설정. 값은 models.yaml 에서 온다."""

    model: str
    num_ctx: int          # menu.yaml 길이가 길수록 ↑
    timeout: float        # 호출 하나의 상한(초)
    host: str = OLLAMA_HOST


def config_for(model: str | None = None, *, found=None) -> OllamaConfig:
    """모델 설정을 Ollama 호출 설정으로.

    입력  모델 이름(None 이면 기본 모델) · 이미 읽어 둔 ModelConfig
    출력  OllamaConfig
    규칙  host 만 환경변수에서 오고 나머지는 models.yaml 에서 옴.
          어디에 붙는가는 기계마다 다르고, 어떻게 부르는가는 모델마다 다름
    """
    found = found or get_model_config(model)
    return OllamaConfig(
        model=found.model, num_ctx=found.num_ctx, timeout=found.timeout
    )


class OllamaProvider:
    def __init__(self, config: OllamaConfig | None = None):
        self.config = config or config_for()

    def generate(self, prompt: str, response_schema: dict) -> str:
        return call_ollama(prompt, response_schema, config=self.config)


def ping(timeout: float = 3) -> bool:
    """LLM 에 닿는가.

    입력  타임아웃 초. 기본 3. 오래 걸리는 점검은 점검이 아님
    출력  참이면 닿음. 못 닿는 이유는 묻지 않음
    규칙  시연 직전 점검용
    제약  예외를 올리지 않는다.
          못 닿는다는 사실 자체가 답이고, 점검하다 화면이 죽으면 점검이 아님
    """
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=timeout):
            return True
    except Exception:  # noqa: BLE001 — 연결 거부 · 타임아웃 · DNS 전부 같은 답이다.
        return False


def call_ollama(
    prompt: str,
    response_schema: dict,
    *,
    config: OllamaConfig | None = None,
) -> str:
    config = config or config_for()

    body = json.dumps(
        {
            "model": config.model,
            "prompt": prompt,
            "stream": False,
            "format": response_schema,
            "think": False,
            "keep_alive": "2h",
            "options": {"temperature": 0, "seed": 0, "num_ctx": config.num_ctx},
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        f"{config.host}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=config.timeout) as response:
        return json.loads(response.read().decode("utf-8"))["response"]
