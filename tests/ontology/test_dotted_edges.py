"""대상 : ontology/graph.py — dotted_edges()

dotted_edges() 검증. properties 의 같은 key: value 를 공유하는 노드 쌍.
"""

from ontology.graph import dotted_edges, load_ontology


def test_same_subject_links_nodes_of_different_kinds():
    """subject 를 key 하나로 둔 이유가 이것이다.

    불러오기(load_track_image)와 분석(detect_track_crack)은 종류가 다르지만
    같은 대상을 다룬다. 예전에는 불러오기가 site, 분석이 target 을 써서
    같은 대상인데도 이어지지 않았다.
    """
    edges = dotted_edges()

    assert "subject: 궤도" in edges[("detect_track_crack", "load_track_image")]


def test_a_subject_group_is_linked_pairwise():
    """기상 세 노드가 서로 다 이어져야 한 덩어리로 보인다."""
    edges = dotted_edges()
    weather = ["analyze_icing_risk", "analyze_wind_risk", "load_weather_sensor"]

    for index, a in enumerate(weather):
        for b in weather[index + 1 :]:
            assert "subject: 기상" in edges[(a, b)], (a, b)


def test_differing_value_is_not_a_shared_property():
    """analyze_congestion 은 subject: 승강장, detect_track_crack 은 subject: 궤도 다.

    key 만 같고 value 가 다르면 '같은 것을 다룬다' 가 아니다.
    """
    edges = dotted_edges()

    assert ("analyze_congestion", "detect_track_crack") not in edges
    assert ("detect_track_crack", "analyze_congestion") not in edges


def test_label_is_key_colon_value():
    """value 만 쓰면 무엇을 공유하는지 화면에서 알 수 없다."""
    for labels in dotted_edges().values():
        for label in labels:
            assert ": " in label, label
            key, _, value = label.partition(": ")
            assert key and value


def test_node_without_properties_never_appears():
    nodes = load_ontology()["nodes"]
    bare = {node_id for node_id, node in nodes.items() if not node.get("properties")}

    appearing = {node_id for pair in dotted_edges() for node_id in pair}

    assert not (bare & appearing), f"properties 없는 노드가 점선에 나타났다: {bare & appearing}"


def test_pair_is_stored_once_in_sorted_order():
    """점선은 방향이 없다. (a, b) 와 (b, a) 를 둘 다 담으면 선이 겹쳐 그려진다."""
    edges = dotted_edges()

    for pair in edges:
        assert list(pair) == sorted(pair), f"정렬되지 않은 쌍: {pair}"
        assert (pair[1], pair[0]) not in edges, f"양방향 중복: {pair}"


def test_no_self_loop():
    assert not [pair for pair in dotted_edges() if pair[0] == pair[1]]
