"""resolve_route() 검증. LLM 은 호출하지 않는다 (Stub 사용)."""

import json

import pytest

import paths
from conftest import CLARIFY, NO_MATCH, SELECT, assert_route_contract
from orchestrator.route_resolver import RouteResolutionError, resolve_route
from orchestrator.schemas.response_schema import RESPONSE_SCHEMA
from workflows.static.menu.load import load_menu

# ------------------------------------------------------------ 정상 경로
ROUTE_CASES = [
    # (사용자 발화, LLM 이 돌려준 구조화 응답, 기대 status, 기대 recipe_id, 기대 후보)
    (
        "CCTV로 군중을 분석해줘",
        {
            "reason": "CCTV 군중 분석과 하는 일이 같다.",
            "candidate_recipe_ids": ["recipe_002"],
            "status": SELECT,
            "recipe_id": "recipe_002",
        },
        SELECT,
        "recipe_002",
        ["recipe_002"],
    ),
    (
        "CCTV 군중 분석 결과를 문서로 만들어줘",
        {
            "reason": "문서 형식이 Word 인지 PPT 인지 발화에 없다.",
            "candidate_recipe_ids": ["recipe_003", "recipe_004"],
            "status": CLARIFY,
            "recipe_id": None,
        },
        CLARIFY,
        None,
        ["recipe_003", "recipe_004"],
    ),
    (
        "CCTV 영상으로 열차 속도를 분석해줘",
        {
            "reason": "열차 속도 분석을 하는 Recipe 가 Menu 에 없다.",
            "candidate_recipe_ids": [],
            "status": NO_MATCH,
            "recipe_id": None,
        },
        NO_MATCH,
        None,
        [],
    ),
]


@pytest.mark.parametrize(
    "utterance, llm_response, expected_status, expected_recipe_id, expected_candidates",
    ROUTE_CASES,
)
def test_resolve_static_route(
    stub_llm_client,
    utterance,
    llm_response,
    expected_status,
    expected_recipe_id,
    expected_candidates,
):
    """resolve_route() 의 출력 검증.
    SELECT / CLARIFY / NO_MATCH 3가지 상태 출력 검증.
    LLM 사용 안함.
    """
    llm_client = stub_llm_client(json.dumps(llm_response))  # 실제 LLM 호출 없이 테스트

    result = resolve_route(
        prompt=paths.RECIPE_SELECTION_PROMPT_PATH.read_text(encoding="utf-8"),
        variables={"menu": load_menu(), "utterance": utterance},
        response_schema=RESPONSE_SCHEMA,
        llm_client=llm_client,
    )

    assert_route_contract(result)
    assert result["status"] == expected_status
    assert result["recipe_id"] == expected_recipe_id
    assert result["candidate_recipe_ids"] == expected_candidates

    assert utterance in llm_client.prompts[0]


# ------------------------------------------------------------ 실패 경로
BROKEN_RESPONSE_CASES = [
    # (LLM 이 돌려준 raw 응답, 예상되는 문제 원인, 에러 메시지에 남아야 할 문자열)
    (
        "이건 JSON 이 아니다",
        json.JSONDecodeError,
        "이건 JSON 이 아니다",
    ),
    (
        "```json\n{}\n```",
        json.JSONDecodeError,
        "```json",
    ),
    (
        json.dumps({"status": SELECT, "recipe_id": None}),  # 필수 key 누락
        KeyError,
        "'status': 'SELECT'",
    ),
    (
        json.dumps(["recipe_002"]),  # object 가 아닌 JSON
        TypeError,
        "recipe_002",
    ),
]

BROKEN_RESPONSE_IDS = [
    "not_json",
    "json_in_code_block",
    "required_key_missing",
    "not_an_object",
]


@pytest.mark.parametrize(
    "raw_response, expected_cause, expected_message_fragment",
    BROKEN_RESPONSE_CASES,
    ids=BROKEN_RESPONSE_IDS,
)
def test_resolve_route_rejects_broken_llm_response(
    stub_llm_client, raw_response, expected_cause, expected_message_fragment
):
    """
    LLM 응답 구조화 적용 여부 검토.
    LLM 사용 안함.
    """
    llm_client = stub_llm_client(raw_response)  # 실제 LLM 호출 없이 테스트

    with pytest.raises(RouteResolutionError) as error_info:
        resolve_route(
            prompt=paths.RECIPE_SELECTION_PROMPT_PATH.read_text(encoding="utf-8"),
            variables={"menu": load_menu(), "utterance": "CCTV로 군중을 분석해줘"},
            response_schema=RESPONSE_SCHEMA,
            llm_client=llm_client,
        )

    error = error_info.value

    assert isinstance(error.__cause__, expected_cause), (
        "저수준 예외를 __cause__ 로 남기지 않으면 원인을 추적할 수 없다.\n"
        f"  실제 __cause__ : {error.__cause__!r}"
    )

    assert expected_message_fragment in str(error), (
        "에러 메시지에 문제가 된 응답이 남아있지 않다.\n"
        f"  실제 메시지 : {error}"
    )

    assert len(llm_client.prompts) == 1


def test_route_resolution_error_is_a_runtime_error():
    """호출자가 RouteResolutionError 를 몰라도 RuntimeError 로 잡을 수 있어야 한다."""
    assert issubclass(RouteResolutionError, RuntimeError)
