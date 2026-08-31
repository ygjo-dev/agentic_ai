"""발화 → Recipe 해석. route_resolver 호출 + 온톨로지 조회로 후보 좁히기.

길이 둘이다. **기본은 지금 길(끔)이다.** 어느 쪽을 탈지는 사람이 재고 정한다.

  지금 길(narrow=False)  LLM 을 한 번 부른다. 그 한 번에 축 셋(given · want ·
                         about)과 recipe 를 함께 받아, 축으로 온톨로지에서 후보를
                         뽑고 LLM 이 고른 목록과 대조한다(_verdict).
  좁히기 길(narrow=True) LLM 을 두 번 부른다. 1차는 menu 없이 축 셋만 받고,
                         온톨로지가 그 축으로 후보를 2~5개로 좁힌 뒤, 2차가 그
                         후보 문장만 보고 하나를 고른다. 후보가 하나면 2차를
                         안 부른다. 빠져나갈 길이 둘이다 — 조회 후보가 비면(가),
                         2차가 "여기 없다" 고 하면(나) 지금 길로 간다.

**끄면 지금과 한 글자도 다르지 않아야 한다.** 그래서 지금 길의 몸통은
_resolve_full 로 이름만 옮기고 안을 안 건드렸다. 응답에 key 도 안 더한다.
좁히기 길의 응답에만 `narrow` 한 칸이 더 실린다.

## 화면에서 온 값 — 문맥이 없으면 그 축 선택지도 후보도 없다 (2026-08-28)

시작 데이터 노드가 다섯이 됐다. 뒤의 둘(찍은 지점 · 보이는 범위)은 발화가
아니라 저쪽 화면이 보내는 지도 문맥에서 값을 받는다. **그 값이 안 왔으면 그
둘은 아예 없는 것처럼 굴어야 한다** — Streamlit 은 문맥을 안 보내고, 없는
좌표로 도구를 부르면 전국이 나오거나 null 로 거부당한다.

판단이 서는 자리가 둘이다. 둘을 한 자리에 몰지 않았다.

  값이 있는가   여기(_choices_for · _without_dropped). 기계가 센다. 문맥의 칸을 보고
                축 선택지와 조회 후보에서 빼 버린다. LLM 은 그 선택지를
                본 적이 없으므로 고를 수가 없다
  그것을 쓸까   온톨로지의 노드 description. LLM 이 발화를 보고 고른다.
                "발화가 장소 이름 대신 여기나 이 위치라고 가리킬 때 쓴다" 가
                그 문장이다

**왜 판단을 프롬프트 파일이 아니라 노드 설명에 적었나.** 축 선택지 문장은
shortlist._describe 가 노드의 name 과 description 으로 만들어 프롬프트에
그대로 싣는다. 저쪽도 같은 자리에 적어 두었다 —
KRRI_ASAP/ASAP-orchestrator/app/agents/nodes/parse_intent.py 가 문맥이 있을 때만
"If the user says here, this place, …" 한 줄을 프롬프트에 덧붙인다. 우리는
프롬프트 파일을 이번 범위에서 안 건드리므로, 같은 말을 적을 데가 노드
description 뿐이기도 하다.

## 프롬프트에 넣을 menu 를 요청마다 고른다 — ★ 임시방편 (2026-08-29)

시작 데이터가 둘 늘면서 menu 가 3322 -> 4833자가 됐고 문맥 없는 요청의 판정이
16 내렸다. 그래서 **발화가 화면을 가리키느냐로 menu 를 가른다** — 가리키고 그
값이 와 있으면 화면 recipe 만, 아니면 기존 마흔만 프롬프트에 실린다.
가르는 것은 낱말이고 LLM 을 더 부르지 않는다. `_menu_for` · `SCREEN_WORDS` 를
본다. **월요일 시연을 위한 임시방편이다** — 까닭과 한계는 그 자리에 적었다.
"""

import os
import time

import yaml

import paths
from execution import step_service
from ontology import graph, shortlist
from orchestrator.route_resolver import resolve_route
from orchestrator.schemas.response_schema import (
    CLARIFY,
    NO_MATCH,
    SELECT,
    axis_selection_schema,
    recipe_pick_schema,
    recipe_selection_schema,
)
from workflows.static.menu.load import load_menu

