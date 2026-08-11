"""대상 : ontology/graph.py — 온톨로지에서 그래프를 계산한다

노드는 kind 로 갈린다. **function** 은 실행할 수 있는 것, **group** 은 기능이
다루는 대상 개념(승강장 · 궤도 · 기상)이다.

관계는 두 종류이고 원천이 다르다.
  실선 — recipe 에 실제로 이어져 있는 노드 쌍. "이렇게 실행할 수 있다"
  점선 — 온톨로지 edges 에 적힌 관계. "이 기능은 이 대상을 다룬다"

**실선을 edges 에 적지 않는 이유** : 두 곳에 적으면 진실의 원천이 둘이 되고,
어긋났을 때 어느 쪽이 맞는지 알 수 없다. 실행 순서는 recipe 가 정한다.
"""

import paths
from ontology.graph import (
    dotted_edges,
    highlight_edges,
    load_ontology,
    recipe_nodes,
    solid_edges,
)


def recipe_ids() -> list[str]:
    return sorted(path.stem for path in paths.RECIPES_DIR.glob("recipe_*.yaml"))


def test_a_node_is_either_a_function_or_a_group():
    """노드는 평평하게 두고 kind 로 가른다. 중첩 구조는 노드 id 중복을
    YAML 이 잡아주지 못한다.

    **group 은 inputs / outputs 가 없다.** 실행 대상이 아니라서 "비어 있는 것"
    과 "없는 것" 의 뜻이 다르다 — 빈 리스트로 적으면 "입력이 없는 기능" 으로
    읽혀 recipe 시작점이 되어버린다.
    """
    ontology = load_ontology()

    assert set(ontology) >= {"interfaces", "nodes", "edges"}
    assert ontology["nodes"] and ontology["interfaces"]

    interfaces = set(ontology["interfaces"])
    kinds = {node.get("kind") for node in ontology["nodes"].values()}
    assert kinds == {"function", "group"}, kinds

    for node_id, node in ontology["nodes"].items():
        assert set(node) >= {"kind", "name", "description"}, node_id
        assert node["name"] and node["description"], node_id

        if node["kind"] == "group":
            assert "inputs" not in node and "outputs" not in node, node_id
            continue

        assert set(node) >= {"inputs", "outputs"}, node_id
        # 선언되지 않은 인터페이스를 쓰면 엣지 계산이 조용히 빗나간다.
        for name in [*node["inputs"], *node["outputs"]]:
            assert name in interfaces, f"{node_id} 가 모르는 인터페이스를 쓴다: {name}"


def test_nodes_connected_in_a_recipe_become_solid_edges():
    """실선은 "타입이 맞는다" 가 아니라 "recipe 에 실제로 있다" 로 정한다.

    타입만 보면 DocumentData 가 불러오기의 출력이자 생성의 출력이라 순환이
    생긴다. recipe 를 근거로 삼으면 실행 가능한 연결만 남는다.

    라벨은 앞 노드의 outputs 와 뒤 노드의 inputs 가 공유하는 인터페이스다.
    """
    ontology = load_ontology()
    nodes, interfaces = ontology["nodes"], set(ontology["interfaces"])
    edges = solid_edges()

    # recipe 에 있는 인접 쌍이 빠짐없이, 그것만 들어간다.
    from_recipes = set()
    for recipe_id in recipe_ids():
        chain = recipe_nodes(recipe_id)
        from_recipes |= set(zip(chain, chain[1:]))
    assert set(edges) == from_recipes

    for (frm, to), label in edges.items():
        assert label in interfaces
        assert label in nodes[frm]["outputs"] and label in nodes[to]["inputs"]

    # 같은 쌍이 여러 recipe 에 나와도 한 번만 담긴다.
    repeated = [
        pair for pair in from_recipes
        if sum(
            pair in set(zip(recipe_nodes(r), recipe_nodes(r)[1:]))
            for r in recipe_ids()
        ) > 1
    ]
    assert repeated, "중복 제거를 검증하려면 두 recipe 에 나오는 쌍이 있어야 한다"
    assert list(edges).count(repeated[0]) == 1


def test_relations_written_in_the_ontology_become_dotted_edges():
    """관계는 edges 에 적혀 있고 읽기만 한다.

    예전에는 기능마다 properties 에 subject: 궤도 를 적고 같은 값을 가진 노드끼리
    코드가 이어줬다. 그건 관계를 노드 속성으로 적는 것이라 "관계는 파일에
    따로 적는다" 는 원칙과 어긋났다. 대상을 노드로 세우니 관계가 한 곳에 드러난다.

    **점선은 방향이 없다.** (a, b) 와 (b, a) 를 둘 다 담으면 선이 겹쳐 그려지므로
    쌍을 정렬해 한 번만 담는다. 라벨은 관계 이름(type)이다.
    """
    ontology = load_ontology()
    nodes, written = ontology["nodes"], ontology["edges"]
    edges = dotted_edges()

    assert written, "edges 가 비면 이 검사가 무력하다"
    assert len(edges) == len(written)

    for pair, labels in edges.items():
        assert list(pair) == sorted(pair), f"정렬되지 않은 쌍: {pair}"
        assert (pair[1], pair[0]) not in edges, f"양방향 중복: {pair}"
        assert pair[0] != pair[1]
        assert labels and all(labels), pair

    # 적힌 관계가 빠짐없이, 그것만 나온다.
    for edge in written:
        pair = tuple(sorted((edge["from"], edge["to"])))
        assert pair in edges, edge
        assert edge["type"] in edges[pair], edge
        # 관계는 기능 -> 대상이다. 양끝이 실재해야 한다.
        assert nodes[edge["to"]]["kind"] == "group", edge
        assert nodes[edge["from"]]["kind"] == "function", edge

    # 어느 대상에도 안 적힌 기능은 아무와도 안 이어진다.
    attached = {node_id for pair in edges for node_id in pair}
    for node_id, node in nodes.items():
        if node["kind"] == "function" and node_id not in attached:
            assert not [p for p in edges if node_id in p], node_id


def test_a_recipe_becomes_an_ordered_path():
    """실행 경로는 집합이 아니라 리스트다.

    순번 라벨(1, 2, 3)을 붙이려면 순서가 남아야 하고, recipe 에 루프가 생겨
    같은 엣지를 두 번 지날 때 집합은 그것을 하나로 뭉개버린다.
    """
    nodes = load_ontology()["nodes"]

    for recipe_id in recipe_ids():
        chain = recipe_nodes(recipe_id)
        edges = highlight_edges(recipe_id)

        assert isinstance(edges, list)
        assert edges == list(zip(chain, chain[1:]))
        assert len(edges) == max(len(chain) - 1, 0)

        # group 은 실행할 수 없다. 섞이면 inputs 가 없어 계산이 터진다.
        for node_id in chain:
            assert nodes[node_id]["kind"] == "function", (recipe_id, node_id)

        # 불러오기로 시작해 타입이 이어진다. 뒤집히면 경로가 거꾸로 그려진다.
        assert nodes[chain[0]]["inputs"] == [], recipe_id
        for frm, to in edges:
            assert set(nodes[frm]["outputs"]) & set(nodes[to]["inputs"]), (frm, to)


def test_an_unknown_recipe_is_empty_not_an_error():
    """파일이 없으면 예외 대신 빈 결과다. 화면이 죽는 것보다 낫다."""
    assert recipe_nodes("recipe_999") == []
    assert highlight_edges("recipe_999") == []
