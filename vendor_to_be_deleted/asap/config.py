"""vendor_to_be_deleted/asap 가 읽는 설정. 원본 app/config.py 자리를 대신한다. **우리 코드다.**

원본은 pydantic BaseSettings 로 40여 개 값을 들고 있었다. vendor 로 가져온
다섯 모듈이 실제로 읽는 것은 아래 셋뿐이라 그것만 둔다.

**GEMINI_API_KEY · GEMINI_MODEL 이 2026-09-06 에 사라졌다.** 그 둘을 읽던
generic_mcp_executor._compose_answer 가 직접 도구 호출 길과 함께 지워졌다.
"""

import endpoints

# 도구 목록 조회에 21.1초 걸렸다(실측, 42개). 원본 기본값 60초로도 되지만
# KRRI_ASAP 쪽 실측 기록이 "20초로는 모자랐고 120초 안에 끝났다" 라 여유를 둔다.
_MCP_TIMEOUT = 120.0

# 도구 목록 캐시 수명. 원본은 30초다. 목록 한 번에 21초가 걸리므로 30초면
# 발화마다 다시 받아온다. 도구가 늘어나는 것은 시연 중에 일어나지 않는다.
_MCP_TOOLS_CACHE_TTL = 600.0


class _Settings:
    """vendor 모듈이 settings.X 로 읽는 값들.

    규칙  GATEWAY_URL 은 읽는 순간 ASAP_GATEWAY_URL 을 봄. import 시점에 안
          읽으므로 Gateway 를 안 부르는 자리는 값이 없어도 뜸
    제약  이 이름을 안 바꾼다.
          mcp_client 가 settings.GATEWAY_URL 로 읽는데 그것은 KRRI_ASAP 원본이라
          리팩터링 대상이 아님. 환경변수 이름만 ASAP_GATEWAY_URL 로 갈림
    """

    MCP_TIMEOUT: float = _MCP_TIMEOUT
    MCP_TOOLS_CACHE_TTL: float = _MCP_TOOLS_CACHE_TTL

    @property
    def GATEWAY_URL(self) -> str:  # noqa: N802 — 원본이 읽는 이름이라 대문자다.
        return endpoints.asap_gateway_url()


settings = _Settings()
