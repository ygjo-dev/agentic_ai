"""dotted_edges() 검증. properties 의 같은 key: value 를 공유하는 노드 쌍."""

from ontology.graph import dotted_edges, load_ontology


def test_same_source_links_the_two_cctv_loaders():
    edges = dotted_edges()

    assert "source: cctv" in edges[("load_cctv_platform", "load_inspection_car_image")]


def test_same_output_kind_links_the_two_generators():
    edges = dotted_edges()

    assert "output_kind: document" in edges[("generate_ppt", "generate_word")]


def test_differing_value_is_not_a_shared_property():
    """generate_word 는 format: word, generate_ppt 는 format: ppt 다.

    key 만 같고 value 가 다르면 '같은 특성' 이 아니다.
    """
    labels = dotted_edges()[("generate_ppt", "generate_word")]

    assert not [label for label in labels if label.startswith("format:")]


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
