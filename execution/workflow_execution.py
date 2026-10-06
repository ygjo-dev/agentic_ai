"""완성된 KRRI native workflow 를 KRRI_ASAP 의 실행 창구에 맡기고 그 결과를 SSE 이벤트로 낸다.

    workflow_materializer.materialize     agentic_ai 가 만든 완성된 call_mcp_workflow
      -> run                               그대로 넘김
      -> krri_executor_client              HTTP POST <ASAP_ORCHESTRATOR_URL>/workflow/execute/stream
      -> KRRI generic_mcp_executor         실행 · Gateway · 답(Gemini 가 만드는 대로 조각)
      -> 이벤트 · 답

**실행은 KRRI_ASAP 이 한다.** agentic_ai 안에 실행기가 없고, KRRI 를 못 불렀을 때 돌아갈
다른 실행기도 없다.

**여기서 판단하지 않는다.** 기호를 풀거나 · 참조 경로를 적거나 · transform 을 고르는 일은
workflow_materializer 가 끝냈다. 받은 steps 를 바꾸지 않고 넘기고, 돌아온 trace 로
단계 이벤트와 마지막 result 를 낸다.

**실제로 실행한 답은 KRRI 가 만든다.** 성공이든 실패든 KRRI 가 돌려준 answer 를 그대로
result 에 싣는다. KRRI 가 답을 만드는 동안 보내는 조각은 answer_delta 로 text 그대로 넘긴다 —
조각을 이어 붙이거나 고치지 않는다. 완성된 답의 원본은 언제나 result 의 answer 다. 단계가 실패했는지도 KRRI 가 trace 항목에 적은 error 칸으로만 안다 —
도구 결과를 다시 읽어 성공 · 실패를 가르지 않는다. agentic 문구(local_presentation)가 답이
되는 자리는 KRRI 가 아예 안 도는 자리뿐이다 — 지도 명령만 있는 실행과 KRRI 창구를
못 부른 실행.

**실행 기록은 이벤트 칸에 구조로 싣는다.** 답 문장은 사람에게 보일 표현이지 기록의
원천이 아니다. 단계가 실패했는지는 step_end 의 failed, KRRI 가 실행을 어떻게 판정했는지는
result 의 status 다. 둘 다 KRRI 가 적은 것(trace 항목의 error 칸 · 응답의 status)을 옮길
뿐이고, 받는 화면이 모르는 칸이라 버려도 answer · commands 의 뜻은 그대로다.

**step_start / step_end 는 도구 실행이 끝난 뒤에 나간다.** KRRI 창구는 steps 전부를 한 번에
돌리고 execution 이벤트에 trace 를 담아 보내므로 중간에 끼어들 자리가 없다. 단계마다 한 쌍이
recipe 순서대로 나가는 것은 그대로지만, 시각이 실제 호출 시각은 아니다. 답변 조각보다는
먼저 나간다.

**누구의 범위로 부르는지는 두 갈래이고 섞지 않는다.**

    Gateway 범위      KRRI_ASAP 채팅. Gateway 가 /chat/stream 에 X-User-* 를 넣어 보낸다
                      (GATEWAY_SCOPE_HEADERS). 그 사용자가 내 MCP · MCP 화면에서 적용한
                      범위다. 받은 여섯 값을 그대로 KRRI 에 넘기고, 넘기기 전에 workflow 의
                      도구가 모두 그 범위 안에 있는지 본다(tool_refs_outside). 밖이면 KRRI 를
                      부르지 않는다
    standalone 범위   X-User-* 가 하나도 없는 직접 호출. KRRI EASY MCPs 의 「AI로 사용해보기」가
                      그렇다. 내 MCP 등록과 무관하게 돌아야 하므로 범위로 막지 않고
                      STANDALONE_USER_CONTEXT 로 부른다

body 의 context 는 화면 문맥일 뿐이다. 어느 갈래이든 범위를 거기서 읽지 않는다.
"""

import logging

from execution import krri_executor_client, local_presentation

logger = logging.getLogger(__name__)

# standalone 호출(X-User-* 없음)의 신원. KRRI 가 이 값을 Gateway 에 넘기고 Gateway 가
# 권한을 찾는다. **Gateway 범위가 온 호출에는 쓰지 않는다.**
#
# 빠뜨리면 요청마다 새 guest 가 만들어지고 adminBoundary 셋 말고는 전부
# 거부된다(실측).
#
# **부르는 서버만 하나씩 적는다. 전부 열지 않는다.** 안 적은 서버는 workflow 가
# 가리켜도 HTTP 500 "MCP tool '<서버>/<도구>' is not applied for this user."
# 로 막힌다(실측). 부를 것이 없는 서버를 미리 열면 「무엇을 왜 열었나」를
# 나중에 되짚을 수 없다. web-search 는 Gateway 쪽 권한이 안 열려 있다.
STANDALONE_USER_CONTEXT = {
    "user_id": "asap-ontology-orchestrator",
    "selected_mcp_tool_refs": ["asap-mcp-core/*", "r5-server/*", "otp-router/*"],
}

