"""대상 : ontology/registry.py — append_menu()

append_menu() 검증. menu.yaml / menu.md 에 새 recipe 를 추가한다.

function 문장은 LLM 이 recipe 를 고르는 유일한 근거다. 기존 문장이 한 글자라도
바뀌면 이미 검증한 발화들이 다른 recipe 로 갈 수 있다.
"""

import shutil

import pytest
import yaml

import paths
from ontology.registry import MENU_BUDGET, append_menu, function_for

NODES = {
    "load_inspection_document": {
        "description": "점검 과정에서 기록된 문서를 불러온다.",
    },
    "analyze_crack_trend": {
        "description": "문서에서 균열 폭의 시간 변화를 분석한다.",
    },
    "generate_word": {
        "description": "분석 결과를 Word 문서로 생성한다.",
    },
}

CHAINS = [
    ["load_inspection_document", "analyze_crack_trend"],
    ["load_inspection_document", "analyze_crack_trend", "generate_word"],
]
NEW_IDS = ["recipe_029", "recipe_030"]


@pytest.fixture
def menu_files(tmp_path):
    yaml_path = tmp_path / "menu.yaml"
    md_path = tmp_path / "menu.md"
    shutil.copy2(paths.MENU_YAML_PATH, yaml_path)
    shutil.copy2(paths.MENU_MD_PATH, md_path)
    return yaml_path, md_path


def recipes_of(yaml_path):
    return yaml.safe_load(yaml_path.read_text(encoding="utf-8"))["recipes"]


# ------------------------------------------------------------ 추가
def test_new_recipes_appear(menu_files):
    yaml_path, md_path = menu_files

    append_menu(NEW_IDS, CHAINS, NODES, yaml_path=yaml_path, md_path=md_path)

    recipes = recipes_of(yaml_path)
    assert set(NEW_IDS) <= set(recipes)
    for recipe_id in NEW_IDS:
        assert recipes[recipe_id]["function"].strip()


def test_existing_functions_are_byte_identical(menu_files):
    yaml_path, md_path = menu_files
    before = recipes_of(yaml_path)

    append_menu(NEW_IDS, CHAINS, NODES, yaml_path=yaml_path, md_path=md_path)

    after = recipes_of(yaml_path)
    for recipe_id, recipe in before.items():
        assert after[recipe_id]["function"] == recipe["function"], recipe_id


def test_menu_yaml_holds_function_only(menu_files):
    """steps 가 들어가면 context 가 커져 LLM 이 타임아웃한다."""
    yaml_path, md_path = menu_files

    append_menu(NEW_IDS, CHAINS, NODES, yaml_path=yaml_path, md_path=md_path)

    for recipe in recipes_of(yaml_path).values():
        assert set(recipe) == {"function"}


def test_every_function_is_distinct(menu_files):
    """같은 문장이 둘이면 LLM 이 둘을 구별할 근거가 없다."""
    yaml_path, md_path = menu_files

    append_menu(NEW_IDS, CHAINS, NODES, yaml_path=yaml_path, md_path=md_path)

    functions = [r["function"] for r in recipes_of(yaml_path).values()]
    assert len(functions) == len(set(functions))


def test_version_survives(menu_files):
    yaml_path, md_path = menu_files

    append_menu(NEW_IDS, CHAINS, NODES, yaml_path=yaml_path, md_path=md_path)

    assert yaml.safe_load(yaml_path.read_text(encoding="utf-8"))["version"] == 1.0


# ------------------------------------------------------------ menu.md 일치
def test_md_lists_every_recipe_of_the_yaml(menu_files):
    yaml_path, md_path = menu_files

    append_menu(NEW_IDS, CHAINS, NODES, yaml_path=yaml_path, md_path=md_path)

    md = md_path.read_text(encoding="utf-8")
    for recipe_id, recipe in recipes_of(yaml_path).items():
        assert recipe_id in md, recipe_id
        assert recipe["function"] in md, recipe_id


def test_md_body_section_is_added(menu_files):
    yaml_path, md_path = menu_files

    append_menu(NEW_IDS, CHAINS, NODES, yaml_path=yaml_path, md_path=md_path)

    md = md_path.read_text(encoding="utf-8")
    assert "# Recipe 029" in md
    assert "# Recipe 030" in md


def test_md_keeps_its_header(menu_files):
    yaml_path, md_path = menu_files
    head = md_path.read_text(encoding="utf-8").split("## 목차")[0]

    append_menu(NEW_IDS, CHAINS, NODES, yaml_path=yaml_path, md_path=md_path)

    assert md_path.read_text(encoding="utf-8").startswith(head)


# ------------------------------------------------------------ function 문장
def test_function_joins_node_descriptions():
    sentence = function_for(CHAINS[1], NODES)

    assert sentence.endswith(".")
    assert "불러와" in sentence
    assert "Word" in sentence


def test_function_differs_by_chain():
    assert function_for(CHAINS[0], NODES) != function_for(CHAINS[1], NODES)


def test_single_node_function_is_its_description():
    sentence = function_for(["load_inspection_document"], NODES)

    assert sentence == NODES["load_inspection_document"]["description"]


@pytest.mark.parametrize(
    "chain",
    [
        ["load_inspection_document", "analyze_crack_trend"],
        ["load_inspection_document", "analyze_crack_trend", "generate_word"],
    ],
)
def test_no_syllable_is_duplicated_when_joining(chain):
    """이어 붙이며 음절이 겹치면 (불불러와, 분석한하고) 문장이 깨진다."""
    sentence = function_for(chain, NODES)

    for broken in ("불불", "한하고", "온하고", "다하고", "와와"):
        assert broken not in sentence, f"{broken!r} 가 들어 있다: {sentence}"


def test_loading_clause_uses_the_natural_connective():
    """기존 menu 문장이 쓰는 '불러와' 형태를 따른다."""
    sentence = function_for(["load_inspection_document", "analyze_crack_trend"], NODES)

    assert "불러와" in sentence
    assert "불러온다" not in sentence, "이어 붙일 때는 종결형을 쓰지 않는다."


def test_middle_clause_ends_with_hago():
    sentence = function_for(CHAINS[1], NODES)

    assert "분석하고" in sentence, sentence


def test_only_the_last_clause_is_declarative():
    """종결형(~한다)이 문장 끝에만 있어야 한 문장으로 읽힌다."""
    sentence = function_for(CHAINS[1], NODES)

    assert sentence.count("한다") == 1
    assert sentence.endswith("생성한다.")


# ------------------------------------------------------------ 크기 상한
def test_menu_stays_within_budget_after_append(menu_files):
    """상한을 넘으면 num_ctx 를 넘겨 LLM 이 타임아웃한다."""
    yaml_path, md_path = menu_files

    append_menu(NEW_IDS, CHAINS, NODES, yaml_path=yaml_path, md_path=md_path)

    size = len(yaml_path.read_text(encoding="utf-8"))
    assert size < MENU_BUDGET, f"menu 가 {size}자로 상한({MENU_BUDGET})을 넘었다."
