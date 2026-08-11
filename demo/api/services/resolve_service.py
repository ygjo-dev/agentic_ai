"""발화 → Recipe 해석. route_resolver 호출 + 경로(paths) 덧붙이기."""

import paths
from demo.api.services import ontology_service
from orchestrator.route_resolver import resolve_route
from orchestrator.schemas.response_schema import RESPONSE_SCHEMA
from workflows.static.menu.load import load_menu


def resolve(utterance: str, llm_client) -> dict:
    """LLM 이 고른 결과에 각 recipe 의 실행 경로를 붙여 돌려준다.

    llm_client 를 인자로 받는다 — 여기서 OllamaClient 를 import 하면
    demo.api.main 의 OllamaClient 를 갈아끼우는 테스트가 죽는다.

    paths 는 LLM 이 만드는 게 아니다. LLM 스키마(response_schema.py)는 그대로
    두고, 결과를 받아 백엔드가 덧붙인다. 프론트엔드가 recipe 파일을 직접
    읽지 않게 하려는 것이다.
    """
    result = resolve_route(
        prompt=paths.RECIPE_SELECTION_PROMPT_PATH.read_text(encoding="utf-8"),
        variables={"menu": load_menu(), "utterance": utterance},
        response_schema=RESPONSE_SCHEMA,
        llm_client=llm_client,
    )

    # recipe_id 가 있으면 그것부터, 그다음 후보 전부. NO_MATCH 면 둘 다 비어 {} 가 된다.
    wanted = [
        recipe_id
        for recipe_id in [result.get("recipe_id"), *(result.get("candidate_recipe_ids") or [])]
        if recipe_id
    ]

    return {**result, "paths": ontology_service.paths_for(wanted)}
