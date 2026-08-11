"""온톨로지 그래프 계산.

순수 함수만 둔다. Streamlit 도 DOT 문법도 모른다 — 그리는 방법은
frontend/components/graph_section.py 가 안다.
"""

import yaml

import paths


def load_ontology() -> dict:
    """ontology.yaml 원문을 dict 로 돌려준다."""
    return yaml.safe_load(paths.ONTOLOGY_PATH.read_text(encoding="utf-8"))


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
    nodes = load_ontology()["nodes"]
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
    nodes = load_ontology()["nodes"]
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


def node_stages() -> list[list[str]]:
    """같은 열에 놓을 노드 묶음. [시작, 중간, 종료] 순서.

    "소비" 는 타입이 겹치는지가 아니라 recipe 에 그 연결이 실제로 있는지로
    본다. DocumentData 는 불러오기의 출력이자 생성의 출력이라
    generate_word -> DocumentData -> summarize_defect_history 처럼
    타입만 보면 순환이 생기고, 그러면 종료 단계가 비어버린다.
    """
    nodes = load_ontology()["nodes"]
    edges = solid_edges()

    consumed = {frm for frm, _ in edges}  # 뒤로 이어지는 노드

    start = sorted(node_id for node_id, node in nodes.items() if node["inputs"] == [])
    end = sorted(node_id for node_id in nodes if node_id not in consumed)
    middle = sorted(set(nodes) - set(start) - set(end))

    return [stage for stage in (start, middle, end) if stage]


def highlight_edges(recipe_id: str) -> list[tuple[str, str]]:
    """선택된 recipe 의 실행 경로. [(from, to), ...] 순서 그대로.

    집합이 아니라 리스트다 — 순번 라벨을 붙여야 하고, recipe 에 루프가
    생겨 같은 엣지를 두 번 지날 때 그것을 뭉개면 안 된다.
    """
    chain = recipe_nodes(recipe_id)
    return list(zip(chain, chain[1:]))
