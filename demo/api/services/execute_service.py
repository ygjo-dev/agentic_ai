"""발화를 recipe 로 해석하고, 그 노드 순서를 vendor 실행기에 넘긴다.

**실행·배선·답 조합은 우리 것이 아니다.** vendor/asap/generic_mcp_executor 의
_execute_generic_mcp_workflow 가 steps 배열 하나를 받아 참조 해석($s1.location)
· 입력 어댑터(point_radius_to_bbox) · 도구 호출 · 지도 commands 까지 전부 한다.
도구가 늘어도 그쪽은 그대로다 — 우리가 늘리는 것은 step_service 의 표 한 줄이다.

여기 남은 일은 셋이다.
  발화에서 recipe 를 고르고           resolve_service
  recipe 를 steps 로 바꾸고            step_service
  vendor 가 준 것을 이벤트로 흘린다    아래

**step_start / step_end 는 실행이 끝난 뒤에 나간다.** vendor 는 steps 전부를
한 번에 돌리고 trace 를 돌려주므로 중간에 끼어들 자리가 없다. 단계마다 한 쌍이
recipe 순서대로 나가는 것은 그대로지만, 시각이 실제 호출 시각은 아니다.
"""

from collections import Counter

from demo.api.services import ontology_service, resolve_service, step_service
from vendor.asap.generic_mcp_executor import _execute_generic_mcp_workflow

# 우리가 누구인지. 이 값으로 Gateway 가 권한을 찾는다.
#
# 빠뜨리면 요청마다 새 guest 가 만들어지고 adminBoundary 셋 말고는 전부
# 거부된다(실측).
USER_CONTEXT = {
    "user_id": "asap-ontology-orchestrator",
    "selected_mcp_tool_refs": ["asap-mcp-core/*"],
}

# vendor 가 steps 를 workflow 로 알아보게 하는 이름.
WORKFLOW_ACTION = "call_mcp_workflow"

NO_PLACE_ANSWER = (
    "어느 장소인지 알 수 없습니다. '오송역' 처럼 장소를 함께 말씀해 주세요."
)

# 도구가 아직 안 붙은 노드가 경로에 있을 때의 답. 이름을 적어 무엇이 없는지 알린다.
UNWIRED_ANSWER = "{names} 기능이 아직 붙지 않아 실행할 수 없습니다."

# 후보를 하나로 못 좁혔을 때의 머리말. 후보 수로 가른다.
CLARIFY_HEADLINE = "어느 것을 보시겠습니까?"
CLARIFY_MANY_HEADLINE = "여러 가지로 해석됩니다. 어느 것을 보시겠습니까?"

# 긴 머리말로 바뀌는 후보 수.
CLARIFY_MANY_FROM = 4

# 부를 것이 하나도 없을 때의 답.
NO_MATCH_ANSWER = "지금 할 수 있는 일 중에 맞는 것이 없습니다."

# 후보 줄에서 앞 단계를 잇는 표시.
STEP_JOIN = " -> "

# 배선이 아직 없어 골라도 실행되지 않는 후보에 붙이는 표시.
UNWIRED_MARK = " (아직 실행할 수 없음)"


async def run(recipe_id: str, place: str, text: str = "", context: dict | None = None):
    """recipe 의 노드 순서대로 도구를 부름. 이벤트를 차례로 냄.

    입력  recipe id · 장소 · 원 발화 · 저쪽 화면이 보낸 context
    출력  이벤트 dict 를 순서대로 냄. 마지막은 반드시 type=result
          step_start / step_end 는 실제로 불린 단계마다 한 쌍
    규칙  경로에 도구가 안 붙은 노드가 있으면 하나도 안 부르고 그렇다고 답함.
          부르는 것만 부르면 반쪽 결과를 온전한 답인 것처럼 내놓게 됨
          부를 것이 없으면 곧장 result. vendor 는 빈 steps 를 실패로 봄
          한 단계가 실패하면 vendor 가 거기서 멈춤. trace 에 그 단계까지만
          담기므로 이벤트도 거기까지만 나감
    제약  실패 문구를 우리가 다시 쓰지 않는다.
          vendor 가 무엇이 비었는지까지 적어 answer_draft 로 돌려줌
    """
    missing = step_service.unwired(recipe_id)
    if missing:
        yield _result(_unwired_answer(recipe_id, missing), [])
        return

    plan = step_service.plan(recipe_id, place)
    if not plan["steps"]:
        yield _result("부를 도구가 없습니다.", [])
        return

    intent = {
        "action": WORKFLOW_ACTION,
        "steps": plan["steps"],
        "answer_instruction": plan["headline"],
    }
    state = {
        "user_text": text,
        "context": context or {},
        "user_context": dict(USER_CONTEXT),
        "intent": intent,
    }

    executed = await _execute_generic_mcp_workflow(state, intent)

    for node_id, item in zip(plan["nodes"], _trace(executed)):
        tool = item.get("tool") or ""
        yield {"type": "step_start", "node": node_id, "message": f"{tool} 호출 중입니다..."}
        outcome = "실패" if item.get("error") else "완료"
        yield {"type": "step_end", "node": node_id, "message": f"{tool} {outcome}"}

    yield _result(executed.get("answer_draft") or "", _commands(executed))