# 좁히기 길의 프롬프트 둘. paths.py 에 안 박은 것은 두 길이 함께 사는 동안의
# 임시 자리라서다. 어느 쪽으로 정해지면 그때 옮긴다.
AXES_PROMPT_PATH = paths.PROMPTS_DIR / "recipe_axes.md"
PICK_PROMPT_PATH = paths.PROMPTS_DIR / "recipe_pick.md"

# 스위치의 기본값을 주는 환경변수. "1" 이면 켬. **없으면 끔(지금 길)이다.**
#
# /resolve 는 query 로 켤지 끌지를 받지만 /chat 은 저쪽 화면의 계약이라 인자를
# 못 더한다. 화면에서 켠 상태를 보려면 이 변수로 서버를 띄운다.
NARROW_ENV = "RESOLVE_NARROW"

# 폴백 둘의 이름. 응답의 narrow.fallback 에 실린다.
FALLBACK_EMPTY = "empty"  # 가) 조회 후보가 비었다
FALLBACK_NONE = "none"    # 나) 2차가 "여기 없다" 고 했다


def narrow_default() -> bool:
    """스위치를 안 줬을 때의 값. 환경변수가 "1" 일 때만 켬."""
    return os.environ.get(NARROW_ENV, "") == "1"


def resolve(
    utterance: str,
    llm_client,
    reason_max_length: int,
    narrow: bool | None = None,
    context: dict | None = None,
) -> dict:
    """발화를 recipe 로. narrow 가 None 이면 환경변수, 그것도 없으면 끔.

    입력  발화 · LLM 클라이언트 · reason 길이 상한 · 좁히기 길을 탈지 ·
          저쪽 화면이 보낸 지도 문맥(없으면 없는 것으로)
    출력  _resolve_full 또는 _resolve_narrow 의 결과. key 는 아래 docstring 에
    제약  narrow 를 안 줬을 때 지금 길이어야 한다.
          /chat 은 이 인자를 안 넘긴다. 기본값이 바뀌면 시연 화면이 바뀐다
          context 를 안 줬을 때 문맥이 없는 것과 똑같아야 한다.
          2026-08-29 부터 Streamlit 과 dev/tools/check_resolve.py 도 넘기지만,
          --context none 과 옛 부름이 이 자리를 그대로 지남
    """
    if narrow is None:
        narrow = narrow_default()
    if narrow:
        return _resolve_narrow(utterance, llm_client, reason_max_length, context)
    return _resolve_full(utterance, llm_client, reason_max_length, context)


def _choices_for(context: dict | None) -> dict:
    """축 선택지에서 문맥이 못 채우는 시작 데이터를 뺀 것.

    입력  저쪽 화면이 보낸 지도 문맥. 없으면 None
    출력  shortlist.axis_choices() 와 같은 모양
    규칙  뺄 것이 없으면 받은 것을 그대로 돌려줌. 문맥을 안 보내는 쪽에서
          한 글자도 달라지지 않아야 함
          given 목록과 described.given 에서 함께 뺌. 둘 중 하나만 빼면
          프롬프트에는 보이는데 스키마가 막는 선택지가 생김
          described 의 줄은 shortlist._describe 가 "- <id>  (" 로 시작하게
          만듦. 그 앞머리로 고름
    제약  shortlist 를 안 고친다.
          거기는 온톨로지가 무엇을 낼 수 있는지 말하는 자리이고, 이번 요청에
          무엇이 왔는지는 요청을 받는 이 자리가 안다
    """
    choices = shortlist.axis_choices()
    dropped = _dropped_starts(context)
    if not dropped:
        return choices

    given = [node_id for node_id in choices["given"] if node_id not in dropped]
    lines = [
        line
        for line in choices["described"]["given"].split("\n")
        if not any(line.startswith(f"- {node_id}  (") for node_id in dropped)
    ]
    return {
        **choices,
        "given": given,
        "described": {**choices["described"], "given": "\n".join(lines)},
    }


