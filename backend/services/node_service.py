"""노드 등록 / 초기화. registry 호출 → DTO."""

from backend.services import graph_service
from ontology.graph import dotted_edges, load_ontology, solid_edges
from ontology.registry import register_node, reset_to_init


def register(form: dict, llm_client) -> dict:
    """노드를 등록하고 그로 인해 무엇이 늘었는지까지 돌려준다.

    llm_client 를 인자로 받는 이유는 resolve_service 와 같다.

    new_solid_edges / new_dotted_edges 는 등록 직전과 직후의 차집합이다.
    registry 가 알려주지 않으므로 앞뒤로 한 번씩 조회해 직접 계산한다.
    """
    before_solid = set(solid_edges())
    before_dotted = set(dotted_edges())
    before_nodes = len(load_ontology()["nodes"])
    before_recipes = len(graph_service.recipe_ids())

    result = register_node(form, llm_client=llm_client)

    after_solid = solid_edges()
    after_dotted = dotted_edges()
    nodes = load_ontology()["nodes"]

    return {
        "node_id": result["node_id"],
        "node": result["node"],
        "properties": result["properties"],
        "reason": result["reason"],
        "recipe_ids": result["recipe_ids"],
        # registry 의 chains 도 같은 내용이지만 모양이 다르다. /graph · /resolve 와
        # 원소 모양을 맞춰 프론트엔드 어댑터가 하나로 끝나게 한다.
        "paths": graph_service.paths_for(result["recipe_ids"], nodes),
        "new_solid_edges": [
            {"from": frm, "to": to, "interface": interface}
            for (frm, to), interface in after_solid.items()
            if (frm, to) not in before_solid
        ],
        "new_dotted_edges": [
            {"a": a, "b": b, "labels": labels}
            for (a, b), labels in after_dotted.items()
            if (a, b) not in before_dotted
        ],
        "counts": {
            "nodes": [before_nodes, len(nodes)],
            "recipes": [before_recipes, len(graph_service.recipe_ids())],
        },
        "version": graph_service.ontology_version(),
    }


def reset() -> dict:
    """_init 사본으로 되돌린다."""
    reset_to_init()
    return {"ok": True, "version": graph_service.ontology_version()}
