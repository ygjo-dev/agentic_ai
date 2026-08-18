"""그리기 요청 → SVG 한 벌. graph_svg 를 부르는 얇은 껍데기다.

도메인 데이터는 ontology_service 에서만 가져온다. graph_svg 가 ontology 를 직접
읽으면 저장소가 그래프 DB 로 바뀔 때 고칠 곳이 둘이 된다.

여기서 하는 판단은 하나뿐이다 — 어떤 모드가 어떤 recipe 를 강조하느냐.
"""

from demo.graph_svg import build, layout_store
from demo.api.services import ontology_service

MODES = ("plain", "resolve", "register")


class UnknownRenderMode(ValueError):
    """모르는 render mode 다. 오타가 조용히 plain 으로 떨어지면
    시연 중에 "왜 강조가 안 되지" 를 한참 찾게 된다."""


def render(
    mode: str = "plain",
    recipe_ids: list[str] | None = None,
    mark: dict | None = None,
) -> dict:
    """화면 한 장에 필요한 SVG 와 칩 데이터.

    입력  mode        "plain" 실행 전 · "resolve" 발화 해석 결과 ·
                      "register" 노드 등록 직후
                      캐시 키에만 쓰임. 그림을 다르게 만드는 것은 recipe_ids 와
                      mark 이고, 모드는 같은 후보라도 장면이 다르면 다른 칸에
                      담기게 함
          recipe_ids  강조할 recipe. plain 이면 비어 있음
          mark        POST /nodes 응답(또는 이미 줄어든
                      {nodes, solid, dotted}). register 가 아니면 None
    출력  build.render_payload 한 벌
    규칙  모르는 모드면 UnknownRenderMode. 422 로 나감
    """
    if mode not in MODES:
        raise UnknownRenderMode(
            f"모르는 render mode: {mode!r} (가능: {', '.join(MODES)})"
        )

    nodes, solid, dotted = ontology_service.domain_graph()
    ids = list(recipe_ids or [])

    positions = layout_store.ensure_positions(nodes, solid, dotted)
    reduced = build.mark_from_registration(mark) if mode == "register" else None

    return build.render_payload(
        nodes=nodes,
        solid=solid,
        dotted=dotted,
        positions=positions,
        paths=ontology_service.paths_for(ids, nodes),
        recipe_ids=ids,
        mark=reduced,
        version=ontology_service.ontology_version(),
        layout=layout_store.layout_hash(positions),
        mode=mode,
    )
