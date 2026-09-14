"""`POST /resolve` 와 `POST /chat/stream` 이 한 진입점을 지난다.

**두 창구의 차이는 해석 뒤에 실행을 이어 가느냐 하나다.** 창구마다 해석을 따로
부르면 한쪽만 고쳐져도 안 보이고, 화면에서 본 해석과 KRRI_ASAP 이 받은 답이
갈린다.

지키는 것은 셋이다.
  두 창구가 같은 진입점(execute_service.process)을 지나고 continue_after_resolve 만 다르다
  한 요청에서 해석은 한 번이다
  /resolve 는 실행을 안 하고, /chat/stream 은 그 해석 결과를 그대로 실행에 넘긴다
  회차로 남는 것은 /chat/stream 뿐이다
  역할 설정은 요청마다 한 번 읽고, 그 한 벌이 LLM 클라이언트와 해석(등록)에 함께 간다
  요청이 물리 모델을 갈아 끼우는 인자가 없다

LLM 도 Gateway 도 부르지 않는다. 진입점 · resolve · run · 역할 설정을 대역으로 바꾼다.
"""

import inspect

import pytest
from fastapi.testclient import TestClient

from app.api import main
from app.api.services.bridge import recent_service
from llm_engine.role_config import NODE_REGISTRATION, RESOLVE

UTTERANCE = "오송역 CCTV 보여줘"

CONTEXT = {"view": {"bbox": [[127.1598, 36.4853], [127.4956, 36.7547]]}}

# LLM 클라이언트 대역. 부르지 않고, 무엇이 넘어갔는지 대조만 한다.
LLM = object()

# 역할 설정 대역. 창구가 읽은 그 한 벌이 끝까지 가는지를 동일성으로 본다.
ROLE = object()

FORM = {"name": "주변 CCTV 조회", "description": "지도 범위 주변의 CCTV 목록을 조회한다.",
        "inputs": ["map_extent"], "outputs": ["item_list"]}

RESOLVED = {
    "status": "SELECT",
    "recipe_id": "recipe_001",
    "candidate_recipe_ids": ["recipe_001"],
    "reason": "장소 CCTV",
    "argument": "오송역",
    "travel_mode": None,
    "minutes": None,
    "admin_level": None,
    "paths": {},
}

EVENTS = [
    {"type": "step_start", "node": "resolve", "message": "발화를 해석하고 있습니다..."},
    {"type": "step_end", "node": "resolve", "message": "SELECT recipe_001"},
    {"type": "result", "answer": "끝", "commands": []},
]


@pytest.fixture(autouse=True)
def no_turns(monkeypatch):
    """회차 기록이 다른 시험에 안 섞이게 비움. 역할 설정과 LLM 클라이언트도 대역으로 둠.

    무엇을 몇 번 읽었고 무엇으로 LLM 클라이언트를 만들었는지 남김.
    """
    loaded = {"roles": [], "llm_for": []}

    def fake_role_config(role):
        loaded["roles"].append(role)
        return ROLE

    def fake_llm_for(role):
        loaded["llm_for"].append(role)
        return LLM

    monkeypatch.setattr(main, "get_role_config", fake_role_config)
    monkeypatch.setattr(main, "get_llm_for", fake_llm_for)
    recent_service.clear()
    yield loaded
    recent_service.clear()


@pytest.fixture
def entry(monkeypatch):
    """공통 진입점을 대역으로 바꿈. 누가 어떤 값으로 불렀는지만 남김."""
    calls = []

    def fake_process(
        text, llm_client, role, context=None, *, continue_after_resolve
    ):
        calls.append(
            {
                "text": text,
                "llm_client": llm_client,
                "role": role,
                "context": context,
                "continue_after_resolve": continue_after_resolve,
            }
        )
        if not continue_after_resolve:
            return RESOLVED

        async def events():
            for payload in EVENTS:
                yield payload

        return events()

    monkeypatch.setattr(main.execute_service, "process", fake_process)
    return calls


@pytest.fixture
def counted(monkeypatch):
    """진짜 진입점을 두고 resolve 와 run 만 대역으로 바꿈. 몇 번 불렸는지 셈."""
    seen = {"resolve": [], "run": []}

    def fake_resolve(text, llm_client, role):
        seen["resolve"].append((text, llm_client, role))
        return dict(RESOLVED)

    async def fake_run(recipe_id, argument, text="", context=None, options=None):
        seen["run"].append(
            {"recipe_id": recipe_id, "argument": argument, "context": context, "options": options}
        )
        yield {"type": "result", "answer": "끝", "commands": []}

    monkeypatch.setattr(main.resolve_service, "resolve", fake_resolve)
    monkeypatch.setattr(main.execute_service, "run", fake_run)
    return seen


# ================================================================ 한 진입점
def test_the_resolve_endpoint_goes_through_the_common_entry_without_executing(entry):
    """/resolve 가 resolve 를 따로 부르면 두 창구의 해석이 갈릴 자리가 생긴다."""
    with TestClient(main.app) as client:
        response = client.post("/resolve", params={"utterance": UTTERANCE})

    assert response.status_code == 200
    assert response.json() == RESOLVED
    assert entry == [
        {
            "text": UTTERANCE,
            "llm_client": LLM,
            "role": ROLE,
            "context": None,
            "continue_after_resolve": False,
        }
    ]


def test_the_chat_stream_endpoint_goes_through_the_same_entry_and_executes(entry):
    """같은 진입점이고 continue_after_resolve 만 다르다. 문맥은 실행에 쓰이도록 그대로 넘어간다."""
    with TestClient(main.app) as client:
        response = client.post("/chat/stream", json={"text": UTTERANCE, "context": CONTEXT})

    assert response.status_code == 200
    assert entry == [
        {
            "text": UTTERANCE,
            "llm_client": LLM,
            "role": ROLE,
            "context": CONTEXT,
            "continue_after_resolve": True,
        }
    ]