async def chat(text: str, llm_client, reason_max_length: int, context: dict | None = None):
    """발화 한 건을 끝까지. 해석하고 부르고 답을 만듦.

    입력  발화 · LLM 클라이언트 · reason 길이 상한 · 저쪽 화면의 context
    출력  이벤트 dict 를 순서대로 냄. 마지막은 반드시 type=result
    규칙  해석도 한 단계로 냄. 저쪽 화면이 진행 상황을 그림
          SELECT 가 아니면 도구를 하나도 안 부름. CLARIFY 는 후보가 여럿이라
          무엇을 부를지 정해지지 않았고, NO_MATCH 는 부를 것이 없음
          장소를 못 뽑으면 부르지 않고 안내만 함. 무엇을 조회할지 정해지지
          않았는데 부르면 엉뚱한 곳이 나옴
    제약  여기서 LLM 클라이언트를 만들지 않는다.
          demo.api.main 의 make_client 를 갈아끼우는 테스트가 죽음
    """
    yield {"type": "step_start", "node": "resolve", "message": "발화를 해석하고 있습니다..."}
    resolved = resolve_service.resolve(
        text, llm_client=llm_client, reason_max_length=reason_max_length
    )
    recipe_id = resolved.get("recipe_id")
    yield {
        "type": "step_end",
        "node": "resolve",
        "message": f"{resolved.get('status')} {recipe_id or ''}".strip(),
    }

    if resolved.get("status") != "SELECT" or not recipe_id:
        yield _result(_no_recipe_answer(resolved), [])
        return

    place = step_service.place_in(text)
    if place is None:
        yield _result(NO_PLACE_ANSWER, [])
        return

    async for payload in run(recipe_id, place, text=text, context=context):
        yield payload


def _result(answer: str, commands: list) -> dict:
    """마지막 이벤트. 저쪽 화면이 읽는 두 칸."""
    return {"type": "result", "answer": answer, "commands": commands}


def _trace(executed: dict) -> list[dict]:
    """vendor 가 쌓은 단계 기록. 성공이든 실패든 같은 자리에 있음."""
    artifacts = executed.get("artifacts") or {}
    return artifacts.get("mcp_workflow_trace") or []


def _commands(executed: dict) -> list[dict]:
    """지도 명령을 JSON 으로.

    출력  [{"op": ..., "args": {...}}, ...]
    규칙  vendor 는 pydantic Command 로 돌려줌. 저쪽 화면은 JSON 을 받음
    """
    return [
        command.model_dump() if hasattr(command, "model_dump") else command
        for command in (executed.get("commands") or [])
    ]


def _unwired_answer(recipe_id: str, missing: list[str]) -> str:
    """도구가 안 붙은 노드가 있을 때의 답.

    입력  recipe id · STEP_OF 에 없는 실행 노드 id 목록
    출력  무엇이 아직 없는지 적은 한 문장
    규칙  id 가 아니라 노드 이름으로 적음. 사람이 읽는 문장임
    """
    named = {entry["node_id"]: entry["name"] for entry in ontology_service.path_of(recipe_id)}
    return UNWIRED_ANSWER.format(
        names=" · ".join(named.get(node_id, node_id) for node_id in missing)
    )


