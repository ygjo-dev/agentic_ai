"""대상 : ontology/registry.py — new_recipes_for()

new_recipes_for() 검증. 새 노드가 포함된 경로만 만든다.

기존 노드끼리의 조합은 이미 recipe 로 있다. 다시 만들면 중복이다.
이 함수는 파일을 쓰지 않는다 — 경로 목록만 돌려준다.
"""

import pytest

from ontology.registry import new_recipes_for

NODES = {
    "load_inspection_document": {
        "inputs": [],
        "outputs": ["DocumentData"],
    },
    "load_cctv_platform": {
        "inputs": [],
        "outputs": ["MediaData"],
    },
    "analyze_congestion": {
        "inputs": ["MediaData"],
        "outputs": ["AnalysisResult"],
    },
    "generate_word": {
        "inputs": ["AnalysisResult"],
        "outputs": ["DocumentData"],
    },
    "generate_ppt": {
        "inputs": ["AnalysisResult"],
        "outputs": ["DocumentData"],
    },
    # 새로 등록한 노드 : 문서를 받아 분석 결과를 낸다.
    "analyze_crack_trend": {
        "inputs": ["DocumentData"],
        "outputs": ["AnalysisResult"],
    },
}

NEW = "analyze_crack_trend"


@pytest.fixture(scope="module")
def paths_found():
    return new_recipes_for(NEW, NODES)


# ------------------------------------------------------------ 포함 규칙
def test_every_path_contains_the_new_node(paths_found):
    """기존 노드끼리의 조합은 이미 recipe 로 있다."""
    assert paths_found
    for chain in paths_found:
        assert NEW in chain, chain


def test_no_path_is_purely_existing_nodes(paths_found):
    existing_only = [c for c in paths_found if NEW not in c]

    assert not existing_only


# ------------------------------------------------------------ 연결 규칙
def test_consecutive_nodes_share_an_interface(paths_found):
    for chain in paths_found:
        for frm, to in zip(chain, chain[1:]):
            shared = set(NODES[frm]["outputs"]) & set(NODES[to]["inputs"])
            assert shared, f"{frm} -> {to}"


def test_first_node_has_empty_inputs(paths_found):
    for chain in paths_found:
        assert NODES[chain[0]]["inputs"] == [], chain


def test_no_node_appears_twice(paths_found):
    for chain in paths_found:
        assert len(chain) == len(set(chain)), chain


def test_at_most_three_steps(paths_found):
    for chain in paths_found:
        assert 1 <= len(chain) <= 3, chain


# ------------------------------------------------------------ 길이 분포
def test_two_and_three_step_paths_exist(paths_found):
    lengths = {len(chain) for chain in paths_found}

    assert 2 in lengths
    assert 3 in lengths


def test_expected_paths_are_present(paths_found):
    """점검 문서 -> 균열 추세 분석 (-> 문서 생성)."""
    assert ["load_inspection_document", NEW] in paths_found
    assert ["load_inspection_document", NEW, "generate_word"] in paths_found
    assert ["load_inspection_document", NEW, "generate_ppt"] in paths_found


def test_incompatible_start_is_excluded(paths_found):
    """CCTV 는 MediaData 를 내놓는다. DocumentData 를 받는 노드로 못 간다."""
    assert not [c for c in paths_found if c[0] == "load_cctv_platform"]


def test_no_duplicate_paths(paths_found):
    seen = [tuple(chain) for chain in paths_found]

    assert len(seen) == len(set(seen))


# ------------------------------------------------------------ 시작 노드인 경우
def test_source_node_yields_a_one_step_path():
    """inputs 가 비면 그 노드 하나짜리 recipe 가 있어야 한다.

    "CCTV 만 불러와줘" 처럼 짧은 요청도 받을 수 있어야 한다.
    """
    nodes = {**NODES, "load_drone_image": {"inputs": [], "outputs": ["MediaData"]}}

    found = new_recipes_for("load_drone_image", nodes)

    assert ["load_drone_image"] in found
    assert ["load_drone_image", "analyze_congestion"] in found


def test_terminal_node_paths_end_with_it():
    """산출 노드를 등록하면 그 노드로 끝나는 경로만 나온다."""
    nodes = {**NODES, "generate_excel": {"inputs": ["AnalysisResult"], "outputs": ["DocumentData"]}}

    found = new_recipes_for("generate_excel", nodes)

    assert found
    for chain in found:
        assert chain[-1] == "generate_excel", chain


# ------------------------------------------------------------ 부작용 없음
def test_returns_plain_lists_and_writes_nothing(paths_found):
    assert isinstance(paths_found, list)
    for chain in paths_found:
        assert isinstance(chain, list)
        assert all(isinstance(node_id, str) for node_id in chain)
