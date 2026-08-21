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
          status · recipe_id · candidate_recipe_ids · shortlist_recipe_ids · paths
    규칙  축 선택지도 조회 후보도 온톨로지에서 옴. 노드를 등록하면 함께 늘어남
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
        "paths": ontology_service.paths_for(wanted),
    }


def _verdict(result: dict, spoken: list[str], looked_up: list[str]) -> dict:
    """최종 status 와 후보.

    입력  LLM 응답 · LLM 이 고른 목록 · 축으로 뽑은 후보
    출력  status · recipe_id · candidate_recipe_ids
    규칙  겹치는 것 1개    SELECT
          겹치는 것 여럿   CLARIFY. 겹치는 것만 후보로. 순서는 뽑힌 후보를 따름
          겹치는 것 0개    뽑힌 후보를 씀. LLM 이 헛짚은 것으로 봄
          뽑힌 후보 0개    LLM 이 쓴 것을 그대로 둠. 축이 틀린 것이므로
                           조회 결과를 믿지 않음
          둘 다 0개        NO_MATCH
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
    final = overlap or looked_up

    if len(final) == 1:
        return {"status": SELECT, "recipe_id": final[0], "candidate_recipe_ids": final}
    return {"status": CLARIFY, "recipe_id": None, "candidate_recipe_ids": final}
