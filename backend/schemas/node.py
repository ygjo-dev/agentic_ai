"""POST /nodes 요청 형식.

응답 모델은 두지 않는다. 문서화용으로 적어두면 실제 응답과 조용히 어긋나고,
그때 사람은 코드가 아니라 문서를 믿는다. 실제 형태는 핸들러가 만든다.
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
