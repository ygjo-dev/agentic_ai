"""Ollama 구현체."""

import json
import os
import urllib.request

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


class OllamaClient:
    def generate(self, prompt: str, response_schema: dict) -> str:
        return call_ollama(prompt, response_schema)


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


def call_ollama(prompt: str, response_schema: dict) -> str:
    body = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": response_schema,
            "think": False,
            "keep_alive": "2h",
            "options": {"temperature": 0, "seed": 0, "num_ctx": 8192}, # menu.yaml 길이가 길수록, num_ctx ↑.
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))["response"]
