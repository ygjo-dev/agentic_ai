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

    이름 · 설명 · outputs 가 비면 등록을 시작하지 않는다. 빈 이름으로 등록되면
    그래프에 이름 없는 노드가 남는다.
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
    """ASAP-orchestrator 계약의 POST /chat/stream 요청 본문.

    KRRI_ASAP 이 8000 번으로 보내던 것을 그대로 받는다.

    **안 읽는 칸은 선언하지 않는다.** pydantic 이 모르는 칸을 조용히 버리므로
    KRRI_ASAP 이 더 보내도 안 깨진다. 반대로 칸을 남겨 두면 그것이 required 로
    굳거나(안 보내는 날 422 가 난다) 「우리가 읽는다」로 읽힌다.
    KRRI_ASAP(ASAP-web useChat)이 실어 보내는 sessionId 와 target_documents 가
    그래서 여기 없다. 둘 다 버려진다.

    context 는 읽지 않고 vendor 참조 범위($context.…)로 넘기기만 한다.
    """

    text: str
    context: dict = {}
