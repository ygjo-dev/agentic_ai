"""node_stages() 검증. 같은 열에 놓을 노드 묶음을 단계 순서대로 돌려준다."""

from ontology.graph import load_ontology, node_stages, solid_edges


def test_returns_three_stages_in_order():
    """불러오기 -> 분석 -> 산출. rankdir=LR 이므로 순서가 곧 열 순서다."""
    stages = node_stages()

    assert len(stages) == 3


def test_first_stage_is_the_loaders():
    """inputs 가 빈 노드가 시작 단계다."""
    nodes = load_ontology()["nodes"]
    expected = sorted(nid for nid, n in nodes.items() if n["inputs"] == [])

    assert sorted(node_stages()[0]) == expected
    assert len(expected) == 3


def test_last_stage_is_the_generators():
    """어떤 recipe 에서도 뒤로 이어지지 않는 노드가 종료 단계다."""
    assert sorted(node_stages()[-1]) == ["generate_ppt", "generate_word"]


def test_middle_stage_is_the_analyzers():
    assert sorted(node_stages()[1]) == [
        "analyze_congestion",
        "analyze_incident_frequency",
        "detect_structure_crack",
        "summarize_defect_history",
    ]


def test_every_node_appears_exactly_once():
    """어느 단계에도 못 들어간 노드가 있으면 그 노드만 따로 떨어져 그려진다."""
    stages = node_stages()
    flat = [node_id for stage in stages for node_id in stage]

    assert sorted(flat) == sorted(load_ontology()["nodes"])
    assert len(flat) == len(set(flat)), "같은 노드가 두 단계에 들어갔다."


def test_no_stage_is_empty():
    """빈 단계는 rank=same 블록을 비게 만든다."""
    assert all(stage for stage in node_stages())


def test_solid_edges_always_go_forward():
    """엣지가 뒤 단계에서 앞 단계로 가면 열 정렬이 의미를 잃는다."""
    stage_of = {
        node_id: index
        for index, stage in enumerate(node_stages())
        for node_id in stage
    }

    for frm, to in solid_edges():
        assert stage_of[frm] < stage_of[to], f"{frm}({stage_of[frm]}) -> {to}({stage_of[to]})"


def test_returns_plain_data_only():
    """DOT 문법이나 색이 섞이면 렌더링 방식을 바꿀 때 같이 고쳐야 한다."""
    stages = node_stages()

    assert isinstance(stages, list)
    for stage in stages:
        assert isinstance(stage, list)
        assert all(isinstance(node_id, str) for node_id in stage)
