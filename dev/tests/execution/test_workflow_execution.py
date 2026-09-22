"""대상 : execution/workflow_execution.py — 완성된 KRRI native workflow 를 KRRI 실행 창구에 맡기고 이벤트로 낸다

여기서 판단하지 않는다. workflow 를 고치지 않고 넘기고, 돌아온 trace 로 단계 이벤트를,
KRRI 의 answer 로 마지막 result 를 낸다. workflow 를 만드는 규칙은
test_workflow_materializer.py 가, HTTP 로 나르는 일은 test_krri_executor_client.py 가 본다.

LLM 도 KRRI 도 부르지 않는다. KRRI 실행 창구는 가짜로 준다.
"""

import ast
import asyncio
import copy

import pytest

from execution import krri_executor_client, local_presentation, workflow_execution, workflow_materializer
from ontology import ONTOLOGY

CCTV_AROUND_A_PLACE = ["place_name", "geocode_place", "point_to_map_extent", "find_cctv"]

# KRRI 가 만든 답이라는 표시. 우리 local_presentation 문구에 없는 문장이다.
KRRI_ANSWER = "오송역 주변 15km 안에서 CCTV 3대를 찾았습니다. (KRRI)"
KRRI_FAILURE = "s2 단계 MCP tool 실행에 실패했습니다: road.getCctv"
KRRI_COMMAND = {"op": "map.draw", "args": {"layerId": "mcp-place"}}


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


def krri_success(workflow, commands=(KRRI_COMMAND,)):
    """KRRI 창구가 다 돌았을 때 돌려주는 모양."""
    return {
        "status": "success",
        "answer": KRRI_ANSWER,
        "commands": list(commands),
        "trace": [
            {"id": step["id"], "server_id": step["server_id"], "tool": step["tool"], "input": {}, "result": {"items": []}}
            for step in workflow["steps"]
        ],
        "errors": [],
    }


def fake_krri(called, respond=krri_success):
    """KRRI 실행 창구 대역. 받은 것을 남기고 respond 가 만든 응답을 돌려준다."""

    async def fake(workflow, *, user_text, context, user_context):
        called.append({
            "workflow": copy.deepcopy(workflow),
            "user_text": user_text,
            "context": context,
            "user_context": user_context,
        })
        return respond(workflow)

    return fake


def test_the_workflow_goes_to_krri_as_it_was_materialized(monkeypatch):
    """기호를 풀거나 참조 · inputAdapter 를 정하지 않는다. 받은 한 벌이 그대로 나간다."""
    called = []
    monkeypatch.setattr(krri_executor_client, "execute_workflow", fake_krri(called))
    materialized = ready(CCTV_AROUND_A_PLACE, "오송역")
    before = copy.deepcopy(materialized["workflow"])

    collect(workflow_execution.run(materialized, "오송역 CCTV 보여줘"))

    (sent,) = called
    assert sent["workflow"] == before == materialized["workflow"]
    assert sent["user_text"] == "오송역 CCTV 보여줘"
    assert sent["context"] == materialized["context"]


def test_server_tool_order_refs_and_adapter_are_untouched(monkeypatch):
    """KRRI 가 받는 steps 의 서버 · 도구 · 차례 · raw 참조 · inputAdapter 가 materializer 가 적은 그대로다."""
    called = []
    monkeypatch.setattr(krri_executor_client, "execute_workflow", fake_krri(called))
    materialized = ready(CCTV_AROUND_A_PLACE, "오송역")

    collect(workflow_execution.run(materialized, ""))

    sent = called[0]["workflow"]["steps"]
    assert [(step["id"], step["server_id"], step["tool"]) for step in sent] == [
        (step["id"], step["server_id"], step["tool"]) for step in materialized["workflow"]["steps"]
    ]
    assert [step.get("inputAdapter") for step in sent] == [
        step.get("inputAdapter") for step in materialized["workflow"]["steps"]
    ]
    later = sent[1]["input"]
    assert any(isinstance(value, (str, list)) and "$s1." in str(value) for value in later.values())


