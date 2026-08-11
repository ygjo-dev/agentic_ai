"""온톨로지를 읽어 API 응답 형태로 옮긴다.

**demo/ 안에서 온톨로지를 읽는 유일한 지점이다.** 다른 서비스는 여기를 거친다 —
그래프DB 로 바뀔 때 고칠 곳이 하나여야 하기 때문이다.

이름이 graph_service 였는데 graph_svg 와 "graph" 의 뜻이 달라 헷갈렸다.
여기의 graph 는 노드와 관계라는 **데이터**이고, graph_svg 의 graph 는 **그림**이다.
실제로 그 혼동 때문에 두 모듈이 비슷한 계층인 줄 알고 역방향 import 가 생겼었다.

색만은 graph_svg 에게 묻는다. 그리는 쪽이 팔레트의 주인이고, 화면은 그래프 SVG 와
같은 색으로 칩과 배지를 칠해야 한다 — 출처가 둘이면 조용히 어긋난다.

도메인 코드를 옮기거나 고치지 않는다 — 호출만 한다.
"""

import hashlib

import paths
from demo.graph_svg.dot import COLORS
from ontology import store
from ontology.graph import (
    dotted_edges,
    load_ontology,
    recipe_nodes,
    solid_edges,
)


def ontology_version() -> str:
    """ontology.yaml + recipes/*.yaml 내용의 sha1.

    mtime 이 아니라 내용으로 계산한다 — reset_to_init 은 파일을 복사하므로
    내용이 같아도 mtime 이 바뀐다. 그러면 프론트엔드 SVG 캐시가 헛돌고
    그래프가 깜빡인다.

    파일명도 해시에 넣는다. 내용이 같은 recipe 가 다른 번호로 늘어나는 경우를
    내용만으로는 구분할 수 없다.
    """
    digest = hashlib.sha1()
    digest.update(store.raw_bytes())

    for recipe_path in sorted(paths.RECIPES_DIR.glob("*.yaml")):
        digest.update(recipe_path.name.encode("utf-8"))
        digest.update(recipe_path.read_bytes())

    return digest.hexdigest()


def recipe_ids() -> list[str]:
    """지금 있는 recipe id 전부. 번호 순."""
    return sorted(path.stem for path in paths.RECIPES_DIR.glob("recipe_*.yaml"))


def path_of(recipe_id: str, nodes: dict | None = None) -> list[dict]:
    """recipe 한 벌의 실행 경로. [{node_id, name, out_interface}, ...] 순서 그대로.

    out_interface 는 그 노드의 outputs[0] — 다음 노드로 흘러가는 인터페이스다.
    outputs 가 비면 None 이다.

    없는 recipe 는 빈 리스트다. recipe_nodes 가 그렇게 동작하므로 그대로 따른다.
    """
    nodes = load_ontology()["nodes"] if nodes is None else nodes

    chain = []
    for node_id in recipe_nodes(recipe_id):
        node = nodes.get(node_id) or {}
        outputs = node.get("outputs") or []
        chain.append(
            {
                "node_id": node_id,
                "name": node.get("name", node_id),
                "out_interface": outputs[0] if outputs else None,
            }
        )
    return chain


def paths_for(ids, nodes: dict | None = None) -> dict[str, list[dict]]:
    """recipe id 여럿의 경로를 한 번에. 중복은 접고 순서는 유지한다."""
    nodes = load_ontology()["nodes"] if nodes is None else nodes
    return {recipe_id: path_of(recipe_id, nodes) for recipe_id in dict.fromkeys(ids)}


def domain_graph() -> tuple[dict, dict, dict]:
    """그리기가 쓰는 도메인 형태 그대로. (nodes, solid, dotted)

    solid / dotted 는 튜플 키 dict 다. JSON 은 튜플 키를 못 담아 graph_payload 는
    리스트로 펴는데, 서버 안에서 그릴 때는 펼 이유가 없다 — 예전에는 프론트엔드가
    받아서 다시 튜플로 되돌렸다(to_build_dot_args). 그 왕복이 사라졌다.

    온톨로지를 읽는 곳은 이 모듈 하나다. graph_svg 는 여기서 받아 쓰기만 한다.
    """
    return load_ontology()["nodes"], solid_edges(), dotted_edges()


def graph_payload() -> dict:
    """그래프 한 벌 전체. 프론트엔드가 그리는 데 필요한 것만 담는다.

    엣지는 객체(dict)가 아니라 순서 있는 리스트로 담는다. JSON 은 튜플 키를
    못 담기도 하지만, 그보다 순서가 중요하다 — 노드와 엣지가 나오는 순서가
    Graphviz 레이아웃을 정하므로 왕복에서 순서가 흔들리면 좌표가 바뀐다.
    """
    ontology = load_ontology()
    nodes = ontology["nodes"]

    return {
        "version": ontology_version(),
        # 색은 graph_svg 가 정한다. UI 가 자기 팔레트를 따로 들면 두 곳이
        # 조용히 어긋나고, 그때 사람은 화면을 보고 코드를 의심한다.
        "colors": dict(COLORS),
        # interfaces 는 {이름: {description}} 형태의 dict 다. 이름만 뽑아 순서대로.
        "interfaces": list(ontology["interfaces"]),
        "nodes": {
            node_id: {
                "name": node["name"],
                "description": node["description"],
                "inputs": node["inputs"],
                "outputs": node["outputs"],
                "properties": node.get("properties") or {},
            }
            for node_id, node in nodes.items()
        },
        "solid_edges": [
            {"from": frm, "to": to, "interface": interface}
            for (frm, to), interface in solid_edges().items()
        ],
        "dotted_edges": [
            {"a": a, "b": b, "labels": labels}
            for (a, b), labels in dotted_edges().items()
        ],
    }
