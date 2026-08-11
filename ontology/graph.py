"""온톨로지 그래프 계산.

순수 함수만 둔다. Streamlit 도 DOT 문법도 모른다 — 그리는 방법은
demo/graph_svg/ 가 안다.

온톨로지는 store 에게 묻는다. 이 파일은 ontology.yaml 을 직접 열지 않는다 —
저장소가 그래프DB 로 바뀌어도 여기는 그대로여야 하기 때문이다.
recipe 는 아직 store 가 맡는 자산이 아니라 여기서 직접 읽는다.
"""

import yaml

import paths
from ontology import store


def load_ontology() -> dict:
    """ontology.yaml 원문을 dict 로 돌려준다."""
    return store.read()


def recipe_nodes(recipe_id: str) -> list[str]:
    """recipes/<recipe_id>.yaml 에서 노드 id 를 step 순서 그대로 읽는다."""
    recipe_path = paths.RECIPES_DIR / f"{recipe_id}.yaml"
    if not recipe_path.exists():
        return []
    data = yaml.safe_load(recipe_path.read_text(encoding="utf-8"))
    return [step["node"] for step in data.get("steps", [])]


def solid_edges() -> dict[tuple[str, str], str]:
    """recipe 에 실제로 존재하는 연속 step 쌍. {(from, to): 인터페이스}.

    같은 쌍이 여러 recipe 에 나와도 한 번만 담는다.
    """
    nodes = store.nodes()
    edges: dict[tuple[str, str], str] = {}

    for recipe_path in sorted(paths.RECIPES_DIR.glob("*.yaml")):
        chain = recipe_nodes(recipe_path.stem)
        for frm, to in zip(chain, chain[1:]):
            shared = set(nodes[frm]["outputs"]) & set(nodes[to]["inputs"])
            edges[(frm, to)] = sorted(shared)[0]

    return edges


def dotted_edges() -> dict[tuple[str, str], list[str]]:
    """같은 properties 항목을 공유하는 노드 쌍. {(a, b): ["source: cctv", ...]}.

    방향이 없으므로 쌍은 정렬해서 한 번만 담는다.
    """
    nodes = store.nodes()
    edges: dict[tuple[str, str], list[str]] = {}

    node_ids = sorted(nodes)
    for index, a in enumerate(node_ids):
        for b in node_ids[index + 1 :]:
            a_props = nodes[a].get("properties") or {}
            b_props = nodes[b].get("properties") or {}

            shared = [
                f"{key}: {value}"
                for key, value in sorted(a_props.items())
                if key in b_props and b_props[key] == value
            ]
            if shared:
                edges[(a, b)] = shared

    return edges


def highlight_edges(recipe_id: str) -> list[tuple[str, str]]:
    """선택된 recipe 의 실행 경로. [(from, to), ...] 순서 그대로.

    집합이 아니라 리스트다 — 순번 라벨을 붙여야 하고, recipe 에 루프가
    생겨 같은 엣지를 두 번 지날 때 그것을 뭉개면 안 된다.
    """
    chain = recipe_nodes(recipe_id)
    return list(zip(chain, chain[1:]))
