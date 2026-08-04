"""
실제 LLM 대체 (test 용도).
"""

class StubLLMClient:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def generate(self, prompt: str, response_schema: dict) -> str:
        self.prompts.append(prompt)
        return self.response
