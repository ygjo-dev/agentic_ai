"""대상 : ontology/graph.py — highlight_edges()

highlight_edges() 검증. 선택된 recipe 의 step 순서를 엣지 리스트로 돌려준다.
"""

from ontology.graph import highlight_edges


def test_three_step_recipe_yields_two_edges_in_order():
    assert highlight_edges("recipe_010") == [
        ("load_track_image", "detect_track_crack"),
        ("detect_track_crack", "generate_word"),
    ]


def test_edge_count_is_one_less_than_the_steps():
    """노드 n 개짜리 사슬은 엣지가 n-1 개다. 1단 recipe 면 0개다.

    지금 데이터에는 1단 recipe 가 없다(실행 가능한 답이 아니라 넣지 않았다).
    그래도 성질은 코드에 남아 있으므로 모든 recipe 에 대해 재둔다 —
    나중에 1단이 생겨도 여기가 자동으로 덮는다.
    """
    import paths
    from ontology.graph import recipe_nodes

    for recipe_path in sorted(paths.RECIPES_DIR.glob("recipe_*.yaml")):
        chain = recipe_nodes(recipe_path.stem)

        assert len(highlight_edges(recipe_path.stem)) == max(len(chain) - 1, 0)


def test_unknown_recipe_yields_no_edge():
    assert highlight_edges("recipe_999") == []


def test_result_is_an_ordered_list_not_a_set():
    """순번 라벨(1, 2)을 붙이려면 순서가 남아야 한다.

    나중에 recipe 에 루프가 생겨 같은 엣지를 두 번 지나면
    집합은 그것을 하나로 뭉개버린다.
    """
    edges = highlight_edges("recipe_010")

    assert isinstance(edges, list)
    assert edges[0] == ("load_track_image", "detect_track_crack")
    assert edges[1] == ("detect_track_crack", "generate_word")


def test_edges_chain_head_to_tail():
    """앞 엣지의 도착점이 뒤 엣지의 출발점이어야 경로가 끊기지 않는다."""
    edges = highlight_edges("recipe_011")

    assert len(edges) == 2
    for (_, to), (frm, _) in zip(edges, edges[1:]):
        assert to == frm
