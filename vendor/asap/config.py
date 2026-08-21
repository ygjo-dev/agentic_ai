"""vendor/asap 가 읽는 설정. 원본 app/config.py 자리를 대신한다. **우리 코드다.**

원본은 pydantic BaseSettings 로 40여 개 값을 들고 있었다. vendor 로 가져온
다섯 모듈이 실제로 읽는 것은 아래 다섯 개뿐이라 그것만 둔다.

GEMINI_API_KEY 를 None 으로 고정한다. 이 값이 켜지면 generic_mcp_executor 의
_compose_answer 가 지워진 google.genai 를 부르게 된다 — 우리는 도구 하나만
부르는 경로(execute_generic_mcp)를 쓰지 않으므로 그 코드는 닿지 않는다.
"""

import os

# 도구 목록 조회에 21.1초 걸렸다(실측, 42개). 원본 기본값 60초로도 되지만
# 저쪽 실측 기록이 "20초로는 모자랐고 120초 안에 끝났다" 라 여유를 둔다.
_MCP_TIMEOUT = 120.0

# 도구 목록 캐시 수명. 원본은 30초다. 목록 한 번에 21초가 걸리므로 30초면
# 발화마다 다시 받아온다. 도구가 늘어나는 것은 시연 중에 일어나지 않는다.
_MCP_TOOLS_CACHE_TTL = 600.0


class _Settings:
    """vendor 모듈이 settings.X 로 읽는 값들.

    규칙  GATEWAY_URL 은 import 시점에 환경변수를 읽음. mcp_client 가
          전역 인스턴스를 만들며 주소를 굳히므로 나중에 읽어봐야 안 쓰임
    """

    GATEWAY_URL: str = os.environ.get("GATEWAY_URL", "http://localhost:3000").rstrip("/")
    MCP_TIMEOUT: float = _MCP_TIMEOUT
    MCP_TOOLS_CACHE_TTL: float = _MCP_TOOLS_CACHE_TTL
    GEMINI_API_KEY = None
    GEMINI_MODEL: str = ""


settings = _Settings()
