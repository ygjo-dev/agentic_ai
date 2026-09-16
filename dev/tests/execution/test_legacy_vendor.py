"""대상 : execution/legacy_vendor.py — 완성된 KRRI native workflow 를 vendoring 한 실행기로 부르는 임시 다리

여기서 판단하지 않는다. workflow 를 고치지 않고 넘기고, 돌아온 trace 로 단계 이벤트와
마지막 result 를 낸다. workflow 를 만드는 규칙은 test_workflow_materializer.py 가 본다.

LLM 도 Gateway 도 부르지 않는다. vendor 실행기는 가짜로 준다.
"""

import asyncio
import copy

from execution import legacy_vendor, workflow_materializer
from ontology import ONTOLOGY

CCTV_AROUND_A_PLACE = ["place_name", "geocode_place", "point_to_map_extent", "find_cctv"]


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


def ready(chain, argument, context=None):
    """진짜 게시된 recipe 를 READY 로 만든 것."""
    materialized = workflow_materializer.materialize(recipe_of(chain), {"argument": argument}, context)
    assert materialized["status"] == workflow_materializer.READY
    return materialized


def _fake_workflow(called):
    """vendor 실행기 대역. 받은 state · intent 를 남기고 성공 trace 를 돌려준다."""

    async def fake(state, intent):
        called.append((state, copy.deepcopy(intent)))
        return {
            "answer_draft": "답",
            "errors": [],
            "commands": [],
            "artifacts": {"mcp_workflow_trace": [
                {"id": step["id"], "tool": step["tool"], "status": "success"}
                for step in intent["steps"]
            ]},
        }

    return fake


def test_the_workflow_goes_to_the_executor_as_it_was_materialized(monkeypatch):
    """다리는 기호를 풀거나 참조 · inputAdapter 를 정하지 않는다. 받은 한 벌이 그대로 intent 다."""
    called = []
    monkeypatch.setattr(legacy_vendor, "_execute_generic_mcp_workflow", _fake_workflow(called))
    materialized = ready(CCTV_AROUND_A_PLACE, "오송역")

    collect(legacy_vendor.run(materialized, "오송역 CCTV 보여줘"))

    (state, intent), = called
    assert intent == materialized["workflow"]
    assert state["user_text"] == "오송역 CCTV 보여줘"
    assert state["context"] == materialized["context"]


def test_a_step_pair_goes_out_for_every_step_the_vendor_ran(monkeypatch):
    """단계마다 한 쌍이 recipe 순서대로 나감. 마지막은 반드시 result."""
    monkeypatch.setattr(legacy_vendor, "_execute_generic_mcp_workflow", _fake_workflow([]))

    events = collect(legacy_vendor.run(ready(CCTV_AROUND_A_PLACE, "오송역"), ""))

    starts = [event for event in events if event["type"] == "step_start"]
    ends = [event for event in events if event["type"] == "step_end"]

    assert [event["node"] for event in starts] == ["geocode_place", "find_cctv"]
    assert [event["node"] for event in ends] == ["geocode_place", "find_cctv"]
    assert events[-1]["type"] == "result"


def test_the_user_context_names_only_the_servers_a_recipe_calls(monkeypatch):
    """Gateway 가 이 값으로 권한을 찾는다. 빠뜨리면 workflow 가 맞아도 거부된다.

    실측 — refs 에 없는 서버는 HTTP 500 "MCP tool '<서버>/<도구>' is not
    applied for this user." 다.
    """
    called = []
    monkeypatch.setattr(legacy_vendor, "_execute_generic_mcp_workflow", _fake_workflow(called))

    collect(legacy_vendor.run(ready(CCTV_AROUND_A_PLACE, "오송역"), ""))

    user_context = called[0][0]["user_context"]
    assert user_context["user_id"]
    assert user_context["selected_mcp_tool_refs"] == legacy_vendor.USER_CONTEXT["selected_mcp_tool_refs"]


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

    events = collect(legacy_vendor.run(ready(CCTV_AROUND_A_PLACE, "오송역"), ""))

    answer = events[-1]["answer"]
    assert "localhost:3000" not in answer
    assert "Server error" not in answer


def test_a_map_command_only_run_never_reaches_the_vendor(monkeypatch):
    """넘길 steps 가 비고 vendor 는 빈 steps 를 실패로 본다.

    KRRI_ASAP 의 show-facility plugin 에도 `## Run` 절이 없다.
    """
    called = []
    monkeypatch.setattr(legacy_vendor, "_execute_generic_mcp_workflow", _fake_workflow(called))

    events = collect(legacy_vendor.run(ready(["place_name", "show_facility"], "오송 테스트트랙"), ""))

    assert called == []
    assert events[-1]["type"] == "result"
    assert events[-1]["commands"][0] == {"op": "digitalTwin.showFacility", "args": {"facilityName": "오송 테스트트랙"}}
    assert events[-1]["answer"] == legacy_vendor.workflow_answer.NOTHING_RAN


def test_the_step_pair_goes_out_in_the_same_shape_as_a_tool_step():
    """부르는 화면이 진행 표시를 따로 알아볼 것이 없어야 함.

    도구 이름이 오던 자리에 지도 명령 op 이 온다.
    """
    events = collect(legacy_vendor.run(ready(["place_name", "show_facility"], "오송 테스트트랙"), ""))

    starts = [event for event in events if event["type"] == "step_start"]
    ends = [event for event in events if event["type"] == "step_end"]

    assert len(starts) == len(ends) == 1
    assert starts[0]["node"] == ends[0]["node"] == "show_facility"
    assert "digitalTwin.showFacility" in starts[0]["message"]
