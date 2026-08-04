"""실행 경로(Route)를 결정하는 공통 엔진.
- static_workflow : Menu(=Recipes)를 context로 활용하여 실행 경로(Route) 결정.
- dydnamic_workflow : Graph(?)를 context로 활용하여 실행 경로(Route) 결정.

(1) variables 로 Prompt 를 구성
(2) llm_client 로 원하는 LLM 호출,
(3) response_schema 로 LLM 응답 형식 전달
"""

import json


class RouteResolutionError(RuntimeError):
    """LLM 응답 결과가 예상과 다를 때의 오류 처리."""


def resolve_route(
    prompt: str,
    variables: dict,
    response_schema: dict,
    llm_client,
) -> dict:
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
