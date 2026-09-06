"""발화를 recipe 로 해석하고, 그 노드 순서를 vendor 실행기에 넘긴다.

여기 남은 일은 셋이다.

    발화에서 recipe 를 고르고          resolve_service
    recipe 를 steps 로 바꾸고           step_service
    vendor 가 준 것을 이벤트로 흘린다   아래

**고르는 것과 부를 수 있는 것을 가른다.** recipe 선택은 resolve_service 의
LLM 이 혼자 한다. 고른 것을 실제로 부를 수 있는지(배선이 붙었는가 · 인자가
있는가 · 화면 문맥이 왔는가)는 실행 직전에 여기서 본다. 못 부르면 다른
recipe 로 갈아타지 않고 실행을 시작하지 않는다.

**실행 · 배선 해석 · 답 조합은 vendor 것이다.**
vendor_to_be_deleted/asap/generic_mcp_executor 의 _execute_generic_mcp_workflow 가
steps 배열 하나를 받아 참조 해석($s1.location) · 입력 어댑터 · 도구 호출 ·
지도 commands 까지 한다. 도구가 늘어도 그쪽은 그대로고, 우리가 늘리는 것은
wiring.yaml 한 줄이다.

**step_start / step_end 는 실행이 끝난 뒤에 나간다.** vendor 는 steps 전부를
한 번에 돌리고 trace 를 돌려주므로 중간에 끼어들 자리가 없다. 단계마다 한 쌍이
recipe 순서대로 나가는 것은 그대로지만, 시각이 실제 호출 시각은 아니다.

**답 문구를 만드는 workflow_answer 를 부르는 자리가 둘이다.** 성공한 실행은
vendor 안에서 부르고, 실패한 실행은 vendor 가 자기 문구로 돌아오므로 아래
run 이 trace 로 다시 부른다. 같은 함수라 문구가 갈라지지 않는다.

**vendor 를 아예 안 지나는 실행이 하나 있다.** 경로의 실행 노드가 전부
「부를 도구가 없는」 것이면 넘길 steps 가 비고, vendor 는 빈 steps 를 실패로
본다. 그때는 배선표가 만든 지도 명령을 그대로 내고 끝낸다.
"""

from collections import Counter

from execution import step_service
from ontology import graph, store
from orchestrator import resolve_service
from vendor_to_be_deleted.asap.generic_mcp_executor import _execute_generic_mcp_workflow
from vendor_to_be_deleted.asap.workflow_answer import (
    command_answer,
    compose_workflow_answer,
    no_match_answer,
    step_failed,
)

# 우리가 누구인지. 이 값으로 Gateway 가 권한을 찾는다.
#
# 빠뜨리면 요청마다 새 guest 가 만들어지고 adminBoundary 셋 말고는 전부
# 거부된다(실측).
#
# **부르는 서버만 하나씩 적는다. 전부 열지 않는다.** 안 적은 서버는 배선이
# 가리켜도 HTTP 500 "MCP tool '<서버>/<도구>' is not applied for this user."
# 로 막힌다(실측). 부를 것이 없는 서버를 미리 열면 「무엇을 왜 열었나」를
# 나중에 되짚을 수 없다. web-search 는 Gateway 쪽 권한이 안 열려 있다.
USER_CONTEXT = {
    "user_id": "asap-ontology-orchestrator",
    "selected_mcp_tool_refs": ["asap-mcp-core/*", "r5-server/*", "otp-router/*"],
}

# vendor 가 steps 를 workflow 로 알아보게 하는 이름.
WORKFLOW_ACTION = "call_mcp_workflow"

# 부를 인자를 못 뽑았을 때의 안내. 그 recipe 가 무엇으로 시작하느냐에 따라
# 무엇을 더 말해 달라고 할지가 다르다. 장소 문구 하나로 두면 "국회의원
# 선거구 찾아줘" 에 장소를 대라고 답하게 된다.
NO_PLACE_ANSWER = (
    "어느 장소인지 알 수 없습니다. '오송역' 처럼 장소를 함께 말씀해 주세요."
)
NO_KEYWORD_ANSWER = (
    "무엇을 찾을지 알 수 없습니다. '전기차 충전소' 처럼 찾을 것을 함께 말씀해 주세요."
)
NO_IDENTIFIER_ANSWER = (
    "어느 것인지 알 수 없습니다. '충북 제1선거구' 처럼 이름이나 코드를 함께 말씀해 주세요."
)

