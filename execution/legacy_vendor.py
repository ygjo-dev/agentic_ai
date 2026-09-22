"""KRRI native workflow 를 KRRI_ASAP 의 실행 창구로 넘기고 그 결과를 이벤트로 낸다. **임시 다리다.**

    workflow_materializer.materialize     agentic_ai 가 만든 완성된 call_mcp_workflow
      -> run                               그대로 넘김
      -> krri_executor_client              HTTP POST <ASAP_ORCHESTRATOR_URL>/workflow/execute
      -> KRRI generic_mcp_executor         실행 · Gateway · 답
      -> 이벤트 · 답

이름에 vendor 가 남아 있지만 이제 vendoring 한 실행기를 부르지 않는다. 이름과 자리는
다음 정리 때 바꾼다. **vendor_to_be_deleted 를 import 하는 제품 코드는 여기 하나다** —
남은 것은 KRRI 가 안 도는 자리의 문구(workflow_answer)뿐이다.

**여기서 판단하지 않는다.** 기호를 풀거나 · 참조 경로를 적거나 · transform 을 고르는 일은
workflow_materializer 가 끝냈다. 받은 steps 를 바꾸지 않고 넘기고, 돌아온 trace 로
단계 이벤트와 마지막 result 를 낸다.

**실제로 실행한 답은 KRRI 가 만든다.** 성공이든 실패든 KRRI 가 돌려준 answer 를 그대로
result 에 싣는다. 우리 workflow_answer 로 다시 쓰지 않는다. workflow_answer 가 답을
만드는 자리는 KRRI 가 아예 안 도는 자리뿐이다 — 지도 명령만 있는 실행과 KRRI 창구를
못 부른 실행.

**step_start / step_end 는 실행이 끝난 뒤에 나간다.** KRRI 창구는 steps 전부를 한 번에
돌리고 trace 를 돌려주므로 중간에 끼어들 자리가 없다. 단계마다 한 쌍이 recipe 순서대로
나가는 것은 그대로지만, 시각이 실제 호출 시각은 아니다.
"""

import logging

from execution import krri_executor_client
from vendor_to_be_deleted.asap import workflow_answer

__all__ = ["USER_CONTEXT", "run", "workflow_answer"]

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


def _result(answer: str, commands: list) -> dict:
    """마지막 이벤트. 부르는 화면이 읽는 두 칸."""
    return {"type": "result", "answer": answer, "commands": commands}


async def run(materialized: dict, text: str):
    """완성된 KRRI native workflow 한 벌을 KRRI 실행 창구로 부름. 이벤트를 차례로 냄.

    입력  workflow_materializer.materialize 가 READY 로 낸 것 · 발화 원문
    출력  step_start / step_end 를 불린 단계마다 한 쌍, 마지막은 type=result
    규칙  workflow 를 고치지 않고 그대로 넘김
          부를 도구가 없고 지도 명령만 있으면 KRRI 를 안 부름. 빈 steps 를
          넘기면 KRRI 가 실패로 봄. 답은 NOTHING_RAN
          KRRI 가 돌았으면 답은 KRRI 의 answer 그대로. 성공 · 실패 모두
          지도 명령이 도구 단계와 함께 있으면 KRRI 가 돌려준 명령 뒤에
          붙임. 순서가 곧 경로 순서임
          한 단계가 실패하면 KRRI 가 거기서 멈춤. trace 에 그 단계까지만
          담기므로 이벤트도 거기까지만 나감
          KRRI 창구를 못 부르면 단계 이벤트 없이 EXECUTOR_UNREACHABLE
    제약  KRRI 의 answer 를 다시 쓰지 않는다. 실제 실행의 답은 KRRI 가 주인이다
          KRRI 를 못 불렀을 때 vendoring 한 실행기로 돌아가지 않는다
          기호를 풀거나 참조 · inputAdapter 를 여기서 정하지 않는다
    """
    intent = materialized["workflow"]
    commands = materialized["commands"]

    if not intent["steps"]:
        for node_id, command in zip(materialized["command_nodes"], commands):
            yield {"type": "step_start", "node": node_id, "message": workflow_answer.command_start(command["op"])}
            yield {"type": "step_end", "node": node_id, "message": workflow_answer.step_end(command["op"])}
        yield _result(workflow_answer.NOTHING_RAN, commands)
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
        yield _result(workflow_answer.EXECUTOR_UNREACHABLE, commands)
        return

    for node_id, item in zip(materialized["nodes"], executed["trace"]):
        tool = item.get("tool") or ""
        yield {"type": "step_start", "node": node_id, "message": workflow_answer.step_start(tool)}
        failed = workflow_answer.step_failed(item)
        yield {"type": "step_end", "node": node_id, "message": workflow_answer.step_end(tool, failed=failed)}

    yield _result(executed["answer"], executed["commands"] + commands)
