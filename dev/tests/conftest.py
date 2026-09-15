"""테스트 전역 상수 / Helper / Fixture.

폴더 여럿이 공통으로 쓰는 것만 둔다.
"""

import builtins
import os
import shutil
from pathlib import Path

import pytest

import paths

SELECT = "SELECT"
CLARIFY = "CLARIFY"
NO_MATCH = "NO_MATCH"

# 시험이 볼 서비스 주소. **이 기계의 .env 를 안 본다** — 개발자마다 다른 값이
# 들어오면 같은 시험이 기계마다 다른 것을 재게 된다. 부를 일은 없고 요청이
# 어느 주소로 갔는지만 대조한다.
TEST_ENDPOINTS = {
    "OLLAMA_URL": "http://ollama.test:11434",
    "VLLM_URL": "http://vllm.test:18000",
    "ASAP_GATEWAY_URL": "http://gateway.test:3000",
    "AGENTIC_API_URL": "http://agentic.test:8000",
}


# **모으는 때에 이미 두어야 한다.** vendor 의 mcp_client 가 import 시점에
# 전역 인스턴스를 만들며 주소를 읽으므로(KRRI_ASAP 원본이라 안 고친다),
# fixture 만으로는 시험 파일을 읽는 순간 이미 늦는다.
os.environ.update(TEST_ENDPOINTS)


@pytest.fixture(autouse=True)
def endpoints_env(monkeypatch):
    """서비스 주소 넷을 시험마다 다시 시험용 값으로 둔다.

    위에서 한 번 두었지만 시험이 지우거나 바꾼 것을 되돌릴 자리가 필요함.
    주소에 기본값이 없으므로 이것이 없으면 이 기계의 .env 를 그대로 탐.
    """
    for name, value in TEST_ENDPOINTS.items():
        monkeypatch.setenv(name, value)

VALID_STATUSES = {SELECT, CLARIFY, NO_MATCH}

# LLM 에 Context 로 전달하는 Menu 원문.
MENU_YAML_PATH = paths.MENU_YAML_PATH.resolve()


# ------------------------------------------------------------ 공통 Helper
def assert_route_contract(data):
    """recipe 선택 결과가 계약된 형태인지 검증."""
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


def fake_role(**overrides):
    """역할 설정 한 벌을 손으로 만듦. 역할 파일을 안 읽음.

    provider 나 inference 값만 갈아 끼워 보는 시험이 씀. 실물 역할의 모델 이름을
    적으면 모델을 옮길 때마다 상관없는 시험이 빨개짐.
    """
    from llm_engine.role_config import RoleConfig

    values = {
        "role": "시험역할",
        "version": 1,
        "model": "시험모델",
        "provider": "ollama",
        "inference": {"num_ctx": 8192, "timeout": 180},
        "prompt_version": 1,
        "response_schema_version": 1,
        "prompt": "{utterance}",
        "response_schema": {"type": "object", "properties": {}, "required": []},
    }
    values.update(overrides)
    return RoleConfig(**values)


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


@pytest.fixture
def isolated_workspace(monkeypatch, tmp_path):
    """시험이 고쳐 쓰는 게시 자산(온톨로지 · menu · recipe)과 좌표를 임시 사본으로 바꿈.

    격리를 안 하면 시험이 온톨로지에 붙인 노드 · 관계가 진짜 저장소에 남음.

    paths 전역을 호출 시점에 읽으므로 모듈 속성만 바꾸면 됨.
    좌표는 paths 가 아니라 layout_store 가 들고 있어 그쪽 모듈 속성을 바꾼다.
    """
    work = tmp_path / "work"
    work.mkdir()

    for source, target in (
        (paths.ONTOLOGY_PATH, work / "ontology.yaml"),
        (paths.MENU_YAML_PATH, work / "menu.yaml"),
        (paths.MENU_MD_PATH, work / "menu.md"),
    ):
        shutil.copy2(source, target)
    shutil.copytree(paths.RECIPES_DIR, work / "recipes")

    for name, value in (
        ("ONTOLOGY_PATH", work / "ontology.yaml"),
        ("MENU_YAML_PATH", work / "menu.yaml"),
        ("MENU_MD_PATH", work / "menu.md"),
        ("RECIPES_DIR", work / "recipes"),
    ):
        monkeypatch.setattr(paths, name, value)

    from app.ui.graph import layout_store

    shutil.copy2(layout_store.INIT_LAYOUT_PATH, work / "layout.json")
    monkeypatch.setattr(layout_store, "LAYOUT_PATH", work / "layout.json")

    return work
