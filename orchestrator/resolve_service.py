"""발화 → recipe 해석.

길은 하나다. menu.yaml 원문 전부와 발화를 프롬프트에 싣고 LLM 이 recipe 를
고른다. 고른 것을 그대로 쓴다 — 온톨로지에 다시 물어보지도, 문맥으로 후보를
다시 거르지도 않는다.

    menu 전문 + 발화  ->  LLM  ->  status · recipe_id · candidate_recipe_ids

**고르는 것과 부를 수 있는 것을 가른다.** 실행에 화면 문맥이 실제로 필요한지는
execution/execute_service 가 실행 직전에 본다. 여기서 미리 빼면 「무엇을
골랐는가」와 「지금 부를 수 있는가」가 한 값에 섞여 어느 쪽이 결정했는지
읽을 수 없다.
"""

import json

import paths
from ontology import graph
from orchestrator.schemas.response_schema import recipe_selection_schema
from workflows.static.menu.load import load_menu


class RouteResolutionError(RuntimeError):
    """LLM 응답이 계약과 다르다. JSON 이 아니거나 필요한 key 가 없다."""


def resolve(utterance: str, llm_client, reason_max_length: int) -> dict:
    """발화를 recipe 로.

    출력  LLM 응답(reason · argument 포함) +
          status · recipe_id · candidate_recipe_ids · paths
    규칙  프롬프트에 실리는 menu 는 menu.yaml 원문 전부임. 요청마다 안 갈림
          status 와 recipe_id 는 LLM 이 고른 것임. 후처리 규칙으로 바꾸지 않음
          candidate_recipe_ids 응답은 그 선택을 부르는 쪽이 읽기 좋게 편 것임 —
          고른 recipe 를 앞에 두고 중복을 지운 목록이라 LLM 이 쓴 배열과 차례가
          다를 수 있음. **무엇이 후보인가는 안 바뀜. 순서와 중복만 다듬음**
          paths 는 그 정돈된 후보 목록으로 계산해 덧붙임. 프론트엔드가 recipe
          파일을 직접 읽지 않게 하려는 것
    제약  고른 것을 여기서 다시 거르지 않는다.
          실행할 수 있는지는 실행 직전에 봄. 두 판단을 한 값에 섞으면 어느
          쪽이 후보를 없앴는지 알 수 없음
          여기서 LLM 클라이언트를 만들지 않는다.
          app.api.main 의 get_llm 을 갈아끼우는 테스트가 죽음
    """
    result = _selected(
        prompt=paths.RECIPE_SELECTION_PROMPT_PATH.read_text(encoding="utf-8"),
        variables={"menu": load_menu(), "utterance": utterance},
        response_schema=recipe_selection_schema(reason_max_length),
        llm_client=llm_client,
    )

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

    return {
        **result,
        "candidate_recipe_ids": spoken,
        "paths": graph.paths_for(spoken),
    }


def _selected(
    prompt: str, variables: dict, response_schema: dict, llm_client
) -> dict:
    """프롬프트를 채워 LLM 을 한 번 부르고 계약된 key 만 남김.

    출력  response_schema 의 required 에 적힌 key 만. LLM 이 덧붙인 것은 버림
    제약  계약을 어긴 응답을 조용히 넘기지 않는다.
          빈 결과가 화면에 뜨면 원인을 못 찾음. 원문을 붙여 예외로 올림
    """
    raw = llm_client.generate(prompt.format(**variables), response_schema)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RouteResolutionError(
            f"LLM 응답을 JSON 으로 파싱할 수 없다: {raw!r}"
        ) from exc

    try:
        return {key: data[key] for key in response_schema["required"]}
    except (KeyError, TypeError) as exc:
        raise RouteResolutionError(
            f"LLM 응답에 필요한 schema가 정의되지 않음: {data!r}"
        ) from exc
