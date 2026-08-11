"""대상 : ontology/registry.py — append_recipes()

append_recipes() 검증. 생성된 경로를 recipe 파일로 쓴다.

기존 21개의 번호는 바뀌면 안 된다 — menu 와 SAMPLES 가 그 번호를 가리킨다.
"""

import shutil

import pytest
import yaml

import paths
from ontology.registry import append_recipes

NODES = {
    "load_inspection_document": {"inputs": [], "outputs": ["DocumentData"]},
    "analyze_crack_trend": {"inputs": ["DocumentData"], "outputs": ["AnalysisResult"]},
    "generate_word": {"inputs": ["AnalysisResult"], "outputs": ["DocumentData"]},
}

CHAINS = [
    ["load_inspection_document", "analyze_crack_trend"],
    ["load_inspection_document", "analyze_crack_trend", "generate_word"],
]


@pytest.fixture
def recipes_dir(tmp_path):
    """실제 recipes 를 복사해 임시 디렉터리로 쓴다."""
    target = tmp_path / "recipes"
    shutil.copytree(paths.RECIPES_DIR, target)
    return target


def ids_in(directory):
    return sorted(p.stem for p in directory.glob("*.yaml"))


# ------------------------------------------------------------ 번호 부여
def test_existing_numbers_are_untouched(recipes_dir):
    before = {p.name: p.read_bytes() for p in recipes_dir.glob("*.yaml")}

    append_recipes(CHAINS, NODES, directory=recipes_dir)

    for name, content in before.items():
        assert (recipes_dir / name).read_bytes() == content, name


def test_new_files_continue_from_022(recipes_dir):
    created = append_recipes(CHAINS, NODES, directory=recipes_dir)

    assert created == ["recipe_022", "recipe_023"]
    assert (recipes_dir / "recipe_022.yaml").exists()
    assert (recipes_dir / "recipe_023.yaml").exists()


def test_second_registration_keeps_counting(recipes_dir):
    append_recipes(CHAINS, NODES, directory=recipes_dir)
    created = append_recipes(CHAINS, NODES, directory=recipes_dir)

    assert created == ["recipe_024", "recipe_025"]
    assert len(ids_in(recipes_dir)) == 25


def test_ids_are_zero_padded_to_three(recipes_dir):
    append_recipes(CHAINS, NODES, directory=recipes_dir)

    for recipe_id in ids_in(recipes_dir):
        assert recipe_id.startswith("recipe_")
        assert len(recipe_id) == len("recipe_000")


def test_empty_chain_list_creates_nothing(recipes_dir):
    before = ids_in(recipes_dir)

    assert append_recipes([], NODES, directory=recipes_dir) == []
    assert ids_in(recipes_dir) == before


# ------------------------------------------------------------ 파일 형식
def test_written_file_matches_the_existing_shape(recipes_dir):
    append_recipes(CHAINS, NODES, directory=recipes_dir)

    data = yaml.safe_load((recipes_dir / "recipe_023.yaml").read_text(encoding="utf-8"))

    assert set(data) == {"steps"}
    assert [step["node"] for step in data["steps"]] == CHAINS[1]
    for step in data["steps"]:
        assert set(step) == {"node", "inputs", "outputs"}


def test_steps_carry_the_ontology_interfaces(recipes_dir):
    append_recipes(CHAINS, NODES, directory=recipes_dir)

    steps = yaml.safe_load(
        (recipes_dir / "recipe_023.yaml").read_text(encoding="utf-8")
    )["steps"]

    assert steps[0]["inputs"] == []
    assert steps[0]["outputs"] == ["DocumentData"]
    assert steps[1]["inputs"] == ["DocumentData"]
    assert steps[2]["outputs"] == ["DocumentData"]


def test_new_file_parses_like_the_old_ones(recipes_dir):
    append_recipes(CHAINS, NODES, directory=recipes_dir)

    old = yaml.safe_load((recipes_dir / "recipe_010.yaml").read_text(encoding="utf-8"))
    new = yaml.safe_load((recipes_dir / "recipe_023.yaml").read_text(encoding="utf-8"))

    assert set(old) == set(new)
    assert set(old["steps"][0]) == set(new["steps"][0])
