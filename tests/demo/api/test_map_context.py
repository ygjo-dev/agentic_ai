"""저쪽 화면이 발화와 함께 보내는 지도 문맥을 받는 것.

LLM 을 부르지 않는다. 축 선택지를 고르는 자리와 배선이 채우는 값만 본다.

**관문은 「문맥이 없을 때 지금과 같다」다.** 화면에서 온 값으로 시작하는 recipe 가
그때도 후보에 들면 없는 좌표로 도구를 부르게 된다.

2026-08-29 부터 Streamlit 과 tools/check_resolve.py 는 문맥을 보낸다
(`--context none` 이면 안 보낸다). 문맥이 없는 길은 그때도 그대로 있어야 한다.

recipe id 를 박지 않는다. 온톨로지가 바뀌면 번호가 통째로 밀리므로 사슬로 찾는다.
"""

import asyncio

import pytest

from demo.api.services import execute_service, ontology_service, resolve_service, step_service

# 저쪽 화면이 실제로 보내는 모양. KRRI_ASAP/ASAP-web 의 ChatRequest 타입과
# CameraManager.getMapContext 를 그대로 옮긴 것이다 (2026-08-28 확인).
FULL_CONTEXT = {
    "camera": {"lon": 127.3, "lat": 36.62, "height": 1500.0},
    "view": {"bbox": [[127.20, 36.55], [127.40, 36.70]]},
    "selectedLocation": {
        "lon": 127.2974,
        "lat": 36.6199,
        "label": "관심 지점",
        "source": "map-right-click",
    },
}

# 우클릭을 아직 안 한 상태. 저쪽은 selectedLocation 을 null 로 보낸다.
NO_PICK_CONTEXT = {**FULL_CONTEXT, "selectedLocation": None}

# 지금 셋. 발화에서 온 값이다.
SPOKEN = ["spoken_place", "spoken_keyword", "spoken_identifier"]


def recipe_for(chain):
    """그 사슬을 가진 recipe id. 번호를 박지 않으려고 찾아서 쓴다."""
    for recipe_id in ontology_service.recipe_ids():
        nodes = [entry["node_id"] for entry in ontology_service.path_of(recipe_id)]
        if nodes == list(chain):
            return recipe_id
    raise AssertionError(f"그런 사슬의 recipe 가 없다: {chain}")


def test_with_no_context_the_given_axis_choices_stay_the_three_from_the_utterance():
    """Streamlit 은 문맥을 안 보낸다. 그쪽에서 프롬프트가 한 글자도 달라지면 안 된다."""
    choices = resolve_service._choices_for(None)

    assert choices["given"] == SPOKEN
    for node_id in step_service.CONTEXT_STARTS:
        assert node_id not in choices["described"]["given"]


def test_an_arriving_context_adds_to_the_choices_only_what_it_can_fill():
    """우클릭을 안 했으면 찍은 지점은 없다. 값이 안 온 축을 고르게 두지 않는다."""
    assert resolve_service._choices_for(FULL_CONTEXT)["given"] == [
        *SPOKEN,
        "picked_point",
        "visible_extent",
    ]
    assert resolve_service._choices_for(NO_PICK_CONTEXT)["given"] == [
        *SPOKEN,
        "visible_extent",
    ]


def test_with_no_context_recipes_starting_from_the_screen_drop_out_of_the_candidates():
    """LLM 이 menu 를 보고 그것을 골라도 뺀다. menu 에는 그 문장이 남아 있다."""
    screen = recipe_for(["visible_extent", "find_cctv"])
    spoken = recipe_for(["spoken_place", "geocode_place", "find_cctv"])
    dropped = resolve_service._dropped_starts(None)

    assert resolve_service._without_dropped([screen, spoken], dropped) == [spoken]


def test_with_a_context_that_recipe_stays_a_candidate():
    screen = recipe_for(["visible_extent", "find_cctv"])
    dropped = resolve_service._dropped_starts(FULL_CONTEXT)

    assert resolve_service._without_dropped([screen], dropped) == [screen]


