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

**답 문구를 만드는 우리 쪽 vendor/asap/workflow_answer 를 부르는 자리가 둘이다.**
성공한 실행은 vendor 안에서 _compose_workflow_answer 가 부르고, 실패한 실행은
vendor 가 자기 문구(_failed_workflow_result)로 돌아오므로 아래 run 이 trace 로
다시 부른다. 같은 함수라 문구가 갈라지지 않는다.
"""

from collections import Counter

from demo.api.services import (
    clarify_service,
    ontology_service,
    resolve_service,
    step_service,
)
from vendor.asap.generic_mcp_executor import _execute_generic_mcp_workflow
from vendor.asap.workflow_answer import compose_workflow_answer, step_failed

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

# 부를 인자를 못 뽑았을 때의 안내. given 이 무엇이냐에 따라 무엇을 더 말해
# 달라고 할지가 다르다. 장소 문구 하나로 두면 "국회의원 선거구 찾아줘" 에
# 장소를 대라고 답하게 된다.
NO_PLACE_ANSWER = (
    "어느 장소인지 알 수 없습니다. '오송역' 처럼 장소를 함께 말씀해 주세요."
)
NO_KEYWORD_ANSWER = (
    "무엇을 찾을지 알 수 없습니다. '전기차 충전소' 처럼 찾을 것을 함께 말씀해 주세요."
)
NO_IDENTIFIER_ANSWER = (
    "어느 것인지 알 수 없습니다. '충북 제1선거구' 처럼 이름이나 코드를 함께 말씀해 주세요."
)

# given -> 안내 문구. key 는 온톨로지의 데이터 노드 id 이고 축 선택지와 같은 값이다.
# given 이 null 이거나 여기 없는 값이면 장소 문구로 떨어진다.
#
# **화면에서 온 둘(찍은 지점 · 보이는 범위)은 여기 없다.** 그 둘은 사람이 더
# 말해 줄 것이 없다 — 값은 이미 화면이 보냈고, 안 보냈으면 resolve 가 그
# 후보를 아예 안 내놓아 이 문구까지 오지 않는다.
NO_ARGUMENT_ANSWER = {
    "spoken_place": NO_PLACE_ANSWER,
    "spoken_keyword": NO_KEYWORD_ANSWER,
    "spoken_identifier": NO_IDENTIFIER_ANSWER,
}

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

# 되묻기 뒤에 고른 것을 되비추는 줄. 답 맨 앞에 붙는다.
#
# 조사를 안 쓴다. "{label} 을" 로 적으면 이름의 끝 글자마다 을/를 이 갈려
# 줄마다 어미가 틀어진다. 화면 목록과 같은 "번호 이름" 꼴로 되뇌기만 한다.
CHOICE_HEAD = "고르신 것 — {number} {label}"


async def run(recipe_id: str, argument: str, text: str = "", context: dict | None = None):
    """recipe 의 노드 순서대로 도구를 부름. 이벤트를 차례로 냄.

    입력  recipe id · 발화에서 뽑은 인자 · 원 발화 · 저쪽 화면이 보낸 context
    출력  이벤트 dict 를 순서대로 냄. 마지막은 반드시 type=result
          step_start / step_end 는 실제로 불린 단계마다 한 쌍
    규칙  경로에 도구가 안 붙은 노드가 있으면 하나도 안 부르고 그렇다고 답함.
          부르는 것만 부르면 반쪽 결과를 온전한 답인 것처럼 내놓게 됨
          부를 것이 없으면 곧장 result. vendor 는 빈 steps 를 실패로 봄
          한 단계가 실패하면 vendor 가 거기서 멈춤. trace 에 그 단계까지만
          담기므로 이벤트도 거기까지만 나감
          실패한 실행의 답은 vendor 의 answer_draft 를 버리고 trace 로 다시
          만듦. vendor 문구가 HTTP 오류 원문 · 내부 URL · Gateway 응답 본문을
          그대로 담음 (실측 : "s1 단계 MCP tool 실행에 실패했습니다: Server
          error '500 Internal Server Error' for url
          'http://localhost:3000/api/tools/execute' … Response body: …")
    제약  실패 문구를 vendor 에서 가져오지 않는다.
          무엇이 비었는지는 vendor 가 적어 주지만 그 문장이 사용자에게 보일
          것이 아님. 무엇이 비었는지만 workflow_answer 가 골라 씀
    """
    missing = step_service.unwired(recipe_id)
    if missing:
        yield _result(_unwired_answer(recipe_id, missing), [])
        return

    plan = step_service.plan(recipe_id, argument)
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
        outcome = "실패" if step_failed(item) else "완료"
        yield {"type": "step_end", "node": node_id, "message": f"{tool} {outcome}"}

    yield _result(_answer(intent, executed), _commands(executed))


async def chat(
    text: str,
    llm_client,
    reason_max_length: int,
    context: dict | None = None,
    session_id: str = "",
):
    """발화 한 건을 끝까지. 해석하고 부르고 답을 만듦.

    입력  발화 · LLM 클라이언트 · reason 길이 상한 · 저쪽 화면의 context ·
          세션 id(없으면 빈 문자열)
    출력  이벤트 dict 를 순서대로 냄. 마지막은 반드시 type=result
    규칙  직전 되묻기를 먼저 본다. 이 발화가 그 후보 중 하나를 고른
          것이면 해석을 건너뛰고 곧장 부름 — LLM 을 다시 안 부름
          고르기가 아니면 지금까지와 똑같이 새 발화로 해석함. 그때도
          직전 되묻기는 지워짐(take 가 꺼내면서 지움) — 두 발화 전의
          후보를 나중에 고르는 일이 없어야 함
          해석도 한 단계로 냄. 저쪽 화면이 진행 상황을 그림
          문맥을 해석에도 넘김. 화면에서 온 값으로 시작하는 recipe 는 그 값이
          실제로 와 있을 때만 후보가 됨 — 없는 좌표로 도구를 부르지 않음
          SELECT 가 아니면 도구를 하나도 안 부름. CLARIFY 는 후보가 여럿이라
          무엇을 부를지 정해지지 않았고, NO_MATCH 는 부를 것이 없음
          번호 붙은 후보를 내놓았으면 그것을 세션에 기억해 둠. 다음 발화가
          고르기일 수 있음
          인자는 LLM 이 argument 로 준 것을 먼저 씀. 그것이 없을 때만
          place_in 이 장소를 뽑음. 정규식은 장소 어절 하나밖에 못 봄
          인자를 못 뽑으면 부르지 않고 안내만 함. 무엇을 조회할지 정해지지
          않았는데 부르면 엉뚱한 곳이 나옴
          화면에서 온 값으로 시작하는 recipe 는 인자가 없어도 부름.
          "지금 보이는 곳 CCTV 보여줘" 에는 뽑을 말이 없고, 조회할 곳은
          이미 문맥이 말했음
    제약  여기서 LLM 클라이언트를 만들지 않는다.
          demo.api.main 의 make_client 를 갈아끼우는 테스트가 죽음
          세션이 없으면 되묻기를 기억하지도 고르지도 않는다.
          지금까지와 똑같이 동작한다
    """
    pending = clarify_service.take(session_id)
    if pending is not None:
        chosen = clarify_service.pick(text, pending)
        if chosen is not None:
            async for payload in _run_choice(pending, chosen, context):
                yield payload
            return

    yield {"type": "step_start", "node": "resolve", "message": "발화를 해석하고 있습니다..."}
    resolved = resolve_service.resolve(
        text,
        llm_client=llm_client,
        reason_max_length=reason_max_length,
        context=context,
    )
    recipe_id = resolved.get("recipe_id")
    yield {
        "type": "step_end",
        "node": "resolve",
        "message": f"{resolved.get('status')} {recipe_id or ''}".strip(),
    }

    # 인자는 되묻기 때도 뽑아 둔다. 고른 뒤에 다시 뽑을 자리가 없다 —
    # 그때는 원래 발화가 아니라 "1번" 이 들어온다.
    argument = resolved.get("argument") or step_service.place_in(text)

    if resolved.get("status") != "SELECT" or not recipe_id:
        _remember_clarify(session_id, resolved, argument, text)
        yield _result(_no_recipe_answer(resolved), [])
        return

    if not argument and not _from_screen(resolved.get("given")):
        yield _result(_no_argument_answer(resolved.get("given")), [])
        return

    async for payload in run(recipe_id, argument, text=text, context=context):
        yield payload


async def _run_choice(pending: dict, chosen: int, context: dict | None):
    """되묻기 뒤에 고른 것을 실행. 해석을 다시 안 함.

    입력  기억해 둔 되묻기 · 고른 자리(0부터) · 저쪽 화면의 context
    출력  chat 과 같은 이벤트 흐름. 마지막은 반드시 type=result
    규칙  기억해 둔 recipe id 와 인자로 곧장 run 을 부름. resolve 도 LLM 도
          안 부름 — 무엇을 부를지는 이미 정해졌음
          무엇을 골랐는지 답 맨 앞에 한 줄 보임. 사람이 잘못 고른 것을
          그 자리에서 알아야 함
          인자가 없으면 실행하지 않고 안내만 함. 되묻기 때 인자를 못 뽑았으면
          고른 뒤에도 없음 — 새 발화가 인자를 못 뽑았을 때와 같이 처신함.
          화면에서 온 값으로 시작하는 것은 여기서도 인자 없이 부름
          text 는 원래 발화를 넘김. "1번" 이 아니라 그것이 무엇을 물은 것인지임
    """
    head = CHOICE_HEAD.format(number=chosen + 1, label=pending["labels"][chosen])

    yield {"type": "step_start", "node": "choice", "message": "고르신 것을 실행합니다..."}
    yield {"type": "step_end", "node": "choice", "message": head}

    if not pending["argument"] and not _from_screen(pending["given"]):
        yield _result(f"{head}\n\n{_no_argument_answer(pending['given'])}", [])
        return

    async for payload in run(
        pending["recipe_ids"][chosen],
        pending["argument"],
        text=pending["text"],
        context=context,
    ):
        if payload["type"] == "result":
            yield _result(f"{head}\n\n{payload['answer']}", payload["commands"])
        else:
            yield payload


def _remember_clarify(session_id: str, resolved: dict, argument: str, text: str) -> None:
    """화면에 번호를 보인 되묻기를 세션에 남김.

    입력  세션 id · resolve 결과 · 뽑아둔 인자 · 원래 발화
    규칙  후보가 있을 때만 남김. 번호가 화면에 보인 것이 곧 고를 수 있다는
          뜻임 — status 가 아니라 후보 유무로 가름 (_no_recipe_answer 가
          목록을 그리는 조건과 같음)
          번호 순서는 화면에 보인 그대로임. 같은 목록으로 이름도 함께 남김
          배선 표시(UNWIRED_MARK)는 떼고 남김. 사람이 고를 때 되뇌는 것은
          이름이지 그 표시가 아님
    제약  라벨을 화면과 따로 만들지 않는다.
          _candidate_labels 를 다시 부른다. 두 번 도는 값이 아깝지만 화면에
          보인 줄과 기억해 둔 줄이 갈라지면 이름으로 고를 수가 없다
    """
    candidates = resolved.get("candidate_recipe_ids") or []
    if not candidates:
        return

    paths = resolved.get("paths") or {}
    labels = [
        label.removesuffix(UNWIRED_MARK)
        for label in _candidate_labels(candidates, paths)
    ]
    names = []
    for recipe_id in candidates:
        chain = _step_names(recipe_id, paths)
        names.append(chain[-1] if chain else recipe_id)

    clarify_service.remember(
        session_id,
        recipe_ids=candidates,
        labels=labels,
        names=names,
        argument=argument,
        given=resolved.get("given"),
        text=text,
    )


def _from_screen(given: str | None) -> bool:
    """그 시작 데이터가 화면에서 값을 받는 것인가.

    입력  발화 해석이 쓴 given. 없으면 None
    출력  참이면 발화에서 뽑을 인자가 없어도 부를 수 있음
    규칙  어느 것이 화면에서 오는지는 step_service.CONTEXT_STARTS 가 앎
    """
    return given in step_service.CONTEXT_STARTS


def _no_argument_answer(given: str | None) -> str:
    """부를 인자를 못 뽑았을 때의 답.

    입력  발화 해석이 쓴 given. 없으면 None
    출력  무엇을 더 말해 달라는 한 문장
    규칙  given 으로 가름. 그 값이 이미 장소인지 키워드인지 식별자인지 말함
          모르는 given 과 None 은 장소 문구. 지금까지의 문구가 그것임
    """
    return NO_ARGUMENT_ANSWER.get(given, NO_PLACE_ANSWER)


def _result(answer: str, commands: list) -> dict:
    """마지막 이벤트. 저쪽 화면이 읽는 두 칸."""
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
    규칙  vendor 는 pydantic Command 로 돌려줌. 저쪽 화면은 JSON 을 받음
    """
    return [
        command.model_dump() if hasattr(command, "model_dump") else command
        for command in (executed.get("commands") or [])
    ]


def _unwired_answer(recipe_id: str, missing: list[str]) -> str:
    """도구가 안 붙은 노드가 있을 때의 답.

    입력  recipe id · 맞는 배선 줄이 없는 실행 노드 id 목록
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
    제약  여기서 만든 줄이 곧 고를 수 있는 이름이다.
          _remember_clarify 가 같은 함수(_candidate_labels)로 이름을 남기고
          clarify_service 가 그것과 통째로 같은 문구만 고르기로 봄. 이 줄의
          모양을 바꾸면 이름으로 고르는 길이 함께 바뀜
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