def _dropped_starts(context: dict | None) -> set[str]:
    """이번 요청에서 값을 못 받는 화면 시작 데이터 노드.

    출력  노드 id 집합. 문맥이 다 갖췄으면 빈 집합
    규칙  무엇이 화면에서 오는지는 step_service.CONTEXT_STARTS 가 앎.
          여기서 노드 id 를 다시 적지 않음
    """
    return set(step_service.CONTEXT_STARTS) - set(step_service.context_starts(context))


def _without_dropped(recipe_ids: list[str], dropped: set[str]) -> list[str]:
    """값을 못 받는 시작 데이터에서 출발하는 recipe 를 뺀 목록.

    입력  recipe id 목록 · 뺄 시작 데이터 노드 id 집합
    출력  차례를 지킨 목록. 뺄 것이 없으면 받은 것 그대로
    규칙  경로의 첫 칸이 곧 시작 데이터임. 그것을 보고 가름
          타입 판정은 ontology.graph 가 함. 여기서 recipe 파일을 열지 않음
    제약  shortlist.candidates 로 막을 목록을 만들지 않는다.
          그것은 축 셋으로 후보를 뽑는 자리이고, 여기서 또 부르면 요청마다
          전체 recipe 를 두 번 더 훑게 됨
          menu 에서 그 문장을 지우지 않는다.
          menu 는 온톨로지가 만드는 것이고 요청마다 다를 수 없음. 지울 수
          없으니 LLM 이 그것을 골라도 여기서 뺀다
    이력  2026-08-29 에 그 제약을 깼다. _menu_for 가 요청마다 menu 를 가른다.
          까닭과 임시방편이라는 것은 SCREEN_WORDS 위 주석에 있다.
          이 자리는 그대로 둔다. 축 조회는 menu 를 안 보고 뽑으므로 menu 에서
          뺀 뒤에도 여기서 한 번 더 걸러야 한다
    """
    if not dropped:
        return recipe_ids
    return [recipe_id for recipe_id in recipe_ids if _starts_at(recipe_id) not in dropped]


def _starts_at(recipe_id: str) -> str | None:
    """그 recipe 가 무엇에서 출발하는가.

    출력  경로 첫 칸의 노드 id. 경로가 비면 None
    """
    path = graph.path_of(recipe_id)
    return path[0]["node_id"] if path else None


# ── 프롬프트에 넣을 menu 를 요청마다 고른다 ────────────────────────
#
# 발화가 화면을 가리키느냐로 menu 를 가른다. 가리키고 그 값이 와 있으면 화면
# recipe 만, 아니면 기존 recipe 마흔만 프롬프트에 실린다. 어느 쪽이든 짧다.
#
#   화면 recipe   경로 첫 칸이 picked_point 또는 visible_extent 인 것
#                 둘 다 오면 열아홉 1535자. 우클릭 전이면 열 809자
#   기존 마흔     그 밖. 3322자. 화면 노드가 붙기 전 menu 와 본문이 같다
#
# 화면·도구마다 다르게 하지 않는다. Streamlit 도 저쪽도 같은 발화에 같은 menu
# 를 본다. 가르는 것은 발화와 문맥이지 부르는 쪽이 아니다.
#
# 이것은 월요일 시연을 위한 임시방편이다. 아래 목록에 없는 말투는 화면 recipe
# 를 아예 못 본다 ("내가 보고 있는 데 CCTV" · 장소 없는 "CCTV 보여줘").
# 후보에서 빼는 것이 아니라 보여주지도 않는 것이라 LLM 이 고칠 길이 없다.
# 왜 이 방향인지와 무엇이 진짜 문제인지는 NOTES.md 「마흔여덟째」에 있다.

# 발화가 화면을 가리키는지 가르는 낱말. 한 곳에 모은다.
#
# 앞의 일곱은 사람이 정했다(2026-08-29). 관심 지점 하나는 저쪽 프롬프트에서
# 맞춰 넣었다 — KRRI_ASAP 의 parse_intent 가 문맥이 있을 때 덧붙이는 한 줄이
# "here, this place, selected location, 관심 지점, 선택한 위치, 이 위치" 이고,
# 그 한국어 셋 중 둘은 이미 사람 목록에 있었다. 저쪽 파일은 읽기만 했다.
#
# 부분 문자열로 찾는다. "오송역 근처" 는 "이 근처" 가 아니고 "오송역 위치" 도
# "이 위치" 가 아니라서 안 걸린다. 정답표 서른한 발화에 하나도 안 걸리는 것을
# dev/tests/app/api/test_menu_split.py 가 지킨다.
SCREEN_WORDS = (
    "여기",
    "이 위치",
    "선택한 위치",
    "지금 보이는",
    "현재 화면",
    "이 근처",
    "이 지역",
    "관심 지점",
)


