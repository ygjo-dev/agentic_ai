"""테스트 전역 상수 / Helper / Fixture.

기능 단위 폴더(context_loading, route_resolution, llm_client, api_contract)가
공통으로 쓰는 것만 둔다.
"""

import builtins
import hashlib
import shutil
from pathlib import Path

import pytest

import paths

SELECT = "SELECT"
CLARIFY = "CLARIFY"
NO_MATCH = "NO_MATCH"

VALID_STATUSES = {SELECT, CLARIFY, NO_MATCH}

# LLM 에 Context 로 전달하는 Menu 원문.
MENU_YAML_PATH = paths.MENU_YAML_PATH.resolve()

# 진짜 저장소 파일. monkeypatch 로 paths 가 바뀌어도 이 값은 그대로다 —
# 격리가 실제로 되는지 검사할 때 쓴다.
REAL_ONTOLOGY_PATH = paths.ONTOLOGY_PATH.resolve()
REAL_RECIPES_DIR = paths.RECIPES_DIR.resolve()


def workspace_digest() -> str:
    """진짜 저장소의 온톨로지 + recipe 내용 해시.

    등록 테스트가 저장소를 건드리지 않았는지 확인하는 데 씀.
    """
    digest = hashlib.sha1()
    digest.update(REAL_ONTOLOGY_PATH.read_bytes())
    for recipe in sorted(REAL_RECIPES_DIR.glob("*.yaml")):
        digest.update(recipe.name.encode("utf-8"))
        digest.update(recipe.read_bytes())
    return digest.hexdigest()


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


@pytest.fixture
def isolated_workspace(monkeypatch, tmp_path):
    """등록이 건드리는 파일을 전부 임시 디렉터리 사본으로 바꿈.

    등록 테스트는 원래 진짜 저장소에 쓰고 reset_to_init() 으로 되돌렸음.
    동작에 버그는 없었지만, 리허설로 시연 상태를 만들어둔 뒤 누가 pytest 를
    돌리면 등록해둔 노드가 전부 날아감. 시연 당일 사고가 될 수 있어 격리함.

    register_node 는 paths 전역을 호출 시점에 읽으므로 모듈 속성만 바꾸면 됨.
    프롬프트 경로는 읽기만 하므로 그대로 둠.

    **노드 좌표도 여기서 막는다.** reset_to_init() 이 좌표까지 되돌리게 되면서
    (등록한 노드가 사라진 뒤에도 좌표가 남는 것을 막으려는 것) 격리를 안 하면
    pytest 가 시연용 작업본을 _init 으로 덮어쓴다. 좌표는 paths 가 아니라
    layout_store 가 들고 있으므로 그쪽 모듈 속성을 바꾼다.
    """
    work = tmp_path / "work"
    init = tmp_path / "init"
    work.mkdir()
    init.mkdir()

    # 작업본과 _init 사본 둘 다 만든다. reset_to_init() 이 init -> work 로 복사한다.
    for source, target in (
        (paths.INIT_ONTOLOGY_PATH, work / "ontology.yaml"),
        (paths.INIT_MENU_YAML_PATH, work / "menu.yaml"),
        (paths.INIT_MENU_MD_PATH, work / "menu.md"),
        (paths.INIT_ONTOLOGY_PATH, init / "ontology.yaml"),
        (paths.INIT_MENU_YAML_PATH, init / "menu.yaml"),
        (paths.INIT_MENU_MD_PATH, init / "menu.md"),
    ):
        shutil.copy2(source, target)
    shutil.copytree(paths.INIT_RECIPES_DIR, work / "recipes")
    shutil.copytree(paths.INIT_RECIPES_DIR, init / "recipes")

    for name, value in (
        ("ONTOLOGY_PATH", work / "ontology.yaml"),
        ("MENU_YAML_PATH", work / "menu.yaml"),
        ("MENU_MD_PATH", work / "menu.md"),
        ("RECIPES_DIR", work / "recipes"),
        ("INIT_ONTOLOGY_PATH", init / "ontology.yaml"),
        ("INIT_MENU_YAML_PATH", init / "menu.yaml"),
        ("INIT_MENU_MD_PATH", init / "menu.md"),
        ("INIT_RECIPES_DIR", init / "recipes"),
    ):
        monkeypatch.setattr(paths, name, value)

    from app.ui.graph import layout_store

    shutil.copy2(layout_store.INIT_LAYOUT_PATH, init / "layout.json")
    shutil.copy2(layout_store.INIT_LAYOUT_PATH, work / "layout.json")
    monkeypatch.setattr(layout_store, "LAYOUT_PATH", work / "layout.json")
    monkeypatch.setattr(layout_store, "INIT_LAYOUT_PATH", init / "layout.json")

    return work