def _no_recipe_answer(resolved: dict) -> str:
    """고른 recipe 가 없을 때의 답.

    입력  resolve 결과. candidate_recipe_ids · paths · reason 을 읽음
    출력  후보가 있으면 머리말 한 줄과 번호 붙은 후보 목록. 없으면 영역 밖이라는
          한 문장. 둘 다 뒤에 LLM 이 적은 이유가 붙음
    규칙  후보 수로 머리말을 가름. 4개 이상이면 여러 갈래라고 먼저 말함
          수를 문장에 넣지 않음. "둘 중" 처럼 쓰면 후보 수가 바뀔 때마다
          어미가 틀어짐
    제약  recipe id 를 문장에 적지 않는다.
          사람에게 뜻이 없고, 온톨로지를 개편하면 번호가 통째로 바뀜.
          응답 JSON 의 candidate_recipe_ids 는 그대로 두므로 화면과 도구는
          여전히 id 로 읽음
    """
    candidates = resolved.get("candidate_recipe_ids") or []
    reason = resolved.get("reason") or ""

    if candidates:
        head = _clarify_head(candidates, resolved.get("paths") or {})
    else:
        head = NO_MATCH_ANSWER

    return f"{head}\n\n{reason}".rstrip()


def _clarify_head(candidates: list[str], paths: dict) -> str:
    """후보 목록을 사람이 고를 수 있는 모양으로.

    입력  후보 recipe id 목록 · resolve 가 붙인 후보별 경로
    출력  머리말 한 줄 + 후보마다 한 줄. 앞에 번호가 붙음
    규칙  번호는 1부터. 사용자가 "1번" 이라고 답할 수 있어야 함
          번호 자릿수를 맞춰 이름이 같은 칸에서 시작함
    제약  번호로 답한 것을 받아 실행하지 않는다.
          세션 상태와 저쪽 화면 계약이 필요함. 지금은 문구만 냄
    """
    labels = _candidate_labels(candidates, paths)
    width = len(str(len(labels)))
    headline = (
        CLARIFY_MANY_HEADLINE if len(labels) >= CLARIFY_MANY_FROM else CLARIFY_HEADLINE
    )

    lines = [
        f"  {str(number).rjust(width)}  {label}"
        for number, label in enumerate(labels, start=1)
    ]
    return "\n".join([headline, *lines])


def _candidate_labels(candidates: list[str], paths: dict) -> list[str]:
    """후보마다 무엇을 하는 것인지 한 줄.

    입력  후보 recipe id 목록 · 후보별 경로
    출력  후보와 같은 순서의 문자열 목록
    규칙  마지막 실행 노드의 이름이 그 recipe 가 결국 무엇을 하는지임
          마지막 이름이 겹치는 후보끼리는 앞 단계를 붙여 가름. 안 겹치는
          후보에는 안 붙임. 짧을수록 읽기 쉬움
          경로가 비면 id 로 떨어짐. 사람에게 뜻은 없지만 줄이 사라지는 것보다
          나음
          배선이 없는 후보도 목록에 남기고 표시만 함. 온톨로지가 그 경로를
          안다는 것이 보여야 하고, 무엇이 안 붙었는지가 다음 할 일임
    """
    chains = {recipe_id: _step_names(recipe_id, paths) for recipe_id in candidates}
    tails = Counter(chain[-1] for chain in chains.values() if chain)

    labels = []
    for recipe_id in candidates:
        chain = chains[recipe_id]
        if not chain:
            label = recipe_id
        elif tails[chain[-1]] > 1:
            label = STEP_JOIN.join(chain)
        else:
            label = chain[-1]

        if step_service.unwired(recipe_id):
            label += UNWIRED_MARK
        labels.append(label)

    return labels


def _step_names(recipe_id: str, paths: dict) -> list[str]:
    """경로에서 부를 노드의 이름만. 순서 그대로.

    입력  recipe id · 후보별 경로
    출력  실행 노드 이름 목록. 경로가 없으면 빈 목록
    규칙  데이터 노드(말한 장소)는 뺌. 부를 것이 없고 모든 후보에 똑같이 들어
          있어 후보를 가르는 데 쓸모가 없음
    """
    executable = set(ontology_service.executable_in(recipe_id))
    return [
        entry["name"]
        for entry in (paths.get(recipe_id) or [])
        if entry["node_id"] in executable
    ]
