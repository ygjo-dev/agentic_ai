"""대상 : orchestrator/ — 발화를 실행 경로(Recipe)로 해석한다

해석 엔진은 도메인을 모른다. **무엇을 고를지는 전부 Context 로 들어온다** —
지금은 menu.yaml(실행 가능한 recipe 목록)이고, 나중에 그래프DB 로 바뀌어도
엔진은 그대로다.

응답은 세 상태다.
  SELECT   — 하나로 정해졌다
  CLARIFY  — 후보가 여럿이라 되물어야 한다
  NO_MATCH — 할 수 있는 것이 없다

LLM 은 호출하지 않는다(Stub). 여기서 검증하는 것은 엔진의 계약이지
LLM 의 판단력이 아니다.
"""

import json

import pytest

import paths
from conftest import CLARIFY, NO_MATCH, SELECT, assert_route_contract, menu_was_read
from orchestrator.route_resolver import RouteResolutionError, resolve_route
from orchestrator.schemas.response_schema import RESPONSE_SCHEMA
from workflows.static.menu.load import load_menu

UTTERANCE = "기상 관측값으로 결빙 위험도를 분석해줘"


def resolve(stub_llm_client, raw: str, utterance: str = UTTERANCE):
    client = stub_llm_client(raw)
    result = resolve_route(
        prompt=paths.RECIPE_SELECTION_PROMPT_PATH.read_text(encoding="utf-8"),
        variables={"menu": load_menu(), "utterance": utterance},
        response_schema=RESPONSE_SCHEMA,
        llm_client=client,
    )
    return result, client


def test_the_menu_and_the_utterance_become_the_prompt(stub_llm_client, read_file_paths):
    """Context 로딩은 LLM 호출보다 먼저 일어난다.

    menu 를 실제 파일에서 읽어야 한다 — 코드에 박아두면 recipe 를 등록해도
    LLM 이 새 recipe 를 영영 못 고른다. 발화도 그대로 실려야 하고,
    LLM 은 정확히 한 번만 부른다.
    """
    read_file_paths.clear()
    menu = load_menu()

    assert menu_was_read(read_file_paths), f"실제 menu.yaml 을 안 읽었다: {paths.MENU_YAML_PATH}"
    assert isinstance(menu, str) and menu.strip()

    _, client = resolve(stub_llm_client, json.dumps({
        "reason": "결빙 위험도 분석과 하는 일이 같다.",
        "candidate_recipe_ids": ["recipe_004"],
        "status": SELECT,
        "recipe_id": "recipe_004",
    }))

    assert len(client.prompts) == 1
    assert UTTERANCE in client.prompts[0]
    for recipe_id in ("recipe_004", "recipe_005"):
        assert recipe_id in client.prompts[0], f"menu 가 프롬프트에 안 실렸다: {recipe_id}"


@pytest.mark.parametrize(
    "answer, status, recipe_id, candidates",
    [
        (
            {"reason": "하는 일이 같다.", "candidate_recipe_ids": ["recipe_004"],
             "status": SELECT, "recipe_id": "recipe_004"},
            SELECT, "recipe_004", ["recipe_004"],
        ),
        (
            {"reason": "Word 인지 PPT 인지 발화에 없다.",
             "candidate_recipe_ids": ["recipe_012", "recipe_013"],
             "status": CLARIFY, "recipe_id": None},
            CLARIFY, None, ["recipe_012", "recipe_013"],
        ),
        (
            {"reason": "menu 에 없는 기능이다.", "candidate_recipe_ids": [],
             "status": NO_MATCH, "recipe_id": None},
            NO_MATCH, None, [],
        ),
    ],
    ids=["SELECT", "CLARIFY", "NO_MATCH"],
)
def test_only_the_contracted_keys_survive(
    stub_llm_client, answer, status, recipe_id, candidates
):
    """세 상태 모두 같은 형태로 나온다. 호출하는 쪽이 분기하지 않아도 되게.

    스키마에 없는 key 는 버린다 — LLM 이 덧붙인 것을 그대로 흘리면 계약이
    조용히 넓어지고, 나중에 그것에 기대는 코드가 생긴다.
    """
    result, _ = resolve(stub_llm_client, json.dumps({**answer, "군더더기": "버려야 한다"}))

    assert_route_contract(result)
    assert set(result) == set(RESPONSE_SCHEMA["required"])
    assert result["status"] == status
    assert result["recipe_id"] == recipe_id
    assert result["candidate_recipe_ids"] == candidates
    assert result["reason"]


@pytest.mark.parametrize(
    "raw, cause, fragment",
    [
        ("이건 JSON 이 아니다", json.JSONDecodeError, "이건 JSON 이 아니다"),
        ("```json\n{}\n```", json.JSONDecodeError, "```json"),
        (json.dumps({"status": SELECT, "recipe_id": None}), KeyError, "'status': 'SELECT'"),
        (json.dumps(["recipe_004"]), TypeError, "recipe_004"),
    ],
    ids=["not_json", "code_block", "key_missing", "not_an_object"],
)
def test_a_broken_answer_raises_with_the_original_text(
    stub_llm_client, raw, cause, fragment
):
    """LLM 은 계약을 어긴다. 코드 블록으로 감싸거나 키를 빠뜨린다.

    조용히 넘기면 화면에 빈 결과가 뜨고 원인을 못 찾는다. 예외로 올리되
    **원문과 저수준 예외를 남긴다** — 그게 없으면 무엇이 잘못됐는지 알 수 없다.
    호출자가 RouteResolutionError 를 몰라도 RuntimeError 로 잡을 수 있어야 한다.
    """
    assert issubclass(RouteResolutionError, RuntimeError)

    with pytest.raises(RouteResolutionError) as error_info:
        resolve(stub_llm_client, raw)

    error = error_info.value
    assert isinstance(error.__cause__, cause), f"__cause__ 가 없다: {error.__cause__!r}"
    assert fragment in str(error), f"원문이 안 남았다: {error}"
