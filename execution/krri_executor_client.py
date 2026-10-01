"""완성된 KRRI native workflow 를 KRRI_ASAP Orchestrator 의 실행 창구로 보낸다. **나르기만 한다.**

    POST <ASAP_ORCHESTRATOR_URL>/workflow/execute/stream
      헤더  X-User-*                         Gateway 가 /chat 에 붙이는 것과 같은 이름 · 같은 뜻.
                                             부르는 쪽(workflow_execution)이 고른 것을 그대로 싣는다
      본문  {"workflow": …, "user_text": …, "context": …}
      응답  text/event-stream. data 한 줄에 JSON 하나, 끝은 [DONE]
              {"type": "execution", "status", "commands", "trace", "errors"}  도구 실행이 끝났을 때
              {"type": "answer_delta", "text"}                                 Gemini 최종 답변 조각
              {"type": "result", "status", "answer", "commands", "trace", "errors"}
                                                                               /workflow/execute 응답과 같은 칸

KRRI 는 도구 실행 뒤 Gemini 가 답변을 만드는 동안 조각을 보낸다. **받는 대로 넘긴다** —
본문을 다 읽고 나서 나누지 않는다. 같은 실행을 한 번에 돌려주는 /workflow/execute 도 KRRI 에
그대로 있다(이쪽은 부르지 않는다).

**여기서 판단하지 않는다.** workflow 를 고치거나 · 서버 · 도구를 짐작하거나 · 참조를
풀거나 · 답을 다시 쓰지 않는다. 그 일은 앞(workflow_materializer)과 뒤(KRRI_ASAP)가 한다.

**못 부르면 KrriExecutorError 하나로 올린다.** 주소가 없거나 · 연결이 안 되거나 · 시간이
넘거나 · HTTP 오류이거나 · 이벤트 모양이 다르거나 · result 없이 끝나면 전부 그것이다. 다른
실행기로 몰래 돌아가지 않는다 — 돌아가면 KRRI 가 실제로 돌았는지 아무도 모르고 실행 주인이
둘이 된다.
"""

import json
import logging

import httpx

import endpoints

logger = logging.getLogger(__name__)

# 실행 창구 경로. KRRI_ASAP ASAP-orchestrator app/api/routes/workflow.py 에 있다.
STREAM_PATH = "/workflow/execute/stream"

# 연결 · 읽기 한 번에 기다리는 시간(초). 스트림에서는 다음 조각까지의 시간이다.
#
# KRRI 쪽 한 도구 호출 제한이 60초(MCP_TIMEOUT)이고 도구 목록 한 번에 21초가 걸렸다
# (실측, 42개). 도구 실행이 끝나야 첫 이벤트가 오므로 Gateway 의 프록시 제한(300초)과 맞춘다.
TIMEOUT_SECONDS = 300.0

# 이벤트마다 읽는 칸과 그 모양. 하나라도 다르면 받은 것으로 치지 않는다.
# result 는 /workflow/execute 응답 한 벌과 같은 칸이다.
EVENT_FIELDS = {
    "execution": {"status": str, "commands": list, "trace": list, "errors": list},
    "answer_delta": {"text": str},
    "result": {"status": str, "answer": str, "commands": list, "trace": list, "errors": list},
}


class KrriExecutorError(RuntimeError):
    """KRRI 실행 창구를 못 불렀거나 알아볼 수 없는 것이 돌아왔다. 실행 결과가 아니다."""


def identity_headers(user_context: dict) -> dict:
    """standalone 신원(user_id · selected_mcp_tool_refs)을 KRRI 가 읽는 X-User-* 로.

    규칙  /chat 에 Gateway 가 붙이는 X-User-* 와 같은 이름 · 같은 쉼표 구분
    """
    return {
        "X-User-ID": user_context["user_id"],
        "X-User-MCP-Tools": ",".join(user_context["selected_mcp_tool_refs"]),
    }


def _event(data: str) -> dict | None:
    """SSE data 한 줄을 이벤트 dict 로. 모르는 type 은 None(건너뜀), 모양이 다르면 KrriExecutorError."""
    try:
        event = json.loads(data)
    except ValueError as exc:
        raise KrriExecutorError("KRRI 실행 창구 이벤트가 JSON 이 아니다") from exc
    if not isinstance(event, dict):
        raise KrriExecutorError("KRRI 실행 창구 이벤트가 object 가 아니다")
    fields = EVENT_FIELDS.get(event.get("type"))
    if fields is None:
        return None
    wrong = [name for name, kind in fields.items() if not isinstance(event.get(name), kind)]
    if wrong:
        raise KrriExecutorError(f"KRRI 실행 창구 {event['type']} 이벤트에 칸이 없거나 모양이 다르다: {', '.join(wrong)}")
    return event


async def stream_workflow(workflow: dict, *, user_text: str, context: dict, headers: dict):
    """workflow 한 벌을 KRRI 에 보내 실행 이벤트를 받는 대로 냄.

    입력  workflow_materializer 가 만든 workflow 그대로 · 발화 원문 · 화면 문맥 ·
          X-User-* 헤더 {이름: 값}(Gateway 가 준 것 또는 identity_headers 결과)
    출력  async generator. KRRI 이벤트 dict 를 온 차례대로. execution · answer_delta · result.
          result 가 마지막이고 그 뒤는 읽지 않음
    규칙  workflow 를 바꾸지 않고 본문에 그대로 실음
          헤더 값을 고치지 않고 받은 바이트 그대로 실음. 들어온 헤더는 latin-1 로
          풀린 문자열이라 latin-1 로 되돌림
          본문을 줄 단위로 읽는 대로 냄. 다 받은 뒤에 나누지 않음
          data 줄만 읽음. ping 같은 주석 줄 · 모르는 type 은 건너뜀
          HTTP 200 이 아니면 실패. KRRI 가 실행하다 실패한 것은 200 + status=failed 로 옴
          result 없이 끝나면 실패
    제약  원문 오류(주소 · 응답 본문)는 로그에만 남긴다. 예외 문장에는 싣지 않는다
          조각(answer_delta)의 text 를 고치지 않는다
    """
    try:
        url = endpoints.asap_orchestrator_url() + STREAM_PATH
    except endpoints.EndpointError as exc:
        raise KrriExecutorError(str(exc)) from exc

    payload = {"workflow": workflow, "user_text": user_text, "context": context or {}}
    finished = False
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            async with client.stream(
                "POST", url, json=payload,
                headers={name: value.encode("latin-1") for name, value in headers.items()},
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    logger.error("KRRI 실행 창구 HTTP %s: %s", response.status_code, body[:1000])
                    raise KrriExecutorError(f"KRRI 실행 창구가 HTTP {response.status_code} 을 돌려줬다")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    event = _event(data)
                    if event is None:
                        continue
                    yield event
                    if event["type"] == "result":
                        finished = True
                        break
    except httpx.TimeoutException as exc:
        logger.error("KRRI 실행 창구 시간 초과: %s", exc)
        raise KrriExecutorError("KRRI 실행 창구가 제한 시간 안에 답하지 않았다") from exc
    except httpx.HTTPError as exc:
        logger.error("KRRI 실행 창구 연결 실패: %s", exc)
        raise KrriExecutorError("KRRI 실행 창구에 연결하지 못했다") from exc

    if not finished:
        raise KrriExecutorError("KRRI 실행 창구가 result 없이 스트림을 끝냈다")
