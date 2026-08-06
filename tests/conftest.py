"""테스트 전역 상수 / Helper / Fixture.

기능 단위 폴더(context_loading, route_resolution, llm_client, api_contract)가
공통으로 쓰는 것만 둔다.
"""

import builtins
from pathlib import Path

import pytest

import paths

SELECT = "SELECT"
CLARIFY = "CLARIFY"
NO_MATCH = "NO_MATCH"

VALID_STATUSES = {SELECT, CLARIFY, NO_MATCH}

# LLM 에 Context 로 전달하는 Menu 원문.
MENU_YAML_PATH = paths.MENU_YAML_PATH.resolve()


# ------------------------------------------------------------ 공통 Helper
def assert_route_contract(data):
    """resolve_route() 결과가 계약된 형태인지 검증."""
    assert data["status"] in VALID_STATUSES
    assert data["recipe_id"] is None or isinstance(data["recipe_id"], str)
    assert isinstance(data["candidate_recipe_ids"], list)
    assert all(isinstance(rid, str) for rid in data["candidate_recipe_ids"])

    assert isinstance(data["reason"], str)


def menu_was_read(recorded):
    for entry in recorded:
        if not isinstance(entry, (str, Path)):
            continue
        try:
            if Path(entry).resolve() == MENU_YAML_PATH:
                return True
        except OSError:
            continue
    return False


class StubLLMClient:
    """실제 LLM 대체 (test 용도)."""

    def __init__(self, response):
        self.response = response
        self.prompts = []

    def generate(self, prompt: str, response_schema: dict) -> str:
        self.prompts.append(prompt)
        return self.response


# ------------------------------------------------------------ 공통 Fixture
@pytest.fixture
def read_file_paths(monkeypatch):
    recorded = []

    real_open = builtins.open

    def spy_open(file, *args, **kwargs):
        recorded.append(file)
        return real_open(file, *args, **kwargs)

    real_read_text = Path.read_text

    def spy_read_text(self, *args, **kwargs):
        recorded.append(self)
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(Path, "read_text", spy_read_text)
    return recorded


@pytest.fixture
def stub_llm_client():
    return StubLLMClient
