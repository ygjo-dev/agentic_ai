"""`POST /resolve` 와 `POST /chat/stream` 이 한 진입점을 지난다.

**두 창구의 차이는 해석 뒤에 실행을 이어 가느냐 하나다.** 창구마다 해석을 따로
부르면 한쪽만 고쳐져도 안 보이고, 화면에서 본 해석과 KRRI_ASAP 이 받은 답이
갈린다.

지키는 것은 이것이다.
  두 창구가 같은 진입점(main._process)을 지나고 continue_after_resolve 만 다르다
  한 요청에서 해석은 한 번이고, 해석 단계의 step_start 가 LLM 보다 먼저 나간다
  /resolve 는 실행을 안 하고, /chat/stream 은 그 해석 결과를 그대로 실행에 넘긴다
  SELECT 가 아니거나 지금 부를 수 없으면 도구를 안 부르고 그렇다고 답한다
  요청 중에 온톨로지로 계획을 다시 만들지 않는다
  회차로 남는 것은 /chat/stream 뿐이다
  역할 설정은 요청마다 한 번 읽고, 그 한 벌이 LLM 클라이언트와 해석에 함께 간다
  요청이 물리 모델을 갈아 끼우는 인자가 없다

LLM 도 KRRI 도 부르지 않는다. resolve · 실행(workflow_execution) · 역할 설정을 대역으로 바꾼다.
"""

import asyncio
import inspect

import pytest
from fastapi.testclient import TestClient

from app.api import main
from app.api.services.bridge import recent_service
from execution import krri_executor_client, local_presentation, workflow_materializer
from llm_engine.role_config import RESOLVE
from ontology import ONTOLOGY, Ontology

UTTERANCE = "오송역 CCTV 보여줘"

CONTEXT = {"view": {"bbox": [[127.1598, 36.4853], [127.4956, 36.7547]]}}

# LLM 클라이언트 대역. 부르지 않고, 무엇이 넘어갔는지 대조만 한다.
LLM = object()

# 역할 설정 대역. 창구가 읽은 그 한 벌이 끝까지 가는지를 동일성으로 본다.
ROLE = object()

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


def collect(events):
    """async generator 가 낸 이벤트를 순서대로 모음."""

    async def pump():
        return [event async for event in events]

    return asyncio.run(pump())


def recipe_of(chain):
    """그 사슬을 가진 recipe id. 번호를 박지 않으려고 찾아서 쓴다."""
    for recipe_id in ONTOLOGY.recipe_ids():
        if ONTOLOGY.recipe_nodes(recipe_id) == list(chain):
            return recipe_id
    raise AssertionError(f"그런 사슬의 recipe 가 없다: {chain}")


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
    """진입점 뒤의 두 갈래(해석만 · 실행까지)를 대역으로 바꿈. 누가 어떤 값으로 불렀는지만 남김."""
    calls = []

    def fake_resolve(text, llm_client, role):
        calls.append({"text": text, "llm_client": llm_client, "role": role, "continue_after_resolve": False})
        return RESOLVED

    async def fake_stream(text, llm_client, role, context):
        calls.append({"text": text, "llm_client": llm_client, "role": role, "context": context,
                      "continue_after_resolve": True})
        for payload in EVENTS:
            yield payload

    monkeypatch.setattr(main, "_resolve", fake_resolve)
    monkeypatch.setattr(main, "_stream", fake_stream)
    return calls


@pytest.fixture
def counted(monkeypatch):
    """진짜 진입점을 두고 resolve 와 실행 다리만 대역으로 바꿈. 몇 번 불렸고 무엇을 받았는지 셈."""
    seen = {"resolve": [], "run": [], "answer": dict(RESOLVED)}

    def fake_resolve(text, llm_client, role):
        seen["resolve"].append((text, llm_client, role))
        return seen["answer"]

    async def fake_run(materialized, text):
        seen["run"].append(materialized)
        yield {"type": "result", "answer": "끝", "commands": []}

    monkeypatch.setattr(main.resolve_service, "resolve", fake_resolve)
    monkeypatch.setattr(main.workflow_execution, "run", fake_run)
    return seen


def stream(text=UTTERANCE, context=None):
    """진짜 _process 흐름을 끝까지 돌림. 역할 설정 · LLM 은 대역."""
    return collect(main._process(text, context=context, continue_after_resolve=True))


# ================================================================ 한 진입점
def test_the_resolve_endpoint_goes_through_the_common_entry_without_executing(entry):
    """/resolve 가 resolve 를 따로 부르면 두 창구의 해석이 갈릴 자리가 생긴다."""
    with TestClient(main.app) as client:
        response = client.post("/resolve", params={"utterance": UTTERANCE})

    assert response.status_code == 200
    assert response.json() == RESOLVED
    assert entry == [{"text": UTTERANCE, "llm_client": LLM, "role": ROLE, "continue_after_resolve": False}]


