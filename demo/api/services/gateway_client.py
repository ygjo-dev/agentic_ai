"""KRRI_ASAP Gateway 와 통신. 바깥과 맞닿는 유일한 파일.

도메인이 아니다. 온톨로지도 recipe 도 모른다 — 어느 서버의 어느 도구를 무슨
input 으로 부를지는 부르는 쪽(execute_service)이 정한다. 여기는 "그 요청을
Gateway 계약대로 보내고 결과를 돌려준다" 만 안다.

**성공 판정을 HTTP 상태로 하지 않는다.** Gateway 전역 핸들러가 모든 오류를
500 + {"error": "Internal Server Error"} 로 덮는다. 대신 본문을 본다.

    200 + {"error": {...}}   실패
    200 + []                 성공. 결과가 0건일 뿐이다
    200 + {...}              성공

그래서 실패를 알리는 GatewayError 에 **응답 본문을 그대로 담는다.** 요약하면
시연 중에 원인을 못 찾는다.

user_context 는 사실상 필수다. 없으면 요청마다 새 guest 가 만들어지고
adminBoundary 셋 말고는 전부 거부된다.
"""

import json
import os

import requests

DEFAULT_GATEWAY_URL = "http://localhost:3000"

# 우리가 누구인지. 이 값으로 Gateway 가 권한을 찾는다.
USER_ID = "asap-ontology-orchestrator"
TOOL_REFS = ["asap-mcp-core/*"]

# 도구 실행 상한. road.getCctv 가 몇 초 걸린다.
EXECUTE_TIMEOUT = 60
# 목록 조회 상한. 42개를 모으는 데 20초로는 모자랐고 120초 안에 끝났다(실측).
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


def _user_context() -> dict:
    """요청에 실어 보낼 신원.

    출력  user_id 와 selected_mcp_tool_refs
    규칙  빠뜨리면 요청마다 새 guest 가 만들어져 대부분의 도구가 거부됨
    """
    return {"user_id": USER_ID, "selected_mcp_tool_refs": list(TOOL_REFS)}


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


def execute_tool(server_id: str, tool: str, tool_input: dict) -> object:
    """도구 하나를 실행.

    입력  서버 id · 도구 이름 · 도구가 받는 input
    출력  응답 본문 그대로. dict 일 수도 list 일 수도 있음
    규칙  실패하면 GatewayError. 메시지에 본문 원문이 들어감
          본문에 error 가 있으면 HTTP 가 200 이어도 실패임
          본문이 빈 배열이면 성공임. 결과가 0건일 뿐
    제약  응답 형태를 여기서 다듬지 않는다.
          도구마다 다르고, 그것을 아는 곳은 부르는 쪽의 배선표임
    """
    url = f"{base_url()}/api/tools/execute"
    payload = {
        "server_id": server_id,
        "tool": tool,
        "input": tool_input,
        "user_context": _user_context(),
    }

    try:
        response = requests.post(url, json=payload, timeout=EXECUTE_TIMEOUT)
    except requests.RequestException as exc:
        raise GatewayError(f"Gateway 에 닿지 못했다 ({url}) : {exc}") from exc

    found = _body(response)

    if isinstance(found, dict) and found.get("error"):
        raise GatewayError(
            f"{server_id}/{tool} 실패 (HTTP {response.status_code}) : "
            f"{json.dumps(found['error'], ensure_ascii=False)}"
        )
    if response.status_code >= 400:
        raise GatewayError(
            f"{server_id}/{tool} 실패 (HTTP {response.status_code}) : "
            f"{json.dumps(found, ensure_ascii=False)}"
        )

    return found