# 경로의 시작 데이터 노드 -> 안내 문구. key 는 온톨로지의 데이터 노드 id 다.
# 여기 없는 노드로 시작하는 경로는 장소 문구로 떨어진다.
#
# **화면에서 온 둘(찍은 지점 · 보이는 범위)은 여기 없다.** 그 둘로 시작하는
# 경로에서 사람이 더 말해 줄 것은 뒤 단계의 @arg 뿐이고, 그것은 대개 장소다
# (경로 탐색의 도착지가 그 자리다).
NO_ARGUMENT_ANSWER = {
    "spoken_place": NO_PLACE_ANSWER,
    "spoken_keyword": NO_KEYWORD_ANSWER,
    "spoken_identifier": NO_IDENTIFIER_ANSWER,
}

# 도구가 아직 안 붙은 노드가 경로에 있을 때의 답. 이름을 적어 무엇이 없는지 알린다.
UNWIRED_ANSWER = "{names} 기능이 아직 붙지 않아 실행할 수 없습니다."

# 실행에 필요한 화면 문맥이 안 왔을 때의 안내. key 는 온톨로지의 데이터 노드
# id 이고 step_service.CONTEXT_STARTS 와 같은 자리를 가리킨다.
#
# **고른 것을 바꾸지 않고 실행만 멈춘다.** 무엇을 골랐는지는 LLM 이 정했고,
# 지금 부를 수 있는지는 값이 왔는가의 문제라 사람에게 그대로 말한다.
NO_CONTEXT_ANSWER = {
    "picked_point": "지도에서 기준 지점을 먼저 찍어 주세요.",
    "visible_extent": "지금 보고 있는 지도 범위가 필요합니다. 지도 화면에서 다시 말씀해 주세요.",
}
NO_CONTEXT_DEFAULT = "지도 화면에서 와야 하는 값이 없어 실행할 수 없습니다."

# 후보를 하나로 못 좁혔을 때의 머리말. 후보 수로 가른다.
CLARIFY_HEADLINE = "어느 것을 보시겠습니까?"
CLARIFY_MANY_HEADLINE = "여러 가지로 해석됩니다. 어느 것을 보시겠습니까?"

# 긴 머리말로 바뀌는 후보 수.
CLARIFY_MANY_FROM = 4

# 부를 것이 하나도 없을 때의 답은
# vendor_to_be_deleted/asap/workflow_answer.no_match_answer 가 만든다.

# 도구를 안 부르는 단계의 진행 표시. 도구 단계와 같은 모양이라 부르는 화면이
# 따로 알아볼 것이 없다 — 그 자리에 도구 이름 대신 지도 명령 op 이 온다.
COMMAND_START = "{op} 명령을 내는 중입니다..."
COMMAND_END = "{op} 완료"

# 후보 줄에서 앞 단계를 잇는 표시.
STEP_JOIN = " -> "

# 배선이 아직 없어 골라도 실행되지 않는 후보에 붙이는 표시.
UNWIRED_MARK = " (아직 실행할 수 없음)"


# ── 답 문구 ────────────────────────────────────────────────────

def _result(answer: str, commands: list) -> dict:
    """마지막 이벤트. 부르는 화면이 읽는 두 칸."""
    return {"type": "result", "answer": answer, "commands": commands}


def _no_argument_answer(recipe_id: str) -> str:
    """부를 인자를 못 뽑았을 때의 답.

    출력  무엇을 더 말해 달라는 한 문장
    규칙  경로의 첫 노드로 가름. 그 노드가 이미 장소인지 키워드인지 식별자인지
          말함. 모르는 노드와 빈 경로는 장소 문구
    """
    path = graph.path_of(recipe_id)
    start = path[0]["node_id"] if path else None
    return NO_ARGUMENT_ANSWER.get(start, NO_PLACE_ANSWER)


def _no_context_answer(absent: set[str]) -> str:
    """화면에서 와야 하는 값이 없을 때의 답.

    입력  값을 못 받은 시작 데이터 노드 id 집합
    출력  무엇이 없는지 적은 문장. 여럿이면 줄바꿈으로 이음
    규칙  차례는 CONTEXT_STARTS 를 따름. 집합 차례로 내면 요청마다 순서가 바뀜
    """
    return "\n".join(
        NO_CONTEXT_ANSWER.get(node_id, NO_CONTEXT_DEFAULT)
        for node_id in step_service.CONTEXT_STARTS
        if node_id in absent
    ) or NO_CONTEXT_DEFAULT


