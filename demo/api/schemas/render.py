"""POST /render 요청 형식.

응답 모델은 두지 않는다 — SVG 문자열과 자유형 dict 라 모델로 재구성하면
순서만 흔들리고 얻는 게 없다. 실제 형태는 render_service 가 만든다.
"""

from pydantic import BaseModel


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
