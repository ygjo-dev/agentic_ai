"""해석 경로 해석 로직 검증 (frontend/focus.py).

클릭 의미론이 예전과 다르다 — 그 노드를 *지나는* recipe 가 아니라
그 노드로 **끝나는** recipe 만 남긴다.
"""

import pytest

from frontend import focus


def steps(*node_ids):
    return [{"node_id": n, "name": n.upper(), "out_interface": "X"} for n in node_ids]


PATHS = {
    # 분석까지만 (마지막 = analyze_congestion)
    "recipe_004": steps("load_cctv", "analyze_congestion"),
    # 같은 끝점, 다른 시작
    "recipe_006": steps("load_car", "analyze_congestion"),
    # 문서까지 (마지막 = generate_word)
    "recipe_010": steps("load_cctv", "analyze_congestion", "generate_word"),
    # 1단 recipe — 엣지가 없다
    "recipe_001": steps("load_cctv"),
}
IDS = ["recipe_004", "recipe_006", "recipe_010", "recipe_001"]


# ------------------------------------------------------------ 기본
def test_step_ids():
    assert focus.step_ids(PATHS["recipe_010"]) == [
        "load_cctv", "analyze_congestion", "generate_word",
    ]


def test_path_edges_are_adjacent_pairs():
    assert focus.path_edges(PATHS["recipe_010"]) == [
        ("load_cctv", "analyze_congestion"),
        ("analyze_congestion", "generate_word"),
    ]


def test_single_step_path_has_no_edges():
    """1단 recipe 는 엣지가 없다. 노드는 따로 모아야 강조된다."""
    assert focus.path_edges(PATHS["recipe_001"]) == []
    assert focus.nodes_of(PATHS, ["recipe_001"]) == {"load_cctv"}


def test_last_node():
    assert focus.last_node(PATHS["recipe_010"]) == "generate_word"
    assert focus.last_node([]) is None


# ------------------------------------------------------------ 마지막 노드
def test_last_nodes_are_deduplicated():
    """recipe_004 와 recipe_006 은 끝점이 같다. 한 번만 나와야 한다."""
    assert focus.last_nodes(PATHS, IDS) == [
        "analyze_congestion", "generate_word", "load_cctv",
    ]


def test_last_nodes_order_is_deterministic():
    assert focus.last_nodes(PATHS, IDS) == focus.last_nodes(PATHS, IDS)


def test_last_nodes_follow_recipe_order():
    reordered = ["recipe_010", "recipe_004", "recipe_001", "recipe_006"]

    assert focus.last_nodes(PATHS, reordered) == [
        "generate_word", "analyze_congestion", "load_cctv",
    ]


def test_last_nodes_skips_empty_paths():
    assert focus.last_nodes({"r": []}, ["r"]) == []


# ------------------------------------------------------------ 좁히기
def test_narrowing_keeps_only_recipes_ending_there():
    assert focus.recipes_ending_at(PATHS, IDS, "analyze_congestion") == [
        "recipe_004", "recipe_006",
    ]


def test_narrowing_to_a_document_node():
    assert focus.recipes_ending_at(PATHS, IDS, "generate_word") == ["recipe_010"]


def test_middle_node_is_not_a_click_target():
    """analyze_congestion 은 recipe_010 의 중간이지만 끝점이기도 하다.

    load_cctv 로 끝나는 것은 recipe_001 뿐이라, 중간으로만 쓰이는 노드는
    클릭 대상에 없어야 한다.
    """
    assert "load_car" not in focus.last_nodes(PATHS, IDS)
    assert focus.recipes_ending_at(PATHS, IDS, "load_car") == []


# ------------------------------------------------------------ 변형
def test_variants_have_all_plus_one_per_last_node():
    variants = focus.focus_variants(PATHS, IDS)

    assert set(variants) == {"", "analyze_congestion", "generate_word", "load_cctv"}


def test_all_variant_keeps_every_candidate():
    assert focus.focus_variants(PATHS, IDS)[""] == IDS


def test_each_variant_holds_only_its_own_recipes():
    variants = focus.focus_variants(PATHS, IDS)

    assert variants["analyze_congestion"] == ["recipe_004", "recipe_006"]
    assert variants["generate_word"] == ["recipe_010"]
    assert variants["load_cctv"] == ["recipe_001"]


def test_narrowed_to_one_is_a_single_path():
    """하나로 좁혀지면 build_dot 의 len(paths)==1 규칙이 순번을 붙인다."""
    variants = focus.focus_variants(PATHS, IDS)

    assert len(variants["generate_word"]) == 1
    assert len(variants["analyze_congestion"]) == 2


def test_no_candidates_gives_only_the_all_variant():
    assert focus.focus_variants(PATHS, []) == {"": []}


# ------------------------------------------------------------ 후보 순서
def test_ordered_recipe_ids_dedupes_the_selected_one():
    result = {"recipe_id": "r1", "candidate_recipe_ids": ["r1", "r2"]}

    assert focus.ordered_recipe_ids(result) == ["r1", "r2"]


def test_ordered_recipe_ids_of_nothing():
    assert focus.ordered_recipe_ids(None) == []
    assert focus.ordered_recipe_ids({}) == []


@pytest.mark.parametrize("missing", [{}, {"paths": None}])
def test_missing_paths_do_not_crash(missing):
    assert focus.last_nodes(missing.get("paths"), ["r"]) == []