def _unwired_answer(recipe_id: str, missing: list[str]) -> str:
    """도구가 안 붙은 노드가 있을 때의 답.

    입력  recipe id · 맞는 배선 줄이 없는 실행 노드 id 목록
    출력  무엇이 아직 없는지 적은 한 문장
    규칙  id 가 아니라 노드 이름으로 적음. 사람이 읽는 문장임
    """
    named = {entry["node_id"]: entry["name"] for entry in graph.path_of(recipe_id)}
    return UNWIRED_ANSWER.format(
        names=" · ".join(named.get(node_id, node_id) for node_id in missing)
    )


def _no_recipe_answer(resolved: dict) -> str:
    """고른 recipe 가 없을 때의 답.

    입력  resolve 결과. candidate_recipe_ids · paths · reason 을 읽음
    출력  후보가 있으면 머리말 한 줄과 번호 붙은 후보 목록. 없으면 영역 밖이라는
          한 문장과 안내 두 줄. 둘 다 뒤에 LLM 이 적은 이유가 붙음
    규칙  후보 수로 머리말을 가름. 4개 이상이면 여러 갈래라고 먼저 말함
          후보가 없으면 문구를 workflow_answer 가 만듦. 도구가 안 돈 자리의
          답을 한 파일에 모아 둔 것임
          수를 문장에 넣지 않음. "둘 중" 처럼 쓰면 후보 수가 바뀔 때마다
          어미가 틀어짐
    제약  recipe id 를 문장에 적지 않는다.
          사람에게 뜻이 없고, 온톨로지를 개편하면 번호가 통째로 바뀜.
          응답 JSON 의 candidate_recipe_ids 는 그대로 두므로 화면과 도구는
          여전히 id 로 읽음
    """
    candidates = resolved.get("candidate_recipe_ids") or []
    reason = resolved.get("reason") or ""

    if not candidates:
        topics, starts = _offer_names()
        return no_match_answer(reason, topics, starts)

    head = _clarify_head(candidates, resolved.get("paths") or {})
    return f"{head}\n\n{reason}".rstrip()


def _offer_names() -> tuple[list[str], list[str]]:
    """안내에 적을 이름 두 벌.

    출력  (대상 이름 목록, 발화로 시작할 수 있는 데이터 이름 목록)
    규칙  대상은 about 의 대상으로 등장하는 노드. 시작 데이터는 경로가 시작할
          수 있는 노드에서 화면에서 오는 둘을 뺀 것
          화면에서 오는 둘을 빼는 것은 사람이 더 말해 줄 것이 없기 때문임.
          어느 것이 그것인지는 step_service.CONTEXT_STARTS 가 앎
          (NO_ARGUMENT_ANSWER 가 그 둘을 빼 둔 것과 같은 까닭임)
    제약  이름을 코드에 적지 않는다.
          노드를 등록하면 안내도 함께 늘어야 함
    """
    nodes = store.nodes()
    topics = [nodes[node_id]["name"] for node_id in graph.group_ids() if node_id in nodes]
    starts = [
        nodes[node_id]["name"]
        for node_id in graph.start_ids()
        if node_id in nodes and node_id not in step_service.CONTEXT_STARTS
    ]
    return topics, starts


