"""발화 → Recipe 해석. route_resolver 호출 + 온톨로지 조회로 후보 좁히기.

LLM 은 한 번만 부른다. 그 한 번에 축 셋(given · want · about)을 함께 받아,
그 값으로 온톨로지에서 후보를 뽑고 LLM 이 고른 목록과 대조한다.
"""

import paths
from demo.api.services import ontology_service
from ontology import shortlist
from orchestrator.route_resolver import resolve_route
from orchestrator.schemas.response_schema import (
    CLARIFY,
    NO_MATCH,
    SELECT,
    recipe_selection_schema,
)
from workflows.static.menu.load import load_menu


def resolve(utterance: str, llm_client, reason_max_length: int) -> dict:
    """LLM 이 쓴 축으로 후보를 뽑고, 고른 결과와 대조해 최종 status 를 정함.

    입력  발화 · LLM 클라이언트 · reason 길이 상한(모델마다 다름)
    출력  LLM 응답(reason · given · want · about 포함) +
          status · recipe_id · candidate_recipe_ids · shortlist_recipe_ids ·
          llm_recipe_id · llm_candidate_recipe_ids · paths
    규칙  축 선택지도 조회 후보도 온톨로지에서 옴. 노드를 등록하면 함께 늘어남
          recipe_id 와 candidate_recipe_ids 는 _verdict 를 지난 값임.
          검산 전에 LLM 이 쓴 날것은 llm_ 이 붙은 두 key 에 따로 실림 —
          검산이 답을 바꾼 자리를 세려면 둘이 다 있어야 함
          paths 는 LLM 이 만드는 게 아님. 최종 후보로 다시 계산해 덧붙임.
          프론트엔드가 recipe 파일을 직접 읽지 않게 하려는 것
    제약  여기서 LLM 클라이언트를 만들지 않는다.
          demo.api.main 의 make_client 를 갈아끼우는 테스트가 죽음
          기존 key 의 이름과 뜻을 바꾸지 않는다.
          Streamlit 과 tools/check_resolve.py 가 그것을 읽음
    """
    choices = shortlist.axis_choices()
    described = choices["described"]

    result = resolve_route(
        prompt=paths.RECIPE_SELECTION_PROMPT_PATH.read_text(encoding="utf-8"),
        variables={
            "menu": load_menu(),
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

    # recipe_id 가 있으면 그것부터, 그다음 후보 전부.
    spoken = list(
        dict.fromkeys(
            recipe_id
            for recipe_id in [
                result.get("recipe_id"),
                *(result.get("candidate_recipe_ids") or []),
            ]
            if recipe_id
        )
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
        # tools/check_resolve.py 가 함께 흔들린다. key 를 둘 더할 뿐이다.
        "llm_recipe_id": result.get("recipe_id"),
        "llm_candidate_recipe_ids": list(result.get("candidate_recipe_ids") or []),
        "paths": ontology_service.paths_for(wanted),
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
