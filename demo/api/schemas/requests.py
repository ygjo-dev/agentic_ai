"""요청 본문 형식.

**응답 모델은 두지 않는다.** 문서화용으로 적어두면 실제 응답과 조용히 어긋나고,
그때 사람은 코드가 아니라 문서를 믿는다. 실제 형태는 서비스가 만든다.

FastAPI 의 response_model 로도 걸지 않는다 — 응답을 모델로 재구성하면서
nodes / properties 같은 자유형 dict 의 순서가 흔들릴 수 있고, 노드와 엣지
순서는 Graphviz 레이아웃을 정하므로 흔들리면 화면이 깜빡인다.
"""

from pydantic import BaseModel, Field


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


class RenderRequest(BaseModel):
    """무엇을 강조해 그릴지.

    mode 는 장면 이름이다. 그림을 정하는 것은 recipe_ids 와 mark 이고,
    mode 는 같은 후보라도 장면이 다르면 캐시가 섞이지 않게 한다.
    """

    mode: str = "plain"
    recipe_ids: list[str] = []
    # POST /nodes 응답을 그대로 넘겨도 되고, 이미 줄인 형태여도 된다.
    # 줄이는 일은 서버가 한다 — UI 가 도메인 형태를 알 필요가 없다.
    mark: dict | None = None


class ChatRequest(BaseModel):
    """ASAP-orchestrator 계약의 POST /chat 요청 본문.

    KRRI_ASAP 이 8000 번으로 보내던 것을 그대로 받는다. 안 읽는 필드도
    선언은 해둔다 — 없는 필드가 오면 FastAPI 가 422 를 내고, 저쪽 화면에서는
    연결이 안 된 것과 구분되지 않는다.

    **sessionId 는 읽는다** (2026-08-26). 되묻기를 세션마다 하나 기억해 두고
    다음 발화가 그것을 고른 것인지 가르는 데 쓴다 —
    demo/api/services/clarify_service.py 다. 빈 문자열이면 그 기능을 안 쓴다.
    text 와 sessionId 말고 둘(context · target_documents)은 여전히 안 읽는다.
    """

    text: str
    sessionId: str  # noqa: N815 — 저쪽 계약의 이름이다. 바꾸면 422 가 난다.
    context: dict = {}
    target_documents: list = []
