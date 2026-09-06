"""대상 : orchestrator/resolve_service.py — 발화를 recipe 로 해석한다

**무엇을 고를지는 menu 원문과 발화로만 들어온다.** 고르는 것은 LLM 하나이고,
고른 것을 문맥이나 온톨로지로 다시 거르지 않는다. 실행에 무엇이 필요한지는
execution 이 실행 직전에 본다.

응답은 세 상태다.
  SELECT   — 하나로 정해졌다
  CLARIFY  — 후보가 여럿이라 되물어야 한다
  NO_MATCH — 할 수 있는 것이 없다

LLM 은 호출하지 않는다(Stub). 여기서 검증하는 것은 계약이지 LLM 의 판단력이
아니다.
"""

import json

import pytest

import paths
from conftest import CLARIFY, NO_MATCH, SELECT, assert_route_contract, menu_was_read
from orchestrator import resolve_service
from orchestrator.resolve_service import RouteResolutionError
from orchestrator.schemas.response_schema import recipe_selection_schema

# 상한 값 자체는 이 테스트의 관심이 아니다. 모델별 값은 models.yaml 에 있다.
#
# argument 는 선택지가 없다. 발화에서 그대로 떼어 온 값이라 닫힌 목록이 아니다.
SCHEMA = recipe_selection_schema(200)

from workflows.static.menu.load import load_menu

UTTERANCE = "기상 관측값으로 결빙 위험도를 분석해줘"


def resolve(stub_llm_client, raw: str, utterance: str = UTTERANCE):
    """계약 부분만 본다. paths 조립은 아래 test_the_result_carries_the_paths 가 봄."""
    client = stub_llm_client(raw)
    result = resolve_service._selected(
        prompt=paths.RECIPE_SELECTION_PROMPT_PATH.read_text(encoding="utf-8"),
        variables={"menu": load_menu(), "utterance": utterance},
        response_schema=SCHEMA,
        llm_client=client,
    )
    return result, client


def test_the_menu_and_the_utterance_become_the_prompt(stub_llm_client, read_file_paths):
    """Context 로딩은 LLM 호출보다 먼저 일어남.

    menu 를 실제 파일에서 읽어야 함. 코드에 박아두면 recipe 를 등록해도
    LLM 이 새 recipe 를 영영 못 고름. 발화도 그대로 실려야 하고,
    LLM 은 정확히 한 번만 부름.
    """
    read_file_paths.clear()
    menu = load_menu()

    assert menu_was_read(read_file_paths), f"실제 menu.yaml 을 안 읽었다: {paths.MENU_YAML_PATH}"
    assert isinstance(menu, str) and menu.strip()

    _, client = resolve(stub_llm_client, json.dumps({
        "reason": "결빙 위험도 분석과 하는 일이 같다.",
        "argument": "기상 관측값",
        "candidate_recipe_ids": ["recipe_004"],
        "status": SELECT,
        "recipe_id": "recipe_004",
    }))

    assert len(client.prompts) == 1
    assert UTTERANCE in client.prompts[0]
    for recipe_id in ("recipe_001", "recipe_002"):
        assert recipe_id in client.prompts[0], f"menu 가 프롬프트에 안 실렸다: {recipe_id}"


@pytest.mark.parametrize(
    "answer, status, recipe_id, candidates",
    [
        (
            {"reason": "하는 일이 같다.",
             "argument": "기상 관측값",
             "candidate_recipe_ids": ["recipe_004"],
             "status": SELECT, "recipe_id": "recipe_004"},
            SELECT, "recipe_004", ["recipe_004"],
        ),
        (
            {"reason": "Word 인지 PPT 인지 발화에 없다.",
             "argument": "기상 관측값",
             "candidate_recipe_ids": ["recipe_012", "recipe_013"],
             "status": CLARIFY, "recipe_id": None},
            CLARIFY, None, ["recipe_012", "recipe_013"],
        ),
        (
            {"reason": "menu 에 없는 기능이다.",
             "argument": None,
             "candidate_recipe_ids": [],
             "status": NO_MATCH, "recipe_id": None},
            NO_MATCH, None, [],
        ),
    ],
    ids=["SELECT", "CLARIFY", "NO_MATCH"],
)
def test_only_the_contracted_keys_survive(
    stub_llm_client, answer, status, recipe_id, candidates
):
    """세 상태 모두 같은 형태로 나옴. 호출하는 쪽이 분기하지 않아도 되게.

    스키마에 없는 key 는 버림. LLM 이 덧붙인 것을 그대로 흘리면 계약이
    조용히 넓어지고, 나중에 그것에 기대는 코드가 생김.
    """
    result, _ = resolve(stub_llm_client, json.dumps({**answer, "군더더기": "버려야 한다"}))

    assert_route_contract(result)
    assert set(result) == set(SCHEMA["required"])
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
    """LLM 은 계약을 어김. 코드 블록으로 감싸거나 키를 빠뜨림.

    조용히 넘기면 화면에 빈 결과가 뜨고 원인을 못 찾음. 예외로 올리되
    원문과 저수준 예외를 남김. 그게 없으면 무엇이 잘못됐는지 알 수 없음.
    호출자가 RouteResolutionError 를 몰라도 RuntimeError 로 잡을 수 있어야 함.
    """
    assert issubclass(RouteResolutionError, RuntimeError)

    with pytest.raises(RouteResolutionError) as error_info:
        resolve(stub_llm_client, raw)

    error = error_info.value
    assert isinstance(error.__cause__, cause), f"__cause__ 가 없다: {error.__cause__!r}"
    assert fragment in str(error), f"원문이 안 남았다: {error}"


