"""대상 : execution/execute_service.py — 고른 recipe 를 실제로 부른다

**고르는 것과 부를 수 있는 것을 가른다.** recipe 선택은 resolve_service 의
LLM 이 혼자 하고, 여기서는 고른 것을 지금 부를 수 있는지만 본다.

    배선이 붙었는가    unwired
    화면 문맥이 왔는가  context_needs
    인자가 있는가      spoken_needed

셋 중 하나라도 아니면 다른 recipe 로 갈아타지 않고 실행을 시작하지 않는다.

**셋 다 recipe 에 게시된 execution 이 말한다.** 고른 recipe 를 부르려고 온톨로지를
다시 훑어 계획을 만들지 않고, 블록이 없으면 오류로 멈춘다.

LLM 도 Gateway 도 부르지 않는다. resolve 결과와 vendor 실행기는 가짜로 준다.
"""

import asyncio

import pytest

import paths
from execution import execute_service, legacy_vendor, plan_service, step_service
from ontology import graph, store

# resolve 역할 설정 대역. 해석을 가짜로 주므로 읽히지 않고, 받은 그대로 넘어가는지만 본다.
ROLE = object()


def collect(events):
    """async generator 가 낸 이벤트를 순서대로 모음."""

    async def pump():
        return [event async for event in events]

    return asyncio.run(pump())


def recipe_of(chain):
    """그 사슬을 가진 recipe id. 번호를 박지 않으려고 찾아서 쓴다."""
    for recipe_id in graph.recipe_ids():
        nodes = [entry["node_id"] for entry in graph.path_of(recipe_id)]
        if nodes == list(chain):
            return recipe_id
    raise AssertionError(f"그런 사슬의 recipe 가 없다: {chain}")


def resolved(monkeypatch, **result):
    """resolve 결과를 가짜로 줌. LLM 은 안 부름. recipe 는 진짜 것을 씀."""
    answer = {"status": "SELECT", "recipe_id": "recipe_001", **result}
    monkeypatch.setattr(
        execute_service.resolve_service,
        "resolve",
        lambda text, llm_client, role: answer,
    )


@pytest.fixture
def no_execution(monkeypatch):
    """run 을 가로챔. vendor 실행기와 Gateway 를 안 부름. 받은 것만 남김."""
    seen = {}

    async def fake_run(recipe_id, argument, text="", context=None, options=None):
        seen["recipe_id"], seen["argument"] = recipe_id, argument
        seen["context"] = context
        seen["options"] = options
        yield {"type": "result", "answer": "", "commands": []}

    monkeypatch.setattr(execute_service, "run", fake_run)
    return seen


# ── 해석 결과를 그대로 받는다 ───────────────────────────────────────


def test_the_resolution_goes_out_as_a_step_of_its_own(monkeypatch, no_execution):
    """해석도 한 단계로 냄. 부르는 화면이 진행 상황을 그림."""
    resolved(monkeypatch, argument="오송역")

    events = collect(execute_service.process("오송역 위치 보여줘", None, ROLE, continue_after_resolve=True))

    assert events[0] == {
        "type": "step_start",
        "node": "resolve",
        "message": "발화를 해석하고 있습니다...",
    }
    assert events[1]["type"] == "step_end" and events[1]["node"] == "resolve"


def test_the_context_is_not_passed_to_the_resolution(monkeypatch, no_execution):
    """**무엇을 고를지는 발화와 menu 만 본다.**

    문맥을 해석에 넘기면 「무엇을 골랐는가」와 「지금 부를 수 있는가」가 한
    값에 섞인다. 실행에는 그대로 넘어가야 하므로 그것도 함께 본다.
    """
    seen = {}

    def fake_resolve(text, llm_client, role):
        seen["kwargs"] = (llm_client, role)
        return {"status": "SELECT", "recipe_id": "recipe_001", "argument": "오송역"}

    monkeypatch.setattr(execute_service.resolve_service, "resolve", fake_resolve)

    context = {"view": {"bbox": [[1, 2], [3, 4]]}, "selectedLocation": None}
    collect(execute_service.process("오송역 위치", None, ROLE, context=context, continue_after_resolve=True))

    assert seen["kwargs"] == (None, ROLE), "받은 역할 설정이 해석까지 그대로 가야 한다"
    assert no_execution["context"] == context, "실행에는 문맥이 그대로 가야 한다"


