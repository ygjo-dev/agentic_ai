"""완성된 KRRI native workflow 를 KRRI_ASAP 의 실행 창구에 맡기고 그 결과를 SSE 이벤트로 낸다.

    workflow_materializer.materialize     agentic_ai 가 만든 완성된 call_mcp_workflow
      -> run                               그대로 넘김
      -> krri_executor_client              HTTP POST <ASAP_ORCHESTRATOR_URL>/workflow/execute
      -> KRRI generic_mcp_executor         실행 · Gateway · 답
      -> 이벤트 · 답

**실행은 KRRI_ASAP 이 한다.** agentic_ai 안에 실행기가 없고, KRRI 를 못 불렀을 때 돌아갈
다른 실행기도 없다.

**여기서 판단하지 않는다.** 기호를 풀거나 · 참조 경로를 적거나 · transform 을 고르는 일은
workflow_materializer 가 끝냈다. 받은 steps 를 바꾸지 않고 넘기고, 돌아온 trace 로
단계 이벤트와 마지막 result 를 낸다.

**실제로 실행한 답은 KRRI 가 만든다.** 성공이든 실패든 KRRI 가 돌려준 answer 를 그대로
result 에 싣는다. 단계가 실패했는지도 KRRI 가 trace 항목에 적은 error 칸으로만 안다 —
도구 결과를 다시 읽어 성공 · 실패를 가르지 않는다. agentic 문구(local_presentation)가 답이
되는 자리는 KRRI 가 아예 안 도는 자리뿐이다 — 지도 명령만 있는 실행과 KRRI 창구를
못 부른 실행.

**실행 기록은 이벤트 칸에 구조로 싣는다.** 답 문장은 사람에게 보일 표현이지 기록의
원천이 아니다. 단계가 실패했는지는 step_end 의 failed, KRRI 가 실행을 어떻게 판정했는지는
result 의 status 다. 둘 다 KRRI 가 적은 것(trace 항목의 error 칸 · 응답의 status)을 옮길
뿐이고, 받는 화면이 모르는 칸이라 버려도 answer · commands 의 뜻은 그대로다.

**step_start / step_end 는 실행이 끝난 뒤에 나간다.** KRRI 창구는 steps 전부를 한 번에
돌리고 trace 를 돌려주므로 중간에 끼어들 자리가 없다. 단계마다 한 쌍이 recipe 순서대로
나가는 것은 그대로지만, 시각이 실제 호출 시각은 아니다.
"""

import logging

from execution import krri_executor_client, local_presentation

logger = logging.getLogger(__name__)

# 우리가 누구인지. KRRI 가 이 값을 Gateway 에 넘기고 Gateway 가 권한을 찾는다.
#
# 빠뜨리면 요청마다 새 guest 가 만들어지고 adminBoundary 셋 말고는 전부
# 거부된다(실측).
#
# **부르는 서버만 하나씩 적는다. 전부 열지 않는다.** 안 적은 서버는 workflow 가
# 가리켜도 HTTP 500 "MCP tool '<서버>/<도구>' is not applied for this user."
# 로 막힌다(실측). 부를 것이 없는 서버를 미리 열면 「무엇을 왜 열었나」를
# 나중에 되짚을 수 없다. web-search 는 Gateway 쪽 권한이 안 열려 있다.
USER_CONTEXT = {
    "user_id": "asap-ontology-orchestrator",
    "selected_mcp_tool_refs": ["asap-mcp-core/*", "r5-server/*", "otp-router/*"],
}


def _result(answer: str, commands: list, status: str | None = None) -> dict:
    """마지막 이벤트. 부르는 화면이 읽는 두 칸.

    규칙  KRRI 가 실행했으면 그 응답의 status 를 그대로 덧붙임(success · failed).
          KRRI 가 안 돈 자리에는 status 칸이 없음. 우리가 대신 판정을 지어내지 않음
    """
    result = {"type": "result", "answer": answer, "commands": commands}
    if status is not None:
        result["status"] = status
    return result


async def run(materialized: dict, text: str):
    """완성된 KRRI native workflow 한 벌을 KRRI 실행 창구로 부름. 이벤트를 차례로 냄.

    입력  workflow_materializer.materialize 가 READY 로 낸 것 · 발화 원문
    출력  step_start / step_end 를 불린 단계마다 한 쌍, 마지막은 type=result
          step_end 의 failed 는 그 단계가 실패했는가. result 의 status 는 KRRI 가
          돌았을 때만 있고 KRRI 응답의 status 그대로
    규칙  workflow 를 고치지 않고 그대로 넘김
          부를 도구가 없고 지도 명령만 있으면 KRRI 를 안 부름. 빈 steps 를
          넘기면 KRRI 가 실패로 봄. 답은 NOTHING_RAN
          KRRI 가 돌았으면 답은 KRRI 의 answer 그대로. 성공 · 실패 모두
          단계의 실패 표시는 KRRI 가 trace 항목에 error 칸을 적었는가 하나로 정함.
          KRRI 는 필수 입력이 비었거나 · 호출이 터졌거나 · 200 오류 envelope 가
          돌아온 단계에 그 칸을 적고 거기서 멈춤
          지도 명령이 도구 단계와 함께 있으면 KRRI 가 돌려준 명령 뒤에
          붙임. 순서가 곧 경로 순서임
          한 단계가 실패하면 KRRI 가 거기서 멈춤. trace 에 그 단계까지만
          담기므로 이벤트도 거기까지만 나감
          KRRI 창구를 못 부르면 단계 이벤트 없이 EXECUTOR_UNREACHABLE
    제약  KRRI 의 answer 를 다시 쓰지 않는다. 실제 실행의 답은 KRRI 가 주인이다
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

    try:
        executed = await krri_executor_client.execute_workflow(
            intent,
            user_text=text,
            context=materialized["context"],
            user_context=USER_CONTEXT,
        )
    except krri_executor_client.KrriExecutorError as exc:
        logger.error("KRRI 실행 창구를 부르지 못했다: %s", exc)
        yield _result(local_presentation.EXECUTOR_UNREACHABLE, commands)
        return

    for node_id, item in zip(materialized["nodes"], executed["trace"]):
        tool = item.get("tool") or ""
        failed = "error" in item
        yield {"type": "step_start", "node": node_id, "message": local_presentation.step_start(tool)}
        yield {"type": "step_end", "node": node_id, "message": local_presentation.step_end(tool, failed=failed), "failed": failed}

    yield _result(executed["answer"], executed["commands"] + commands, executed["status"])
