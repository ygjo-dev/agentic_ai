"""대상 : ontology/graph.py — solid_edges()

solid_edges() 검증. recipes/*.yaml 의 연속 step 쌍을 모아 중복을 없앤다.
"""

from ontology.graph import load_ontology, solid_edges


def test_edge_label_is_the_shared_interface():
    """라벨은 앞.outputs 와 뒤.inputs 의 교집합이다."""
    edges = solid_edges()

    assert edges[("load_cctv_platform", "analyze_congestion")] == "MediaData"
    assert edges[("analyze_congestion", "generate_word")] == "AnalysisResult"
    assert edges[("load_inspection_document", "summarize_defect_history")] == "DocumentData"


def test_pair_appearing_in_many_recipes_is_stored_once():
    """load_cctv_platform -> analyze_congestion 은 recipe_005/013/014 에 나온다.

    dict 이므로 키가 하나뿐인 것은 자명하다. 실제로 그 recipe 들이
    존재하는지까지 확인해야 중복 제거를 검증한 것이 된다.
    """
    from ontology.graph import recipe_nodes

    pair = ("load_cctv_platform", "analyze_congestion")
    containing = [
        rid
        for rid in (f"recipe_{n:03d}" for n in range(1, 29))
        if pair in list(zip(recipe_nodes(rid), recipe_nodes(rid)[1:]))
    ]

    assert len(containing) > 1, f"중복 제거를 검증하려면 2개 이상이어야 한다: {containing}"
    assert list(solid_edges()).count(pair) == 1


def test_single_step_recipe_creates_no_edge():
    """1단 recipe 의 노드는 시작점으로만 쓰이고, 그 자체로 엣지를 만들지 않는다."""
    edges = solid_edges()

    assert not any(
        frm == "load_cctv_platform" and to == "load_cctv_platform" for frm, to in edges
    )
    # 불러오기 노드로 들어오는 엣지는 없다 (inputs 가 비어 있으므로).
    load_nodes = {
        node_id
        for node_id, node in load_ontology()["nodes"].items()
        if node["inputs"] == []
    }
    assert not [to for _, to in edges if to in load_nodes]


def test_every_edge_is_backed_by_the_ontology():
    """엣지 양끝이 온톨로지 노드이고, 라벨이 실제 인터페이스여야 한다."""
    ontology = load_ontology()
    nodes, interfaces = ontology["nodes"], set(ontology["interfaces"])

    for (frm, to), label in solid_edges().items():
        assert frm in nodes and to in nodes
        assert label in interfaces
        assert label in nodes[frm]["outputs"]
        assert label in nodes[to]["inputs"]