@pytest.mark.parametrize("status", ["CLARIFY", "NO_MATCH"])
def test_a_status_that_is_not_select_calls_no_tool(monkeypatch, no_execution, status):
    """CLARIFY 는 무엇을 부를지 정해지지 않았고 NO_MATCH 는 부를 것이 없음."""
    resolved(
        monkeypatch,
        status=status,
        recipe_id=None,
        candidate_recipe_ids=[],
        paths={},
        reason="",
    )

    events = collect(execute_service.process("아무 말", None, ROLE, continue_after_resolve=True))

    assert not no_execution, "SELECT 가 아닌데 도구를 불렀다"
    assert events[-1]["type"] == "result"


# ── 해석은 한 번, 실행은 이어 갈 때만 ───────────────────────────────


def counting_resolve(monkeypatch, answer):
    """resolve 가 무엇으로 몇 번 불렸는지 남기는 가짜. LLM 은 안 부름."""
    calls = []

    def fake_resolve(text, llm_client, role):
        calls.append((text, llm_client, role))
        return answer

    monkeypatch.setattr(execute_service.resolve_service, "resolve", fake_resolve)
    return calls


def test_resolve_only_returns_the_resolution_and_does_not_execute(monkeypatch, no_execution):
    """POST /resolve 가 지나는 길. 해석 결과를 그대로 돌려주고 거기서 멈춘다."""
    answer = {"status": "SELECT", "recipe_id": "recipe_001", "argument": "오송역"}
    calls = counting_resolve(monkeypatch, answer)

    result = execute_service.process("오송역 위치 보여줘", None, ROLE, continue_after_resolve=False)

    assert result is answer
    assert calls == [("오송역 위치 보여줘", None, ROLE)]
    assert not no_execution, "해석만 하는 길이 실행까지 갔다"


def test_execution_uses_the_one_resolution_as_it_is(monkeypatch, no_execution):
    """**실행 쪽이 다시 해석하지 않는다.**

    두 번 해석하면 LLM 을 두 번 부르고, 두 답이 갈리면 화면에 보인 해석과 실제로
    부른 recipe 가 달라진다. 해석이 낸 인자와 이름 있는 값이 그대로 run 에 간다.
    """
    answer = {
        "status": "SELECT",
        "recipe_id": "recipe_001",
        "argument": "오송역",
        "travel_mode": "도보",
        "minutes": 15,
        "admin_level": None,
    }
    calls = counting_resolve(monkeypatch, answer)

    collect(execute_service.process("오송역 위치 보여줘", None, ROLE, continue_after_resolve=True))

    assert len(calls) == 1
    assert no_execution["recipe_id"] == answer["recipe_id"]
    assert no_execution["argument"] == answer["argument"]
    assert no_execution["options"] == {
        name: answer[name] for name in execute_service.SPOKEN_OPTIONS
    }


def test_the_resolution_starts_only_after_its_step_start_goes_out(monkeypatch, no_execution):
    """KRRI_ASAP 화면은 step_start 를 보고 지금 도는 단계를 그린다.

    해석을 먼저 하고 흐름을 만들면 LLM 이 도는 동안 화면에 아무것도 안 뜬다.
    """
    calls = counting_resolve(
        monkeypatch, {"status": "SELECT", "recipe_id": "recipe_001", "argument": "오송역"}
    )

    async def pump():
        events = execute_service.process("오송역 위치 보여줘", None, ROLE, continue_after_resolve=True)
        before_reading = len(calls)
        first = await events.__anext__()
        after_first = len(calls)
        rest = [event async for event in events]
        return before_reading, first, after_first, rest

    before_reading, first, after_first, rest = asyncio.run(pump())

    assert before_reading == 0, "흐름을 읽기도 전에 해석했다"
    assert first["type"] == "step_start" and first["node"] == "resolve"
    assert after_first == 0, "step_start 가 나가기 전에 해석했다"
    assert len(calls) == 1
    assert rest[-1]["type"] == "result"


