"""`POST /resolve` 와 `POST /chat/stream` 이 한 진입점을 지난다.

**두 창구의 차이는 해석 뒤에 실행을 이어 가느냐 하나다.** 창구마다 해석을 따로
부르면 한쪽만 고쳐져도 안 보이고, 화면에서 본 해석과 KRRI_ASAP 이 받은 답이
갈린다.

지키는 것은 셋이다.
  두 창구가 같은 진입점(execute_service.process)을 지나고 continue_after_resolve 만 다르다
  한 요청에서 해석은 한 번이다
  /resolve 는 실행을 안 하고, /chat/stream 은 그 해석 결과를 그대로 실행에 넘긴다
  회차로 남는 것은 /chat/stream 뿐이다

LLM 도 Gateway 도 부르지 않는다. 진입점 · resolve · run 을 대역으로 바꾼다.
"""

import pytest
from fastapi.testclient import TestClient

from app.api import main
from app.api.services.bridge import recent_service

UTTERANCE = "오송역 CCTV 보여줘"

CONTEXT = {"view": {"bbox": [[127.1598, 36.4853], [127.4956, 36.7547]]}}

# LLM 클라이언트 대역. 부르지 않고, 무엇이 넘어갔는지 대조만 한다.
LLM = object()

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
    """회차 기록이 다른 시험에 안 섞이게 비움. LLM 클라이언트도 대역으로 둠."""
    monkeypatch.setattr(main, "get_llm_for", lambda config: LLM)
    recent_service.clear()
    yield
    recent_service.clear()


@pytest.fixture
def entry(monkeypatch):
    """공통 진입점을 대역으로 바꿈. 누가 어떤 값으로 불렀는지만 남김."""
    calls = []

    def fake_process(
        text, llm_client, reason_max_length, context=None, *, continue_after_resolve
    ):
        calls.append(
            {
                "text": text,
                "llm_client": llm_client,
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

    def fake_resolve(text, llm_client, reason_max_length):
        seen["resolve"].append((text, llm_client, reason_max_length))
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
    assert only_resolve[:2] == (UTTERANCE, LLM)


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
