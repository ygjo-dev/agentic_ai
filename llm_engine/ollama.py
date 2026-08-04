"""Ollama 구현체."""

import json
import os
import urllib.request

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")


class OllamaClient:
    def generate(self, prompt: str, response_schema: dict) -> str:
        return call_ollama(prompt, response_schema)


def call_ollama(prompt: str, response_schema: dict) -> str:
    body = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": response_schema,
            "think": False,            
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