def test_the_chat_stream_endpoint_goes_through_the_same_entry_and_executes(entry):
    """같은 진입점이고 continue_after_resolve 만 다르다. 문맥은 실행에 쓰이도록 그대로 넘어간다."""
    with TestClient(main.app) as client:
        response = client.post("/chat/stream", json={"text": UTTERANCE, "context": CONTEXT})

    assert response.status_code == 200
    assert entry == [
        {"text": UTTERANCE, "llm_client": LLM, "role": ROLE, "context": CONTEXT, "continue_after_resolve": True}
    ]


# ================================================================ 해석은 한 번
def test_the_resolve_endpoint_resolves_once_and_runs_nothing(counted):
    with TestClient(main.app) as client:
        response = client.post("/resolve", params={"utterance": UTTERANCE})

    assert response.json() == RESOLVED
    assert len(counted["resolve"]) == 1
    assert counted["run"] == [], "해석만 하는 창구가 실행까지 갔다"


def test_the_chat_stream_resolves_once_and_hands_that_result_to_execution(counted):
    """실행 쪽이 다시 해석하면 LLM 을 두 번 부르고, 화면에 보인 해석과 실제로 부른 recipe 가 갈릴 수 있다.

    해석이 낸 recipe · 인자가 그대로 workflow 가 되고 화면 문맥이 실행기까지 간다.
    "충북대" 처럼 끝 글자가 장소답지 않은 말도 그대로 간다 — 무엇이 인자인지는 발화 해석 LLM 이 안다.
    """
    counted["answer"] = {**RESOLVED, "argument": "충북대"}

    with TestClient(main.app) as client:
        client.post("/chat/stream", json={"text": UTTERANCE, "context": CONTEXT})

    assert len(counted["resolve"]) == 1
    (materialized,) = counted["run"]
    assert (materialized["status"], materialized["recipe_id"]) == (workflow_materializer.READY, RESOLVED["recipe_id"])
    assert materialized["workflow"]["steps"][0]["input"]["query"] == "충북대"
    assert materialized["context"] == CONTEXT


def test_both_endpoints_hand_the_resolution_the_same_inputs(counted):
    """같은 발화면 두 창구의 해석이 받는 값이 같다. 문맥은 어느 쪽에서도 해석에 안 간다."""
    with TestClient(main.app) as client:
        client.post("/resolve", params={"utterance": UTTERANCE})
        client.post("/chat/stream", json={"text": UTTERANCE, "context": CONTEXT})

    only_resolve, with_execution = counted["resolve"]
    assert only_resolve == with_execution
    assert only_resolve == (UTTERANCE, LLM, ROLE)


def test_the_resolution_starts_only_after_its_step_start_goes_out(counted):
    """KRRI_ASAP 화면은 step_start 를 보고 지금 도는 단계를 그린다.

    해석을 먼저 하고 흐름을 만들면 LLM 이 도는 동안 화면에 아무것도 안 뜬다.
    """

    async def pump():
        events = main._process(UTTERANCE, continue_after_resolve=True)
        before_reading = len(counted["resolve"])
        first = await events.__anext__()
        after_first = len(counted["resolve"])
        rest = [event async for event in events]
        return before_reading, first, after_first, rest

    before_reading, first, after_first, rest = asyncio.run(pump())

    assert before_reading == 0, "흐름을 읽기도 전에 해석했다"
    assert first == EVENTS[0]
    assert after_first == 0, "step_start 가 나가기 전에 해석했다"
    assert len(counted["resolve"]) == 1
    assert rest[0] == EVENTS[1]
    assert rest[-1]["type"] == "result"


# ================================================================ 부르지 않는 자리
@pytest.mark.parametrize("status", ["CLARIFY", "NO_MATCH"])
def test_a_status_that_is_not_select_calls_no_tool(counted, status):
    """CLARIFY 는 무엇을 부를지 정해지지 않았고 NO_MATCH 는 부를 것이 없음."""
    counted["answer"] = {**RESOLVED, "status": status, "recipe_id": None, "candidate_recipe_ids": [], "reason": ""}

    events = stream()

    assert counted["run"] == [], "SELECT 가 아닌데 도구를 불렀다"
    assert events[-1]["type"] == "result"
    assert events[-1]["answer"].startswith(local_presentation.NO_MATCH_HEADLINE)


