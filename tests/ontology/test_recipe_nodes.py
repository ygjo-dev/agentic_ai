"""대상 : ontology/graph.py — recipe_nodes()

recipe_nodes() 검증. recipes/<id>.yaml 의 step 순서대로 노드 id 를 돌려준다.
"""

from ontology.graph import recipe_nodes


def test_three_step_recipe_returns_nodes_in_order():
    """recipe_010 : 승강장 CCTV -> 혼잡도 분석 -> Word 생성."""
    assert recipe_nodes("recipe_010") == [
        "load_cctv_platform",
        "analyze_congestion",
        "generate_word",
    ]


def test_one_step_recipe_returns_single_node():
    assert recipe_nodes("recipe_001") == ["load_cctv_platform"]


def test_unknown_recipe_returns_empty_list():
    """파일이 없으면 예외 대신 빈 리스트. 화면이 죽지 않아야 한다."""
    assert recipe_nodes("recipe_999") == []
