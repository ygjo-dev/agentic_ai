"""KRRI_ASAP 이 실행하지 않은 자리에서 agentic_ai 가 사람에게 보이는 문구.

**실제로 실행한 워크플로의 답은 여기서 만들지 않는다.** 그 답은 KRRI_ASAP
/workflow/execute 가 만들고 execution.workflow_execution 이 그대로 넘긴다. 성공인지
실패인지도 KRRI 가 정한다. 여기에는 trace 를 읽어 답을 짓거나 결과를 성공 · 빈 결과 ·
오류로 가르는 함수가 없고, 앞으로도 두지 않는다.

여기가 말하는 자리는 KRRI 까지 가지 않은 것뿐이다.

    해석 단계                 진행 표시(RESOLVE_START · resolve_end)
    고른 것이 없다            CLARIFY 되묻기 · NO_MATCH 안내 — unresolved_answer
    고른 것을 지금 못 부른다  workflow_materializer 가 READY 아닌 판정 — unready_answer
    지도 명령만 있다          NOTHING_RAN. KRRI 를 안 부른다
    KRRI 창구를 못 불렀다     EXECUTOR_UNREACHABLE
    단계 진행 표시            step_start · command_start · step_end

**여기는 온톨로지를 읽지 않는다.** 사람에게 보일 노드 이름은 부르는 쪽이 넘긴 것만
쓴다(orchestrator.resolve_service.answer_names · resolve 결과의 paths).
"""

from typing import Any, Dict, List, Optional


# ── KRRI 가 안 돈 자리 ───────────────────────────────────────────────
#
# 실행까지 갔는데 KRRI 답이 없는 자리가 둘이다. 둘 다 trace 가 없다.
#
#   지도 명령만 낸 실행     부를 도구가 없는 노드가 경로의 전부였다. KRRI 를 안 부른다
#   KRRI 를 못 부른 실행    실행 창구에 닿지 못했다. KRRI 가 돌았는지 모른다
#
# **여기도 도구 이름을 모른다.** 아래 둘은 문자열만 받는다.

# 지도 명령만 낸 실행의 답. 단계 목록이 없으므로 이 한 줄이 답 전부다.
# 무엇을 냈는지 op 이름으로 적지 않는다 — 사람에게 뜻이 없고, 이 파일은 부르는
# 쪽이 무엇을 부르는지 모른다.
NOTHING_RAN = "화면에 표시했습니다."

# KRRI 실행 창구를 못 불렀을 때의 답. 실행 여부를 모르므로 단계 목록이 없다.
# 주소 · 오류 원문을 적지 않는다 — 원인은 로그(execution.krri_executor_client)에 있다.
EXECUTOR_UNREACHABLE = "실행 서비스에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요."

# 맞는 경로가 없을 때의 첫 줄.
NO_MATCH_HEADLINE = "지금 할 수 있는 일 중에 맞는 것이 없습니다."

# 그 뒤에 붙는 안내 두 줄.
#
# **낱말은 온톨로지가 댄다.** 여기는 틀만 갖는다 — 노드를 등록하면 안내도 함께
# 늘고, 두 곳이 어긋날 자리가 없다. KRRI_ASAP 의 unsupported-request 답은 고정 문구
# 한 줄이라("죄송합니다. 현재 지원하지 않는 요청입니다") 무엇을 대신 말해야
# 할지는 안 알려준다.
NO_MATCH_TOPICS = "제가 다루는 것은 {topics}입니다."
NO_MATCH_STARTS = "{starts} 가운데 하나를 함께 말씀해 주세요."

# 이름을 늘어놓을 때의 사이. 답 문구가 쓰는 다른 구분자와 같다.
NAME_JOIN = " · "

# ── 고른 것을 못 부르는 자리 ──────────────────────────────────────────
#
# 도구가 안 도는 자리가 둘 더 있다. 둘 다 trace 가 없고, 무엇이 모자랐는지는 부르는
# 쪽이 구조로 넘긴다. **여기는 그 구조를 문장으로 옮길 뿐이다.** 온톨로지를 읽지
# 않고, 사람에게 보일 노드 이름은 넘겨받은 것만 쓴다.
#
#   후보를 하나로 못 좁혔다     resolve 가 CLARIFY 를 냈다. unresolved_answer
#   고른 것을 지금 못 부른다    workflow_materializer 가 READY 가 아닌 판정을 냈다. unready_answer

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

# 경로의 시작 노드 -> 안내 문구. key 는 source 가 발화(spoken.argument)인 온톨로지
# 노드 id 다. 여기 없는 노드로 시작하는 경로는 장소 문구로 떨어진다.
#
# **화면에서 오는 둘(지점 좌표 · 지도 범위)은 여기 없다.** 그 둘로 시작하는
# 경로에서 사람이 더 말해 줄 것은 뒤 단계의 발화 인자뿐이고, 그것은 대개 장소다
# (경로 탐색의 도착지가 그 자리다).
NO_ARGUMENT_ANSWER = {
    "place_name": NO_PLACE_ANSWER,
    "keyword": NO_KEYWORD_ANSWER,
    "district_code": NO_IDENTIFIER_ANSWER,
}