def _points_at_screen(utterance: str) -> bool:
    """발화가 화면을 가리키는가.

    출력  참이면 화면을 가리킴
    규칙  낱말로만 가름. 부분 문자열이 걸리면 참
    제약  가르자고 LLM 을 부르지 않는다.
          요청 한 번에 한 번만 부르는 것이 지금 길의 값임
    """
    return any(word in utterance for word in SCREEN_WORDS)


def _menu_for(utterance: str, context: dict | None) -> str:
    """이번 요청의 프롬프트에 실을 menu.

    입력  발화 · 저쪽 화면이 보낸 지도 문맥(없으면 없는 것으로)
    출력  menu.yaml 에서 recipe 몇 벌만 남긴 문자열
    규칙  발화가 화면을 가리키고 그 값이 실제로 와 있을 때만 화면 recipe.
          낱말이 걸렸는데 문맥에 값이 없으면 기존 마흔으로 감. 없는 것을
          제안하면 LLM 이 고르고 나서 _without_dropped 에 지워짐
          어느 recipe 가 화면 것인지는 경로 첫 칸으로 봄. _starts_at 이 이미
          그 판단을 하므로 새 기준을 만들지 않음
          값이 온 노드만 남김. 우클릭 전이면 보이는 범위 열 벌뿐임.
          찍은 지점 아홉 벌은 그때 골라도 못 쓰므로 안 보여줌
          남길 것이 없으면 원문 전부를 냄. 머리말만 실리는 것보다 나음
    제약  menu.yaml 을 안 고친다.
          읽은 문자열에서 블록을 뺄 뿐임
    """
    starts = {recipe_id: _starts_at(recipe_id) for recipe_id in graph.recipe_ids()}

    available = set(step_service.context_starts(context))
    if available and _points_at_screen(utterance):
        keep = [rid for rid, start in starts.items() if start in available]
    else:
        keep = [rid for rid, start in starts.items() if start not in step_service.CONTEXT_STARTS]

    return load_menu(keep) if keep else load_menu()


