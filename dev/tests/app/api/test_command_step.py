"""도구를 안 부르고 지도 명령만 내는 실행.

**vendor 를 안 지난다.** 경로의 실행 노드가 전부 「부를 도구가 없는」 것이면
넘길 steps 가 비고, vendor 는 빈 steps 를 실패로 본다. 그때 배선표가 만든 지도
명령을 그대로 낸다.

저쪽 show-facility plugin 이 하는 일이 그것이다. 아홉 개 plugin 에는 다 있는
`## Run` 절이 그 셋(show-facility · system-chat · unsupported-request)에만
없고, show-facility 는 `## Map` 의 `show_facility $facilityName` 한 줄이 전부다.

LLM 도 Gateway 도 부르지 않는다. 온톨로지와 배선표를 그대로 읽는다.
"""

import asyncio

from app.api.services import execute_service, step_service

# 「말한 장소 → 시설물 표시」 한 벌. 사슬로 찾는다 — 번호는 노드가 늘면 밀린다.
FACILITY_CHAIN = ["spoken_place", "show_facility"]


def recipe_of(chain):
    """그 사슬을 가진 recipe id. 없으면 None."""
    for recipe_id in execute_service.ontology_service.recipe_ids():
        nodes = [entry["node_id"] for entry in execute_service.ontology_service.path_of(recipe_id)]
        if nodes == chain:
            return recipe_id
    return None


def collect(events):
    """async generator 가 낸 이벤트를 순서대로 모음."""

    async def pump():
        return [event async for event in events]

    return asyncio.run(pump())


def test_a_means_of_execution_that_is_not_a_tool_is_recorded_in_the_wiring_table():
    """TOOL_OF 가 「노드 -> 서버 · 도구」에서 「노드 -> 실행 수단」이 됨.

    온톨로지는 그것을 모른다. 거기 적힌 것은 「장소 이름을 받아 시설물 화면을
    내놓는다」 뿐이고, 무엇으로 수행하는지는 예나 지금이나 배선표가 안다.
    """
    row = step_service.TOOL_OF["show_facility"]

    assert row["command"] == step_service.SHOW_FACILITY_COMMAND
    assert "tool" not in row and "server_id" not in row


def test_a_path_with_only_a_map_command_has_empty_steps():
    """vendor 에 넘길 것이 없음. 빈 steps 를 넘기면 vendor 가 실패로 봄."""
    recipe_id = recipe_of(FACILITY_CHAIN)
    plan = step_service.plan(recipe_id, "오송 테스트트랙")

    assert plan["steps"] == []
    assert plan["command_nodes"] == ["show_facility"]
    assert plan["headline"]


def test_the_map_command_is_in_the_shape_the_other_screen_reads():
    """저쪽이 op 이름과 args.facilityName 으로 알아봄.

    KRRI_ASAP/ASAP-web 의 useChat 이 `cmd.op === 'digitalTwin.showFacility'` 로
    가르고 args.facilityName 을 문자열일 때만 읽는다. 둘 중 하나만 어긋나도
    명령이 조용히 버려진다.
    """
    recipe_id = recipe_of(FACILITY_CHAIN)
    command = step_service.plan(recipe_id, "오송 테스트트랙")["commands"][0]

    assert command["op"] == "digitalTwin.showFacility"
    assert command["args"]["facilityName"] == "오송 테스트트랙"
    assert isinstance(command["args"]["facilityName"], str)


def test_it_is_not_counted_as_unwired():
    """unwired 가 비어야 execute_service 가 실행함.

    도구가 없는 것과 배선이 없는 것은 다르다. tools/check_wiring.py 의 C 도
    같은 자리를 본다 — STEP_OF 에 줄이 있으면 안 세어진다.
    """
    assert step_service.unwired(recipe_of(FACILITY_CHAIN)) == []


def test_the_command_and_the_answer_go_out_together_without_passing_vendor(monkeypatch):
    """도구를 하나도 안 부름. 부를 것이 없는데 부르면 vendor 가 실패로 답함."""
    called = []
    monkeypatch.setattr(
        execute_service,
        "_execute_generic_mcp_workflow",
        lambda state, intent: called.append(intent),
    )

    events = collect(
        execute_service.run(recipe_of(FACILITY_CHAIN), "오송 테스트트랙", text="오송 테스트트랙 시설물 보여줘")
    )

    assert called == []
    assert events[-1]["type"] == "result"
    assert events[-1]["commands"][0]["op"] == "digitalTwin.showFacility"
    assert "오송 테스트트랙" in events[-1]["answer"]


def test_the_step_pair_goes_out_in_the_same_shape_as_a_tool_step():
    """저쪽 화면이 진행 표시를 따로 알아볼 것이 없어야 함.

    도구 이름이 오던 자리에 지도 명령 op 이 온다.
    """
    events = collect(execute_service.run(recipe_of(FACILITY_CHAIN), "오송 테스트트랙"))

    starts = [event for event in events if event["type"] == "step_start"]
    ends = [event for event in events if event["type"] == "step_end"]

    assert len(starts) == len(ends) == 1
    assert starts[0]["node"] == ends[0]["node"] == "show_facility"
    assert "digitalTwin.showFacility" in starts[0]["message"]