def _clarify_head(candidates: list[str], paths: dict) -> str:
    """후보 목록을 사람이 고를 수 있는 모양으로.

    출력  머리말 한 줄 + 후보마다 한 줄. 앞에 번호가 붙음
    규칙  번호는 1부터. 사람이 몇째 것인지 세어 말할 수 있어야 함
          번호 자릿수를 맞춰 이름이 같은 칸에서 시작함
    제약  이 줄의 모양을 안 바꾼다. 화면에 보이는 되묻기 문구 그 자체임
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
    executable = set(graph.executable_in(recipe_id))
    return [
        entry["name"]
        for entry in (paths.get(recipe_id) or [])
        if entry["node_id"] in executable
    ]


# ── vendor 가 준 것을 읽는다 ───────────────────────────────────

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


# ── 실행 ───────────────────────────────────────────────────────

async def run(recipe_id: str, argument: str, text: str = "", context: dict | None = None):
    """recipe 의 노드 순서대로 도구를 부름. 이벤트를 차례로 냄.

    출력  이벤트 dict 를 순서대로 냄. 마지막은 반드시 type=result
          step_start / step_end 는 실제로 불린 단계마다 한 쌍
    규칙  경로에 도구가 안 붙은 노드가 있으면 하나도 안 부르고 그렇다고 답함.
          부르는 것만 부르면 반쪽 결과를 온전한 답인 것처럼 내놓게 됨
          배선이 실제로 읽는 화면 문맥이 안 왔으면 시작하지 않음. 없는 좌표로
          부르면 전국이 나오거나 required 가 빈 채로 도구가 거부함.
          무엇을 읽는지는 step_service.context_needs 가 배선으로 셈
          부를 도구가 없고 지도 명령만 있으면 vendor 를 안 지남. 빈 steps 를
          넘기면 vendor 가 실패로 봄
          지도 명령이 도구 단계와 함께 있으면 도구 응답에서 나온 명령 뒤에
          붙임. 순서가 곧 경로 순서임
          한 단계가 실패하면 vendor 가 거기서 멈춤. trace 에 그 단계까지만
          담기므로 이벤트도 거기까지만 나감
    제약  실패 문구를 vendor 에서 가져오지 않는다.
          vendor 의 answer_draft 가 HTTP 오류 원문 · 내부 URL · Gateway 응답
          본문을 그대로 담음(실측 : "… Server error '500 Internal Server Error'
          for url 'http://localhost:3000/api/tools/execute' … Response body: …").
          무엇이 비었는지만 trace 로 다시 만들어 씀
    """
    missing = step_service.unwired(recipe_id)
    if missing:
        yield _result(_unwired_answer(recipe_id, missing), [])
        return

    absent = step_service.context_needs(recipe_id) - set(
        step_service.context_starts(context)
    )
    if absent:
        yield _result(_no_context_answer(absent), [])
        return

    plan = step_service.plan(recipe_id, argument)
    if not plan["steps"] and not plan["commands"]:
        yield _result("부를 도구가 없습니다.", [])
        return

    if not plan["steps"]:
        for node_id, command in zip(plan["command_nodes"], plan["commands"]):
            op = command["op"]
            yield {
                "type": "step_start",
                "node": node_id,
                "message": COMMAND_START.format(op=op),
            }
            yield {
                "type": "step_end",
                "node": node_id,
                "message": COMMAND_END.format(op=op),
            }
        yield _result(command_answer(plan["headline"]), plan["commands"])
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

    yield _result(_answer(intent, executed), _commands(executed) + plan["commands"])


async def chat(
    text: str,
    llm_client,
    reason_max_length: int,
    context: dict | None = None,
):
    """발화 한 건을 끝까지. 해석하고 부르고 답을 만듦.

    출력  이벤트 dict 를 순서대로 냄. 마지막은 반드시 type=result
    규칙  해석도 한 단계로 냄. 부르는 화면이 진행 상황을 그림
          해석에는 문맥을 안 넘김. 무엇을 고를지는 발화와 menu 만 보고 LLM 이
          정하고, 문맥이 실제로 왔는지는 run 이 실행 직전에 봄
          SELECT 가 아니면 도구를 하나도 안 부름. CLARIFY 는 무엇을 부를지
          정해지지 않았고 NO_MATCH 는 부를 것이 없음
          인자는 LLM 이 argument 로 준 것을 먼저 씀. 그것이 없을 때만 place_in
          이 장소를 뽑음. 정규식은 장소 어절 하나밖에 못 봄
          인자를 못 뽑으면 부르지 않고 안내만 함. 무엇을 조회할지 정해지지
          않았는데 부르면 엉뚱한 곳이 나옴
          배선이 발화에서 온 값을 안 쓰는 recipe 는 인자가 없어도 부름.
          "지금 보이는 곳 CCTV 보여줘" 에는 뽑을 말이 없고 조회할 곳은 이미
          문맥이 말했음. 그 판정은 step_service.spoken_needed 가 함
    제약  여기서 LLM 클라이언트를 만들지 않는다.
          app.api.main 의 get_llm 을 갈아끼우는 테스트가 죽음
          상태를 두지 않는다.
          발화 한 건이 한 건으로 끝남. 앞 발화를 안 기억하므로 「1번」도 다른
          말과 똑같이 새 발화로 해석됨. 되묻기 자체는 그대로 남
    """
    yield {"type": "step_start", "node": "resolve", "message": "발화를 해석하고 있습니다..."}
    resolved = resolve_service.resolve(
        text,
        llm_client=llm_client,
        reason_max_length=reason_max_length,
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

    argument = resolved.get("argument") or step_service.place_in(text)
    if not argument and step_service.spoken_needed(recipe_id):
        yield _result(_no_argument_answer(recipe_id), [])
        return

    async for payload in run(recipe_id, argument, text=text, context=context):
        yield payload
