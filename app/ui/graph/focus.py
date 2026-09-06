"""해석된 경로를 다루는 순수 함수.

무엇을 강조하고, 칩에 어떤 이름이 실리는지 정한다. Streamlit 도 Graphviz 도
모른다 — 그래야 런타임 없이 검증할 수 있다.

★ **2026-09-06 에 「끝노드로 좁히기」 여섯을 걷었다.** SVG 판은 변형 키가
경로의 마지막 노드였고, 노드를 누르면 그 노드로 끝나는 recipe 만 남았다.
그런데 후보가 마지막 노드를 함께 쓰면(인구 둘이 그렇다) 좁힌 것이 전체와
똑같아져 고를 뜻이 없어졌다. **지금 변형 키는 recipe id 하나씩**이고 그 표는
build.network_payload 가 만든다 — 여기서 마지막 노드를 셀 자리가 없어졌다.
"""


def step_ids(steps: list[dict]) -> list[str]:
    """경로에서 노드 id 만 순서대로."""
    return [step["node_id"] for step in steps or []]


def path_edges(steps: list[dict]) -> list[tuple[str, str]]:
    """경로를 인접 쌍으로.

    출력  (from, to) 목록
    제약  집합으로 만들지 않는다. 순서가 곧 실행 순서임
    """
    ids = step_ids(steps)
    return list(zip(ids, ids[1:]))


def edges_of(paths: dict, recipe_ids: list[str]) -> list[list[tuple[str, str]]]:
    """recipe 들의 경로를 엣지 목록의 목록으로."""
    return [path_edges((paths or {}).get(recipe_id) or []) for recipe_id in recipe_ids]


def nodes_of(paths: dict, recipe_ids: list[str]) -> set[str]:
    """recipe 들이 지나는 모든 노드.

    출력  노드 id 집합
    규칙  1단 recipe 는 엣지가 없어 엣지에서 유도할 수 없으므로 따로 모음
    """
    return {
        node_id
        for recipe_id in recipe_ids
        for node_id in step_ids((paths or {}).get(recipe_id) or [])
    }


def chain_names(steps: list[dict]) -> list[str]:
    """경로 하나를 화면에 적을 이름 사슬로.

    출력  이름 목록. id 가 아니라 사람이 읽는 이름
    규칙  이름이 없으면 id 로 떨어짐. 시연 중에 빈 칩이 뜨는 것보다 나음
    """
    return [
        str(step.get("name") or step.get("node_id", ""))
        for step in steps or []
    ]


def chips_of(paths: dict, recipe_ids: list[str]) -> list[list[str]]:
    """recipe 여럿을 이름 사슬 목록으로. UI 는 받아 칩으로 그리기만 함.

    제약  차례를 다시 매기지 않는다.
          받은 recipe 차례가 곧 목록 줄 차례이고, 그것이 network 의 변형
          차례와 같아야 목록에서 고른 줄과 그래프가 같은 후보를 가리킴
    """
    return [
        chain_names((paths or {}).get(recipe_id) or [])
        for recipe_id in recipe_ids
    ]
