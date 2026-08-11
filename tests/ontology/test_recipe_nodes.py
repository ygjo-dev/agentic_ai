"""대상 : ontology/graph.py — recipe_nodes()

recipe_nodes() 검증. recipes/<id>.yaml 의 step 순서대로 노드 id 를 돌려준다.
"""

from ontology.graph import recipe_nodes


def test_three_step_recipe_returns_nodes_in_order():
    """recipe_010 : 궤도 이미지 -> 균열 검출 -> Word 보고서."""
    assert recipe_nodes("recipe_010") == [
        "load_track_image",
        "detect_track_crack",
        "generate_word",
    ]


def test_every_recipe_starts_at_a_loader_and_flows_forward():
    """순서가 뒤집히면 경로가 거꾸로 그려진다.

    특정 recipe 번호를 박지 않는다 — 온톨로지를 바꿀 때마다 여기가 깨진다.
    모든 recipe 가 지켜야 하는 성질로 적는다.
    """
    import paths
    from ontology.graph import load_ontology

    nodes = load_ontology()["nodes"]
    for recipe_path in sorted(paths.RECIPES_DIR.glob("recipe_*.yaml")):
        chain = recipe_nodes(recipe_path.stem)

        assert chain, recipe_path.stem
        assert nodes[chain[0]]["inputs"] == [], f"{recipe_path.stem} 이 불러오기로 시작하지 않는다"
        for frm, to in zip(chain, chain[1:]):
            assert set(nodes[frm]["outputs"]) & set(nodes[to]["inputs"]), (frm, to)


def test_unknown_recipe_returns_empty_list():
    """파일이 없으면 예외 대신 빈 리스트. 화면이 죽지 않아야 한다."""
    assert recipe_nodes("recipe_999") == []
