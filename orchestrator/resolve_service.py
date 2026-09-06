"""발화 → Recipe 해석. route_resolver 를 한 번 부른다.

길은 하나다. menu 전벌과 발화를 프롬프트에 싣고 LLM 이 recipe 를 고른다.
고른 것을 그대로 쓴다 — 온톨로지에 다시 물어보지 않는다. 몸통은 _resolve_full 이다.

## 화면에서 온 값 — 값이 안 왔으면 그 시작 데이터는 없는 것으로 (2026-08-28)

시작 데이터 노드가 다섯이다. 뒤의 둘(찍은 지점 · 보이는 범위)은 발화가 아니라
저쪽 화면이 보내는 지도 문맥에서 값을 받는다. **그 값이 안 왔으면 그 둘은 아예
없는 것처럼 굴어야 한다** — Streamlit 은 문맥을 안 보내고, 없는 좌표로 도구를
부르면 전국이 나오거나 null 로 거부당한다.

판단이 서는 자리가 둘이다. 둘을 한 자리에 몰지 않았다.

  값이 있는가   여기(_dropped_starts · _without_dropped). 기계가 센다. 문맥의 칸을
                보고, 값이 안 온 시작 데이터에서 출발하는 recipe 를 후보에서 뺀다
  그것을 쓸까   온톨로지의 노드 description. LLM 이 발화를 보고 고른다.
                "발화가 장소 이름 대신 여기나 이 위치라고 가리킬 때 쓴다" 가
                그 문장이고, 그 말은 menu 문장에도 그대로 실린다

## 걷어낸 버팀목 넷 — 2026-09-04 (태그 `before-buttress-removed`)

넷을 하나씩 끄고 재 보니 실제로는 둘이었다. 축 선택지를 빼면 축이 셋 다 null 이
되어 조회가 안 불리고, 조회 후보가 비면 검산이 LLM 이 쓴 것을 그대로 돌려준다.

  ④ 화면 문맥으로 menu 가르기   _menu_for · _points_at_screen · SCREEN_WORDS
  ① 프롬프트의 축 절 셋         recipe_selection.md 의 given/want/about + 스키마 세 칸
  ② 축으로 온톨로지 조회        shortlist.candidates
  ③ 검산                        _verdict

**여섯 발화를 잃는 것을 알고 걷었다** (37/39 → 30/39). 사람이 정했다.
지금 남은 실패와 그 갈래, 걷기 전 다섯 판의 표는 NOTES.md 「아흔여섯째」에 있다.
되살리려면 `git show before-buttress-removed:orchestrator/resolve_service.py`.
"""

import paths
from execution import step_service
from ontology import graph
from orchestrator.route_resolver import resolve_route
from orchestrator.schemas.response_schema import recipe_selection_schema
from workflows.static.menu.load import load_menu


def resolve(
    utterance: str,
    llm_client,
    reason_max_length: int,
    context: dict | None = None,
) -> dict:
    """발화를 recipe 로.

    입력  발화 · LLM 클라이언트 · reason 길이 상한 ·
          저쪽 화면이 보낸 지도 문맥(없으면 없는 것으로)
    출력  _resolve_full 의 결과. key 는 그쪽 docstring 에
    제약  context 를 안 줬을 때 문맥이 없는 것과 똑같아야 한다.
          2026-08-29 부터 Streamlit 과 dev/tools/check_resolve.py 도 넘기지만,
          --context none 과 옛 부름이 이 자리를 그대로 지남
    """
    return _resolve_full(utterance, llm_client, reason_max_length, context)


def _dropped_starts(context: dict | None) -> set[str]:
    """이번 요청에서 값을 못 받는 화면 시작 데이터 노드.

    출력  노드 id 집합. 문맥이 다 갖췄으면 빈 집합
    규칙  무엇이 화면에서 오는지는 step_service.CONTEXT_STARTS 가 앎.
          여기서 노드 id 를 다시 적지 않음
    """
    return set(step_service.CONTEXT_STARTS) - set(step_service.context_starts(context))


