"""
LLM 인터페이스.
"""

from typing import Protocol


class LLMClient(Protocol):
    def generate(self, prompt: str, response_schema: dict) -> str:
        """prompt 를 보내고 response_schema 를 따르는 응답 원문을 돌려준다."""
        ...
