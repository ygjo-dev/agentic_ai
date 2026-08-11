"""대상 : ontology/graph.py — 온톨로지에서 그래프를 계산한다

노드 사이의 관계는 파일에 적지 않는다. **읽는 쪽이 계산한다.**
적어두면 노드를 하나 고칠 때 관계까지 손으로 맞춰야 하고, 그러면 조용히 어긋난다.

관계는 두 종류다.
  실선 — recipe 에 실제로 이어져 있는 노드 쌍. "이렇게 실행할 수 있다"
  점선 — 같은 subject 를 가진 노드 쌍. "같은 것을 다룬다"
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


def test_ontology_is_a_flat_map_of_nodes_and_interfaces():
    """노드는 그룹 없이 평평하다. 종류(불러오기·분석·생성) 구분은 적지 않는다.

    inputs/outputs 에서 유도되므로 중복이고, 중첩 구조는 노드 id 중복을
    YAML 이 잡아주지 못한다.
    """
    ontology = load_ontology()

    assert set(ontology) >= {"interfaces", "nodes"}
    assert ontology["nodes"] and ontology["interfaces"]

    interfaces = set(ontology["interfaces"])
    for node_id, node in ontology["nodes"].items():
        assert set(node) >= {"name", "description", "inputs", "outputs"}, node_id
        assert node["name"] and node["description"], node_id
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


def test_nodes_sharing_a_subject_become_dotted_edges():
    """점선은 방향이 없다. (a, b) 와 (b, a) 를 둘 다 담으면 선이 겹쳐 그려진다.

    라벨을 "key: value" 로 두는 이유 : value 만 쓰면 무엇을 공유하는지
    화면에서 알 수 없다.

    같은 subject 를 가진 노드는 종류가 달라도 이어진다 — 그게 key 를 하나로
    둔 이유다. 예전에는 불러오기가 site, 분석이 target 을 써서 같은 대상인데도
    이어지지 않았다.
    """
    nodes = load_ontology()["nodes"]
    edges = dotted_edges()

    def subject(node_id):
        return (nodes[node_id].get("properties") or {}).get("subject")

    for pair, labels in edges.items():
        assert list(pair) == sorted(pair), f"정렬되지 않은 쌍: {pair}"
        assert (pair[1], pair[0]) not in edges, f"양방향 중복: {pair}"
        assert pair[0] != pair[1]
        assert labels and all(": " in label for label in labels)
        # 값이 같아야 이어진다. key 만 같고 값이 다르면 "같은 것" 이 아니다.
        assert subject(pair[0]) == subject(pair[1])

    # 같은 값을 가진 노드는 빠짐없이 서로 이어진다.
    for a, b in ((a, b) for a in nodes for b in nodes if a < b):
        if subject(a) and subject(a) == subject(b):
            assert (a, b) in edges, (a, b)

    # properties 가 없는 노드는 아무와도 안 이어진다.
    bare = {node_id for node_id in nodes if not subject(node_id)}
    assert not (bare & {node_id for pair in edges for node_id in pair})


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

        # 불러오기로 시작해 타입이 이어진다. 뒤집히면 경로가 거꾸로 그려진다.
        assert nodes[chain[0]]["inputs"] == [], recipe_id
        for frm, to in edges:
            assert set(nodes[frm]["outputs"]) & set(nodes[to]["inputs"]), (frm, to)


def test_an_unknown_recipe_is_empty_not_an_error():
    """파일이 없으면 예외 대신 빈 결과다. 화면이 죽는 것보다 낫다."""
    assert recipe_nodes("recipe_999") == []
    assert highlight_edges("recipe_999") == []
