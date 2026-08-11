"""POST /nodes 요청 / 응답 형식.

요청(NodeRegisterRequest)은 실제로 본문 검증에 쓴다.
응답은 문서화용이다 — graph.py 와 같은 이유로 response_model 로 걸지 않는다.
"""

from pydantic import BaseModel, Field

from backend.schemas.graph import DottedEdgeDTO, NodeDTO, SolidEdgeDTO
from backend.schemas.resolve import PathStepDTO


class NodeRegisterRequest(BaseModel):
    """사람이 폼에 적는 것. node_id 와 properties 는 LLM 이 정한다.

    이름 · 설명 · outputs 가 비면 등록을 시작하지 않는다. 예전에는 프론트엔드가
    이 검사를 했지만, 계산을 백엔드로 옮겼으므로 검증도 여기 있어야 한다.
    빈 이름으로 등록되면 그래프에 이름 없는 노드가 남는다.
    """

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    inputs: list[str] = []  # 불러오기 노드는 입력이 없다. 비어도 된다.
    outputs: list[str] = Field(min_length=1)


class NodeCounts(BaseModel):
    """[등록 전, 등록 후]."""

    nodes: list[int]
    recipes: list[int]


class NodeRegisterResponse(BaseModel):
    node_id: str
    node: NodeDTO
    properties: dict[str, str]
    reason: str
    recipe_ids: list[str]
    paths: dict[str, list[PathStepDTO]]
    # 등록 직전과 직후의 차집합. 이번 작업에서 프론트엔드는 쓰지 않는다 —
    # 계약을 확정해두는 것이 목적이고, 다음 작업에서 쓴다.
    new_solid_edges: list[SolidEdgeDTO]
    new_dotted_edges: list[DottedEdgeDTO]
    counts: NodeCounts
    version: str