# 도구가 아직 안 붙은 노드가 경로에 있을 때의 답. 이름을 적어 무엇이 없는지 알린다.
UNWIRED_ANSWER = "{names} 기능이 아직 붙지 않아 실행할 수 없습니다."

# 부를 도구도 지도 명령도 없을 때의 답. 받아들인 recipe 가 아닌 id 를 골랐을 때도 이것이다.
NO_TOOL_ANSWER = "부를 도구가 없습니다."

# 실행에 필요한 화면 문맥이 안 왔을 때의 안내. key 는 source 가 화면(context.…)인
# 온톨로지 노드 id 이고 게시된 execution 의 context_needs 와 같은 자리를 가리킨다.
#
# **고른 것을 바꾸지 않고 실행만 멈춘다.** 무엇을 골랐는지는 LLM 이 정했고,
# 지금 부를 수 있는지는 값이 왔는가의 문제라 사람에게 그대로 말한다.
NO_CONTEXT_ANSWER = {
    "point": "지도에서 기준 지점을 먼저 찍어 주세요.",
    "map_extent": "지금 보고 있는 지도 범위가 필요합니다. 지도 화면에서 다시 말씀해 주세요.",
}
NO_CONTEXT_DEFAULT = "지도 화면에서 와야 하는 값이 없어 실행할 수 없습니다."

# workflow_materializer 의 판정 중 여기서 문장을 가르는 셋. 이름이 그쪽과 같아야 한다.
MISSING_ARGUMENT = "MISSING_ARGUMENT"
UNWIRED = "UNWIRED"
MISSING_CONTEXT = "MISSING_CONTEXT"

# 후보를 하나로 못 좁혔을 때의 머리말. 후보 수로 가른다.
CLARIFY_HEADLINE = "어느 것을 보시겠습니까?"
CLARIFY_MANY_HEADLINE = "여러 가지로 해석됩니다. 어느 것을 보시겠습니까?"

# 긴 머리말로 바뀌는 후보 수.
CLARIFY_MANY_FROM = 4

# 후보 줄에서 앞 단계를 잇는 표시.
STEP_JOIN = " -> "

# 배선이 아직 없어 골라도 실행되지 않는 후보에 붙이는 표시.
UNWIRED_MARK = " (아직 실행할 수 없음)"

# ── 진행 표시 ────────────────────────────────────────────────────────
#
# step_start / step_end 이벤트의 message. 도구 단계와 지도 명령이 같은 모양이라
# 부르는 화면이 따로 알아볼 것이 없다 — 도구 이름 자리에 지도 명령 op 이 온다.
RESOLVE_START = "발화를 해석하고 있습니다..."
STEP_START = "{name} 호출 중입니다..."
COMMAND_START = "{name} 명령을 내는 중입니다..."
STEP_DONE = "{name} 완료"
STEP_FAILED = "{name} 실패"


