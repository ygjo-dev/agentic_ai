"""발화를 recipe 로 해석하고, 그 노드 순서를 vendor 실행기에 넘긴다.

**실행·배선·답 조합은 우리 것이 아니다.** vendor_to_be_deleted/asap/generic_mcp_executor 의
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

**답 문구를 만드는 우리 쪽 vendor_to_be_deleted/asap/workflow_answer 를 부르는 자리가 둘이다.**
성공한 실행은 vendor 안에서 _compose_workflow_answer 가 부르고, 실패한 실행은
vendor 가 자기 문구(_failed_workflow_result)로 돌아오므로 아래 run 이 trace 로
다시 부른다. 같은 함수라 문구가 갈라지지 않는다.

**vendor 를 아예 안 지나는 실행이 하나 있다** (2026-08-29). 경로의 실행 노드가
전부 「부를 도구가 없는」 것이면 넘길 steps 가 비고, vendor 는 빈 steps 를
실패로 본다. 그때는 배선표가 만든 지도 명령을 그대로 내고 끝낸다 —
step_service.plan 의 commands 가 그것이다. 저쪽 show-facility plugin 이 하는
일이 그것이고, 그쪽도 `## Run` 절이 없다.
"""

from collections import Counter

from execution import reach_districts, shadow_districts, step_service
from ontology import graph, store
from orchestrator import resolve_service
from vendor_to_be_deleted.asap.command_renderer import build_commands_from_artifacts
from vendor_to_be_deleted.asap.generic_mcp_executor import _execute_generic_mcp_workflow
from vendor_to_be_deleted.asap.workflow_answer import (
    AREA_REFERENCE_INTENT_KEY,
    CUTOFFS_KEY,
    DEPARTURE_DATE_KEY,
    DEPARTURE_TIME_KEY,
    MODE_KEY,
    MODE_WORDS,
    SHADOW_KEY,
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
# **서버마다 한 줄이 있어야 한다.** refs 에 없는 서버의 도구를 부르면 Gateway 가
# 500 에 "MCP tool 'r5-server/compute_isochrone' is not applied for this user."
# 를 실어 돌려준다 — 도구가 /api/tools 에 보이고 인자가 맞아도 그렇다. 한 줄을
# 더하니 같은 호출이 200 이 됐다(2026-09-01 실측, NOTES.md 「일흔넷째」).
USER_CONTEXT = {
    "user_id": "asap-ontology-orchestrator",
    "selected_mcp_tool_refs": ["asap-mcp-core/*", "r5-server/*"],
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

# 부를 것이 하나도 없을 때의 답은 vendor_to_be_deleted/asap/workflow_answer.no_match_answer 가
# 만든다. 문구는 한 글자도 안 바뀌었고 뒤에 안내 두 줄이 붙는다.

# 배선에 sampled 가 적힌 노드를 무엇이 실행하는가.
#
# 둘 다 adminBoundary.findBoundaryByPoint 를 여러 번 부르고 도달권 응답을
# 읽는다. 갈리는 것은 어느 점을 찍느냐다 — 도달 범위 안이냐, 그 볼록 껍질
# 안이면서 도달 범위 밖이냐.
SAMPLED_RUNNERS = {
    "list_reach_districts": reach_districts.run,
    "list_shadow_districts": shadow_districts.run,
}

# 도구를 안 부르는 단계의 진행 표시. 도구 단계와 같은 모양이라 저쪽 화면이
# 따로 알아볼 것이 없다 — 그 자리에 도구 이름 대신 지도 명령 op 이 온다.
COMMAND_START = "{op} 명령을 내는 중입니다..."
COMMAND_END = "{op} 완료"

# 후보 줄에서 앞 단계를 잇는 표시.
STEP_JOIN = " -> "

# 배선이 아직 없어 골라도 실행되지 않는 후보에 붙이는 표시.
UNWIRED_MARK = " (아직 실행할 수 없음)"


# ── ★ 임시 · 보도자료용 이름표 ──────────────────────────────────
#
# **이것은 임시다. 보도자료 이미지를 찍고 나면 걷는다.**
# 걷는 자리가 이 파일 하나다 — 아래 표 넷(DISPLAY_NAME · RESOLVE_STEP_NAME ·
# REACH_HEADLINE · AREA_REFERENCE)과 그것을 쓰는 함수 넷(_relabel ·
# _reach_headline · _area_reference · _shown_name)을 지우고, run 과 chat 에서
# 부르던 네 줄을 되돌리면 끝난다.
# (2026-09-01 「일흔여덟째」·「일흔아홉째」. NOTES.md 「열린 과제」 22번.)
#
# **원천이 둘이 되는 것을 알고 한다.** 이름의 원천은 온톨로지의 노드 name 이고
# step_service 가 그것을 step 에 실어 보낸다. 여기 표는 그 위에 덧씌운다.
# 노드 이름을 고쳐도 표에 든 둘은 안 따라 바뀐다.
#
# **왜 온톨로지를 안 고치나.** 노드 name 은 프롬프트의 축 목록에도 실린다
# (ontology/shortlist.py:102). 이름을 바꾸면 발화 판정이 함께 흔들리고,
# 그것을 다시 재는 것이 이번 일이 아니다. 화면에 찍는 이름만 따로 둔다.
#
# **표에 없는 노드는 온톨로지 name 이 그대로 나간다.** 조용히 빈칸이 되면
# 어느 단계였는지가 화면에서 사라진다 — _shown_name 의 되돌아가는 차례가
# 이름표 -> 온톨로지 name -> node_id 다.
DISPLAY_NAME = {
    "geocode_place": "요청 장소",
    "compute_reach_area": "도달 범위",
}

# 화면에 안 내보낼 노드.
#
# **★ 임시 · 보도자료용이다** (2026-09-02). 발화("의왕역에서 30분 안에 갈 수
# 있는 곳을 보여 줘")가 물은 것은 도달 범위 하나다. 도달 지역(동 목록)과 음영
# 지역은 사용자가 요청한 것이 아닌데 답의 3 · 4번 줄과 지도의 점선을 차지한다.
#
# **노드도 배선도 안 지운다.** 온톨로지에도 배선에도 그대로 두고 이 표에 든
# 것만 부르지 않는다. 이 집합을 비우면 넷 다 예전대로 돌아온다 — 되돌리는
# 자리가 이 한 줄이다.
#
# 여기 든 것은 둘 다 sampled 노드(우리가 부르는 쪽)라 부르지 않으면 그것으로
# 끝난다 — 답의 줄도, 생성과정의 단계도, 음영 껍질 점선도 전부 그 응답에서
# 나오므로 함께 사라진다. vendor 가 부르는 단계였다면 이 방법이 안 통한다.
HIDDEN_NODES = {"list_reach_districts", "list_shadow_districts"}

# 색 판정기에 보일 겹 목록.
#
# **★ 임시 · 보도자료용이다** (2026-09-02). 겹을 [10, 20, 30] 셋에서 [30]
# 하나로 줄이면서 30분 겹의 색이 진홍(#B91C1C)에서 하늘색(#0EA5E9)으로
# 바뀌었다. 저쪽 판정기가 겹이 하나면 팔레트를 아예 안 보고 하늘색을 낸다
# (vendor_to_be_deleted/asap/command_renderer.py 의 _isochrone_color,
# `if len(cutoffs) == 1: return "#0EA5E9"`).
#
# **저쪽 파일은 안 고친다.** 판정기가 보는 겹 목록은 도구에 보낸 요청이 아니라
# **화면 조각(display artifact)의 cutoffs_minutes** 다 — 두 자리가 다르다.
# 배선(execution/wiring.yaml 의 reach_cutoffs)은 도구에 보내는 쪽이고 [30]
# 그대로 둔다. 그려지는 겹은 여전히 하나다.
#
# 이 목록을 화면 조각에만 얹으면 30분이 index 2 가 되어 팔레트의 마지막
# #B91C1C 가 나온다. 셋인 것이 중요하지 값이 중요한 것이 아니다 — 판정기는
# 목록에서 못 찾은 겹도 마지막 자리로 치므로(_isochrone_color 의 ValueError
# 갈래) 배선이 30이 아닌 값으로 바뀌어도 진홍이 그대로 나온다.
#
# 이 목록을 비우면 예전대로 하늘색으로 돌아온다 — 되돌리는 자리가 여기다.
PALETTE_CUTOFFS = [10, 20, 30]

# 발화를 해석하는 단계의 이름.
#
# **이 자리는 노드가 아니다.** 온톨로지에 없고 recipe 를 고르는 우리 단계다.
# 그래서 이름을 여기서 짓는다 — `resolve` 는 개발자 낱말이라 화면에 못 쓴다.
# 저쪽 화면이 자기 오케스트레이터의 parse_intent 를 「요청 이해」로 적고
# 있어(ASAP-web ChatPanel.PROCESS_STEP_META, 읽기만 했다) 같은 말을 쓴다.
# ★ 이것도 위 표와 함께 걷는다.
RESOLVE_STEP_NAME = "요청 이해"

# 답의 첫 줄.
#
# 배선의 headline 은 "{arg} 도달권을 계산했습니다." 한 마디다. 발화가 물은
# 것("30분 안에 갈 수 있는 곳")을 되돌려 주지 않아 답이 무엇에 대한 답인지
# 읽히지 않는다. **조건을 문장으로 되돌려 준다.**
#
# **값을 글자로 안 박는다.** 수단 · 자를 겹 · 날짜 · 시각이 전부 그 단계의
# 실제 호출 인자에서 온다(step 의 input. @today 와 배선의 departure_time 이
# 이미 채워져 있다). 배선을 고치면 첫 줄이 따라 움직인다.
#
# ★ 임시다. 아래 표와 함께 걷는다. **제대로 고치는 자리는 여기가 아니라**
# `execution/wiring.yaml` 의 headline 이다 — 다만 그 틀은 {arg} 하나만
# 채우므로 조건을 담으려면 틀 자체를 늘려야 한다.
REACH_HEADLINE_NODE = "compute_reach_area"
REACH_HEADLINE = "{arg}에서 {mode}{josa} {minutes}분 안에 닿을 수 있는 범위를 계산했습니다."
# 시·분만 두 자리로 채운다. 「8시 15분」보다 「08시 15분」이 시각으로 읽힌다.
REACH_CONDITION = "({year}년 {month}월 {day}일 {hour:02d}시 {minute:02d}분 출발 기준)"

# 면적을 견줄 넓이. **의왕역 전용이다.**
#
# 29.96 km² 가 넓은지 좁은지를 사람이 스스로 답할 수 없어 아는 넓이 하나에
# 댄다. **다른 장소에는 맞는 시군구 넓이가 없다.** 표에 없는 인자는 괄호가
# 통째로 안 나온다 — 아무 넓이나 갖다 대면 조용히 틀린 수가 붙는다.
#
# 54.02 km² 는 의왕시청 일반현황의 값이다(2025-12-31 기준).
# https://www.uiwang.go.kr — 시 소개 > 일반현황 > 면적.
#
# **넓이를 견준 것이지 도달 범위가 의왕시 안에 있다는 뜻이 아니다.**
# 실제로는 군포 · 안양 · 수원까지 걸친다(실측, NOTES.md 「일흔아홉째」).
# 문구를 「의왕시 전체 면적 …의 55%」로 적는 까닭이 그것이다.
AREA_REFERENCE = {
    "의왕역": {"name": "의왕시", "area_km2": 54.02},
}

# 음영 지역의 볼록 껍질 테두리. **점선 한 겹만 얹는다.**
#
# 음영 폴리곤을 통째로 칠하지 않은 까닭은 색이 넷이 되어 도달권 세 겹이
# 흐려지기 때문이다. 테두리는 색을 안 늘리고 「어디를 놓고 잰 것인가」만 말한다.
#
# ★ **저쪽 화면에 line-dasharray 가 없다** (ASAP-web 의
# packages/map/src/components/MapLibre2DMap.tsx, managed line 레이어를 읽기만
# 했다. `dasharray` 검색 0건). 그래서 점선을 **조각으로 나눠** 보낸다 —
# shadow_districts.dashes 가 그 일을 한다.
#
# **이름표는 선을 안 그리는 feature 하나가 따로 진다.** 같은 레이어의 label
# 층은 `$type == LineString` 이고 `showLabel == 1` 인 것을 고르는데(위 파일
# 1373~1380줄) 선을 그리는 층은 `outline != false` 를 함께 본다. 그래서 고리
# 전체를 `outline: false` 로 한 벌 더 보내면 선은 안 그려지고 글자만 테두리를
# 따라 붙는다. **`showLabel` 은 참이 아니라 1 이다** — 저쪽 필터가 수 1 과
# 견준다.
#
# 이름을 붙이는 까닭은 껍질 안쪽 전체가 음영으로 읽히는 것을 막기 위해서다.
# 실제 음영은 그 안에서 도달권 세 겹을 뺀 나머지다.
SHADOW_HULL_LAYER = "shadow-hull"
SHADOW_HULL_LABEL = "음영 지역 판정 범위"
SHADOW_HULL_COLOR = "#6B7280"
SHADOW_HULL_WIDTH = 2
# 획과 틈의 길이(m). 껍질 둘레가 28.6km 라 획 29개가 된다 (2026-09-01 실측).
SHADOW_DASH_M = 600.0
SHADOW_GAP_M = 400.0


async def run(recipe_id: str, argument: str, text: str = "", context: dict | None = None):
    """recipe 의 노드 순서대로 도구를 부름. 이벤트를 차례로 냄.

    입력  recipe id · 발화에서 뽑은 인자 · 원 발화 · 저쪽 화면이 보낸 context
    출력  이벤트 dict 를 순서대로 냄. 마지막은 반드시 type=result
          step_start / step_end 는 실제로 불린 단계마다 한 쌍
    규칙  경로에 도구가 안 붙은 노드가 있으면 하나도 안 부르고 그렇다고 답함.
          부르는 것만 부르면 반쪽 결과를 온전한 답인 것처럼 내놓게 됨
          부를 도구가 없고 지도 명령만 있으면 vendor 를 안 지남. 빈 steps 를
          넘기면 vendor 가 실패로 보고, 부를 것이 없는데 부를 이유도 없음
          지도 명령이 도구 단계와 함께 있으면 도구 응답에서 나온 명령 뒤에
          붙임. 순서가 곧 경로 순서임
          부를 것도 낼 것도 없으면 곧장 result
          ★ 화면에 나가는 이름은 이름표를 한 번 지남. 답의 단계 이름과
            이벤트의 node 가 같은 표를 보므로 두 곳이 갈리지 않음
            (임시다 — 위 「보도자료용 이름표」)
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
    # ★ 임시 · 보도자료용. 화면에 안 내보낼 노드를 여기서 한 번 걷는다.
    # 뒤로는 이 목록만 보므로 부르는 것 · 답의 줄 · 생성과정의 단계 ·
    # 지도 명령이 한 자리에서 함께 줄어든다 (위 HIDDEN_NODES).
    plan["sampled_nodes"] = [
        node_id for node_id in plan["sampled_nodes"] if node_id not in HIDDEN_NODES
    ]
    named = {entry["node_id"]: entry["name"] for entry in graph.path_of(recipe_id)}
    _relabel(plan["steps"], plan["nodes"])
    plan["headline"] = (
        _reach_headline(plan["steps"], plan["nodes"], argument) or plan["headline"]
    )
    if not plan["steps"] and not plan["commands"]:
        yield _result("부를 도구가 없습니다.", [])
        return

    if not plan["steps"]:
        for node_id, command in zip(plan["command_nodes"], plan["commands"]):
            op = command["op"]
            shown = _shown_name(node_id, named)
            yield {
                "type": "step_start",
                "node": shown,
                "message": COMMAND_START.format(op=op),
            }
            yield {
                "type": "step_end",
                "node": shown,
                "message": COMMAND_END.format(op=op),
            }
        yield _result(command_answer(plan["headline"]), plan["commands"])
        return

    intent = {
        "action": WORKFLOW_ACTION,
        "steps": plan["steps"],
        "answer_instruction": plan["headline"],
    }
    reference = _area_reference(argument)
    if reference:
        intent[AREA_REFERENCE_INTENT_KEY] = reference
    state = {
        "user_text": text,
        "context": context or {},
        "user_context": dict(USER_CONTEXT),
        "intent": intent,
    }

    executed = await _execute_generic_mcp_workflow(state, intent)

    trace = _trace(executed)
    sampled = await _sampled(plan["sampled_nodes"], trace)
    _name_sampled(intent, plan["sampled_nodes"], named)

    for node_id, item in zip(plan["nodes"] + plan["sampled_nodes"], trace + sampled):
        tool = item.get("tool") or ""
        shown = _shown_name(node_id, named)
        yield {"type": "step_start", "node": shown, "message": f"{tool} 호출 중입니다..."}
        outcome = "실패" if step_failed(item) else "완료"
        yield {"type": "step_end", "node": shown, "message": f"{tool} {outcome}"}

    yield _result(
        _answer(intent, executed, sampled),
        _repainted_commands(executed) + plan["commands"] + _shadow_commands(sampled),
    )


async def chat(
    text: str,
    llm_client,
    reason_max_length: int,
    context: dict | None = None,
):
    """발화 한 건을 끝까지. 해석하고 부르고 답을 만듦.

    입력  발화 · LLM 클라이언트 · reason 길이 상한 · 저쪽 화면의 context
    출력  이벤트 dict 를 순서대로 냄. 마지막은 반드시 type=result
    규칙  발화 한 건이 한 건으로 끝남. 앞 발화를 기억해 두지 않으므로
          "1번" 도 다른 말과 똑같이 새 발화로 해석됨
          해석도 한 단계로 냄. 저쪽 화면이 진행 상황을 그림
          문맥을 해석에도 넘김. 화면에서 온 값으로 시작하는 recipe 는 그 값이
          실제로 와 있을 때만 후보가 됨 — 없는 좌표로 도구를 부르지 않음
          SELECT 가 아니면 도구를 하나도 안 부름. CLARIFY 는 후보가 여럿이라
          무엇을 부를지 정해지지 않았고, NO_MATCH 는 부를 것이 없음
          인자는 LLM 이 argument 로 준 것을 먼저 씀. 그것이 없을 때만
          place_in 이 장소를 뽑음. 정규식은 장소 어절 하나밖에 못 봄
          인자를 못 뽑으면 부르지 않고 안내만 함. 무엇을 조회할지 정해지지
          않았는데 부르면 엉뚱한 곳이 나옴
          화면에서 온 값으로 시작하는 recipe 는 인자가 없어도 부름.
          "지금 보이는 곳 CCTV 보여줘" 에는 뽑을 말이 없고, 조회할 곳은
          이미 문맥이 말했음
    제약  여기서 LLM 클라이언트를 만들지 않는다.
          app.api.main 의 make_client 를 갈아끼우는 테스트가 죽음
          상태를 두지 않는다.
          2026-09-01 에 세션을 걷었다. 되묻기 뒤에 「1번」으로 고르던 한
          걸음이 그것을 쓰던 유일한 자리였다 — 되묻기 자체는 그대로 난다
    """
    yield {
        "type": "step_start",
        "node": RESOLVE_STEP_NAME,
        "message": "발화를 해석하고 있습니다...",
    }
    resolved = resolve_service.resolve(
        text,
        llm_client=llm_client,
        reason_max_length=reason_max_length,
        context=context,
    )
    recipe_id = resolved.get("recipe_id")
    yield {
        "type": "step_end",
        "node": RESOLVE_STEP_NAME,
        "message": f"{resolved.get('status')} {recipe_id or ''}".strip(),
    }

    if resolved.get("status") != "SELECT" or not recipe_id:
        yield _result(_no_recipe_answer(resolved), [])
        return

    argument = resolved.get("argument") or step_service.place_in(text)
    if not argument and not _from_screen(resolved.get("given")):
        yield _result(_no_argument_answer(resolved.get("given")), [])
        return

    async for payload in run(recipe_id, argument, text=text, context=context):
        yield payload


def _relabel(steps: list[dict], nodes: list[str]) -> None:
    """★ 임시 · 보도자료용. 답에 찍히는 단계 이름을 이름표로 갈아 끼운다.

    입력  step_service.plan 의 steps · 같은 차례의 노드 id 목록
    출력  없음. steps 를 그 자리에서 고침
    규칙  DISPLAY_NAME 에 있는 노드만 갈아 끼움. 없는 노드는 손대지 않아
          step_service 가 실어 둔 온톨로지 name 이 그대로 남음
          steps 와 nodes 는 step_service.plan 이 같은 차례로 쌓음
    제약  이름이 없는 노드에 뭔가를 지어 넣지 않는다.
          그때는 workflow_answer 가 도구 이름으로 되돌아가는 것이 맞다 —
          그것이 이 표가 있기 전부터 서 있던 규칙이다
    ★ 이 함수는 DISPLAY_NAME 과 함께 걷는다. 표가 없으면 부를 이유가 없다
    """
    for node_id, step in zip(nodes, steps):
        label = DISPLAY_NAME.get(node_id)
        if label:
            step[step_service.STEP_NAME] = label


def _reach_headline(steps: list[dict], nodes: list[str], argument: str) -> str:
    """★ 임시 · 보도자료용. 도달 범위를 물은 답의 첫 줄. 그 경로가 아니면 "".

    입력  step_service.plan 의 steps · 같은 차례의 노드 id 목록 · 발화의 인자
    출력  두 줄. 무엇을 계산했는지와 괄호 안의 조건
    규칙  REACH_HEADLINE_NODE 가 이번 실행에 들었을 때만 지음
          수단 · 자를 겹 · 날짜 · 시각을 그 단계의 실제 호출 인자에서 읽음
          넷 중 하나라도 못 읽으면 "". 반만 채운 문장을 내지 않음
          자를 겹은 제일 큰 것 하나. 지도의 바깥 겹이자 면적을 잰 겹임
    제약  값을 여기에 적지 않는다.
          날짜와 시각과 겹은 배선이 정하고 step 의 input 에 이미 채워져 있다
    ★ 이 함수는 REACH_HEADLINE 과 함께 걷는다
    """
    tool_input = _input_of(REACH_HEADLINE_NODE, steps, nodes)
    if tool_input is None:
        return ""

    mode = MODE_WORDS.get(tool_input.get(MODE_KEY))
    minutes = _largest_cutoff(tool_input.get(CUTOFFS_KEY))
    when = _departure(tool_input)
    if not mode or minutes is None or when is None:
        return ""

    year, month, day, hour, minute = when
    first = REACH_HEADLINE.format(
        arg=argument, mode=mode, josa=_with_josa(mode), minutes=minutes
    )
    second = REACH_CONDITION.format(
        year=year, month=month, day=day, hour=hour, minute=minute
    )
    return f"{first}\n{second}"


def _input_of(node_id: str, steps: list[dict], nodes: list[str]):
    """그 노드가 실제로 부른 인자. 경로에 없으면 None."""
    for other_id, step in zip(nodes, steps):
        if other_id == node_id and isinstance(step.get("input"), dict):
            return step["input"]
    return None


def _largest_cutoff(values):
    """제일 큰 자를 겹. 셀 것이 없으면 None.

    규칙  정수 목록이어야 함. bool 은 수로 안 봄
    """
    if not isinstance(values, list):
        return None
    numbers = [
        value
        for value in values
        if not isinstance(value, bool) and isinstance(value, (int, float))
    ]
    return int(max(numbers)) if numbers else None


def _departure(tool_input: dict):
    """출발 날짜와 시각을 숫자 다섯으로. 못 읽으면 None.

    출력  (연, 월, 일, 시, 분). 앞의 0 을 뗀 정수임
    규칙  "2026-09-01" 과 "08:15" 꼴만 읽음. 다른 꼴이면 None
    제약  날짜를 여기서 만들지 않는다.
          오늘 날짜는 배선의 @today 를 step_service 가 이미 채웠다
    """
    date = tool_input.get(DEPARTURE_DATE_KEY)
    time = tool_input.get(DEPARTURE_TIME_KEY)
    if not isinstance(date, str) or not isinstance(time, str):
        return None

    parts = date.split("-") + time.split(":")
    if len(parts) != 5 or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _with_josa(word: str) -> str:
    """그 낱말 뒤에 붙는 조사. "로" 또는 "으로".

    규칙  끝 글자에 받침이 없거나 받침이 ㄹ 이면 "로". 아니면 "으로"
          한글이 아니면 "로". 「대중교통으로」·「도보로」·「자전거로」
    """
    if not word:
        return "로"
    code = ord(word[-1]) - 0xAC00
    if code < 0 or code > 11171:
        return "로"
    final = code % 28
    return "로" if final in (0, 8) else "으로"


def _area_reference(argument: str):
    """★ 임시 · 보도자료용. 면적을 견줄 넓이. 그 장소가 표에 없으면 None.

    입력  발화에서 뽑은 인자
    출력  workflow_answer 가 읽는 {name, area_km2}
    제약  표에 없는 장소에 아무 넓이나 대지 않는다.
          조용히 틀린 수가 화면에 붙는다. 없으면 괄호가 통째로 안 나온다
    ★ 이 함수는 AREA_REFERENCE 와 함께 걷는다
    """
    return AREA_REFERENCE.get((argument or "").strip())


def _shown_name(node_id: str, named: dict) -> str:
    """★ 임시 · 보도자료용. 생성과정 화면에 찍힐 단계 이름.

    입력  노드 id · {노드 id: 온톨로지 name}
    출력  화면에 그대로 나갈 한 마디. 절대 빈 문자열이 아님
    규칙  이름표 -> 온톨로지 name -> node_id 차례로 되돌아감
          답과 같은 표를 봄. 두 곳이 다른 말을 하면 안 됨
    제약  빈칸을 내놓지 않는다.
          저쪽 화면이 이 값을 단계의 제목으로 그대로 찍고(ASAP-web
          ChatPanel.getStepMeta, 읽기만 했다) step_start 와 step_end 를
          맞추는 열쇠로도 쓴다. 비면 단계가 사라진다
    ★ 이 함수는 DISPLAY_NAME 과 함께 걷는다
    """
    label = DISPLAY_NAME.get(node_id)
    if label:
        return label
    name = named.get(node_id)
    return name.strip() if isinstance(name, str) and name.strip() else node_id


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


def _answer(intent: dict, executed: dict, sampled: list | None = None) -> str:
    """이 실행에 보일 답 한 벌.

    입력  vendor 에 넘긴 intent · vendor 가 돌려준 것 · 우리가 부른 단계들
    출력  화면에 그대로 나갈 문자열
    규칙  errors 가 있으면 trace 로 우리가 다시 만듦. 이때 failed 를 넘김.
          vendor 는 중단할 때 대개 trace 에 아무것도 안 남기고, 남은 마지막
          항목은 성공한 앞 단계라 trace 만 보면 성공으로 읽힘
          우리가 부른 단계가 있으면 그것을 trace 뒤에 붙여 다시 만듦.
          vendor 의 answer_draft 는 그 단계를 모름
          둘 다 없으면 vendor 의 answer_draft. 그 안에서 이미
          workflow_answer 가 만든 것임
          trace 가 비면 단계 목록 없이 첫 줄만 나옴
    제약  답을 두 번 짓지 않는다.
          vendor 도 같은 함수로 answer_draft 를 만든다. 여기서 다시 짓는
          것은 vendor 가 모르는 것이 붙었을 때뿐이다
    """
    if executed.get("errors"):
        return compose_workflow_answer(intent, _trace(executed), failed=True)
    if sampled:
        return compose_workflow_answer(intent, _trace(executed) + sampled)
    return executed.get("answer_draft") or ""


def _name_sampled(intent: dict, nodes: list[str], named: dict) -> None:
    """우리가 부른 단계의 이름을 답까지 실어 보냄.

    입력  vendor 에 넘겼던 intent · sampled 노드 id 목록 · 온톨로지 name 한 벌
    출력  없음. intent["steps"] 에 이름만 든 항목을 덧붙임
    규칙  vendor 가 이미 돌고 난 뒤에 부름. steps 를 늘려도 부를 것이 안 늘어남
          id 를 노드 id 로 씀. _sampled 가 항목에 붙이는 id 와 같아야 함
          이름은 도구 단계와 같은 표를 봄. 두 곳이 다른 말을 하면 안 됨
    제약  vendor 를 부르기 전에 부르지 않는다.
          steps 에 tool 이 없는 항목이 들면 vendor 가 그 자리에서 실패한다
    """
    for node_id in nodes:
        intent["steps"].append(
            {"id": node_id, step_service.STEP_NAME: _shown_name(node_id, named)}
        )


async def _sampled(nodes: list[str], trace: list[dict]) -> list[dict]:
    """vendor 가 아니라 우리가 부르는 단계들. 없으면 빈 목록.

    입력  배선에 sampled 가 적힌 노드 id 목록 · vendor 가 쌓은 trace
    출력  trace 항목과 같은 모양의 목록. 부른 차례
    규칙  vendor 가 마지막에 부른 것의 응답을 노드마다 그대로 넘김. 이 노드들은
          경로의 끝에 늘어서고 둘 다 도달권 폴리곤을 읽음. 앞 sampled 노드가
          내놓는 것은 동 이름뿐이라 이어 받을 것이 없음
          어느 노드를 무엇이 실행하는지는 SAMPLED_RUNNERS 가 앎. 표에 없는
          노드는 건너뜀
          앞에 성공한 단계가 하나도 없으면 아무것도 안 부름. 받을 것이 없음
          앞 단계가 실패했으면 안 부름. vendor 가 거기서 멈춘 것이라
          이어서 부를 근거가 없음
          한 단계가 실패하면 뒤엣것도 안 부름. 같은 응답을 읽으므로 앞이
          못 읽은 것을 뒤가 읽을 수 있을 리 없음
          Gateway 창에 보낸 건수를 노드 사이에 이어 셈. 둘이 따로 세면 뒤엣
          노드가 앞 노드의 건수를 모른 채 보내 한도에 걸림
          항목의 id 를 노드 id 로 붙임. 답이 그 id 로 단계 이름을 찾음
    제약  여기서 도구를 부르지 않는다.
          무엇을 어떻게 부르는지는 execution/reach_districts ·
          execution/shadow_districts 가 안다
    """
    if not nodes or not trace:
        return []
    last = trace[-1]
    if step_failed(last) or "result" not in last:
        return []

    done = []
    sent = 0
    for node_id in nodes:
        runner = SAMPLED_RUNNERS.get(node_id)
        if runner is None:
            continue
        item, sent = await runner(
            step_service.TOOL_OF[node_id], last["result"], dict(USER_CONTEXT), sent
        )
        item["id"] = node_id
        done.append(item)
        if step_failed(item):
            break
    return done


def _shadow_commands(sampled: list[dict]) -> list[dict]:
    """★ 임시 · 보도자료용. 음영 지역의 볼록 껍질 테두리를 그리는 명령. 없으면 빈 목록.

    입력  _sampled 가 낸 항목들
    출력  map.clear 하나와 map.draw 하나. 그리기 전에 지움
    규칙  껍질을 실어 온 항목이 있을 때만 냄. 실패한 항목에는 없음
          획을 조각으로 나눠 보냄. 저쪽에 점선 속성이 없음
          이름표는 선을 안 그리는 feature 한 벌이 따로 짐
          지도 명령 뒤에 붙임. 나중에 그린 것이 위에 올라감
    제약  음영 폴리곤을 칠하지 않는다.
          색이 넷이 되어 도달권 세 겹이 흐려진다. 그것은 사람이 정한 값이다
    ★ 이 함수는 SHADOW_HULL_LAYER 무리와 함께 걷는다
    """
    hull = None
    for item in sampled:
        shadow = (item.get("result") or {}).get(SHADOW_KEY)
        if isinstance(shadow, dict):
            hull = shadow.get(shadow_districts.HULL_KEY)
    if not isinstance(hull, dict):
        return []

    segments = shadow_districts.dashes(hull, SHADOW_DASH_M, SHADOW_GAP_M)
    if not segments:
        return []

    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [list(point) for point in segment],
            },
            "properties": {
                "id": f"{SHADOW_HULL_LAYER}-{index}",
                "name": SHADOW_HULL_LABEL,
                "color": SHADOW_HULL_COLOR,
                "outlineColor": SHADOW_HULL_COLOR,
                "width": SHADOW_HULL_WIDTH,
            },
        }
        for index, segment in enumerate(segments)
    ]
    features.append(
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [list(point) for point in hull["coordinates"][0]],
            },
            "properties": {
                "id": f"{SHADOW_HULL_LAYER}-label",
                "name": SHADOW_HULL_LABEL,
                "label": SHADOW_HULL_LABEL,
                "showLabel": 1,
                "outline": False,
            },
        }
    )
    return [
        {"op": "map.clear", "args": {"layerId": SHADOW_HULL_LAYER}},
        {"op": "map.draw", "args": {"layerId": SHADOW_HULL_LAYER, "features": features}},
    ]


def _trace(executed: dict) -> list[dict]:
    """vendor 가 쌓은 단계 기록. 성공이든 실패든 같은 자리에 있음."""
    artifacts = executed.get("artifacts") or {}
    return artifacts.get("mcp_workflow_trace") or []


def _repainted_commands(executed: dict) -> list[dict]:
    """★ 임시 · 보도자료용. 30분 겹을 진홍으로 되돌린 지도 명령.

    입력  vendor 가 돌려준 것
    출력  _commands 와 같은 모양. 고칠 것이 없으면 _commands 그대로
    규칙  화면 조각의 겹 목록이 하나일 때만 PALETTE_CUTOFFS 로 갈아 끼우고
          저쪽 판정기를 **한 번 더 부른다**. 색을 여기서 적지 않고 팔레트가
          고르게 두는 것이 요점임
          갈아 끼운 것이 없으면 vendor 가 이미 만든 명령을 그대로 씀
    제약  색을 코드에 적지 않는다.
          #B91C1C 는 저쪽 팔레트의 마지막 칸이고 그 표는 저쪽 것이다.
          여기에 색을 박으면 표가 바뀌어도 이 줄만 조용히 옛 색으로 남는다
          그리는 겹을 안 늘린다.
          갈아 끼우는 것은 색을 고르는 목록뿐이고 폴리곤은 그대로다.
          화면 조각의 data 는 저쪽 inspector 가 새로 지은 dict 라 도구 응답과
          따로 논다 — 여기를 고쳐도 trace 도 답 문구도 안 움직인다
    ★ 이 함수는 PALETTE_CUTOFFS 와 함께 걷는다. 목록이 비면 부를 이유가 없다
    """
    if not PALETTE_CUTOFFS:
        return _commands(executed)

    artifacts = (executed.get("artifacts") or {}).get("display_artifacts") or []
    repainted = False
    for artifact in artifacts:
        if artifact.get("kind") != "isochrone":
            continue
        data = artifact.get("data")
        if not isinstance(data, dict):
            continue
        if len(data.get("cutoffs_minutes") or []) != 1:
            continue
        data["cutoffs_minutes"] = list(PALETTE_CUTOFFS)
        repainted = True

    if not repainted:
        return _commands(executed)
    return _commands({"commands": build_commands_from_artifacts(artifacts)})


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

    입력  후보 recipe id 목록 · resolve 가 붙인 후보별 경로
    출력  머리말 한 줄 + 후보마다 한 줄. 앞에 번호가 붙음
    규칙  번호는 1부터. 사람이 몇째 것인지 세어 말할 수 있어야 함
          번호 자릿수를 맞춰 이름이 같은 칸에서 시작함
    제약  이 줄의 모양을 안 바꾼다.
          화면에 보이는 되묻기 문구 그 자체다. 2026-09-01 에 세션을 걷으면서
          이 줄을 「1번」이라고 답해 고르던 뒷걸음은 없어졌지만, 문구는 한
          글자도 안 바뀌었다
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