@pytest.mark.parametrize(
    "chain, fragment",
    [
        (["place_name", "geocode_place"], "장소를 함께"),
        (["keyword", "search_admin_boundaries"], "찾을 것을 함께"),
        (["district_code", "get_election_district"], "이름이나 코드를 함께"),
    ],
    ids=["place", "keyword", "identifier"],
)
def test_a_null_argument_stops_the_call_with_the_guidance_matching_the_start_node(counted, chain, fragment):
    """**LLM 이 인자를 null 로 냈으면 파이썬이 발화를 다시 훑지 않는다.**

    장소 문구 하나로 두면 "선거구 찾아줘" 에 장소를 대라고 답하게 됨. 무엇으로 시작하는 경로인지는
    게시된 recipe 가 말한다 — 여기서 다시 안 적는다.
    """
    recipe_id = recipe_of(chain)
    counted["answer"] = {**RESOLVED, "recipe_id": recipe_id, "argument": None}

    events = stream("오송역 찾아줘")

    assert counted["run"] == [], "인자가 없는데 도구를 불렀다"
    assert fragment in events[-1]["answer"]


def test_a_context_only_recipe_still_runs_without_a_spoken_argument(counted):
    """"지금 보이는 곳 CCTV" 에는 뽑을 말이 없고 조회할 곳은 이미 문맥이 말했음."""
    counted["answer"] = {**RESOLVED, "recipe_id": recipe_of(["map_extent", "find_cctv"]), "argument": None}

    stream(context=CONTEXT)

    assert counted["run"], "문맥으로 도는 recipe 인데 안 불렀다"


@pytest.mark.parametrize(
    "chain, context, fragment",
    [
        (["point", "point_to_map_extent", "find_cctv"], None, "찍어"),
        (["map_extent", "find_cctv"], {"selectedLocation": {"lon": 1, "lat": 2}}, "지도 범위"),
    ],
    ids=["point", "map_extent"],
)
def test_a_recipe_needing_the_screen_context_does_not_start_without_it(counted, chain, context, fragment):
    """**고른 것을 바꾸지 않고 실행만 멈춘다.** 무엇이 없어서 못 부르는지 사람이 읽을 수 있어야 함."""
    counted["answer"] = {**RESOLVED, "recipe_id": recipe_of(chain), "argument": None}

    events = stream(context=context)

    assert counted["run"] == []
    assert events[-1]["commands"] == []
    assert fragment in events[-1]["answer"]


def test_an_id_that_is_not_an_accepted_recipe_calls_nothing(counted):
    """resolve 응답 schema 에는 recipe id 목록이 없다. 없는 번호가 오면 부를 것이 없다고만 답한다."""
    counted["answer"] = {**RESOLVED, "recipe_id": "recipe_없음"}

    events = stream()

    assert counted["run"] == []
    assert events[-1] == {"type": "result", "answer": local_presentation.NO_TOOL_ANSWER, "commands": []}


# ================================================================ 게시된 계획만
def _untouchable(*args, **kwargs):
    raise AssertionError("요청 중에 온톨로지를 읽었다")


def test_the_chosen_recipe_runs_from_its_published_plan_without_reading_the_ontology(monkeypatch):
    """**고른 recipe 를 실행하려고 온톨로지를 다시 훑지 않는다.**

    요청 중에 온톨로지를 읽으면 게시된 블록과 온톨로지 중 무엇이 실행을 정하는지
    다시 둘이 된다. 해석부터 실행기에 넘기는 workflow 까지 온톨로지 읽기를
    막아 두고 돈다. 넘긴 workflow 는 게시된 블록을 채운 것 그대로다.
    """
    spoken = recipe_of(["place_name", "geocode_place", "point_to_map_extent", "find_cctv"])
    published = workflow_materializer.workflow_of(workflow_materializer.load(spoken), {"argument": "오송역"})["workflow"]
    called = []

    async def fake_workflow(workflow, **kwargs):
        called.append(workflow)
        trace = [{"id": step["id"], "tool": step["tool"], "result": {}} for step in workflow["steps"]]
        return {"status": "success", "answer": "답", "commands": [], "trace": trace, "errors": []}

    monkeypatch.setattr(krri_executor_client, "execute_workflow", fake_workflow)
    monkeypatch.setattr(
        main.resolve_service, "resolve",
        lambda text, llm_client, role: {**RESOLVED, "recipe_id": spoken, "candidate_recipe_ids": [spoken]},
    )
    # class 에 건다. 창구가 어느 Ontology 를 들고 있든 파일에 닿으면 걸린다.
    for name in ("document", "raw_bytes", "nodes", "edges"):
        monkeypatch.setattr(Ontology, name, _untouchable)

    events = stream()

    assert called == [published]
    assert [event["node"] for event in events if event["type"] == "step_start"] == [
        "resolve", "geocode_place", "find_cctv",
    ]
    assert events[-1]["type"] == "result"


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


def test_no_endpoint_takes_a_model_to_swap_the_role_for():
    """요청이 물리 모델을 갈아 끼우는 길이 없다. 역할 manifest 가 정한 판으로만 돈다.

    요청 하나가 manifest 와 다른 모델로 돌면 무엇을 쟀는지 파일로 못 읽는다.
    """
    for endpoint, expected in (
        (main.resolve_endpoint, ["utterance"]),
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