def _resolve_full(
    utterance: str, llm_client, reason_max_length: int, context: dict | None = None
) -> dict:
    """지금 길. LLM 이 쓴 축으로 후보를 뽑고, 고른 결과와 대조해 최종 status 를 정함.

    입력  발화 · LLM 클라이언트 · reason 길이 상한(모델마다 다름) ·
          저쪽 화면이 보낸 지도 문맥(없으면 없는 것으로)
    출력  LLM 응답(reason · given · want · about 포함) +
          status · recipe_id · candidate_recipe_ids · shortlist_recipe_ids ·
          llm_recipe_id · llm_candidate_recipe_ids · paths
    규칙  축 선택지도 조회 후보도 온톨로지에서 옴. 노드를 등록하면 함께 늘어남
          문맥이 못 채우는 시작 데이터는 선택지에서도 후보에서도 빠짐.
          LLM 이 그것으로 시작하는 recipe 를 골라도 뺌
          menu 도 요청마다 갈림(_menu_for). 발화가 화면을 가리키고 그 값이
          와 있으면 화면 recipe 만, 아니면 기존 마흔만 실림
          recipe_id 와 candidate_recipe_ids 는 _verdict 를 지난 값임.
          검산 전에 LLM 이 쓴 날것은 llm_ 이 붙은 두 key 에 따로 실림 —
          검산이 답을 바꾼 자리를 세려면 둘이 다 있어야 함
          paths 는 LLM 이 만드는 게 아님. 최종 후보로 다시 계산해 덧붙임.
          프론트엔드가 recipe 파일을 직접 읽지 않게 하려는 것
    제약  여기서 LLM 클라이언트를 만들지 않는다.
          app.api.main 의 make_client 를 갈아끼우는 테스트가 죽음
          기존 key 의 이름과 뜻을 바꾸지 않는다.
          Streamlit 과 dev/tools/check_resolve.py 가 그것을 읽음
    """
    dropped = _dropped_starts(context)
    choices = _choices_for(context)
    described = choices["described"]

    result = resolve_route(
        prompt=paths.RECIPE_SELECTION_PROMPT_PATH.read_text(encoding="utf-8"),
        variables={
            "menu": _menu_for(utterance, context),
            "utterance": utterance,
            "given_choices": described["given"],
            "want_choices": described["want"],
            "about_choices": described["about"],
        },
        response_schema=recipe_selection_schema(
            reason_max_length,
            given_choices=choices["given"],
            want_choices=choices["want"],
            about_choices=choices["about"],
        ),
        llm_client=llm_client,
    )

    # 축이 셋 다 null 이면 조회하지 않는다. candidates() 는 그때 전체를 내는데,
    # 그것을 후보로 삼으면 발화가 영역 밖일 때 NO_MATCH 가 48개 CLARIFY 가 된다.
    # 고를 근거가 하나도 없다는 뜻이므로 LLM 이 쓴 것을 그대로 둔다.
    axes = [result.get("given"), result.get("want"), result.get("about")]
    looked_up = shortlist.candidates(*axes) if any(axes) else []
    looked_up = _without_dropped(looked_up, dropped)

    # recipe_id 가 있으면 그것부터, 그다음 후보 전부.
    spoken = _without_dropped(
        list(
            dict.fromkeys(
                recipe_id
                for recipe_id in [
                    result.get("recipe_id"),
                    *(result.get("candidate_recipe_ids") or []),
                ]
                if recipe_id
            )
        ),
        dropped,
    )

    verdict = _verdict(result, spoken, looked_up)
    wanted = [rid for rid in [verdict["recipe_id"], *verdict["candidate_recipe_ids"]] if rid]

    return {
        **result,
        **verdict,
        "shortlist_recipe_ids": looked_up,
        # 검산을 거치기 전에 LLM 이 쓴 것. **날것이다.**
        #
        # 위의 **verdict 가 recipe_id 와 candidate_recipe_ids 를 덮는다. 그래서
        # 응답에 실리는 그 두 key 는 조회 후보와 대조한 뒤의 값이지 LLM 이 쓴
        # 값이 아니다. 검산이 얼마나 값을 하는지 재려면 날것이 있어야 한다.
        #
        # **덮어쓰는 쪽은 그대로 둔다.** 기존 key 의 뜻을 바꾸면 화면과
        # dev/tools/check_resolve.py 가 함께 흔들린다. key 를 둘 더할 뿐이다.
        "llm_recipe_id": result.get("recipe_id"),
        "llm_candidate_recipe_ids": list(result.get("candidate_recipe_ids") or []),
        # 날것은 뺀 것까지 그대로 둔다. LLM 이 무엇을 골랐는지가 이 두 칸의
        # 뜻이고, 문맥이 없어 뺀 자리를 세려면 뺀 것이 보여야 한다.
        "paths": graph.paths_for(wanted),
    }