def unresolved_answer(resolved: Dict[str, Any], names: Dict[str, Any]) -> str:
    """고른 recipe 가 없을 때의 답.

    입력  resolve 결과(candidate_recipe_ids · reason 을 읽음) ·
          orchestrator.resolve_service.answer_names 가 낸 이름
    출력  후보가 있으면 머리말 한 줄과 번호 붙은 후보 목록. 없으면 영역 밖이라는
          한 문장과 안내 두 줄. 둘 다 뒤에 LLM 이 적은 이유가 붙음
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

    if not candidates:
        return no_match_answer(reason, names["topics"], names["starts"])

    head = _clarify_head(candidates, names["steps"], names["unwired"])
    return f"{head}\n\n{reason}".rstrip()


def _clarify_head(candidates: List[str], steps: Dict[str, List[str]], unwired: List[str]) -> str:
    """후보 목록을 사람이 고를 수 있는 모양으로.

    출력  머리말 한 줄 + 후보마다 한 줄. 앞에 번호가 붙음
    규칙  번호는 1부터. 사람이 몇째 것인지 세어 말할 수 있어야 함
          번호 자릿수를 맞춰 이름이 같은 칸에서 시작함
    제약  이 줄의 모양을 안 바꾼다. 화면에 보이는 되묻기 문구 그 자체임
    """
    labels = _candidate_labels(candidates, steps, unwired)
    width = len(str(len(labels)))
    headline = (
        CLARIFY_MANY_HEADLINE if len(labels) >= CLARIFY_MANY_FROM else CLARIFY_HEADLINE
    )

    lines = [
        f"  {str(number).rjust(width)}  {label}"
        for number, label in enumerate(labels, start=1)
    ]
    return "\n".join([headline, *lines])


def _candidate_labels(candidates: List[str], steps: Dict[str, List[str]], unwired: List[str]) -> List[str]:
    """후보마다 무엇을 하는 것인지 한 줄.

    입력  후보 recipe id 목록 · 후보마다 부를 노드 이름 · 배선이 없는 후보
    출력  후보와 같은 순서의 문자열 목록
    규칙  마지막 실행 노드의 이름이 그 recipe 가 결국 무엇을 하는지임
          마지막 이름이 겹치는 후보끼리는 앞 단계를 붙여 가름. 안 겹치는
          후보에는 안 붙임. 짧을수록 읽기 쉬움
          이름이 없으면 id 로 떨어짐. 사람에게 뜻은 없지만 줄이 사라지는 것보다
          나음
          배선이 없는 후보도 목록에 남기고 표시만 함. 온톨로지가 그 경로를
          안다는 것이 보여야 하고, 무엇이 안 붙었는지가 다음 할 일임
    """
    chains = {recipe_id: steps.get(recipe_id) or [] for recipe_id in candidates}
    tails: Dict[str, int] = {}
    for chain in chains.values():
        if chain:
            tails[chain[-1]] = tails.get(chain[-1], 0) + 1

    labels = []
    for recipe_id in candidates:
        chain = chains[recipe_id]
        if not chain:
            label = recipe_id
        elif tails[chain[-1]] > 1:
            label = STEP_JOIN.join(chain)
        else:
            label = chain[-1]

        if recipe_id in unwired:
            label += UNWIRED_MARK
        labels.append(label)

    return labels


def unready_answer(materialized: Dict[str, Any], paths: Optional[Dict[str, Any]]) -> str:
    """고른 recipe 를 지금 부를 수 없을 때의 답.

    입력  workflow_materializer.materialize 가 READY 아닌 판정으로 낸 것 ·
          resolve 결과의 paths(노드 이름을 읽음)
    출력  무엇이 모자라 못 부르는지 적은 문장
    규칙  MISSING_ARGUMENT  시작 노드로 무엇을 더 말할지 가름. 모르는 노드는 장소 문구
          UNWIRED           안 붙은 노드를 이름으로 적음. 이름이 없으면 id
          MISSING_CONTEXT   빠진 화면 값마다 한 줄. 받은 차례 그대로
          그 밖(NOT_ACCEPTED · NOTHING_TO_CALL) 은 부를 것이 없다는 답
    제약  무엇을 골랐는지 바꾸지 않는다. 못 부른다고만 말함
    """
    status = materialized.get("status")
    missing = materialized.get("missing") or []

    if status == MISSING_ARGUMENT:
        return NO_ARGUMENT_ANSWER.get(missing[0] if missing else None, NO_PLACE_ANSWER)

    if status == UNWIRED:
        path = (paths or {}).get(materialized.get("recipe_id")) or []
        named = {entry["node_id"]: entry["name"] for entry in path}
        return UNWIRED_ANSWER.format(
            names=" · ".join(named.get(node_id, node_id) for node_id in missing)
        )

    if status == MISSING_CONTEXT:
        return "\n".join(
            NO_CONTEXT_ANSWER.get(node_id, NO_CONTEXT_DEFAULT) for node_id in missing
        ) or NO_CONTEXT_DEFAULT

    return NO_TOOL_ANSWER


def resolve_end(status: Any, recipe_id: Optional[str]) -> str:
    """해석 단계가 끝났다는 진행 표시. 판정과 고른 recipe id."""
    return f"{status} {recipe_id or ''}".strip()


def step_start(tool: str) -> str:
    """도구 단계를 부르기 시작했다는 진행 표시."""
    return STEP_START.format(name=tool)


def command_start(op: str) -> str:
    """지도 명령을 내기 시작했다는 진행 표시. 도구 단계와 같은 자리에 op 이 옴."""
    return COMMAND_START.format(name=op)


def step_end(name: str, failed: bool = False) -> str:
    """단계 하나가 끝났다는 진행 표시. 도구 이름이나 지도 명령 op."""
    return (STEP_FAILED if failed else STEP_DONE).format(name=name)


def no_match_answer(reason: str, topics: List[str], starts: List[str]) -> str:
    """맞는 경로가 없을 때의 답.

    입력  발화 해석이 적은 이유 · 온톨로지의 대상 이름 · 시작 데이터 이름
    출력  첫 줄, 빈 줄, 이유, 빈 줄, 안내 두 줄
    규칙  이유가 비면 그 칸이 통째로 빠짐. 빈 줄만 남지 않음
          이름 목록이 비면 그 안내 줄도 빠짐. 온톨로지가 비었을 때 틀만
          남아 "제가 다루는 것은입니다" 가 되지 않아야 함
    """
    blocks = [NO_MATCH_HEADLINE]

    if reason.strip():
        blocks.append(reason.strip())

    guide = []
    if topics:
        guide.append(NO_MATCH_TOPICS.format(topics=NAME_JOIN.join(topics)))
    if starts:
        guide.append(NO_MATCH_STARTS.format(starts=NAME_JOIN.join(starts)))
    if guide:
        blocks.append("\n".join(guide))

    return "\n\n".join(blocks)
