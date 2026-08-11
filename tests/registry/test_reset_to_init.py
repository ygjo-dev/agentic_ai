"""대상 : ontology/registry.py — reset_to_init()

reset_to_init() 검증. _init 사본을 작업 파일로 되돌린다.

실제 저장소 파일을 건드리므로 fixture 로 원복한다. 이 테스트가 저장소를
망가뜨리면 안 된다.
"""

import shutil

import pytest

import paths
from ontology.registry import reset_to_init

TARGETS = [
    paths.ONTOLOGY_PATH,
    paths.MENU_YAML_PATH,
    paths.MENU_MD_PATH,
]


@pytest.fixture
def restore_workspace(tmp_path):
    """작업 파일 전체를 백업했다가 테스트가 끝나면 되돌린다."""
    backup = tmp_path / "backup"
    backup.mkdir()

    for path in TARGETS:
        shutil.copy2(path, backup / path.name)
    shutil.copytree(paths.RECIPES_DIR, backup / "recipes")

    yield

    for path in TARGETS:
        shutil.copy2(backup / path.name, path)
    shutil.rmtree(paths.RECIPES_DIR)
    shutil.copytree(backup / "recipes", paths.RECIPES_DIR)


def test_restores_ontology_byte_for_byte(restore_workspace):
    paths.ONTOLOGY_PATH.write_text("망가뜨림\n", encoding="utf-8")

    reset_to_init()

    assert paths.ONTOLOGY_PATH.read_bytes() == paths.INIT_ONTOLOGY_PATH.read_bytes()


def test_restores_menu_yaml_and_md(restore_workspace):
    paths.MENU_YAML_PATH.write_text("망가뜨림\n", encoding="utf-8")
    paths.MENU_MD_PATH.write_text("망가뜨림\n", encoding="utf-8")

    reset_to_init()

    assert paths.MENU_YAML_PATH.read_bytes() == paths.INIT_MENU_YAML_PATH.read_bytes()
    assert paths.MENU_MD_PATH.read_bytes() == paths.INIT_MENU_MD_PATH.read_bytes()


def test_extra_recipes_disappear(restore_workspace):
    """등록으로 늘어난 recipe 가 남아 있으면 초기화가 아니다."""
    added = paths.RECIPES_DIR / "recipe_099.yaml"
    added.write_text("steps: []\n", encoding="utf-8")

    reset_to_init()

    assert not added.exists()
    assert {p.stem for p in paths.RECIPES_DIR.glob("*.yaml")} == {
        p.stem for p in paths.INIT_RECIPES_DIR.glob("*.yaml")
    }


def test_modified_recipe_is_restored(restore_workspace):
    target = paths.RECIPES_DIR / "recipe_001.yaml"
    original = target.read_bytes()
    target.write_text("망가뜨림\n", encoding="utf-8")

    reset_to_init()

    assert target.read_bytes() == original


def test_init_copies_are_untouched(restore_workspace):
    """초기화가 원본을 건드리면 다시는 되돌릴 수 없다."""
    before = {
        paths.INIT_ONTOLOGY_PATH: paths.INIT_ONTOLOGY_PATH.read_bytes(),
        paths.INIT_MENU_YAML_PATH: paths.INIT_MENU_YAML_PATH.read_bytes(),
        paths.INIT_MENU_MD_PATH: paths.INIT_MENU_MD_PATH.read_bytes(),
    }
    init_recipes = sorted(p.name for p in paths.INIT_RECIPES_DIR.glob("*.yaml"))

    paths.ONTOLOGY_PATH.write_text("망가뜨림\n", encoding="utf-8")
    reset_to_init()

    for path, content in before.items():
        assert path.read_bytes() == content, path
    assert sorted(p.name for p in paths.INIT_RECIPES_DIR.glob("*.yaml")) == init_recipes


def test_reset_is_idempotent(restore_workspace):
    reset_to_init()
    once = paths.ONTOLOGY_PATH.read_bytes()
    reset_to_init()

    assert paths.ONTOLOGY_PATH.read_bytes() == once