# ── 인자가 있는가 ───────────────────────────────────────────────────


def test_the_argument_comes_from_the_llm_and_reaches_execution(monkeypatch, no_execution):
    """LLM 이 뽑은 인자가 그대로 실행까지 감.

    "충북대" 처럼 끝 글자가 장소답지 않은 말도 그대로 감 — 발화에서 무엇이
    인자인지는 문자열 모양이 아니라 발화 해석 LLM 이 안다.
    """
    resolved(monkeypatch, argument="충북대")

    collect(execute_service.process("충북대 근처 CCTV 보여줘", None, ROLE, continue_after_resolve=True))

    assert no_execution["argument"] == "충북대"


def test_a_null_argument_stops_the_call_instead_of_being_re_extracted(
    monkeypatch, no_execution
):
    """**LLM 이 인자를 null 로 냈으면 파이썬이 발화를 다시 훑지 않는다.**

    예전에는 정규식 대비책(place_in)이 "오송역" 을 집어 실행을 살렸음. 그
    자리를 걷었다 — 두 곳이 인자를 뽑으면 어느 값이 어디서 왔는지 표에서 안
    갈리고, 정규식은 "충북대 근처" 를 못 잡으면서 "지금 화면에 든 읍면동
    경계" 의 「읍면동」은 장소로 집었다(실측).

    발화에 장소가 또렷이 있어도 마찬가지다. 그것이 이 시험의 뜻이다.
    """
    resolved(monkeypatch, argument=None)

    events = collect(execute_service.process("오송역 위치 보여줘", None, ROLE, continue_after_resolve=True))

    assert not no_execution, "인자가 없는데 도구를 불렀다"
    assert events[-1]["type"] == "result"


def test_a_context_only_recipe_still_runs_without_a_spoken_argument(
    monkeypatch, no_execution
):
    """발화에서 뽑을 말이 없는 recipe 는 인자가 null 이어도 그대로 돎.

    "지금 보이는 곳 CCTV" 에는 뽑을 말이 없고 조회할 곳은 이미 문맥이 말했음.
    판정은 게시된 execution 의 spoken_needed 가 하고, recipe id 를 여기
    적지 않는다.
    """
    resolved(monkeypatch, recipe_id="recipe_026", argument=None)

    collect(execute_service.process("지금 보이는 데 CCTV 다 띄워줘", None, ROLE, continue_after_resolve=True))

    assert no_execution, "문맥으로 도는 recipe 인데 안 불렀다"
    assert no_execution["argument"] is None, "없는 인자를 지어내지 않는다"


@pytest.mark.parametrize(
    "recipe_id, fragment",
    [
        ("recipe_001", "장소를 함께"),          # 장소 이름(발화)으로 시작
        ("recipe_005", "찾을 것을 함께"),        # 키워드(발화)로 시작
        ("recipe_015", "이름이나 코드를 함께"),   # 선거구 코드(발화)로 시작
    ],
    ids=["place", "keyword", "identifier"],
)
def test_with_neither_the_guidance_matching_the_start_node_goes_out(
    monkeypatch, no_execution, recipe_id, fragment
):
    """장소 문구 하나로 두면 "선거구 찾아줘" 에 장소를 대라고 답하게 됨.

    무엇으로 시작하는 경로인지는 온톨로지가 말한다 — 여기서 다시 안 적는다.
    """
    resolved(monkeypatch, recipe_id=recipe_id, argument=None)

    events = collect(execute_service.process("찾아줘", None, ROLE, continue_after_resolve=True))

    assert fragment in events[-1]["answer"]
    assert not no_execution, "인자가 없는데 도구를 불렀다"


def test_an_unknown_start_node_falls_back_to_the_place_wording(monkeypatch, no_execution):
    """모르는 경로면 장소 문구 그대로다. 줄이 사라지는 것보다 낫다."""
    resolved(monkeypatch, recipe_id="recipe_없음", argument=None)
    monkeypatch.setattr(
        execute_service.plan_service,
        "load",
        lambda recipe_id: {"spoken_needed": True, "context_needs": {}, "workflow": []},
    )

    events = collect(execute_service.process("찾아줘", None, ROLE, continue_after_resolve=True))

    assert "장소를 함께" in events[-1]["answer"]


