"""KRRI native workflow 를 지금 저장소에 vendoring 한 KRRI_ASAP 실행기로 부른다. **임시 다리다.**

    workflow_materializer.materialize     agentic_ai 가 만든 완성된 call_mcp_workflow
      -> run                               vendor 실행기에 그대로 넘김
      -> _execute_generic_mcp_workflow     vendor_to_be_deleted
      -> 이벤트 · 답

**vendor_to_be_deleted 를 import 하는 제품 코드는 여기 하나다.** KRRI_ASAP 의
generic_mcp_executor 에 workflow 를 직접 넘기게 되면 이 파일이 vendor 와 함께 사라진다.

**여기서 판단하지 않는다.** 기호를 풀거나 · 참조 경로를 적거나 · transform 을 고르는 일은
workflow_materializer 가 끝냈다. 받은 steps 를 바꾸지 않고 넘기고, 돌아온 trace 로
단계 이벤트와 마지막 result 를 낸다.

**step_start / step_end 는 실행이 끝난 뒤에 나간다.** vendor 는 steps 전부를 한 번에
돌리고 trace 를 돌려주므로 중간에 끼어들 자리가 없다. 단계마다 한 쌍이 recipe 순서대로
나가는 것은 그대로지만, 시각이 실제 호출 시각은 아니다.

**사람에게 보일 문장은 workflow_answer 가 만든다.** 그 파일이 vendor 폴더에 있어 이 경계를
지나 나간다(workflow_answer 를 다시 내놓는 것이 그 까닭이다). 성공한 실행은 vendor 안에서
부르고, 실패한 실행은 vendor 가 자기 문구로 돌아오므로 아래 run 이 trace 로 다시 부른다.
같은 함수라 문구가 갈라지지 않는다.
"""

from vendor_to_be_deleted.asap import workflow_answer
from vendor_to_be_deleted.asap.generic_mcp_executor import _execute_generic_mcp_workflow

__all__ = ["USER_CONTEXT", "run", "workflow_answer"]

# 우리가 누구인지. 이 값으로 Gateway 가 권한을 찾는다.
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


def _answer(intent: dict, executed: dict) -> str:
    """이 실행에 보일 답 한 벌.

    입력  vendor 에 넘긴 intent · vendor 가 돌려준 것
    출력  화면에 그대로 나갈 문자열
    규칙  errors 가 비어 있으면 vendor 의 answer_draft. 그 안에서 이미
          workflow_answer 가 만든 것임
          errors 가 있으면 trace 로 우리가 다시 만듦. 이때 failed 를 넘김.
          vendor 는 중단할 때 대개 trace 에 아무것도 안 남기고, 남은 마지막
          항목은 성공한 앞 단계라 trace 만 보면 성공으로 읽힘
          trace 가 비면 단계 목록 없이 첫 줄만 나옴
    """
    if executed.get("errors"):
        return workflow_answer.compose_workflow_answer(intent, _trace(executed), failed=True)
    return executed.get("answer_draft") or ""


def _trace(executed: dict) -> list[dict]:
    """vendor 가 쌓은 단계 기록. 성공이든 실패든 같은 자리에 있음."""
    artifacts = executed.get("artifacts") or {}
    return artifacts.get("mcp_workflow_trace") or []


def _commands(executed: dict) -> list[dict]:
    """지도 명령을 JSON 으로.

    출력  [{"op": ..., "args": {...}}, ...]
    규칙  vendor 는 pydantic Command 로 돌려줌. 부르는 화면은 JSON 을 받음
    """
    return [
        command.model_dump() if hasattr(command, "model_dump") else command
        for command in (executed.get("commands") or [])
    ]


async def run(materialized: dict, text: str):
    """완성된 KRRI native workflow 한 벌을 vendor 실행기로 부름. 이벤트를 차례로 냄.

    입력  workflow_materializer.materialize 가 READY 로 낸 것 · 발화 원문
    출력  step_start / step_end 를 불린 단계마다 한 쌍, 마지막은 type=result
    규칙  workflow 를 고치지 않고 vendor 의 intent 로 그대로 넘김
          부를 도구가 없고 지도 명령만 있으면 vendor 를 안 지남. 빈 steps 를
          넘기면 vendor 가 실패로 봄. 답은 NOTHING_RAN
          지도 명령이 도구 단계와 함께 있으면 도구 응답에서 나온 명령 뒤에
          붙임. 순서가 곧 경로 순서임
          한 단계가 실패하면 vendor 가 거기서 멈춤. trace 에 그 단계까지만
          담기므로 이벤트도 거기까지만 나감
          발화 원문은 vendor state 에 원래 자리대로 실음
    제약  실패 문구를 vendor 에서 가져오지 않는다.
          vendor 의 answer_draft 가 HTTP 오류 원문 · 내부 URL · Gateway 응답
          본문을 그대로 담음(실측 : "… Server error '500 Internal Server Error'
          for url '<ASAP_GATEWAY_URL>/api/tools/execute' … Response body: …").
          무엇이 비었는지만 trace 로 다시 만들어 씀
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

    state = {
        "user_text": text,
        "context": materialized["context"],
        "user_context": dict(USER_CONTEXT),
        "intent": intent,
    }

    executed = await _execute_generic_mcp_workflow(state, intent)

    for node_id, item in zip(materialized["nodes"], _trace(executed)):
        tool = item.get("tool") or ""
        yield {"type": "step_start", "node": node_id, "message": workflow_answer.step_start(tool)}
        failed = workflow_answer.step_failed(item)
        yield {"type": "step_end", "node": node_id, "message": workflow_answer.step_end(tool, failed=failed)}

    yield _result(_answer(intent, executed), _commands(executed) + commands)
