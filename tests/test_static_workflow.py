import builtins
import json
import os
import re
import urllib.request
from pathlib import Path

import pytest

import paths
from common.llm.ollama import OllamaClient
from common.nlu.route_resolver import RouteResolutionError, resolve_route
from orchestrators.static.menu.load import load_menu
from orchestrators.static.schemas.response_schema import RESPONSE_SCHEMA
from stubs.stub_llm_client import StubLLMClient

SELECT = "SELECT"
CLARIFY = "CLARIFY"
NO_MATCH = "NO_MATCH"

VALID_STATUSES = {SELECT, CLARIFY, NO_MATCH}

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

MENU_PATH = paths.MENU_PATH.resolve()


# ------------------------------------------------------------ 공통 Helper
def assert_route_contract(data, menu_recipe_ids=None):
    """
    실제 menu 에 존재하는 Recipe 를 돌려주는지 검증.
    """
    assert data["status"] in VALID_STATUSES
    assert data["recipe_id"] is None or isinstance(data["recipe_id"], str)
    assert isinstance(data["candidate_recipe_ids"], list)
    assert all(isinstance(rid, str) for rid in data["candidate_recipe_ids"])

    assert isinstance(data["reason"], str)

    if menu_recipe_ids is None:
        return

    assert data["reason"].strip() != ""
    for recipe_id in data["candidate_recipe_ids"]:
        assert recipe_id in menu_recipe_ids
    if data["recipe_id"] is not None:
        assert data["recipe_id"] in menu_recipe_ids


@pytest.fixture
def read_file_paths(monkeypatch):
    recorded = []

    real_open = builtins.open

    def spy_open(file, *args, **kwargs):
        recorded.append(file)
        return real_open(file, *args, **kwargs)

    real_read_text = Path.read_text

    def spy_read_text(self, *args, **kwargs):
        recorded.append(self)
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(Path, "read_text", spy_read_text)
    return recorded


def menu_was_read(recorded):
    for entry in recorded:
        if not isinstance(entry, (str, Path)):
            continue
        try:
            if Path(entry).resolve() == MENU_PATH:
                return True
        except OSError:
            continue
    return False


@pytest.fixture(scope="session")
def menu_recipe_ids():
    assert MENU_PATH.exists(), f"실제 menu 파일이 없다: {MENU_PATH}"
    menu_text = MENU_PATH.read_text(encoding="utf-8")

    numbers = re.findall(r"^#\s*Recipe\s*(\d+)", menu_text, flags=re.MULTILINE)
    recipe_ids = {f"recipe_{number}" for number in numbers}

    assert len(recipe_ids) >= 2, f"실제 menu 에서 Recipe 를 찾지 못했다: {recipe_ids}"
    return recipe_ids


@pytest.fixture(scope="session")
def ollama_status():
    """Ollama 상태 확인"""
    url = f"{OLLAMA_HOST}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {
            "ok": False,
            "detail": (
                f"  연결 주소 : {url}\n"
                f"  실패 원인 : {type(exc).__name__}: {exc}\n"
                "  해결 방법 : ollama serve 로 데몬을 띄운 뒤 다시 실행한다.\n"
                "              주소가 다르면 OLLAMA_HOST 환경변수로 지정한다."
            ),
        }

    models = [model.get("name") for model in payload.get("models", [])]
    if not models:
        return {
            "ok": False,
            "detail": (
                f"  연결 주소 : {url}\n"
                "  실패 원인 : Ollama 는 응답하지만 설치된 모델이 하나도 없다.\n"
                "  해결 방법 : ollama pull <model> 로 모델을 먼저 내려받는다."
            ),
        }

    return {"ok": True, "detail": f"  설치된 모델 : {models}"}


def require_ollama(ollama_status):
    if not ollama_status["ok"]:
        pytest.fail(
            "Ollama 에 연결할 수 없다.\n"
            "이 테스트는 Mock 없이 실제 Ollama 를 호출하는 Integration Test 이므로\n"
            "Ollama 데몬이 반드시 실행 중이어야 한다.\n" + ollama_status["detail"],
            pytrace=False,
        )


