"""대상 : ontology/graph.py — highlight_edges()

highlight_edges() 검증. 선택된 recipe 의 step 순서를 엣지 리스트로 돌려준다.
"""

from ontology.graph import highlight_edges


def test_three_step_recipe_yields_two_edges_in_order():
    assert highlight_edges("recipe_010") == [
        ("load_cctv_platform", "analyze_congestion"),
        ("analyze_congestion", "generate_word"),
    ]


def test_one_step_recipe_yields_no_edge():
    assert highlight_edges("recipe_001") == []


def test_unknown_recipe_yields_no_edge():
    assert highlight_edges("recipe_999") == []


def test_result_is_an_ordered_list_not_a_set():
    """순번 라벨(1, 2)을 붙이려면 순서가 남아야 한다.

    나중에 recipe 에 루프가 생겨 같은 엣지를 두 번 지나면
    집합은 그것을 하나로 뭉개버린다.
    """
    edges = highlight_edges("recipe_010")

    assert isinstance(edges, list)
    assert edges[0] == ("load_cctv_platform", "analyze_congestion")
    assert edges[1] == ("analyze_congestion", "generate_word")


def test_edges_chain_head_to_tail():
    """앞 엣지의 도착점이 뒤 엣지의 출발점이어야 경로가 끊기지 않는다."""
    edges = highlight_edges("recipe_017")

    assert len(edges) == 2
    for (_, to), (frm, _) in zip(edges, edges[1:]):
        assert to == frm