def _verdict(result: dict, spoken: list[str], looked_up: list[str]) -> dict:
    """최종 status 와 후보.

    입력  LLM 응답 · LLM 이 고른 목록 · 축으로 뽑은 후보
    출력  status · recipe_id · candidate_recipe_ids
    규칙  겹치는 것 1개    SELECT
          겹치는 것 여럿   CLARIFY. 겹치는 것만 후보로. 순서는 뽑힌 후보를 따름
          겹치는 것 0개    축과 LLM 이 어긋난 것임. 둘을 합쳐 CLARIFY.
                           LLM 이 쓴 것이 앞, 뽑힌 후보가 뒤
          뽑힌 후보 0개    LLM 이 쓴 것을 그대로 둠. 축이 틀린 것이므로
                           조회 결과를 믿지 않음
          둘 다 0개        NO_MATCH
    이력  2026-08-26 에 「겹치는 것 0개」 규칙을 바꿈. 안 셋을 재고 고른 것이고
          표와 고른 까닭은 NOTES.md 「서른셋째」에 있음
    """
    if not looked_up:
        if not spoken:
            return {"status": NO_MATCH, "recipe_id": None, "candidate_recipe_ids": []}
        return {
            "status": result["status"],
            "recipe_id": result["recipe_id"],
            "candidate_recipe_ids": spoken,
        }

    overlap = [recipe_id for recipe_id in looked_up if recipe_id in set(spoken)]

    # 겹치는 것이 0개면 축과 LLM 이 어긋난 것이다. 어느 쪽이 맞는지 이 자리에서는
    # 가릴 근거가 없으므로 둘을 합쳐 사람에게 되묻는다.
    #
    # **2026-08-26 이전에는 뽑힌 후보만 썼다** ("LLM 이 헛짚은 것으로 봄").
    # 바로 위의 「뽑힌 후보 0개」 규칙은 같은 어긋남에서 정반대로 LLM 을 믿는데,
    # 두 규칙이 한 상황을 다르게 처신하고 있었다. 그 탓에 발화 셋(28 · 29 · 30)
    # 에서 LLM 이 기대값과 똑같이 고른 답을 아홉 번 덮었다 (「서른두째」 실측).
    #
    # LLM 을 믿는 안(나)도 함께 쟀다. 적중은 그쪽이 아홉 높지만(62/93 → 71/93)
    # 확신하고 틀리는 자리가 넷에서 여섯으로 늘어 1순위 기준에서 밀렸다.
    # 되물음이 늘어나는 것이 이 안의 대가다.
    final = overlap or list(dict.fromkeys([*spoken, *looked_up]))

    if len(final) == 1:
        return {"status": SELECT, "recipe_id": final[0], "candidate_recipe_ids": final}
    return {"status": CLARIFY, "recipe_id": None, "candidate_recipe_ids": final}


# ── 좁히기 길 ─────────────────────────────────────────────────────