# ── 실행 전제 : 화면 문맥이 왔는가 ──────────────────────────────────


def test_a_recipe_needing_the_screen_context_does_not_start_without_it():
    """**고른 것을 바꾸지 않고 실행만 멈춘다.**

    없는 좌표로 부르면 전국이 나오거나 required 가 빈 채로 도구가 거부한다.
    무엇을 읽는지는 배선이 말하고 context_needs 가 그것을 센다.
    """
    picked = recipe_of(["point", "point_to_map_extent", "find_cctv"])

    events = collect(execute_service.run(picked, "", context=None))

    assert len(events) == 1 and events[0]["type"] == "result"
    assert events[0]["commands"] == []
    assert "찍어" in events[0]["answer"]


def test_the_guard_names_what_is_missing():
    """무엇이 없어서 못 부르는지 사람이 읽을 수 있어야 함."""
    extent = recipe_of(["map_extent", "find_cctv"])

    events = collect(execute_service.run(extent, "", context={"selectedLocation": {"lon": 1, "lat": 2}}))

    assert "지도 범위" in events[0]["answer"]


def test_a_recipe_that_reads_no_context_runs_without_one(monkeypatch):
    """문맥을 안 읽는 recipe 까지 막으면 말한 장소 발화가 전부 죽는다."""
    called = []
    monkeypatch.setattr(
        legacy_vendor,
        "_execute_generic_mcp_workflow",
        _fake_workflow(called),
    )

    spoken = recipe_of(["place_name", "geocode_place", "point_to_map_extent", "find_cctv"])
    events = collect(execute_service.run(spoken, "오송역", context=None))

    assert called, "문맥이 필요 없는데 막혔다"
    assert events[-1]["type"] == "result"


def test_the_context_that_actually_arrived_lets_it_through(monkeypatch):
    """값이 오면 그대로 실행한다. 판정은 값의 유무이지 recipe id 가 아니다."""
    called = []
    monkeypatch.setattr(
        legacy_vendor,
        "_execute_generic_mcp_workflow",
        _fake_workflow(called),
    )

    picked = recipe_of(["point", "point_to_map_extent", "find_cctv"])
    events = collect(
        execute_service.run(
            picked, "", context={"selectedLocation": {"lon": 127.3, "lat": 36.6}}
        )
    )

    assert called, "문맥이 왔는데 막혔다"
    assert events[-1]["type"] == "result"


def _fake_workflow(called):
    """vendor 실행기 대역. 부른 intent 를 남기고 빈 trace 를 돌려준다."""

    async def fake(state, intent):
        called.append(intent)
        return {
            "answer_draft": "답",
            "errors": [],
            "commands": [],
            "artifacts": {"mcp_workflow_trace": [
                {"id": f"s{index + 1}", "tool": step["tool"], "status": "success"}
                for index, step in enumerate(intent["steps"])
            ]},
        }

    return fake


# ── 실행 전제 : 배선이 붙었는가 ─────────────────────────────────────


def test_a_recipe_with_an_unwired_node_calls_nothing(monkeypatch):
    """부르는 것만 부르면 반쪽 결과를 온전한 답인 것처럼 내놓게 됨."""
    called = []
    monkeypatch.setattr(
        legacy_vendor, "_execute_generic_mcp_workflow", _fake_workflow(called)
    )
    monkeypatch.setattr(
        execute_service.plan_service,
        "load",
        lambda recipe_id: {"spoken_needed": False, "unwired": ["find_cctv"], "context_needs": {}, "workflow": []},
    )

    events = collect(execute_service.run("recipe_001", "오송역"))

    assert called == []
    assert len(events) == 1
    assert "아직 붙지 않아" in events[0]["answer"]


# ── 게시된 계획만 읽는다 ────────────────────────────────────────────


def _untouchable(*args, **kwargs):
    raise AssertionError("요청 중에 온톨로지를 읽거나 계획을 다시 compile 했다")