# Gateway 가 /api/orchestrator/* 프록시에서 넣는 사용자 범위. KRRI /workflow/execute/stream 도 같은
# 이름으로 읽는다(KRRI_ASAP ASAP-orchestrator build_user_scope). 하나라도 오면 Gateway 범위다.
GATEWAY_SCOPE_HEADERS = (
    "X-User-ID",
    "X-User-Name",
    "X-User-Role",
    "X-User-MCP-Servers",
    "X-User-MCP-Tools",
    "X-User-MCP-Groups",
)

# 실행해도 되는 도구 refs. Gateway 가 selection 에 SYSTEM_MCP_TOOL_REFS 를 더해 적는다.
SELECTED_TOOLS_HEADER = "X-User-MCP-Tools"

# Gateway 가 「고른 것이 없다」를 적는 값.
NONE_SELECTED = "__none__"

# Gateway contract 의 server 전체 허용. "<server>/*".
SERVER_WILDCARD = "/*"


class InvalidToolRef(ValueError):
    """workflow step 의 server/tool 이 exact 가 아니다. 잘못 만들어진 실행 계획이다."""


def gateway_scope(headers) -> dict | None:
    """요청 헤더에서 Gateway 가 넣은 사용자 범위만 꺼냄.

    입력  요청 헤더(이름의 대소문자를 가리지 않는 mapping)
    출력  {헤더 이름: 받은 값} — GATEWAY_SCOPE_HEADERS 중 온 것만. 하나도 없으면 None
    제약  값을 고치거나 채우지 않는다. 받은 그대로 KRRI 에 넘길 것이다
    """
    scope = {name: headers[name] for name in GATEWAY_SCOPE_HEADERS if name in headers}
    return scope or None


def tool_refs_outside(steps: list[dict], scope: dict) -> list[str]:
    """workflow 가 부를 도구 중 Gateway 범위 밖인 것.

    입력  workflow steps · gateway_scope 가 꺼낸 범위
    출력  범위 밖 "<server>/<tool>" (소문자, steps 차례)
    규칙  부를 도구 = lower(server_id) + "/" + lower(tool). exact 여야 함
          허용 = X-User-MCP-Tools 를 쉼표로 나눈 것(소문자). Gateway contract 그대로
          exact "<server>/<tool>" 과 "<server>/*" 둘만 뜻이 있음
          X-User-MCP-Tools 가 없거나 __none__ 이면 허용이 비어 전부 밖임
    제약  부를 도구에 "*" 가 있으면 InvalidToolRef. 실행 계획이 도구를 정하지 못한 것이다
    """
    allowed = {
        ref.strip().lower()
        for ref in scope.get(SELECTED_TOOLS_HEADER, "").split(",")
        if ref.strip() and ref.strip() != NONE_SELECTED
    }
    outside = []
    for step in steps:
        server = str(step["server_id"]).lower()
        ref = f"{server}/{str(step['tool']).lower()}"
        if "*" in ref:
            raise InvalidToolRef(ref)
        if ref not in allowed and server + SERVER_WILDCARD not in allowed:
            outside.append(ref)
    return outside


def _result(answer: str, commands: list, status: str | None = None) -> dict:
    """마지막 이벤트. 부르는 화면이 읽는 두 칸.

    규칙  KRRI 가 실행했으면 그 응답의 status 를 그대로 덧붙임(success · failed).
          KRRI 가 안 돈 자리에는 status 칸이 없음. 우리가 대신 판정을 지어내지 않음
    """
    result = {"type": "result", "answer": answer, "commands": commands}
    if status is not None:
        result["status"] = status
    return result


