"""해석된 경로를 다루는 순수 함수.

무엇을 강조하고 무엇을 클릭할 수 있는지 정한다. Streamlit 도 Graphviz 도
모른다 — 그래야 런타임 없이 검증할 수 있다.

클릭 의미론 : 노드를 누르면 **그 노드로 끝나는** recipe 만 남는다.
그 노드를 지나는 recipe 를 남기는 것이 아니다. 후보가 여럿일 때 갈라지는
지점은 대개 "어디까지 하느냐" 이므로, 끝점으로 좁히는 편이 분기를 잘 드러낸다.
`승강장 혼잡도 분석` 을 누르면 분석까지만, `Word 생성` 을 누르면 문서까지인
경로가 남는다.
"""


def step_ids(steps: list[dict]) -> list[str]:
    """경로에서 노드 id 만 순서대로."""
    return [step["node_id"] for step in steps or []]


def path_edges(steps: list[dict]) -> list[tuple[str, str]]:
    """경로를 인접 쌍으로. 순번을 붙여야 하므로 집합이 아니라 리스트다."""
    ids = step_ids(steps)
    return list(zip(ids, ids[1:]))


def last_node(steps: list[dict]) -> str | None:
    """경로의 마지막 노드. 빈 경로면 None."""
    ids = step_ids(steps)
    return ids[-1] if ids else None


def ordered_recipe_ids(result: dict | None) -> list[str]:
    """그릴 recipe 순서. recipe_id 가 후보에도 있으면 한 번만."""
    if not result:
        return []

    wanted = [
        recipe_id
        for recipe_id in [
            result.get("recipe_id"),
            *(result.get("candidate_recipe_ids") or []),
        ]
        if recipe_id
    ]
    return list(dict.fromkeys(wanted))


def last_nodes(paths: dict, recipe_ids: list[str]) -> list[str]:
    """후보들의 마지막 노드. 중복은 접고 순서는 recipe 순서를 따른다.

    이것이 클릭할 수 있는 노드의 전부다. 마지막이 아닌 노드를 누르면 남는
    recipe 가 0개가 되어 화면이 비어버리므로 클릭 대상에서 뺀다.
    """
    found = []
    for recipe_id in recipe_ids:
        node_id = last_node((paths or {}).get(recipe_id) or [])
        if node_id and node_id not in found:
            found.append(node_id)
    return found


def recipes_ending_at(paths: dict, recipe_ids: list[str], node_id: str) -> list[str]:
    """그 노드로 끝나는 recipe 만. 순서는 그대로."""
    return [
        recipe_id
        for recipe_id in recipe_ids
        if last_node((paths or {}).get(recipe_id) or []) == node_id
    ]


def focus_variants(paths: dict, recipe_ids: list[str]) -> dict[str, list[str]]:
    """보여줄 조합들. {"": 전체} + {마지막노드: 그것으로 끝나는 recipe}.

    변형 개수는 1 + 서로 다른 마지막 노드 수다. 보통 2~4벌이라 미리 다 만들어도 싸다.
    """
    variants = {"": list(recipe_ids)}
    for node_id in last_nodes(paths, recipe_ids):
        variants[node_id] = recipes_ending_at(paths, recipe_ids, node_id)
    return variants


def edges_of(paths: dict, recipe_ids: list[str]) -> list[list[tuple[str, str]]]:
    """recipe 들의 경로를 build_dot 이 받는 형태로."""
    return [path_edges((paths or {}).get(recipe_id) or []) for recipe_id in recipe_ids]


def nodes_of(paths: dict, recipe_ids: list[str]) -> set[str]:
    """recipe 들이 지나는 모든 노드.

    1단 recipe 는 엣지가 없어 엣지에서 유도할 수 없으므로 따로 모은다.
    """
    return {
        node_id
        for recipe_id in recipe_ids
        for node_id in step_ids((paths or {}).get(recipe_id) or [])
    }
