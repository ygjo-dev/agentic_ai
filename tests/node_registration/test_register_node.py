"""register_node() 검증. 등록 전체 흐름을 한 번에 묶는다.

실제 저장소 파일을 바꾸므로 매 테스트마다 reset_to_init() 으로 되돌린다.
LLM 은 Stub 이다.
"""

import json

import pytest
import yaml

import paths
from conftest import StubLLMClient
from ontology.registry import InvalidInference, register_node, reset_to_init

FORM = {
    "name": "구조물 균열 진행 추세 분석",
    "description": "문서에서 구조물 균열 폭의 시간 변화를 분석한다.",
    "inputs": ["DocumentData"],
    "outputs": ["AnalysisResult"],
}

INFERRED = {
    "node_id": "analyze_crack_trend",
    "properties": {"target": "구조물"},
    "reason": "구조물 균열 분석과 같은 대상을 다룬다.",
}


@pytest.fixture(autouse=True)
def clean_workspace(isolated_workspace):
    """등록이 건드리는 파일을 임시 디렉터리로 격리한 뒤 앞뒤로 원복한다.

    예전에는 진짜 저장소에 쓰고 되돌렸다. 그러면 리허설로 만들어둔 시연 상태가
    pytest 한 번에 날아간다. isolated_workspace 가 paths 를 임시 사본으로
    바꿔주므로 아래 단언들은 그대로 두고 대상만 옮겼다.
    """
    reset_to_init()
    yield
    reset_to_init()


def stub(response=INFERRED):
    return StubLLMClient(json.dumps(response))


def ontology_nodes():
    return yaml.safe_load(paths.ONTOLOGY_PATH.read_text(encoding="utf-8"))["nodes"]


def menu_recipes():
    return yaml.safe_load(paths.MENU_YAML_PATH.read_text(encoding="utf-8"))["recipes"]


# ------------------------------------------------------------ 전체 흐름
def test_node_lands_in_the_ontology():
    register_node(FORM, llm_client=stub())

    node = ontology_nodes()["analyze_crack_trend"]
    assert node["name"] == FORM["name"]
    assert node["properties"] == {"target": "구조물"}


def test_recipes_are_created_and_numbered_after_021():
    result = register_node(FORM, llm_client=stub())

    assert result["recipe_ids"]
    assert result["recipe_ids"][0] == "recipe_022"
    for recipe_id in result["recipe_ids"]:
        assert (paths.RECIPES_DIR / f"{recipe_id}.yaml").exists()


def test_menu_gains_the_new_recipes():
    result = register_node(FORM, llm_client=stub())

    recipes = menu_recipes()
    for recipe_id in result["recipe_ids"]:
        assert recipe_id in recipes
        assert recipes[recipe_id]["function"].strip()


def test_menu_and_recipes_dir_agree():
    """menu 에 있는데 파일이 없으면 실행 단계에서 깨진다."""
    register_node(FORM, llm_client=stub())

    assert set(menu_recipes()) == {p.stem for p in paths.RECIPES_DIR.glob("*.yaml")}


def test_existing_21_recipes_are_untouched():
    before = {
        p.name: p.read_bytes() for p in paths.INIT_RECIPES_DIR.glob("*.yaml")
    }

    register_node(FORM, llm_client=stub())

    for name, content in before.items():
        assert (paths.RECIPES_DIR / name).read_bytes() == content, name


def test_every_new_recipe_passes_through_the_new_node():
    result = register_node(FORM, llm_client=stub())

    for recipe_id in result["recipe_ids"]:
        data = yaml.safe_load(
            (paths.RECIPES_DIR / f"{recipe_id}.yaml").read_text(encoding="utf-8")
        )
        assert "analyze_crack_trend" in [step["node"] for step in data["steps"]]


# ------------------------------------------------------------ 실패 시 부작용 없음
def test_rejected_inference_leaves_everything_alone():
    """온톨로지에 못 넣은 노드로 recipe 를 만들면 없는 노드를 가리키게 된다."""
    before_nodes = len(ontology_nodes())
    before_recipes = len(list(paths.RECIPES_DIR.glob("*.yaml")))
    before_menu = paths.MENU_YAML_PATH.read_bytes()

    with pytest.raises(InvalidInference):
        register_node(FORM, llm_client=stub({**INFERRED, "node_id": "Bad-Id"}))

    assert len(ontology_nodes()) == before_nodes
    assert len(list(paths.RECIPES_DIR.glob("*.yaml"))) == before_recipes
    assert paths.MENU_YAML_PATH.read_bytes() == before_menu


def test_unknown_property_key_stops_before_writing():
    before = paths.ONTOLOGY_PATH.read_bytes()

    with pytest.raises(InvalidInference):
        register_node(FORM, llm_client=stub({**INFERRED, "properties": {"modality": "x"}}))

    assert paths.ONTOLOGY_PATH.read_bytes() == before


# ------------------------------------------------------------ 반복 등록
def test_second_registration_continues_numbering():
    first = register_node(FORM, llm_client=stub())
    second = register_node(
        {**FORM, "name": "Excel 생성", "description": "분석 결과를 Excel 표로 생성한다.",
         "inputs": ["AnalysisResult"], "outputs": ["DocumentData"]},
        llm_client=stub({**INFERRED, "node_id": "generate_excel", "properties": {}}),
    )

    assert int(second["recipe_ids"][0].split("_")[1]) > int(first["recipe_ids"][-1].split("_")[1])
    assert set(menu_recipes()) == {p.stem for p in paths.RECIPES_DIR.glob("*.yaml")}


def test_reset_undoes_a_registration():
    register_node(FORM, llm_client=stub())

    reset_to_init()

    assert "analyze_crack_trend" not in ontology_nodes()
    assert len(list(paths.RECIPES_DIR.glob("*.yaml"))) == 21
    assert len(menu_recipes()) == 21


# ------------------------------------------------------------ 반환값
def test_returns_what_the_screen_needs():
    result = register_node(FORM, llm_client=stub())

    assert result["node_id"] == "analyze_crack_trend"
    assert result["properties"] == {"target": "구조물"}
    assert result["reason"]
    assert result["recipe_ids"]
    assert result["chains"]