def test_the_chosen_recipe_runs_from_its_published_plan_without_reading_the_ontology(monkeypatch):
    """**고른 recipe 를 실행하려고 온톨로지를 다시 훑지 않는다.**

    요청 중에 온톨로지를 읽으면 게시된 블록과 온톨로지 중 무엇이 실행을 정하는지
    다시 둘이 된다. 해석부터 vendor 에 넘기는 steps 까지 온톨로지 읽기와 compile 을
    막아 두고 돈다. 넘긴 steps 는 게시된 블록을 채운 것 그대로다.
    """
    spoken = recipe_of(["place_name", "geocode_place", "point_to_map_extent", "find_cctv"])
    published = legacy_vendor.to_legacy(plan_service.request(spoken, plan_service.load(spoken), "오송역"))["steps"]
    called = []
    monkeypatch.setattr(legacy_vendor, "_execute_generic_mcp_workflow", _fake_workflow(called))
    resolved(monkeypatch, recipe_id=spoken, argument="오송역")

    for name in ("read", "raw_bytes", "nodes"):
        monkeypatch.setattr(store, name, _untouchable)
    monkeypatch.setattr(step_service, "compile_execution", _untouchable)

    events = collect(execute_service.process("오송역 CCTV 보여줘", None, ROLE, continue_after_resolve=True))

    assert [intent["steps"] for intent in called] == [published]
    assert [event["node"] for event in events if event["type"] == "step_start"] == [
        "resolve", "geocode_place", "find_cctv",
    ]
    assert events[-1]["type"] == "result"


def test_a_recipe_file_with_no_published_plan_stops_with_an_error_instead_of_planning_again(
    monkeypatch, tmp_path
):
    """execution 이 없는 recipe 파일은 게시 오류다. 온톨로지로 계획을 짜서 대신 부르지 않는다.

    대신 부르는 길이 있으면 블록이 낡거나 빠져도 아무도 모르고, 원천이 다시 둘이 된다.
    """
    (tmp_path / "recipe_900.yaml").write_text(
        "steps:\n\n  - node: place_name\n\n  - node: geocode_place\n", encoding="utf-8"
    )
    monkeypatch.setattr(paths, "RECIPES_DIR", tmp_path)
    monkeypatch.setattr(step_service, "compile_execution", _untouchable)
    called = []
    monkeypatch.setattr(legacy_vendor, "_execute_generic_mcp_workflow", _fake_workflow(called))

    with pytest.raises(plan_service.PlanError, match="블록이 없다"):
        collect(execute_service.run("recipe_900", "오송역"))

    assert called == []


def test_an_id_that_is_not_an_accepted_recipe_calls_nothing(monkeypatch):
    """resolve 응답 schema 에는 recipe id 목록이 없다. 없는 번호가 오면 부를 것이 없다고만 답한다."""
    called = []
    monkeypatch.setattr(legacy_vendor, "_execute_generic_mcp_workflow", _fake_workflow(called))

    events = collect(execute_service.run("recipe_없음", "오송역"))

    assert called == []
    assert events == [{"type": "result", "answer": execute_service.NO_TOOL_ANSWER, "commands": []}]


# ── 도구를 안 부르는 실행 ───────────────────────────────────────────


def test_a_map_command_only_run_never_reaches_the_vendor(monkeypatch):
    """넘길 steps 가 비고 vendor 는 빈 steps 를 실패로 본다.

    KRRI_ASAP 의 show-facility plugin 에도 `## Run` 절이 없다.
    """
    called = []
    monkeypatch.setattr(
        legacy_vendor,
        "_execute_generic_mcp_workflow",
        lambda state, intent: called.append(intent),
    )

    facility = recipe_of(["place_name", "show_facility"])
    events = collect(
        execute_service.run(facility, "오송 테스트트랙", text="오송 테스트트랙 시설물 보여줘")
    )

    assert called == []
    assert events[-1]["type"] == "result"
    assert events[-1]["commands"][0] == {"op": "digitalTwin.showFacility", "args": {"facilityName": "오송 테스트트랙"}}
    assert events[-1]["answer"] == legacy_vendor.NOTHING_RAN


