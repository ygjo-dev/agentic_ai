"""노드 등록 / 초기화. registry 호출 → DTO.

온톨로지는 screen_service 에게 묻는다. 예전에는 ontology.graph 를 직접
불렀는데, 그러면 "온톨로지를 읽는 유일한 지점" 이라는 screen_service 의 약속이
깨지고 그래프DB 로 갈 때 고칠 곳이 둘이 된다.

등록은 한 번에 끝난다. 노드와 관계를 쓰고, 대상이 어긋나지 않는 경로만 recipe 와
menu 로 만든다. 어긋나는 경로는 registry 가 버리고 여기까지 오지 않는다.
"""

from app.api.services.streamlit import screen_service
from registration import registry
from registration.registry import reset_to_init


def _edges():
    """지금의 실선 · 점선. 등록 전후로 한 번씩 불러 차집합을 냄."""
    _, solid, dotted = screen_service.domain_graph()
    return solid, dotted


def register(form: dict, llm_client) -> dict:
    """노드를 등록하고 그로 인해 무엇이 늘었는지까지.

    입력  노드 폼 · LLM 클라이언트
    출력  node_id · node · groups · reason · recipe_ids · paths · accepted ·
          new_solid_edges · new_dotted_edges · counts · version
    규칙  new_solid_edges / new_dotted_edges 는 등록 직전과 직후의 차집합.
          registry 가 알려주지 않으므로 앞뒤로 한 번씩 조회해 직접 계산함
    제약  llm_client 를 여기서 import 하지 않는다. 이유는 resolve_service 와 같음
    """
    before_solid, before_dotted = _edges()
    before_nodes = len(screen_service.domain_graph()[0])
    before_recipes = len(screen_service.recipe_ids())

    result = registry.register_node(form, llm_client=llm_client)

    nodes, after_solid, after_dotted = screen_service.domain_graph()

    return {
        "node_id": result["node_id"],
        "node": result["node"],
        # 고른 대상(그룹 노드 id)들. **여럿일 수 있다** — 승강장 CCTV 영상이
        # 승강장에도 CCTV 에도 관한 것처럼. 어느 대상에도 안 관하면 빈 목록이다.
        "groups": result["groups"],
        "reason": result["reason"],
        # 등록으로 만들어진 recipe. 대상이 어긋나 버려진 경로는 여기 없다.
        "recipe_ids": result["recipe_ids"],
        # registry 의 chains 도 같은 내용이지만 모양이 다르다. /screen · /resolve 와
        # 원소 모양을 맞춰 프론트엔드 어댑터가 하나로 끝나게 한다.
        "paths": screen_service.paths_for(result["recipe_ids"], nodes),
        # 경로 전체를 분홍으로 칠하는 데 쓴다. recipe_ids 와 겹쳐 보이지만 용도가
        # 다르다 — recipe_ids 는 칩과 강조 후보를 정하고, chains 는 지나는 엣지를
        # 정한다. 새로 생긴 연결(new_solid_edges)만으로는 이미 있던 연결을 지나는
        # 구간이 빠져 길이 끊겨 보인다.
        "accepted": {"recipe_ids": result["recipe_ids"], "chains": result["chains"]},
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
            "recipes": [before_recipes, len(screen_service.recipe_ids())],
        },
        "version": screen_service.ontology_version(),
    }


def reset() -> dict:
    """_init 사본으로 되돌림."""
    reset_to_init()
    return {"ok": True, "version": screen_service.ontology_version()}