# ------------------------------------------- 01. Context Loading for static workflow (menu.md)
def test_01_load_static_context(read_file_paths):
    """Static Workflow 는 Context 로 실제 menu.md 원문을 사용해야 한다.
    LLM 은 여기서 호출하지 않는다. Context 로딩은 LLM 호출보다 먼저 일어난다.
    """
    read_file_paths.clear()

    menu = load_menu()

    assert menu_was_read(read_file_paths), (
        "load_menu() 가 실제 menu.md 를 읽지 않았다.\n"
        f"  기대한 파일 : {MENU_PATH}"
    )
    assert isinstance(menu, str)
    assert menu.strip() != ""


# ------------------------------------------ 02. Recipe Resolution w/o LLM for static workflow
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
def test_02_resolve_static_route(
    utterance, llm_response, expected_status, expected_recipe_id, expected_candidates
):
    """resolve_route() 의 출력 검증.
    SELECT / CLARIFY / NO_MATCH 3가지 상태 출력 검증.
    LLM 사용 안함.
    """
    llm_client = StubLLMClient(json.dumps(llm_response)) # Stub LLM Client 를 만들어서 실제 LLM 호출 없이 테스트

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


# ------------------------------------------ 03. Failure Contract w/o LLM for static workflow
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
def test_03_resolve_route_rejects_broken_llm_response(
    raw_response, expected_cause, expected_message_fragment
):
    """
    LLM 응답 구조화 적용 여부 검토.
    LLM 사용 안함.
    """
    llm_client = StubLLMClient(raw_response)  # Stub LLM Client 를 만들어서 실제 LLM 호출 없이 테스트

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


def test_03_route_resolution_error_is_a_runtime_error():
    """호출자가 RouteResolutionError 를 몰라도 RuntimeError 로 잡을 수 있어야 한다."""
    assert issubclass(RouteResolutionError, RuntimeError)


# ----------------------------------------------- 04. Recipe Resolution with LLM for static workflow
END_TO_END_CASES = [
    # SELECT : 사용자 발화와 Recipe가 1개로 매칭.
    ("CCTV 군중 분석 결과를 Word 문서로 만들어줘", SELECT, "recipe_003", {"recipe_003"}),
    ("CCTV 군중 분석 결과를 관리자에게 알려줘", SELECT, "recipe_005", {"recipe_005"}),
    ("이미지 균열 분석 결과를 PPT 문서로 만들어줘", SELECT, "recipe_009", {"recipe_009"}),
    
    # CLARIFY : Recipe 후보가 2개 이상.
    ("CCTV 군중 분석 결과를 문서로 만들어줘", CLARIFY, None, {"recipe_003", "recipe_004"}),
    ("데이터를 불러와서 분석해줘", CLARIFY, None, {"recipe_002", "recipe_007"}),

    # NO_MATCH : Menu.md 에 없는 recipe.
    ("CCTV 영상으로 열차 속도를 분석해줘", NO_MATCH, None, set()),
    ("오늘 날씨 알려줘", NO_MATCH, None, set()),
]


@pytest.mark.parametrize(
    "utterance, expected_status, expected_recipe_id, expected_candidates",
    END_TO_END_CASES,
)
def test_04_static_workflow_end_to_end(
    ollama_status,
    menu_recipe_ids,
    read_file_paths,
    utterance,
    expected_status,
    expected_recipe_id,
    expected_candidates,
):
    """load_menu -> recipe_selection.md(Prompts for LLM) -> OllamaClient(LLM) -> resolve_route -> 결과.

    LLM(Ollama) 사용.
    """
    require_ollama(ollama_status)
    read_file_paths.clear()

    result = resolve_route(
        prompt=paths.RECIPE_SELECTION_PROMPT_PATH.read_text(encoding="utf-8"),
        variables={"menu": load_menu(), "utterance": utterance},
        response_schema=RESPONSE_SCHEMA,
        llm_client=OllamaClient(),
    )

    # 1. menu.md 를 읽었는지 검토
    assert menu_was_read(read_file_paths), (
        "Static Workflow 가 실제 menu.md 를 읽지 않았다.\n"
        f"  기대한 파일 : {MENU_PATH}"
    )

    # 2. 실제 menu 에 존재하는 Recipe 인지 검토
    assert_route_contract(result, menu_recipe_ids)

    # 3. 결과 검토
    assert result["status"] == expected_status
    assert result["recipe_id"] == expected_recipe_id
    assert set(result["candidate_recipe_ids"]) == expected_candidates
    if expected_status == SELECT:
        assert result["recipe_id"] in result["candidate_recipe_ids"]
