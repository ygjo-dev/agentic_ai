"""KRRI_ASAP Gateway 의 도구 목록을 읽는다.

**도구 실행은 여기가 아니다.** vendor_to_be_deleted/asap/mcp_client 가 한다 — 실행기가
그것을 쓰고, 같은 일을 하는 창구가 둘이면 user_context 나 오류 판정이 조용히
갈린다. 여기 남은 것은 목록 조회 하나다. 도구를 늘릴 때 무엇이 있는지 보는 데
쓴다.

**성공 판정을 HTTP 상태로 하지 않는다.** Gateway 전역 핸들러가 모든 오류를
500 + {"error": "Internal Server Error"} 로 덮는다. 대신 본문을 본다.

그래서 실패를 알리는 GatewayError 에 **응답 본문을 그대로 담는다.** 요약하면
시연 중에 원인을 못 찾는다.
"""

import json
import os

import requests

DEFAULT_GATEWAY_URL = "http://localhost:3000"

# 목록 조회 상한. 42개를 모으는 데 21.1초 걸렸다(실측). 20초로는 모자랐다.
CATALOG_TIMEOUT = 120


class GatewayError(RuntimeError):
    """Gateway 호출이 실패했다. 메시지에 응답 본문이 그대로 들어 있다."""


def base_url() -> str:
    """Gateway 주소.

    출력  끝의 / 를 뗀 주소
    규칙  호출할 때마다 환경변수를 읽음. import 시점에 굳히면 .env 를 고치고
          서버를 다시 띄워야 함
    """
    return os.environ.get("GATEWAY_URL", DEFAULT_GATEWAY_URL).rstrip("/")


def _body(response) -> object:
    """응답 본문. JSON 이 아니면 GatewayError.

    출력  파싱한 값. dict 일 수도 list 일 수도 있음
    제약  응답을 요약해서 올리지 않는다. 원문이 원인을 찾는 유일한 근거임
    """
    try:
        return response.json()
    except ValueError as exc:
        raise GatewayError(
            f"JSON 이 아닌 응답 (HTTP {response.status_code}) : {response.text}"
        ) from exc


def fetch_tools() -> list[dict]:
    """Gateway 가 아는 도구 목록.

    출력  [{name, description, inputSchema, serverId, qualifiedName}, ...]
    규칙  실패하면 GatewayError. 본문을 그대로 담음
    """
    url = f"{base_url()}/api/tools"

    try:
        response = requests.get(url, timeout=CATALOG_TIMEOUT)
    except requests.RequestException as exc:
        raise GatewayError(f"Gateway 에 닿지 못했다 ({url}) : {exc}") from exc

    found = _body(response)
    if isinstance(found, dict) and found.get("error"):
        raise GatewayError(f"도구 목록 조회 실패 : {json.dumps(found, ensure_ascii=False)}")
    if not isinstance(found, list):
        raise GatewayError(f"도구 목록이 배열이 아니다 : {json.dumps(found, ensure_ascii=False)}")

    return found
