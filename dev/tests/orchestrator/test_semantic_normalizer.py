"""대상 : orchestrator/semantic_normalizer.py — 뽑힌 값을 표준 꼴로

응답 schema 가 이름마다 갈래를 알고 있어 수는 수로, 목록은 목록으로 온다. 여기서
하는 일은 앞뒤 공백을 지우고 「안 말한 것」을 빼는 것뿐이다. **판정은 안 한다** —
모양이 어긋난 값은 그대로 넘겨 semantic_validator 가 말하게 한다.

LLM 을 부르지 않는다. 도구도 모른다.
"""

import pytest

from orchestrator import semantic_catalog
from orchestrator.semantic_normalizer import normalize


def one(name, value):
    return normalize({name: value})


def test_nothing_said_is_nothing_normalized():
    """안 말하면 항목이 없다. 빈 object 도 None 과 같다."""
    assert normalize(None) == []
    assert normalize({}) == []


def test_the_name_that_was_said_keeps_its_value():
    """말한 이름만 key 로 온다. 그 이름과 값이 그대로 한 항목이 된다."""
    assert normalize({"place_name": "의왕역", "travel_time_cutoffs_min": [15, 30, 60]}) == [
        {"name": "place_name", "value": "의왕역"},
        {"name": "travel_time_cutoffs_min", "value": [15, 30, 60]},
    ]


def test_the_edges_of_a_value_are_trimmed():
    """모델이 남긴 앞뒤 공백은 뜻이 아니다. 이름에 붙은 공백도 같다."""
    assert one("place_name", " 의왕역 ") == [{"name": "place_name", "value": "의왕역"}]
    assert normalize({" place_name ": "의왕역"}) == [{"name": "place_name", "value": "의왕역"}]
    assert one("period_range", [" 2020", "2024 "]) == [
        {"name": "period_range", "value": ["2020", "2024"]}
    ]


def test_an_empty_value_is_not_a_value():
    """빈 문자열 · 빈 목록 · null 은 말한 것이 아니다. 그 이름을 통째로 뺀다.

    남기면 「안 말했다」와 「빈 것을 말했다」가 실행에서 같은 자리로 간다.
    게시된 default 로 가야 하는 것은 앞엣것뿐이다.
    """
    assert one("place_name", "   ") == []
    assert one("place_name", None) == []
    assert one("site_domains", []) == []
    assert one("period_range", ["2020", " ", "2024"]) == [
        {"name": "period_range", "value": ["2020", "2024"]}
    ]


def test_the_order_of_a_list_is_the_order_that_was_said():
    """차례가 뜻이다. 정렬하지도 중복을 접지도 않는다."""
    assert one("travel_time_cutoffs_min", [60, 15, 60]) == [
        {"name": "travel_time_cutoffs_min", "value": [60, 15, 60]}
    ]


def test_a_number_that_came_as_text_is_turned_back_into_a_number():
    """문법이 없는 자리(시험 stub · 다른 provider)에서 온 문자열 수의 보루다.

    vLLM 은 schema 로 정수 · 실수를 강제하므로 이 길은 평소 안 쓰인다. 계약을
    지키는 곳이 provider 하나뿐이면 provider 가 바뀔 때 조용히 무너진다.
    """
    assert one("travel_time_cutoffs_min", ["15", "30"]) == [
        {"name": "travel_time_cutoffs_min", "value": [15, 30]}
    ]
    assert one("search_radius_m", "500") == [{"name": "search_radius_m", "value": 500}]
    assert one("min_output_kw", "7.7") == [{"name": "min_output_kw", "value": 7.7}]
    assert one("place_name", "500") == [{"name": "place_name", "value": "500"}]


def test_a_value_that_is_not_a_number_is_left_as_it_came():
    """수로 못 읽히면 글자 그대로 둔다. 여기서 터지지도 버리지도 않는다.

    자리수 쉼표를 지우지 않는다 — "15,30,60" 이 153060 이 된다.
    """
    assert one("search_radius_m", "가까운 곳") == [
        {"name": "search_radius_m", "value": "가까운 곳"}
    ]
    assert one("search_radius_m", "1,000") == [{"name": "search_radius_m", "value": "1,000"}]


def test_the_shape_of_a_value_is_not_fixed_here():
    """목록인가 값 하나인가를 여기서 고치지 않는다. validator 가 말한다.

    고치면 「모델이 맞게 냈다」와 「여기서 주워 담았다」가 한 모양이 되어, 문법이
    실제로 무엇을 강제하고 있는지 표에서 안 보인다.
    """
    assert one("origin", ["의왕역", "오송역"]) == [
        {"name": "origin", "value": ["의왕역", "오송역"]}
    ]
    assert one("travel_time_cutoffs_min", 15) == [
        {"name": "travel_time_cutoffs_min", "value": 15}
    ]
    assert one("place_name", 500) == [{"name": "place_name", "value": 500}]


def test_an_unknown_name_is_carried_through_not_dropped():
    """모르는 이름도 실어 보낸다. 무엇이 왔는지는 validator 가 말해야 한다."""
    assert normalize({"document_names": ["a.pdf"]}) == [
        {"name": "document_names", "value": ["a.pdf"]}
    ]


def test_something_that_is_not_an_object_is_carried_through_not_dropped():
    """모양이 깨진 것도 삼키지 않는다. 조용히 지우면 안 말한 것과 같아진다."""
    assert normalize("이건 object 가 아니다") == [
        {"name": None, "value": "이건 object 가 아니다"}
    ]
    assert normalize([{"name": "place_name", "values": ["의왕역"]}]) == [
        {"name": None, "value": [{"name": "place_name", "values": ["의왕역"]}]}
    ]


@pytest.mark.parametrize("name", semantic_catalog.NAMES)
def test_every_name_in_the_catalog_normalizes(name):
    """목록에 이름이 늘어도 되돌리는 길이 하나다. 이름마다 분기가 없다."""
    shape = semantic_catalog.CATALOG[name]
    one_value = 7 if shape.kind in semantic_catalog.NUMERIC_KINDS else "말한 값"
    value = [one_value] if shape.many else one_value

    assert normalize({name: value}) == [{"name": name, "value": value}]