def test_the_step_pair_goes_out_in_the_same_shape_as_a_tool_step():
    """부르는 화면이 진행 표시를 따로 알아볼 것이 없어야 함.

    도구 이름이 오던 자리에 지도 명령 op 이 온다.
    """
    facility = recipe_of(["place_name", "show_facility"])
    events = collect(execute_service.run(facility, "오송 테스트트랙"))

    starts = [event for event in events if event["type"] == "step_start"]
    ends = [event for event in events if event["type"] == "step_end"]

    assert len(starts) == len(ends) == 1
    assert starts[0]["node"] == ends[0]["node"] == "show_facility"
    assert "digitalTwin.showFacility" in starts[0]["message"]


# ── vendor 를 지나는 실행 ───────────────────────────────────────────


def test_a_step_pair_goes_out_for_every_step_the_vendor_ran(monkeypatch):
    """단계마다 한 쌍이 recipe 순서대로 나감. 마지막은 반드시 result."""
    called = []
    monkeypatch.setattr(
        legacy_vendor, "_execute_generic_mcp_workflow", _fake_workflow(called)
    )

    spoken = recipe_of(["place_name", "geocode_place", "point_to_map_extent", "find_cctv"])
    events = collect(execute_service.run(spoken, "오송역"))

    starts = [event for event in events if event["type"] == "step_start"]
    ends = [event for event in events if event["type"] == "step_end"]

    assert [event["node"] for event in starts] == ["geocode_place", "find_cctv"]
    assert [event["node"] for event in ends] == ["geocode_place", "find_cctv"]
    assert events[-1]["type"] == "result"


def test_the_user_context_names_only_the_servers_a_recipe_calls(monkeypatch):
    """Gateway 가 이 값으로 권한을 찾는다. 빠뜨리면 배선이 맞아도 거부된다.

    실측 — refs 에 없는 서버는 HTTP 500 "MCP tool '<서버>/<도구>' is not
    applied for this user." 다.
    """
    called = {}

    async def fake(state, intent):
        called["user_context"] = state["user_context"]
        return {"answer_draft": "답", "errors": [], "commands": [], "artifacts": {}}

    monkeypatch.setattr(legacy_vendor, "_execute_generic_mcp_workflow", fake)

    spoken = recipe_of(["place_name", "geocode_place", "point_to_map_extent", "find_cctv"])
    collect(execute_service.run(spoken, "오송역"))

    assert called["user_context"]["user_id"]
    assert called["user_context"]["selected_mcp_tool_refs"] == (
        execute_service.USER_CONTEXT["selected_mcp_tool_refs"]
    )


def test_a_failed_run_never_shows_the_vendor_wording(monkeypatch):
    """vendor 의 answer_draft 가 HTTP 오류 원문 · 내부 URL 을 그대로 담는다(실측).

    errors 가 있으면 trace 로 우리가 다시 만든다.
    """
    async def failing(state, intent):
        return {
            "answer_draft": "Server error '500' for url 'http://localhost:3000/api/tools/execute'",
            "errors": ["터졌다"],
            "commands": [],
            "artifacts": {"mcp_workflow_trace": []},
        }

    monkeypatch.setattr(legacy_vendor, "_execute_generic_mcp_workflow", failing)

    spoken = recipe_of(["place_name", "geocode_place", "point_to_map_extent", "find_cctv"])
    events = collect(execute_service.run(spoken, "오송역"))

    answer = events[-1]["answer"]
    assert "localhost:3000" not in answer
    assert "Server error" not in answer

# ── 되묻기 · 못 찾음 문구 ───────────────────────────────────────────
#
# resolve 결과 dict 를 만들어 넣고 문자열만 본다. 온톨로지 데이터가 바뀌어도
# 흔들리지 않게 경로와 배선 여부는 가짜로 준다.


def clarify_path(*names):
    """이름 목록을 path_of 모양으로. 맨 앞은 언제나 시작 노드(장소 이름)."""
    chain = [{"node_id": "place_name", "name": "장소 이름", "out_type": "장소 이름"}]
    for index, name in enumerate(names):
        chain.append({"node_id": f"n{index}_{name}", "name": name, "out_type": name})
    return chain