def test_the_context_goes_to_krri(monkeypatch):
    """화면 문맥은 KRRI 가 $context 참조를 푸는 재료다. 받은 그대로 나간다."""
    called = []
    monkeypatch.setattr(krri_executor_client, "execute_workflow", fake_krri(called))
    context = {"selectedLocation": {"lon": 127.3, "lat": 36.6}}
    materialized = ready(CCTV_AROUND_A_PLACE, "오송역", context)

    collect(workflow_execution.run(materialized, ""))

    assert called[0]["context"] == materialized["context"]


def test_the_user_context_names_only_the_servers_a_recipe_calls(monkeypatch):
    """KRRI 가 이 값을 Gateway 에 넘긴다. 빠뜨리면 workflow 가 맞아도 거부된다.

    실측 — refs 에 없는 서버는 HTTP 500 "MCP tool '<서버>/<도구>' is not
    applied for this user." 다.
    """
    called = []
    monkeypatch.setattr(krri_executor_client, "execute_workflow", fake_krri(called))

    collect(workflow_execution.run(ready(CCTV_AROUND_A_PLACE, "오송역"), ""))

    user_context = called[0]["user_context"]
    assert user_context["user_id"]
    assert user_context["selected_mcp_tool_refs"] == workflow_execution.USER_CONTEXT["selected_mcp_tool_refs"]


def test_a_step_pair_goes_out_for_every_step_krri_ran(monkeypatch):
    """단계마다 한 쌍이 recipe 순서대로 나감. 마지막은 반드시 result."""
    monkeypatch.setattr(krri_executor_client, "execute_workflow", fake_krri([]))

    events = collect(workflow_execution.run(ready(CCTV_AROUND_A_PLACE, "오송역"), ""))

    starts = [event for event in events if event["type"] == "step_start"]
    ends = [event for event in events if event["type"] == "step_end"]

    assert [event["node"] for event in starts] == ["geocode_place", "find_cctv"]
    assert [event["node"] for event in ends] == ["geocode_place", "find_cctv"]
    assert starts[0]["message"] == local_presentation.step_start("geo.geocode")
    assert ends[0]["message"] == local_presentation.step_end("geo.geocode", failed=False)
    assert events[-1]["type"] == "result"


def test_the_krri_success_answer_goes_out_as_it_is(monkeypatch):
    """실제로 실행한 답은 KRRI 가 주인이다. 우리 문구로 다시 쓰지 않는다."""
    monkeypatch.setattr(krri_executor_client, "execute_workflow", fake_krri([]))

    events = collect(workflow_execution.run(ready(CCTV_AROUND_A_PLACE, "오송역"), ""))

    assert events[-1]["answer"] == KRRI_ANSWER


def test_the_krri_failure_answer_goes_out_as_it_is(monkeypatch):
    """실패도 KRRI 의 답이다. trace 로 우리 실패 문구를 다시 만들지 않는다."""

    def failed(workflow):
        first = workflow["steps"][0]
        second = workflow["steps"][1]
        return {
            "status": "failed",
            "answer": KRRI_FAILURE,
            "commands": [],
            "trace": [
                {"id": first["id"], "tool": first["tool"], "result": {"name": "오송역"}},
                {"id": second["id"], "tool": second["tool"], "error": KRRI_FAILURE},
            ],
            "errors": [KRRI_FAILURE],
        }

    monkeypatch.setattr(krri_executor_client, "execute_workflow", fake_krri([], failed))

    events = collect(workflow_execution.run(ready(CCTV_AROUND_A_PLACE, "오송역"), ""))

    ends = [event for event in events if event["type"] == "step_end"]
    assert ends[-1]["message"] == local_presentation.step_end("road.getCctv", failed=True)
    assert events[-1]["answer"] == KRRI_FAILURE


def test_krri_commands_come_first_and_materialized_commands_follow(monkeypatch):
    """지도 명령은 KRRI 가 도구 응답에서 만든 것 뒤에 우리 지도 명령이 붙는다. 순서가 경로 순서다."""
    monkeypatch.setattr(krri_executor_client, "execute_workflow", fake_krri([]))
    materialized = ready(CCTV_AROUND_A_PLACE, "오송역")
    local = {"op": "digitalTwin.showFacility", "args": {"facilityName": "오송역"}}
    materialized = {**materialized, "commands": [local]}

    events = collect(workflow_execution.run(materialized, ""))

    assert events[-1]["commands"] == [KRRI_COMMAND, local]


