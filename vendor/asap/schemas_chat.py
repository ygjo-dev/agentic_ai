"""원본 app/schemas/chat.py 에서 command_renderer 가 쓰는 것만 옮겼다.

원본 파일에는 ChatRequest · ChatResponse 도 있으나 vendor 안에서 쓰이지 않는다.
우리 요청 모델은 demo/api/schemas/requests.py 에 따로 있다.
"""

from typing import Any, Dict

from pydantic import BaseModel


class Command(BaseModel):
    """지도 조작 명령"""
    op: str
    args: Dict[str, Any]
