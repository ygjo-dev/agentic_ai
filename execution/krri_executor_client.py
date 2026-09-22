"""완성된 KRRI native workflow 를 KRRI_ASAP Orchestrator 의 실행 창구로 보낸다. **나르기만 한다.**

    POST <ASAP_ORCHESTRATOR_URL>/workflow/execute
      헤더  X-User-ID · X-User-MCP-Tools      Gateway 가 /chat 에 붙이는 것과 같은 뜻
      본문  {"workflow": …, "user_text": …, "context": …}
      응답  {"status", "answer", "commands", "trace", "errors"}

**여기서 판단하지 않는다.** workflow 를 고치거나 · 서버 · 도구를 짐작하거나 · 참조를
풀거나 · 답을 다시 쓰지 않는다. 그 일은 앞(workflow_materializer)과 뒤(KRRI_ASAP)가 한다.

**못 부르면 KrriExecutorError 하나로 올린다.** 주소가 없거나 · 연결이 안 되거나 · 시간이
넘거나 · HTTP 오류이거나 · 응답 모양이 다르면 전부 그것이다. vendoring 한 실행기로
몰래 돌아가지 않는다 — 돌아가면 KRRI 가 실제로 돌았는지 아무도 모르고 실행 주인이 둘이 된다.
"""

import logging

import httpx

import endpoints

logger = logging.getLogger(__name__)

# 실행 창구 경로. KRRI_ASAP ASAP-orchestrator app/api/routes/workflow.py 에 있다.
EXECUTE_PATH = "/workflow/execute"

# 한 번 부르는 데 기다리는 시간(초).
#
# KRRI 쪽 한 도구 호출 제한이 60초(MCP_TIMEOUT)이고 도구 목록 한 번에 21초가 걸렸다
# (실측, 42개). 여러 단계 · Gemini 답까지 한 요청에 들어가므로 Gateway 의 프록시
# 제한(300초)과 맞춘다.
TIMEOUT_SECONDS = 300.0

# 응답에서 읽는 칸과 그 모양. 하나라도 다르면 받은 것으로 치지 않는다.
RESPONSE_FIELDS = {"status": str, "answer": str, "commands": list, "trace": list, "errors": list}


class KrriExecutorError(RuntimeError):
    """KRRI 실행 창구를 못 불렀거나 알아볼 수 없는 것이 돌아왔다. 실행 결과가 아니다."""


def _headers(user_context: dict) -> dict:
    """우리가 누구인지 · 어느 도구를 부를 수 있는지. KRRI 가 Gateway 권한으로 그대로 넘긴다.

    규칙  /chat 에 Gateway 가 붙이는 X-User-* 와 같은 이름 · 같은 쉼표 구분
    """
    return {
        "X-User-ID": user_context["user_id"],
        "X-User-MCP-Tools": ",".join(user_context["selected_mcp_tool_refs"]),
    }


def _decoded(response: httpx.Response) -> dict:
    """응답 본문을 dict 로. 모양이 다르면 KrriExecutorError."""
    try:
        body = response.json()
    except ValueError as exc:
        raise KrriExecutorError("KRRI 실행 창구 응답이 JSON 이 아니다") from exc
    if not isinstance(body, dict):
        raise KrriExecutorError("KRRI 실행 창구 응답이 object 가 아니다")
    wrong = [name for name, kind in RESPONSE_FIELDS.items() if not isinstance(body.get(name), kind)]
    if wrong:
        raise KrriExecutorError(f"KRRI 실행 창구 응답에 칸이 없거나 모양이 다르다: {', '.join(wrong)}")
    return body


async def execute_workflow(workflow: dict, *, user_text: str, context: dict, user_context: dict) -> dict:
    """workflow 한 벌을 KRRI 에 보내 실행 결과를 받음.

    입력  workflow_materializer 가 만든 workflow 그대로 · 발화 원문 · 화면 문맥 ·
          우리 신원(user_id · selected_mcp_tool_refs)
    출력  KRRI 응답 dict. status · answer · commands · trace · errors
    규칙  workflow 를 바꾸지 않고 본문에 그대로 실음
          HTTP 200 이 아니면 실패. KRRI 가 실행하다 실패한 것은 200 + status=failed 로 옴
    제약  원문 오류(주소 · 응답 본문)는 로그에만 남긴다. 예외 문장에는 싣지 않는다
    """
    try:
        url = endpoints.asap_orchestrator_url() + EXECUTE_PATH
    except endpoints.EndpointError as exc:
        raise KrriExecutorError(str(exc)) from exc

    payload = {"workflow": workflow, "user_text": user_text, "context": context or {}}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=_headers(user_context))
    except httpx.TimeoutException as exc:
        logger.error("KRRI 실행 창구 시간 초과: %s", exc)
        raise KrriExecutorError("KRRI 실행 창구가 제한 시간 안에 답하지 않았다") from exc
    except httpx.HTTPError as exc:
        logger.error("KRRI 실행 창구 연결 실패: %s", exc)
        raise KrriExecutorError("KRRI 실행 창구에 연결하지 못했다") from exc

    if response.status_code != 200:
        logger.error("KRRI 실행 창구 HTTP %s: %s", response.status_code, response.text[:1000])
        raise KrriExecutorError(f"KRRI 실행 창구가 HTTP {response.status_code} 을 돌려줬다")
    return _decoded(response)