def _without_dropped(recipe_ids: list[str], dropped: set[str]) -> list[str]:
    """값을 못 받는 화면 문맥을 쓰는 recipe 를 뺀 목록.

    입력  recipe id 목록 · 값이 안 온 시작 데이터 노드 id 집합
    출력  차례를 지킨 목록. 뺄 것이 없으면 받은 것 그대로
    규칙  그 recipe 의 배선이 실제로 읽는 문맥을 봄.
          step_service.context_needs 가 그것을 셈. 여기서 recipe 파일도
          배선표도 열지 않음
    제약  menu 에서 그 문장을 지우지 않는다.
          menu 는 온톨로지가 만드는 것이고 요청마다 다를 수 없음. 지울 수
          없으니 LLM 이 그것을 골라도 여기서 뺀다
    이력  2026-08-29 에 그 제약을 깼다 — _menu_for 가 요청마다 menu 를 갈랐다.
          2026-09-04 에 그 갈래를 걷어 제약이 다시 참이 됐다. 프롬프트에는 늘
          menu 전벌이 실리고, 값이 없는 것을 LLM 이 고르면 여기서 뺀다
          2026-09-06 까지는 경로의 첫 칸(_starts_at)만 봤다. 그때는 문맥을
          읽는 줄이 전부 input_first 에 있어 두 방식이 같았고, recipe 37 벌
          어느 하나도 판정이 안 갈렸다(실측). 경로 탐색이 문맥을 둘째 단계에서
          읽어 갈라졌다 — 첫 칸만 보면 찍은 지점 없이도 후보로 남는다
    """
    if not dropped:
        return recipe_ids
    return [
        recipe_id
        for recipe_id in recipe_ids
        if not (step_service.context_needs(recipe_id) & dropped)
    ]


def _resolve_full(
    utterance: str, llm_client, reason_max_length: int, context: dict | None = None
) -> dict:
    """지금 길. menu 전벌을 싣고 LLM 이 고른 것을 그대로 쓴다.

    입력  발화 · LLM 클라이언트 · reason 길이 상한(모델마다 다름) ·
          저쪽 화면이 보낸 지도 문맥(없으면 없는 것으로)
    출력  LLM 응답(reason · argument 포함) +
          status · recipe_id · candidate_recipe_ids ·
          llm_recipe_id · llm_candidate_recipe_ids · paths
    규칙  프롬프트에 실리는 menu 는 menu.yaml 원문 전부임. 요청마다 안 갈림
          문맥이 못 채우는 시작 데이터에서 출발하는 recipe 는 LLM 이 골라도 뺌
          status 는 LLM 이 쓴 것을 그대로 씀. 온톨로지에 다시 안 물어봄
          candidate_recipe_ids 는 문맥 거르개를 지난 값임. 거르기 전에 LLM 이
          쓴 날것은 llm_ 이 붙은 두 key 에 따로 실림 — 문맥이 무엇을 뺐는지
          세려면 둘이 다 있어야 함
          paths 는 LLM 이 만드는 게 아님. 최종 후보로 다시 계산해 덧붙임.
          프론트엔드가 recipe 파일을 직접 읽지 않게 하려는 것
    제약  여기서 LLM 클라이언트를 만들지 않는다.
          app.api.main 의 get_llm 을 갈아끼우는 테스트가 죽음
          기존 key 의 이름과 뜻을 바꾸지 않는다.
          Streamlit 과 dev/tools/check_resolve.py 가 그것을 읽음
    """
    dropped = _dropped_starts(context)

    result = resolve_route(
        prompt=paths.RECIPE_SELECTION_PROMPT_PATH.read_text(encoding="utf-8"),
        variables={"menu": load_menu(), "utterance": utterance},
        response_schema=recipe_selection_schema(reason_max_length),
        llm_client=llm_client,
    )

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

    return {
        **result,
        "candidate_recipe_ids": spoken,
        # 문맥 거르개를 지나기 전에 LLM 이 쓴 것. **날것이다.**
        #
        # 위의 candidate_recipe_ids 는 값이 안 온 시작 데이터를 뺀 뒤의 값이다.
        # 문맥이 무엇을 뺐는지 세려면 날것이 있어야 한다.
        #
        # **덮어쓰는 쪽은 그대로 둔다.** 기존 key 의 뜻을 바꾸면 화면과
        # dev/tools/check_resolve.py 가 함께 흔들린다. key 를 둘 더할 뿐이다.
        "llm_recipe_id": result.get("recipe_id"),
        "llm_candidate_recipe_ids": list(result.get("candidate_recipe_ids") or []),
        "paths": graph.paths_for(
            [rid for rid in [result.get("recipe_id"), *spoken] if rid]
        ),
    }