@pytest.mark.parametrize("reason", ["연결 실패", "시간 초과", "HTTP 500", "모양이 다름", "주소 없음"])
def test_an_unreachable_krri_gets_a_local_answer_and_no_fallback(monkeypatch, reason):
    """KRRI 를 못 부르면 KRRI 가 안 돈 것이다. 우리 문구로 말하고 다른 실행기로 돌아가지 않는다."""

    async def unreachable(workflow, **kwargs):
        raise krri_executor_client.KrriExecutorError(reason)

    monkeypatch.setattr(krri_executor_client, "execute_workflow", unreachable)

    events = collect(workflow_execution.run(ready(CCTV_AROUND_A_PLACE, "오송역"), ""))

    assert [event["type"] for event in events] == ["result"]
    assert events[-1]["answer"] == local_presentation.EXECUTOR_UNREACHABLE
    assert reason not in events[-1]["answer"]


def test_a_map_command_only_run_never_reaches_krri(monkeypatch):
    """넘길 steps 가 비고 KRRI 는 빈 steps 를 실패로 본다.

    KRRI_ASAP 의 show-facility plugin 에도 `## Run` 절이 없다.
    """
    called = []
    monkeypatch.setattr(krri_executor_client, "execute_workflow", fake_krri(called))

    events = collect(workflow_execution.run(ready(["place_name", "show_facility"], "오송 테스트트랙"), ""))

    assert called == []
    assert events[-1]["type"] == "result"
    assert events[-1]["commands"][0] == {"op": "digitalTwin.showFacility", "args": {"facilityName": "오송 테스트트랙"}}
    assert events[-1]["answer"] == local_presentation.NOTHING_RAN


def test_the_step_pair_goes_out_in_the_same_shape_as_a_tool_step():
    """부르는 화면이 진행 표시를 따로 알아볼 것이 없어야 함.

    도구 이름이 오던 자리에 지도 명령 op 이 온다.
    """
    events = collect(workflow_execution.run(ready(["place_name", "show_facility"], "오송 테스트트랙"), ""))

    starts = [event for event in events if event["type"] == "step_start"]
    ends = [event for event in events if event["type"] == "step_end"]

    assert len(starts) == len(ends) == 1
    assert starts[0]["node"] == ends[0]["node"] == "show_facility"
    assert "digitalTwin.showFacility" in starts[0]["message"]


def test_a_step_is_marked_failed_only_where_krri_wrote_an_error(monkeypatch):
    """단계의 성공 · 실패는 KRRI 가 정한다. 도구 결과에 error 칸이 있어도 KRRI 가 trace 항목에
    error 를 안 적었으면 KRRI 는 그것을 성공으로 본 것이고, 우리가 다시 가르지 않는다.
    """

    def judged_by_krri(workflow):
        first, second = workflow["steps"][0], workflow["steps"][1]
        return {
            "status": "success",
            "answer": KRRI_ANSWER,
            "commands": [],
            "trace": [
                {"id": first["id"], "tool": first["tool"], "result": {"error": "도메인 결과 안의 칸"}},
                {"id": second["id"], "tool": second["tool"], "result": {"items": []}},
            ],
            "errors": [],
        }

    monkeypatch.setattr(krri_executor_client, "execute_workflow", fake_krri([], judged_by_krri))

    events = collect(workflow_execution.run(ready(CCTV_AROUND_A_PLACE, "오송역"), ""))

    ends = [event["message"] for event in events if event["type"] == "step_end"]
    assert ends == [local_presentation.step_end("geo.geocode"), local_presentation.step_end("road.getCctv")]


def test_the_runtime_knows_only_the_krri_client_and_local_presentation():
    """실행기는 KRRI_ASAP 에 있다. 이 모듈이 import 하는 프로젝트 모듈은 창구 client 와 문구 둘뿐이다."""
    from paths import REPO_ROOT

    tree = ast.parse((REPO_ROOT / "execution" / "workflow_execution.py").read_text(encoding="utf-8"))
    imported = sorted(
        f"{node.module}.{alias.name}" if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    )
    assert imported == ["execution.krri_executor_client", "execution.local_presentation", "logging"]
    assert not (REPO_ROOT / "vendor_to_be_deleted").exists()