async def run(materialized: dict, text: str, user_scope: dict | None = None):
    """완성된 KRRI native workflow 한 벌을 KRRI 실행 창구로 부름. 이벤트를 차례로 냄.

    입력  workflow_materializer.materialize 가 READY 로 낸 것 · 발화 원문
    출력  step_start / step_end 를 불린 단계마다 한 쌍, 이어서 answer_delta 여럿(KRRI 가
          보낸 만큼), 마지막은 type=result
          step_end 의 failed 는 그 단계가 실패했는가. result 의 status 는 KRRI 가
          돌았을 때만 있고 KRRI 응답의 status 그대로
    규칙  workflow 를 고치지 않고 그대로 넘김
          부를 도구가 없고 지도 명령만 있으면 KRRI 를 안 부름. 빈 steps 를
          넘기면 KRRI 가 실패로 봄. 답은 NOTHING_RAN
          KRRI 가 돌았으면 답은 KRRI 의 answer 그대로. 성공 · 실패 모두
          단계 한 쌍은 KRRI 의 execution 이벤트 trace 로 냄. execution 없이 result 가
          먼저 오면 result 의 trace 로 냄. 한 번만 냄
          KRRI 의 answer_delta 는 받는 대로 text 그대로 answer_delta 로 넘김
          단계의 실패 표시는 KRRI 가 trace 항목에 error 칸을 적었는가 하나로 정함.
          KRRI 는 필수 입력이 비었거나 · 호출이 터졌거나 · 200 오류 envelope 가
          돌아온 단계에 그 칸을 적고 거기서 멈춤
          지도 명령이 도구 단계와 함께 있으면 KRRI 가 돌려준 명령 뒤에
          붙임. 순서가 곧 경로 순서임
          한 단계가 실패하면 KRRI 가 거기서 멈춤. trace 에 그 단계까지만
          담기므로 이벤트도 거기까지만 나감
          KRRI 창구를 못 부르면 단계 이벤트 없이 EXECUTOR_UNREACHABLE. 스트림이 중간에
          끊기면 이미 나간 이벤트 뒤에 EXECUTOR_UNREACHABLE result 가 나감
          user_scope(gateway_scope 결과)가 있으면 그 여섯 값을 그대로 KRRI 에 넘김.
          도구 하나라도 범위 밖이면 KRRI 를 안 부르고 TOOL_NOT_SELECTED. 밖인 refs 는
          로그에만 남김. 부를 도구가 exact 가 아니면 KRRI 를 안 부르고 INVALID_WORKFLOW
          user_scope 가 None 이면 범위로 막지 않고 STANDALONE_USER_CONTEXT 로 부름
    제약  KRRI 의 answer 를 다시 쓰지 않는다. 실제 실행의 답은 KRRI 가 주인이다
          answer_delta 를 모아 result 를 만들지 않는다. result 는 KRRI 의 result 다
          도구 결과를 읽어 성공 · 실패를 다시 가르지 않는다
          KRRI 를 못 불렀을 때 다른 실행기로 돌아가지 않는다
          기호를 풀거나 참조 · inputAdapter 를 여기서 정하지 않는다
    """
    intent = materialized["workflow"]
    commands = materialized["commands"]

    if not intent["steps"]:
        for node_id, command in zip(materialized["command_nodes"], commands):
            yield {"type": "step_start", "node": node_id, "message": local_presentation.command_start(command["op"])}
            yield {"type": "step_end", "node": node_id, "message": local_presentation.step_end(command["op"]), "failed": False}
        yield _result(local_presentation.NOTHING_RAN, commands)
        return

    if user_scope is None:
        headers = krri_executor_client.identity_headers(STANDALONE_USER_CONTEXT)
    else:
        try:
            outside = tool_refs_outside(intent["steps"], user_scope)
        except InvalidToolRef as exc:
            logger.error("exact 가 아닌 도구를 부르는 workflow 라 KRRI 를 부르지 않는다: %s %s",
                         materialized.get("recipe_id"), exc)
            yield _result(local_presentation.INVALID_WORKFLOW, [])
            return
        if outside:
            logger.warning("사용자 MCP 범위 밖 도구라 KRRI 를 부르지 않는다: %s %s",
                           materialized.get("recipe_id"), outside)
            yield _result(local_presentation.TOOL_NOT_SELECTED, [])
            return
        headers = user_scope

    executed = None
    stepped = False
    try:
        async for event in krri_executor_client.stream_workflow(
            intent,
            user_text=text,
            context=materialized["context"],
            headers=headers,
        ):
            if event["type"] in ("execution", "result") and not stepped:
                stepped = True
                for node_id, item in zip(materialized["nodes"], event["trace"]):
                    tool = item.get("tool") or ""
                    failed = "error" in item
                    yield {"type": "step_start", "node": node_id, "message": local_presentation.step_start(tool)}
                    yield {"type": "step_end", "node": node_id, "message": local_presentation.step_end(tool, failed=failed), "failed": failed}
            if event["type"] == "answer_delta":
                yield {"type": "answer_delta", "text": event["text"]}
            elif event["type"] == "result":
                executed = event
    except krri_executor_client.KrriExecutorError as exc:
        logger.error("KRRI 실행 창구를 부르지 못했다: %s", exc)
        yield _result(local_presentation.EXECUTOR_UNREACHABLE, commands)
        return

    yield _result(executed["answer"], executed["commands"] + commands, executed["status"])
