"""GET /graph 응답 형식.

문서화용이다. 핸들러에는 response_model 로 걸지 않는다 —
FastAPI 가 응답을 모델로 재구성하면서 nodes / properties 같은 자유형 dict 의
순서가 흔들릴 수 있고, 노드와 엣지 순서는 Graphviz 레이아웃을 정하므로
흔들리면 화면이 깜빡인다.
"""

from pydantic import BaseModel


class NodeDTO(BaseModel):
    name: str
    description: str
    inputs: list[str]
    outputs: list[str]
    properties: dict[str, str]


class SolidEdgeDTO(BaseModel):
    """recipe 에 실제로 있는 연속 step 쌍."""

    # from 은 파이썬 예약어라 필드명으로 쓸 수 없다. API 는 "from" 그대로 나간다.
    from_: str
    to: str
    interface: str

    model_config = {"populate_by_name": True}


class DottedEdgeDTO(BaseModel):
    """같은 properties 항목을 공유하는 노드 쌍. 방향이 없다."""

    a: str
    b: str
    labels: list[str]


class GraphResponse(BaseModel):
    version: str  # ontology.yaml + recipes/*.yaml 내용 해시. 프론트엔드 캐시 키다.
    interfaces: list[str]
    nodes: dict[str, NodeDTO]
    solid_edges: list[SolidEdgeDTO]
    dotted_edges: list[DottedEdgeDTO]
    # stages 는 없다. 열 정렬(rank=same)을 그만두고 neato 배치로 갔다.
    # ontology.graph.node_stages() 는 도메인 계산으로 남아 있지만 API 는 쓰지 않는다.
