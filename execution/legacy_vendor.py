"""ExecutionRequest 를 지금 KRRI_ASAP vendor 실행기가 받는 옛 입력으로 바꿔 부른다. **임시 호환 계층이다.**

    ExecutionRequest                  plan_service.request. agentic_ai 의 공식 실행 출력
      -> to_legacy                    steps · "$s1.location.0" · "$context.…" · inputAdapter
      -> _execute_generic_mcp_workflow   vendor_to_be_deleted
      -> 이벤트 · 답

**vendor_to_be_deleted 를 import 하는 제품 코드는 여기 하나다.** KRRI_ASAP Gateway 가
ExecutionRequest 를 직접 받게 되면 이 파일이 vendor 와 함께 사라진다. 그래서 옛 입력의
표현은 여기서만 생기고 ExecutionRequest 로 되돌아가지 않는다.

여기서만 하는 일이다. 옛 입력이 기호를 모르기 때문이다.

    발화 인자 · 이름 있는 값 · 부르는 순간     값으로 채움
    조건(if_endswith · unless_endswith)      지금 인자로 가려 칸을 빼거나 둠
    앞 단계 참조 s1.point.lon                 그 단계 outputs 의 경로로 "$s1.location.0"
    화면 값 context.point.lon                 context_needs 의 선언으로 "$context.selectedLocation.lon"
    transform                                 그 입력을 칸에 두고 vendor 입력 어댑터 이름을 걺
    지도 명령                                 인자를 채워 vendor 를 안 지나고 냄

**경로를 짐작하지 않는다.** 참조 경로는 전부 ExecutionRequest 에 적힌 outputs ·
context_needs 에서 옮긴다. 이번 응답에서 그 경로의 값을 실제로 꺼내는 것은 vendor 의
_resolve_reference 이고, 반경 계산은 vendor 의 point_radius_to_bbox 다.

**step_start / step_end 는 실행이 끝난 뒤에 나간다.** vendor 는 steps 전부를 한 번에
돌리고 trace 를 돌려주므로 중간에 끼어들 자리가 없다. 단계마다 한 쌍이 recipe 순서대로
나가는 것은 그대로지만, 시각이 실제 호출 시각은 아니다.

**답 문구를 만드는 workflow_answer 를 부르는 자리가 둘이다.** 성공한 실행은 vendor
안에서 부르고, 실패한 실행은 vendor 가 자기 문구로 돌아오므로 아래 run 이 trace 로 다시
부른다. 같은 함수라 문구가 갈라지지 않는다. 그 파일이 vendor 폴더에 있어 고른 recipe 가
없을 때의 문구(no_match_answer)도 이 경계를 지나 나간다.
"""

import copy
import datetime

from execution import plan_service
from execution.plan_service import RUNTIME_NOW, SPOKEN_ARGUMENT, SPOKEN_SOURCE, TRANSFORM
from vendor_to_be_deleted.asap.generic_mcp_executor import _execute_generic_mcp_workflow
from vendor_to_be_deleted.asap.workflow_answer import (
    NOTHING_RAN,
    compose_workflow_answer,
    no_match_answer,
    step_failed,
)

__all__ = ["no_match_answer"]

# vendor 가 steps 를 workflow 로 알아보게 하는 이름.
WORKFLOW_ACTION = "call_mcp_workflow"

# 중심 좌표와 반경을 bbox 넷으로 바꾸는 vendor 어댑터의 이름.
POINT_RADIUS_TO_BBOX = "point_radius_to_bbox"

# transform id -> 그것을 실제로 하는 vendor 입력 어댑터.
TRANSFORM_ADAPTERS = {
    "builtin/geo.pointRadiusToBbox": POINT_RADIUS_TO_BBOX,
}

# point_radius_to_bbox 가 중심 좌표를 찾는 칸 이름. vendor 의
# _extract_center_point 가 보는 것과 같은 순서 · 같은 이름이다.
#
# 이 중 하나도 안 남으면 어댑터가 ValueError 를 올린다("point_radius_to_bbox에는
# center/location 좌표가 필요합니다"). 그래서 어댑터를 걸기 전에 본다.
CENTER_KEYS = ("center", "point", "coordinate", "coordinates", "location")

# 옛 입력의 참조 머리. vendor 의 _build_resolution_scope 가 state["context"] 를
# scope["context"] 에, 앞 단계 결과를 scope["s<N>"] 에 얹고 제자리에서 푼다.
REFERENCE = "$"

