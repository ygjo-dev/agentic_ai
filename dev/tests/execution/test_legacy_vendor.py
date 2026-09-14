"""대상 : execution/legacy_vendor.py — ExecutionRequest 를 지금 KRRI_ASAP vendor 가 받는 옛 입력으로 바꾼다

임시 호환 계층이다. 옛 입력의 표현("$s1.location.0" · "$context.…" · inputAdapter · 채운
조건 · 시각)은 여기서만 생긴다. 계약 쪽은 test_plan_service.py 가 본다.

여기 블록은 test_plan_service.py 의 손으로 쓴 것을 쓴다. 부르는 흐름(이벤트 · 답)은
test_execute_service.py 가 본다.

LLM 도 Gateway 도 부르지 않는다.
"""

import copy
import datetime
import zoneinfo

import pytest

from execution import legacy_vendor, plan_service

from dev.tests.execution.test_plan_service import EXECUTION, SCREEN

NOW = datetime.datetime(2026, 1, 1, 23, 59, tzinfo=zoneinfo.ZoneInfo("Asia/Seoul"))


def legacy(argument, options=None, execution=EXECUTION):
    return legacy_vendor.to_legacy(plan_service.request("recipe_x", execution, argument, options, SCREEN), NOW)


def test_only_the_argument_the_named_values_and_the_moment_are_filled():
    """앞 단계 결과와 화면 값은 참조로 적어 vendor 가 푼다. 채우는 것은 셋뿐이다."""
    plan = legacy("오송역", {"travel_mode": "도보"})

    assert plan["steps"][0]["input"] == {"query": "오송역", "mode": "WALK"}
    assert plan["steps"][2]["input"] == {
        "from_lon": "$context.selectedLocation.lon",
        "to_lon": "$s1.location.0",
        "date": "2026-01-01",
    }
    assert plan["nodes"] == ["geo", "cctv", "trip"]


def test_the_same_type_from_two_producers_is_filled_from_each_producer():
    """화면에서 찍은 지점과 앞 단계가 찾은 지점은 같은 타입이다. 참조가 누가 내놓았는지로 갈린다."""
    sent = legacy("오송역")["steps"][2]["input"]

    assert sent["from_lon"].startswith("$context.")
    assert sent["to_lon"].startswith("$s1.")


def test_a_transform_becomes_the_vendor_input_adapter_and_its_outputs_are_not_sent():
    """transform 을 여기서 계산하지 않는다. 그 입력을 앞에 두고 vendor 어댑터 이름을 건다.

    transform 이 만드는 칸(minLon …)은 어댑터가 만들므로 안 보낸다. 상수 칸은 뒤에 붙는다.
    """
    step = legacy("오송역")["steps"][1]

    assert step["input"] == {"center": ["$s1.location.0", "$s1.location.1"], "radiusMeters": 15000, "k": 3}
    assert step["inputAdapter"] == legacy_vendor.POINT_RADIUS_TO_BBOX


@pytest.mark.parametrize("argument, sent", [("경부선", True), ("오송역", False), (None, False)])
def test_a_condition_is_decided_by_the_argument_when_the_call_is_made(argument, sent):
    step = legacy(argument)["steps"][0]

    assert ("railwayName" in step["input"]) is sent


def test_a_named_value_that_was_not_said_takes_the_default():
    for said in (None, {"travel_mode": None}, {"travel_mode": "비행기"}):
        assert legacy("오송역", said)["steps"][0]["input"]["mode"] == "TRANSIT"


def test_the_request_is_not_changed_by_turning_it_into_the_legacy_form():
    """옛 표현은 새 dict 에만 적는다. 요청이 바뀌면 계약 쪽에 옛 표현이 남는다."""
    request = plan_service.request("recipe_x", EXECUTION, "오송역", {"travel_mode": "도보"}, SCREEN)
    before = copy.deepcopy(request)

    plan = legacy_vendor.to_legacy(request, NOW)
    plan["steps"][1]["input"]["center"].append("x")

    assert request == before
    plan_service.validate_request(request)
