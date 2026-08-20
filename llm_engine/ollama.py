"""Ollama 구현체."""

import json
import os
import urllib.request
from dataclasses import dataclass, replace

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")


@dataclass(frozen=True)
class OllamaConfig:
    """호출 한 번이 쓰는 설정(기본 값)."""

    host: str = OLLAMA_HOST
    model: str = OLLAMA_MODEL
    timeout: float = 180  # 호출 하나의 상한(초)
    num_ctx: int = 8192   # menu.yaml 길이가 길수록 ↑


DEFAULT_CONFIG = OllamaConfig()


class OllamaClient:
    def __init__(self, config: OllamaConfig = DEFAULT_CONFIG):
        self.config = config

    def generate(self, prompt: str, response_schema: dict) -> str:
        return call_ollama(prompt, response_schema, config=self.config)


def make_client(model: str | None = None) -> OllamaClient:
    """모델만 갈아끼운 클라이언트.

    입력  모델 이름. None 이면 기본 모델
    출력  generate(prompt, response_schema) 를 가진 클라이언트
    규칙  어떤 LLM 을 쓸지 고르는 유일한 자리. 다른 provider 가 붙으면 여기서 갈라짐
          모델이 다른 클라이언트가 한 프로세스에 여럿 살 수 있음.
          같은 발화를 모델만 바꿔 재는 데 프로세스를 다시 띄우지 않으려는 것
    """
    if model is None:
        return OllamaClient()
    return OllamaClient(replace(DEFAULT_CONFIG, model=model))


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
    config: OllamaConfig = DEFAULT_CONFIG,
) -> str:
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
