"""대상 : ontology/registry.py — add_node()

add_node() 검증. 온톨로지에 노드를 추가한다.
"""

import pytest
import yaml

from ontology.registry import (
    PROPERTY_KEYS,
    DuplicateNode,
    UnknownInterface,
    UnknownPropertyKey,
    add_node,
)

NEW = {
    "name": "구조물 균열 진행 추세 분석",
    "description": "문서에서 구조물 균열 폭의 시간 변화를 분석한다.",
    "inputs": ["DocumentData"],
    "outputs": ["AnalysisResult"],
    "properties": {"target": "구조물"},
}


@pytest.fixture
def ontology_file(tmp_path):
    """실제 온톨로지를 복사해 임시 파일로 쓴다. 저장소를 건드리지 않는다."""
    import paths

    path = tmp_path / "ontology.yaml"
    path.write_text(paths.ONTOLOGY_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------ 추가
def test_node_is_added(ontology_file):
    add_node("analyze_crack_trend", NEW, path=ontology_file)

    nodes = load(ontology_file)["nodes"]
    assert "analyze_crack_trend" in nodes
    assert nodes["analyze_crack_trend"]["name"] == NEW["name"]
    assert nodes["analyze_crack_trend"]["inputs"] == ["DocumentData"]
    assert nodes["analyze_crack_trend"]["outputs"] == ["AnalysisResult"]
    assert nodes["analyze_crack_trend"]["properties"] == {"target": "구조물"}


def test_existing_nodes_survive(ontology_file):
    before = load(ontology_file)["nodes"]

    add_node("analyze_crack_trend", NEW, path=ontology_file)

    after = load(ontology_file)["nodes"]
    assert len(after) == len(before) + 1
    for node_id, node in before.items():
        assert after[node_id] == node, node_id


def test_interfaces_block_is_untouched(ontology_file):
    before = load(ontology_file)["interfaces"]

    add_node("analyze_crack_trend", NEW, path=ontology_file)

    assert load(ontology_file)["interfaces"] == before


def test_empty_properties_is_allowed(ontology_file):
    """기존 노드와 관계가 없으면 비운다. 억지로 끼워 맞추지 않는다."""
    add_node("generate_excel", {**NEW, "properties": {}}, path=ontology_file)

    assert load(ontology_file)["nodes"]["generate_excel"]["properties"] == {}


def test_empty_inputs_is_allowed(ontology_file):
    add_node("load_something", {**NEW, "inputs": []}, path=ontology_file)

    assert load(ontology_file)["nodes"]["load_something"]["inputs"] == []


# ------------------------------------------------------------ 거부
def test_duplicate_id_is_rejected(ontology_file):
    with pytest.raises(DuplicateNode):
        add_node("analyze_congestion", NEW, path=ontology_file)


def test_duplicate_does_not_modify_the_file(ontology_file):
    before = ontology_file.read_bytes()

    with pytest.raises(DuplicateNode):
        add_node("analyze_congestion", NEW, path=ontology_file)

    assert ontology_file.read_bytes() == before


def test_unknown_input_interface_is_rejected(ontology_file):
    with pytest.raises(UnknownInterface):
        add_node("x", {**NEW, "inputs": ["VideoData"]}, path=ontology_file)


def test_unknown_output_interface_is_rejected(ontology_file):
    with pytest.raises(UnknownInterface):
        add_node("x", {**NEW, "outputs": ["Report"]}, path=ontology_file)


def test_unknown_property_key_is_rejected(ontology_file):
    """key 어휘가 갈라지면 점선 조회가 조용히 실패한다.

    프롬프트로만 막으면 LLM 이 어기는 순간 통과한다. 코드로도 막는다.
    """
    with pytest.raises(UnknownPropertyKey):
        add_node("x", {**NEW, "properties": {"modality": "video"}}, path=ontology_file)


def test_new_property_value_is_allowed(ontology_file):
    """값은 새로워도 된다. 막는 것은 key 뿐이다."""
    add_node("x", {**NEW, "properties": {"target": "터널"}}, path=ontology_file)

    assert load(ontology_file)["nodes"]["x"]["properties"] == {"target": "터널"}


def test_property_keys_match_the_existing_vocabulary(ontology_file):
    existing = set()
    for node in load(ontology_file)["nodes"].values():
        existing |= set((node.get("properties") or {}).keys())

    assert existing <= PROPERTY_KEYS


# ------------------------------------------------------------ 파일 형식
def test_header_comment_survives(ontology_file):
    """상단 주석에 구조 원칙과 property key 목록이 적혀 있다."""
    before = ontology_file.read_text(encoding="utf-8")
    head = before[: before.index("version:")]

    add_node("analyze_crack_trend", NEW, path=ontology_file)

    assert ontology_file.read_text(encoding="utf-8").startswith(head)


def test_file_stays_valid_yaml_and_readable(ontology_file):
    add_node("analyze_crack_trend", NEW, path=ontology_file)

    text = ontology_file.read_text(encoding="utf-8")
    assert yaml.safe_load(text)  # 파싱되어야 한다
    assert "  analyze_crack_trend:" in text, "노드가 nodes 아래 2칸 들여쓰기여야 한다."


def test_added_node_round_trips(ontology_file):
    """두 번 추가해도 형식이 유지된다."""
    add_node("a_node", NEW, path=ontology_file)
    add_node("b_node", {**NEW, "properties": {}}, path=ontology_file)

    nodes = load(ontology_file)["nodes"]
    assert "a_node" in nodes and "b_node" in nodes