def test_starting_from_the_visible_extent_the_first_step_takes_the_context_bbox():
    """저쪽 current-view-cctv 가 $context.view.bbox 네 칸을 넣는 것과 같은 자리다."""
    plan = step_service.plan(recipe_for(["visible_extent", "find_cctv"]), "")

    assert plan["steps"][0]["tool"] == "road.getCctv"
    assert plan["steps"][0]["input"] == {
        "minLon": "$context.view.minLon",
        "minLat": "$context.view.minLat",
        "maxLon": "$context.view.maxLon",
        "maxLat": "$context.view.maxLat",
    }


def test_charging_stations_starting_from_the_visible_extent_also_take_the_flat_four():
    """2026-08-30 「예순째」. ev.searchStations 에는 bbox 라는 칸이 없다 —
    없는 칸이라 버려져서 지도를 아무리 좁혀도 전국에서 상한 500건이 왔다.
    CCTV 줄과 같은 꼴이어야 한다."""
    plan = step_service.plan(recipe_for(["visible_extent", "search_ev_stations"]), "")

    assert plan["steps"][0]["tool"] == "ev.searchStations"
    assert plan["steps"][0]["input"] == {
        "minLon": "$context.view.minLon",
        "minLat": "$context.view.minLat",
        "maxLon": "$context.view.maxLon",
        "maxLat": "$context.view.maxLat",
    }


def test_a_tool_taking_a_bbox_array_takes_one_bbox_field_in_the_first_step_too():
    """같이 고치면 오히려 깨지는 자리다. geo.getRailwayLines 의 bbox 는
    진짜로 네 수짜리 배열 칸이다(ASAP-mcp/main.py inputSchema)."""
    plan = step_service.plan(recipe_for(["visible_extent", "get_railway_lines"]), "")

    assert plan["steps"][0]["tool"] == "geo.getRailwayLines"
    assert plan["steps"][0]["input"] == {
        "bbox": [
            "$context.view.minLon",
            "$context.view.minLat",
            "$context.view.maxLon",
            "$context.view.maxLat",
        ]
    }


def test_starting_from_the_picked_point_the_first_step_takes_the_context_selected_location():
    """저쪽 cctv-around-point 와 같은 꼴이다. 중심 좌표와 반경을 준다."""
    plan = step_service.plan(recipe_for(["picked_point", "find_cctv"]), "")

    assert plan["steps"][0]["input"] == {
        "location": "$context.selectedLocation",
        "radiusMeters": step_service.RADIUS_METERS,
    }


def test_a_slot_with_a_previous_step_still_points_at_the_previous_step():
    """input_first 를 더해도 두 번째 칸부터는 한 글자도 안 달라져야 한다."""
    plan = step_service.plan(recipe_for(["spoken_place", "geocode_place", "find_cctv"]), "오송역")

    assert plan["steps"][0]["input"] == {"query": "오송역"}
    assert plan["steps"][1]["input"] == {
        "location": "$s1.location",
        "radiusMeters": step_service.RADIUS_METERS,
    }


def test_a_recipe_starting_from_the_screen_runs_even_without_an_argument_in_the_utterance():
    """"지금 보이는 곳 CCTV 보여줘" 에는 뽑을 말이 없다. 조회할 곳은 문맥이 말했다."""
    assert execute_service._from_screen("visible_extent")
    assert execute_service._from_screen("picked_point")
    assert not execute_service._from_screen("spoken_place")
    assert not execute_service._from_screen(None)


def test_an_empty_context_field_does_not_count_that_start_data():
    """저쪽은 우클릭 전에 selectedLocation 을 null 로 보낸다. 빈 bbox 도 마찬가지다."""
    assert step_service.context_starts(FULL_CONTEXT) == ["picked_point", "visible_extent"]
    assert step_service.context_starts(NO_PICK_CONTEXT) == ["visible_extent"]
    assert step_service.context_starts({"view": {"bbox": []}}) == []
    assert step_service.context_starts({}) == []
    assert step_service.context_starts(None) == []