# 도구를 안 부르는 단계의 진행 표시. 도구 단계와 같은 모양이라 부르는 화면이
# 따로 알아볼 것이 없다 — 그 자리에 도구 이름 대신 지도 명령 op 이 온다.
COMMAND_START = "{op} 명령을 내는 중입니다..."
COMMAND_END = "{op} 완료"

# _bound 가 "이 칸은 이 자리에서 안 보낸다" 를 알리는 표시.
#
# None 을 쓰지 않는다. None 은 도구가 받는 값일 수 있어 "빼라" 와 "null 을
# 보내라" 가 안 갈린다.
_OMIT = object()


# ── ExecutionRequest -> 옛 입력 ───────────────────────────────────────


def to_legacy(request: dict, now: datetime.datetime | None = None) -> dict:
    """ExecutionRequest 한 벌을 vendor 가 받는 옛 실행 계획으로.

    입력  plan_service.request 가 만든 것 · 부르는 순간(안 주면 지금)
    출력  steps  vendor 의 intent["steps"] 에 그대로 들어갈 배열
          nodes  steps 와 같은 길이. steps[i] 를 만든 노드 id
          commands  도구를 안 부르고 곧장 내는 지도 명령
          command_nodes  commands 와 같은 길이
    규칙  workflow 차례 그대로 step · 명령을 냄. step id 는 게시된 것 그대로
          부르는 순간은 계획 하나에 한 번만 읽음
    제약  ExecutionRequest 를 바꾸지 않는다. 옛 표현은 새 dict 에만 적음
    """
    # 계획 하나에 한 번만 읽는다. 단계마다 읽으면 자정 언저리에서 date 와
    # time 이 서로 다른 날을 가리킬 수 있다.
    now = now or datetime.datetime.now(plan_service.RUNTIME_ZONE)

    steps: list[dict] = []
    nodes: list[str] = []
    commands: list[dict] = []
    command_nodes: list[str] = []

    for entry in request["workflow"]:
        filled, adapter = bind_input(entry, request, now)

        if "command" in entry:
            commands.append({"op": entry["command"], "args": filled})
            command_nodes.append(entry["node"])
            continue

        step = {"id": entry["id"], "server_id": entry["server_id"], "tool": entry["tool"], "input": filled}
        if adapter:
            step["inputAdapter"] = adapter
        steps.append(step)
        nodes.append(entry["node"])

    return {"steps": steps, "nodes": nodes, "commands": commands, "command_nodes": command_nodes}


def bind_input(entry: dict, request: dict, now: datetime.datetime) -> tuple[dict, str | None]:
    """workflow 항목 하나의 옛 input 과 걸 어댑터.

    입력  workflow 항목 · 그 항목이 든 요청(spoken · context_needs · workflow 를 읽음) · 부르는 순간
    출력  (input, vendor 어댑터 이름 또는 None)
    규칙  input 차례대로 _bound 를 부르고 _OMIT 인 칸은 뺌
          transform 이 있으면 그 입력을 먼저 두고 이 항목의 나머지 칸을 이어 붙임.
          transform 이 만드는 칸(transform.<타입>.<칸>)은 vendor 어댑터가 만들어 안 보냄
          중심 좌표 칸이 남았을 때만 어댑터를 걺
    """
    outputs = {item["id"]: item.get("outputs") or {} for item in request["workflow"] if "id" in item}

    def fill(fields):
        filled = {}
        for field, expression in fields.items():
            value = _bound(expression, request, outputs, now)
            if value is not _OMIT:
                filled[field] = value
        return filled

    filled = fill(entry["input"])
    transform = entry.get("transform")
    if transform is None:
        return filled, None
    filled = {**fill(transform["input"]), **filled}
    return filled, TRANSFORM_ADAPTERS[transform["id"]] if _has_center(filled) else None