def clarify_resolved(paths, status="CLARIFY", reason=""):
    """resolve 가 내는 dict 중 답 문구가 읽는 칸만."""
    return {
        "status": status,
        "recipe_id": None,
        "candidate_recipe_ids": list(paths),
        "paths": paths,
        "reason": reason,
    }


def clarify_wire(monkeypatch, paths, unwired=()):
    """가짜 경로를 실행 노드 판정에 연결. unwired 에 적은 recipe 만 배선이 없음."""
    monkeypatch.setattr(
        execute_service.graph,
        "executable_in",
        lambda recipe_id: [
            entry["node_id"]
            for entry in paths.get(recipe_id, [])
            if entry["node_id"] != "place_name"
        ],
    )
    monkeypatch.setattr(
        execute_service.plan_service,
        "load",
        lambda recipe_id: {"unwired": ["x"] if recipe_id in unwired else []},
    )


@pytest.fixture
def no_ontology(monkeypatch):
    """실행 노드 판정과 배선 조회를 비움. 되묻기 문구만 보는 시험이 씀.

    **autouse 가 아니다.** 이 파일 앞쪽은 진짜 온톨로지와 배선을 봐야 한다.
    """
    monkeypatch.setattr(
        execute_service.graph, "executable_in", lambda recipe_id: []
    )
    monkeypatch.setattr(execute_service.plan_service, "load", lambda recipe_id: {"unwired": []})


def test_two_candidates_give_a_short_preamble_and_numbered_names(monkeypatch, no_ontology):
    """recipe 번호는 사람에게 뜻이 없음. 마지막 노드 이름이 그 recipe 가 하는 일임."""
    paths = {
        "recipe_035": clarify_path("장소 좌표 변환", "전기차 충전소 검색"),
        "recipe_036": clarify_path("장소 좌표 변환", "전기차 충전기 조회"),
    }
    clarify_wire(monkeypatch, paths)

    answer = execute_service._no_recipe_answer(clarify_resolved(paths))

    assert answer.splitlines() == [
        "어느 것을 보시겠습니까?",
        "  1  전기차 충전소 검색",
        "  2  전기차 충전기 조회",
    ]
    assert "recipe_035" not in answer


def test_four_or_more_candidates_make_the_preamble_longer(monkeypatch, no_ontology):
    """둘셋은 그냥 고르면 되지만 다섯이면 먼저 여러 갈래라고 말해야 함."""
    paths = {f"recipe_{index:03d}": clarify_path(f"조회 {index}") for index in range(1, 6)}
    clarify_wire(monkeypatch, paths)

    answer = execute_service._no_recipe_answer(clarify_resolved(paths))
    lines = answer.splitlines()

    assert lines[0] == "여러 가지로 해석됩니다. 어느 것을 보시겠습니까?"
    assert len(lines) == 6


def test_overlapping_tail_names_are_split_apart_by_prefixing_the_previous_step(monkeypatch, no_ontology):
    """둘 다 철도 노선 조회로 끝나면 이름만으로는 고를 수가 없음."""
    paths = {
        "recipe_003": clarify_path("철도 노선 조회"),
        "recipe_026": clarify_path("장소 좌표 변환", "철도 노선 조회"),
    }
    clarify_wire(monkeypatch, paths)

    answer = execute_service._no_recipe_answer(clarify_resolved(paths))

    assert answer.splitlines()[1:] == [
        "  1  철도 노선 조회",
        "  2  장소 좌표 변환 -> 철도 노선 조회",
    ]


def test_non_overlapping_candidates_get_no_previous_step_prefix(monkeypatch, no_ontology):
    """짧을수록 읽기 쉬움. 가를 필요가 없으면 가르지 않음."""
    paths = {
        "recipe_001": clarify_path("장소 좌표 변환", "CCTV 조회"),
        "recipe_004": clarify_path("장소 좌표 변환", "행정구역 조회"),
    }
    clarify_wire(monkeypatch, paths)

    answer = execute_service._no_recipe_answer(clarify_resolved(paths))

    assert "->" not in answer