# ================================================================ 해석은 한 번
def test_the_resolve_endpoint_resolves_once_and_runs_nothing(counted):
    with TestClient(main.app) as client:
        response = client.post("/resolve", params={"utterance": UTTERANCE})

    assert response.json() == RESOLVED
    assert len(counted["resolve"]) == 1
    assert counted["run"] == [], "해석만 하는 창구가 실행까지 갔다"


def test_the_chat_stream_resolves_once_and_hands_that_result_to_execution(counted):
    """실행 쪽이 다시 해석하면 LLM 을 두 번 부르고, 화면에 보인 해석과 실제로 부른 recipe 가 갈릴 수 있다."""
    with TestClient(main.app) as client:
        client.post("/chat/stream", json={"text": UTTERANCE, "context": CONTEXT})

    assert len(counted["resolve"]) == 1
    assert counted["run"] == [
        {
            "recipe_id": RESOLVED["recipe_id"],
            "argument": RESOLVED["argument"],
            "context": CONTEXT,
            "options": {"travel_mode": None, "minutes": None, "admin_level": None},
        }
    ]


def test_both_endpoints_hand_the_resolution_the_same_inputs(counted):
    """같은 발화면 두 창구의 해석이 받는 값이 같다. 문맥은 어느 쪽에서도 해석에 안 간다."""
    with TestClient(main.app) as client:
        client.post("/resolve", params={"utterance": UTTERANCE})
        client.post("/chat/stream", json={"text": UTTERANCE, "context": CONTEXT})

    only_resolve, with_execution = counted["resolve"]
    assert only_resolve == with_execution
    assert only_resolve == (UTTERANCE, LLM, ROLE)


# ================================================================ 역할 설정은 요청마다 한 벌
def test_each_request_loads_the_resolve_role_once_and_hands_that_one_down(counted, no_turns):
    """창구가 resolve 역할 설정을 한 번 읽고, 그 한 벌로 LLM 클라이언트를 만들고 해석에도 넘긴다.

    뒤에서 다시 읽으면 파일을 고치는 중에 온 요청이 모델과 prompt 를 서로 다른 판으로 부른다.
    /chat/stream 도 /resolve 와 같은 한 벌을 쓴다.
    """
    with TestClient(main.app) as client:
        client.post("/resolve", params={"utterance": UTTERANCE})
        client.post("/chat/stream", json={"text": UTTERANCE, "context": CONTEXT})

    assert no_turns["roles"] == [RESOLVE, RESOLVE], "요청 둘에 역할 설정을 한 번씩만 읽어야 한다"
    assert no_turns["llm_for"] == [ROLE, ROLE]
    assert [call[2] for call in counted["resolve"]] == [ROLE, ROLE]


def test_the_node_registration_loads_its_role_once_and_hands_that_one_down(monkeypatch, no_turns):
    """등록도 역할 설정을 한 번 읽고, 그 한 벌이 LLM 클라이언트와 등록에 함께 간다.

    registry 가 prompt 를 위해 다시 읽으면 LLM 클라이언트를 만든 판과 prompt 판이 갈린다.
    """
    seen = []

    def fake_register(form, llm_client, role):
        seen.append((form, llm_client, role))
        return {}

    monkeypatch.setattr(main.node_service, "register", fake_register)

    with TestClient(main.app) as client:
        response = client.post("/nodes", json=FORM)

    assert response.status_code == 200
    assert no_turns["roles"] == [NODE_REGISTRATION]
    assert no_turns["llm_for"] == [ROLE]
    assert seen == [(FORM, LLM, ROLE)]


def test_no_endpoint_takes_a_model_to_swap_the_role_for():
    """요청이 물리 모델을 갈아 끼우는 길이 없다. 역할 manifest 가 정한 판으로만 돈다.

    요청 하나가 manifest 와 다른 모델로 돌면 무엇을 쟀는지 파일로 못 읽는다.
    """
    for endpoint, expected in (
        (main.resolve_endpoint, ["utterance"]),
        (main.register_node_endpoint, ["form"]),
        (main.chat_stream_endpoint, ["form"]),
    ):
        assert list(inspect.signature(endpoint).parameters) == expected, endpoint.__name__
    assert "model" not in inspect.signature(main._process).parameters


# ================================================================ 회차
def test_only_the_chat_stream_leaves_a_turn_and_it_sees_its_resolution(counted, monkeypatch):
    """Streamlit 은 GET /recent 로 KRRI_ASAP 의 회차를 따라 그린다.

    /resolve 가 회차로 남으면 화면에 없는 발화가 끼고, /chat/stream 의 해석이
    회차 칸 밖에서 돌면 고른 recipe 가 비어 남는다.
    """
    monkeypatch.setattr(
        main.resolve_service,
        "resolve",
        recent_service.watch_resolve(main.resolve_service.resolve),
    )

    with TestClient(main.app) as client:
        client.post("/resolve", params={"utterance": UTTERANCE})
        assert recent_service.since()["turns"] == [], "/resolve 가 회차로 남았다"

        client.post("/chat/stream", json={"text": UTTERANCE, "context": CONTEXT})

    turns = recent_service.since()["turns"]
    assert len(turns) == 1
    assert turns[0]["utterance"] == UTTERANCE
    assert turns[0]["recipe_id"] == RESOLVED["recipe_id"]
    assert turns[0]["argument"] == RESOLVED["argument"]