def _resolve_narrow(
    utterance: str, llm_client, reason_max_length: int, context: dict | None = None
) -> dict:
    """좁히기 길. 1차(축만) → 온톨로지 조회 → 2차(후보 중 고르기).

    입력  _resolve_full 과 같음
    출력  _resolve_full 과 같은 key 전부 + narrow 한 칸
            narrow.shortlist_count   온톨로지가 좁힌 후보 수
            narrow.second_called     2차를 불렀는가. 후보가 하나면 안 부름
            narrow.fallback          None · "empty"(가) · "none"(나)
            narrow.first_seconds     1차 LLM 시간
            narrow.second_seconds    2차 LLM 시간. 안 불렀으면 None
            narrow.fallback_seconds  지금 길로 빠져나간 시간. 안 갔으면 None
            narrow.first             1차가 쓴 축 셋과 인자. 폴백이 덮어도 남김
          폴백이 돌면 나머지 key 는 지금 길의 결과 그대로임 (축 셋도 그쪽 것)
    규칙  1차에 menu 를 안 넣음. 프롬프트가 그만큼 짧음
          후보가 하나면 2차를 안 부르고 그것으로 SELECT
          2차가 쓴 것은 후보 밖이면 버림 (스키마가 막지만 한 번 더 거름)
          2차가 NO_MATCH 거나 남는 것이 없으면 폴백 나
          shortlist_recipe_ids 는 1차 축으로 뽑은 후보. llm_recipe_id ·
          llm_candidate_recipe_ids 는 2차가 쓴 날것. 2차를 안 불렀으면 비어 있음
    제약  _verdict 를 안 거친다. 대조할 두 목록이 없음 — 후보가 곧 조회 결과임
          _resolve_full 을 안 고친다. 폴백은 그것을 그대로 부름
    """
    dropped = _dropped_starts(context)
    choices = _choices_for(context)
    described = choices["described"]

    started = time.perf_counter()
    first = resolve_route(
        prompt=AXES_PROMPT_PATH.read_text(encoding="utf-8"),
        variables={
            "utterance": utterance,
            "given_choices": described["given"],
            "want_choices": described["want"],
            "about_choices": described["about"],
        },
        response_schema=axis_selection_schema(
            reason_max_length,
            given_choices=choices["given"],
            want_choices=choices["want"],
            about_choices=choices["about"],
        ),
        llm_client=llm_client,
    )
    first_seconds = time.perf_counter() - started

    # 지금 길과 같은 이유로 축이 셋 다 null 이면 조회하지 않는다 — 전체가 후보가 됨.
    axes = [first.get("given"), first.get("want"), first.get("about")]
    looked_up = shortlist.candidates(*axes) if any(axes) else []
    looked_up = _without_dropped(looked_up, dropped)

    narrow = {
        "enabled": True,
        "shortlist_count": len(looked_up),
        "second_called": False,
        "fallback": None,
        "first_seconds": round(first_seconds, 3),
        "second_seconds": None,
        "fallback_seconds": None,
        "first": {key: first.get(key) for key in ("given", "want", "about", "argument")},
    }

    if not looked_up:  # 가) 축 셋으로 아무것도 못 걸러냈다
        return _fallback(
            FALLBACK_EMPTY, narrow, utterance, llm_client, reason_max_length, context
        )

    if len(looked_up) == 1:  # 부를 이유가 없다
        return {
            **first,
            "status": SELECT,
            "recipe_id": looked_up[0],
            "candidate_recipe_ids": list(looked_up),
            "shortlist_recipe_ids": looked_up,
            "llm_recipe_id": None,
            "llm_candidate_recipe_ids": [],
            "paths": graph.paths_for(looked_up),
            "narrow": narrow,
        }

    started = time.perf_counter()
    second = resolve_route(
        prompt=PICK_PROMPT_PATH.read_text(encoding="utf-8"),
        variables={"utterance": utterance, "candidates": _candidate_lines(looked_up)},
        response_schema=recipe_pick_schema(reason_max_length, looked_up),
        llm_client=llm_client,
    )
    narrow["second_called"] = True
    narrow["second_seconds"] = round(time.perf_counter() - started, 3)

    # 후보 밖의 것은 버린다. 순서는 조회 후보(파일 이름 순)를 따른다 — 지금 길의
    # 「겹치는 것 여럿」 규칙과 같은 차례다.
    spoken = {
        recipe_id
        for recipe_id in [second.get("recipe_id"), *(second.get("candidate_recipe_ids") or [])]
        if recipe_id
    }
    final = [recipe_id for recipe_id in looked_up if recipe_id in spoken]

    if second.get("status") == NO_MATCH or not final:  # 나) "여기 없다"
        return _fallback(
            FALLBACK_NONE, narrow, utterance, llm_client, reason_max_length, context
        )

    if len(final) == 1:
        verdict = {"status": SELECT, "recipe_id": final[0], "candidate_recipe_ids": final}
    else:
        verdict = {"status": CLARIFY, "recipe_id": None, "candidate_recipe_ids": final}

    return {
        **first,
        # reason 은 2차 것. 무엇을 비교해 골랐는지가 화면에 보이는 문장임
        "reason": second.get("reason", first.get("reason")),
        **verdict,
        "shortlist_recipe_ids": looked_up,
        "llm_recipe_id": second.get("recipe_id"),
        "llm_candidate_recipe_ids": list(second.get("candidate_recipe_ids") or []),
        "paths": graph.paths_for(final),
        "narrow": narrow,
    }


def _fallback(
    kind: str,
    narrow: dict,
    utterance: str,
    llm_client,
    reason_max_length: int,
    context: dict | None = None,
) -> dict:
    """지금 길로 빠져나간다. 결과는 지금 길 그대로이고 narrow 에 까닭만 남긴다."""
    started = time.perf_counter()
    result = _resolve_full(utterance, llm_client, reason_max_length, context)
    narrow["fallback"] = kind
    narrow["fallback_seconds"] = round(time.perf_counter() - started, 3)
    return {**result, "narrow": narrow}


def _candidate_lines(recipe_ids: list[str]) -> str:
    """2차 프롬프트에 넣을 후보 문장. menu.yaml 의 function 을 id 와 함께 한 줄씩.

    규칙  menu 전체가 아니라 후보만. 그것이 좁히기의 요점임
          menu 에 없는 id 는 문장 없이 id 만 적음 (등록 직후 어긋난 자리)
    """
    recipes = (yaml.safe_load(load_menu()) or {}).get("recipes") or {}
    return "\n".join(
        f"- {recipe_id}: {(recipes.get(recipe_id) or {}).get('function', '')}".rstrip(": ")
        for recipe_id in recipe_ids
    )