# ── LLM 이 고른 것을 그대로 쓴다 ────────────────────────────────────


def answer(**overrides) -> str:
    """LLM 이 냈다고 칠 응답 한 벌."""
    return json.dumps({
        "reason": "하는 일이 같다.",
        "argument": "오송역",
        "candidate_recipe_ids": [],
        "status": SELECT,
        "recipe_id": None,
        **overrides,
    })


def resolved(stub_llm_client, **overrides) -> dict:
    return resolve_service.resolve(
        UTTERANCE, llm_client=stub_llm_client(answer(**overrides)), reason_max_length=200
    )


def test_the_chosen_recipe_comes_first_in_the_candidates(stub_llm_client):
    """고른 것을 앞에 두고 중복은 접음. 화면과 실행이 그 차례를 그대로 읽음."""
    result = resolved(
        stub_llm_client,
        recipe_id="recipe_002",
        candidate_recipe_ids=["recipe_004", "recipe_002"],
    )

    assert result["candidate_recipe_ids"] == ["recipe_002", "recipe_004"]


def test_a_recipe_reading_the_screen_context_is_not_dropped_from_the_candidates(
    stub_llm_client,
):
    """**고르는 것과 부를 수 있는 것을 가른다.**

    화면 문맥에서 값을 받는 recipe 를 LLM 이 골랐을 때, 해석은 그것을 그대로
    돌려준다. 문맥이 실제로 왔는지는 execution 이 실행 직전에 보는 것이고
    (execute_service 의 실행 전제), 여기서 미리 빼면 「무엇을 골랐는가」와
    「지금 부를 수 있는가」가 한 값에 섞인다.
    """
    from execution import step_service

    screen = next(
        recipe_id
        for recipe_id in _recipe_ids()
        if step_service.context_needs(recipe_id)
    )
    result = resolved(stub_llm_client, recipe_id=screen, candidate_recipe_ids=[screen])

    assert result["recipe_id"] == screen
    assert result["candidate_recipe_ids"] == [screen]


def test_the_result_carries_the_paths_of_the_candidates(stub_llm_client):
    """프론트엔드가 recipe 파일을 직접 안 읽게 경로를 함께 냄."""
    result = resolved(
        stub_llm_client, recipe_id="recipe_002", candidate_recipe_ids=["recipe_004"]
    )

    assert set(result["paths"]) == {"recipe_002", "recipe_004"}
    assert all(entry["node_id"] for entry in result["paths"]["recipe_002"])


def test_no_match_carries_no_paths(stub_llm_client):
    """고른 것이 없으면 그릴 경로도 없음."""
    result = resolved(stub_llm_client, status=NO_MATCH, argument=None)

    assert result["candidate_recipe_ids"] == []
    assert result["paths"] == {}


def test_the_legacy_pre_filter_fields_are_gone(stub_llm_client):
    """문맥 거르개를 걷으면서 그 전후를 견주던 두 key 도 함께 없앴음.

    남겨 두면 「거르기 전」이라는 것이 아직 있다는 뜻으로 읽히고, 계기판이
    같은 값을 두 번 세게 된다.
    """
    result = resolved(stub_llm_client, recipe_id="recipe_002")

    assert "llm_recipe_id" not in result
    assert "llm_candidate_recipe_ids" not in result


def _recipe_ids():
    from ontology import graph

    return graph.recipe_ids()
