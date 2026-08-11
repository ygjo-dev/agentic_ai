"""대상 : ontology/graph.py — load_ontology()

load_ontology() 검증. ontology.yaml 원문을 dict 로 읽는다.
"""

from ontology.graph import load_ontology

# 시설 점검(승강장 · 궤도)과 기상 환경 두 도메인이다. 어휘가 안 겹쳐야
# 발화가 조금 모호해도 후보가 다섯씩 쏟아지지 않는다.
NODE_IDS = {
    "load_platform_cctv",
    "extract_frames",
    "load_track_image",
    "load_inspection_doc",
    "analyze_congestion",
    "detect_track_crack",
    "load_weather_sensor",
    "analyze_icing_risk",
    "analyze_wind_risk",
    "generate_word",
    "generate_ppt",
}


def test_load_ontology_has_interfaces_and_nodes():
    ontology = load_ontology()

    assert "interfaces" in ontology
    assert "nodes" in ontology


def test_load_ontology_has_all_nodes():
    nodes = load_ontology()["nodes"]

    assert set(nodes) == NODE_IDS


def test_every_node_has_required_fields():
    """그래프는 name 을 라벨로, inputs/outputs 를 엣지 계산에 쓴다."""
    nodes = load_ontology()["nodes"]

    for node_id, node in nodes.items():
        for field in ("name", "description", "inputs", "outputs"):
            assert field in node, f"{node_id} 에 {field} 가 없다."
