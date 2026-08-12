"""노드 등록(제안 · 승인) / 초기화. registry 호출 → DTO.

온톨로지는 ontology_service 에게 묻는다. 예전에는 ontology.graph 를 직접
불렀는데, 그러면 "온톨로지를 읽는 유일한 지점" 이라는 ontology_service 의 약속이
깨지고 그래프DB 로 갈 때 고칠 곳이 둘이 된다.

등록은 두 단계다. register(제안)가 노드를 쓰고 대상이 통하는 경로만 조용히
recipe 로 승격하며, 대상이 어긋나는 경로는 pending 으로 돌려준다 — 파일이 없다.
사람이 고른 것을 approve 가 승격한다.
"""

from demo.api.services import ontology_service
from ontology import registry
from ontology.registry import reset_to_init


def _edges():
    """지금의 실선 · 점선. 등록 전후로 한 번씩 불러 차집합을 낸다."""
    _, solid, dotted = ontology_service.domain_graph()
    return solid, dotted


def register(form: dict, llm_client) -> dict:
    """노드를 등록(제안)하고 그로 인해 무엇이 늘었는지까지 돌려준다.

    llm_client 를 인자로 받는 이유는 resolve_service 와 같다.

    new_solid_edges / new_dotted_edges 는 등록 직전과 직후의 차집합이다.
    registry 가 알려주지 않으므로 앞뒤로 한 번씩 조회해 직접 계산한다.

    recipe_ids / paths / counts 는 **승인 전 값**이다 — 자동 승격된 것만 있다.
    승인 후 값은 approve 응답에 담긴다.
    """
    before_solid, before_dotted = _edges()
    before_nodes = len(ontology_service.domain_graph()[0])
    before_recipes = len(ontology_service.recipe_ids())

    result = registry.propose(form, llm_client=llm_client)

    nodes, after_solid, after_dotted = ontology_service.domain_graph()
    accepted = result["accepted"]

    return {
        "node_id": result["node_id"],
        "node": result["node"],
        # 고른 대상(그룹 노드 id)들. **여럿일 수 있다** — 승강장 CCTV 영상이
        # 승강장에도 CCTV 에도 관한 것처럼. 어느 대상에도 안 관하면 빈 목록이다.
        "groups": result["groups"],
        "reason": result["reason"],
        # 자동 승격된 recipe 만이다. 검토 대상은 아직 recipe 가 아니다.
        # accepted.recipe_ids 와 같은 값이지만 이름을 유지한다 — 화면과 /render
        # 의 mark 어댑터가 이 키를 쓰고 있다.
        "recipe_ids": accepted["recipe_ids"],
        # registry 의 chains 도 같은 내용이지만 모양이 다르다. /graph · /resolve 와
        # 원소 모양을 맞춰 프론트엔드 어댑터가 하나로 끝나게 한다.
        "paths": ontology_service.paths_for(accepted["recipe_ids"], nodes),
        "accepted": accepted,
        # 검토 대상. **파일이 없다.** 사람이 고른 chain 들을 /nodes/approve 로
        # 보낸다. steps 는 화면용이다 — about 이 어느 노드에서 어긋나는지 보여준다.
        "pending": [
            {"chain": chain, "steps": ontology_service.chain_steps(chain)}
            for chain in result["pending"]
        ],
        # 실선에 라벨이 없다. 무엇이 오가는지는 경로 안에 노드로 들어 있다.
        "new_solid_edges": [
            {"from": frm, "to": to}
            for frm, to in after_solid
            if (frm, to) not in set(before_solid)
        ],
        "new_dotted_edges": [
            {"a": a, "b": b, "labels": labels}
            for (a, b), labels in after_dotted.items()
            if (a, b) not in before_dotted
        ],
        "counts": {
            "nodes": [before_nodes, len(nodes)],
            "recipes": [before_recipes, len(ontology_service.recipe_ids())],
        },
        "version": ontology_service.ontology_version(),
    }


def approve(chains: list[list[str]]) -> dict:
    """검토 관문 통과. 사람이 고른 경로만 recipe 로 승격한다.

    counts 는 승인 직전과 직후의 값이다 — 화면이 "recipe 9 → 15" 를 갱신한다.
    new_solid_edges 도 승인 전후 차집합이다. 승인으로 처음 생긴 실선만 담긴다.
    제안에 없던 경로는 registry 가 거부한다(UnproposedChain → 422).
    """
    before_solid, _ = _edges()
    before_nodes = len(ontology_service.domain_graph()[0])
    before_recipes = len(ontology_service.recipe_ids())

    result = registry.approve(chains)

    nodes, after_solid, _ = ontology_service.domain_graph()

    return {
        "recipe_ids": result["recipe_ids"],
        "paths": ontology_service.paths_for(result["recipe_ids"], nodes),
        "new_solid_edges": [
            {"from": frm, "to": to}
            for frm, to in after_solid
            if (frm, to) not in set(before_solid)
        ],
        "counts": {
            "nodes": [before_nodes, len(nodes)],
            "recipes": [before_recipes, len(ontology_service.recipe_ids())],
        },
        "version": ontology_service.ontology_version(),
    }


def reset() -> dict:
    """_init 사본으로 되돌린다."""
    reset_to_init()
    return {"ok": True, "version": ontology_service.ontology_version()}