def test_an_unwired_candidate_stays_in_the_list_but_is_marked(monkeypatch, no_ontology):
    """골라도 실행되지 않는다는 것을 미리 알려야 함. 빼면 온톨로지가 아는 경로가 안 보임."""
    paths = {
        "recipe_004": clarify_path("행정구역 조회"),
        "recipe_045": clarify_path("연령별 인구 구성 조회"),
    }
    clarify_wire(monkeypatch, paths, unwired={"recipe_045"})

    answer = execute_service._no_recipe_answer(clarify_resolved(paths))

    assert answer.splitlines()[1:] == [
        "  1  행정구역 조회",
        "  2  연령별 인구 구성 조회 (아직 실행할 수 없음)",
    ]


def test_with_no_candidates_the_answer_says_it_is_out_of_scope(no_ontology):
    """NO_MATCH 첫 줄은 그대로 둠. 고를 것이 없으므로 목록도 없음.

    2026-08-29 에 그 뒤로 안내 두 줄이 붙었다. 첫 줄과 이유는 한 글자도 안
    바뀌었다 — KRRI_ASAP 의 unsupported-request 는 고정 문구 한 줄뿐이라 무엇을 대신
    말해야 할지 안 알려준다.
    """
    answer = execute_service._no_recipe_answer(
        {"status": "NO_MATCH", "candidate_recipe_ids": [], "paths": {}, "reason": "이유"}
    )

    head, reason, guide = answer.split("\n\n")

    assert head == "지금 할 수 있는 일 중에 맞는 것이 없습니다."
    assert reason == "이유"
    assert guide.count("\n") == 1


def test_the_guidance_words_come_from_the_ontology(no_ontology):
    """안내를 코드에 박지 않음. 노드를 등록하면 안내도 함께 늘어야 함.

    대상 이름과 시작 데이터 이름을 그대로 적는다. 화면에서 오는 둘(지점 좌표 ·
    지도 범위)은 뺀다 — 사람이 더 말해 줄 것이 없다.
    """
    topics, starts = execute_service._offer_names()
    answer = execute_service._no_recipe_answer(
        {"status": "NO_MATCH", "candidate_recipe_ids": [], "paths": {}, "reason": ""}
    )

    assert topics and starts
    for name in topics + starts:
        assert name in answer
    nodes = execute_service.store.nodes()
    for node_id in step_service.context_sources():
        assert nodes[node_id]["name"] not in starts


def test_an_empty_reason_does_not_leave_a_bare_blank_line(no_ontology):
    """LLM 이 이유를 안 쓴 회차가 있음. 그때 답에 빈 칸이 뜨면 안 됨."""
    answer = execute_service._no_recipe_answer(
        {"status": "NO_MATCH", "candidate_recipe_ids": [], "paths": {}, "reason": ""}
    )

    assert "\n\n\n" not in answer
    assert answer.startswith("지금 할 수 있는 일 중에 맞는 것이 없습니다.\n\n제가 다루는 것은")


def test_empty_paths_fall_back_to_ids_without_dying(no_ontology):
    """paths 가 비어도 답은 나가야 함. 줄이 사라지는 것보다 뜻 없는 id 가 나음."""
    answer = execute_service._no_recipe_answer(
        {
            "status": "CLARIFY",
            "candidate_recipe_ids": ["recipe_035", "recipe_036"],
            "reason": "",
        }
    )

    assert answer.splitlines() == [
        "어느 것을 보시겠습니까?",
        "  1  recipe_035",
        "  2  recipe_036",
    ]


def test_the_reason_is_appended_verbatim_at_the_end_of_the_answer(monkeypatch, no_ontology):
    """왜 못 좁혔는지 읽을 수 있어야 함. 시연에서 설명할 근거임."""
    paths = {
        "recipe_035": clarify_path("전기차 충전소 검색"),
        "recipe_036": clarify_path("전기차 충전기 조회"),
    }
    clarify_wire(monkeypatch, paths)

    answer = execute_service._no_recipe_answer(
        clarify_resolved(paths, reason="충전소인지 충전기인지 분명하지 않음")
    )

    assert answer.endswith("\n\n충전소인지 충전기인지 분명하지 않음")