def _bound(expression, request: dict, outputs: dict, now):
    """기호 하나를 vendor 에 넘길 값으로. 이 자리에서 안 보내면 _OMIT."""
    if isinstance(expression, list):
        values = [_bound(item, request, outputs, now) for item in expression]
        return _OMIT if any(value is _OMIT for value in values) else values

    if "value" in expression:
        return copy.deepcopy(expression["value"])

    spoken = request["spoken"]
    origin = expression["from"]
    if origin == SPOKEN_ARGUMENT:
        argument = spoken["argument"]
        text = str(argument or "")
        if "if_endswith" in expression and not text.endswith(expression["if_endswith"]):
            return _OMIT
        if "unless_endswith" in expression and text.endswith(expression["unless_endswith"]):
            return _OMIT
        return argument

    if origin.startswith(SPOKEN_SOURCE):
        said = spoken.get(origin[len(SPOKEN_SOURCE):])
        chosen = said if said not in (None, "", [], {}) else expression["default"]
        mapping = expression.get("map")
        if mapping is None:
            return copy.deepcopy(chosen)
        return mapping.get(chosen, mapping[expression["default"]])

    head, *rest = origin.split(".")
    if origin.startswith(RUNTIME_NOW + "."):
        return plan_service.now_field(origin, now)
    if head == TRANSFORM:
        return _OMIT
    if head == "context":
        declaration = request["context_needs"][rest[0]]
        base = f"{REFERENCE}{declaration['from']}"
        return f"{base}.{declaration['fields'][rest[1]]}" if len(rest) > 1 else base

    reading = outputs[head][rest[0]]
    path = reading["fields"][rest[1]] if len(rest) > 1 else reading["value"]
    return f"{REFERENCE}{head}.{path}"


def _has_center(tool_input: dict) -> bool:
    """point_radius_to_bbox 가 걸 중심 좌표가 input 에 남았는지.

    규칙  CENTER_KEYS 중 하나라도 있으면 참. 값이 무엇인지는 안 봄.
          ["$s1.location.0", "$s1.location.1"] 처럼 vendor 가 나중에 푸는 참조라
          지금 판정할 수 없음
    """
    return any(key in tool_input for key in CENTER_KEYS)


# ── vendor 가 준 것을 읽는다 ───────────────────────────────────────


def _result(answer: str, commands: list) -> dict:
    """마지막 이벤트. execute_service 의 것과 같은 모양."""
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
        return compose_workflow_answer(intent, _trace(executed), failed=True)
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


# ── 부른다 ─────────────────────────────────────────────────────────


async def run(request: dict, text: str, user_context: dict):
    """ExecutionRequest 한 벌을 옛 입력으로 바꿔 vendor 로 부름. 이벤트를 차례로 냄.

    입력  plan_service.request 가 만든 것(workflow 가 비지 않음) · 발화 원문 ·
          Gateway 가 권한을 찾는 user_context
    출력  step_start / step_end 를 불린 단계마다 한 쌍, 마지막은 type=result
    규칙  부를 도구가 없고 지도 명령만 있으면 vendor 를 안 지남. 빈 steps 를
          넘기면 vendor 가 실패로 봄. 답은 NOTHING_RAN
          지도 명령이 도구 단계와 함께 있으면 도구 응답에서 나온 명령 뒤에
          붙임. 순서가 곧 경로 순서임
          한 단계가 실패하면 vendor 가 거기서 멈춤. trace 에 그 단계까지만
          담기므로 이벤트도 거기까지만 나감
          발화 원문은 vendor 가 웹 검색 질의를 다듬을 때 읽음(_prepare_tool_input)
    제약  실패 문구를 vendor 에서 가져오지 않는다.
          vendor 의 answer_draft 가 HTTP 오류 원문 · 내부 URL · Gateway 응답
          본문을 그대로 담음(실측 : "… Server error '500 Internal Server Error'
          for url '<ASAP_GATEWAY_URL>/api/tools/execute' … Response body: …").
          무엇이 비었는지만 trace 로 다시 만들어 씀
    """
    plan = to_legacy(request)

    if not plan["steps"]:
        for node_id, command in zip(plan["command_nodes"], plan["commands"]):
            op = command["op"]
            yield {"type": "step_start", "node": node_id, "message": COMMAND_START.format(op=op)}
            yield {"type": "step_end", "node": node_id, "message": COMMAND_END.format(op=op)}
        yield _result(NOTHING_RAN, plan["commands"])
        return

    intent = {"action": WORKFLOW_ACTION, "steps": plan["steps"]}
    state = {
        "user_text": text,
        "context": request["context"],
        "user_context": dict(user_context),
        "intent": intent,
    }

    executed = await _execute_generic_mcp_workflow(state, intent)

    for node_id, item in zip(plan["nodes"], _trace(executed)):
        tool = item.get("tool") or ""
        yield {"type": "step_start", "node": node_id, "message": f"{tool} 호출 중입니다..."}
        outcome = "실패" if step_failed(item) else "완료"
        yield {"type": "step_end", "node": node_id, "message": f"{tool} {outcome}"}

    yield _result(_answer(intent, executed), _commands(executed) + plan["commands"])
