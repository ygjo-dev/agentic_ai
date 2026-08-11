"""POST /resolve 응답 형식.

기존 4개 key 에 paths 가 더해진다. paths 는 LLM 이 만드는 게 아니라
백엔드 서비스가 결과를 받아 덧붙이는 것이다 — 프론트엔드가 recipe 파일을
직접 읽지 않게 하려는 것.
"""

from pydantic import BaseModel


class PathStepDTO(BaseModel):
    """실행 경로의 한 걸음."""

    node_id: str
    name: str
    out_interface: str | None  # 그 노드의 outputs[0]. 다음으로 흘러가는 인터페이스.


class ResolveResponse(BaseModel):
    status: str  # SELECT / CLARIFY / NO_MATCH
    recipe_id: str | None
    candidate_recipe_ids: list[str]
    reason: str
    paths: dict[str, list[PathStepDTO]]  # NO_MATCH 면 빈 객체.
