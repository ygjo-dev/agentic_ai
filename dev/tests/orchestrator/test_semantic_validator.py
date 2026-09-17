"""대상 : orchestrator/semantic_validator.py — 뽑힌 값이 계약을 지키나

보는 것은 **사람이 말한 값의 모양**뿐이다. 이름을 아는가 · 갈래가 맞는가 ·
0 이하가 아닌가 · 닫힌 선택지 안인가. 도구 값(WALK · adm_cd · availableOnly)은
게시된 Recipe.execution 의 map 이 아는 것이라 여기서 안 본다.

**어긋난 값을 버리지 않는다.** 버리면 말하지 않은 기본값으로 조용히 돌아간다.
"""

import pytest

from orchestrator import semantic_catalog
from orchestrator.semantic_normalizer import normalize
from orchestrator.semantic_validator import SemanticError, validate

# 문맥 · 부르는 순간 · 앞 단계가 주는 값. 발화에서 뽑을 수 없다.
내부값 = (
    "retrieval_top_k", "response_row_cap", "document_names", "search_freshness",
    "search_locale", "origin_points", "destination_points", "selected_point",
    "view_extent", "resolved_point", "resolved_extent", "admin_code",
    "ev_station_id", "runtime_now",
)


def said(*pairs):
    return validate([{"name": name, "value": value} for name, value in pairs])


def test_nothing_said_is_an_empty_result():
    assert validate([]) == {}
    assert validate(None) == {}


def test_what_was_said_comes_back_as_one_map_in_the_order_it_came():
    assert said(("place_name", "의왕역"), ("travel_mode", "도보")) == {
        "place_name": "의왕역",
        "travel_mode": "도보",
    }
    assert list(said(("travel_mode", "도보"), ("place_name", "의왕역"))) == [
        "travel_mode",
        "place_name",
    ]


def test_a_name_that_is_not_in_the_catalog_is_refused():
    with pytest.raises(SemanticError, match="뽑을 수 있는 값이 아니다"):
        said(("장소", "의왕역"))


@pytest.mark.parametrize("name", 내부값)
def test_a_value_that_comes_from_context_or_runtime_is_refused(name):
    """LLM 이 화면 값 · 문서 이름 · 지금 시각을 지어내 보내도 받지 않는다.

    받으면 지어낸 값이 진짜 문맥을 덮는다. 이름을 모른다는 같은 이유로 막힌다.
    """
    with pytest.raises(SemanticError, match="뽑을 수 있는 값이 아니다"):
        said((name, "무엇이든"))


def test_the_same_name_twice_is_refused():
    """어느 쪽이 맞는지 아무도 모른다. 뒤엣것으로 덮지 않는다."""
    with pytest.raises(SemanticError, match="두 번"):
        said(("place_name", "의왕역"), ("place_name", "오송역"))


def test_a_value_of_the_wrong_kind_is_refused():
    with pytest.raises(SemanticError, match="정수"):
        said(("search_radius_m", "가까운 곳"))
    with pytest.raises(SemanticError, match="문자열"):
        said(("place_name", 500))
    with pytest.raises(SemanticError, match="수"):
        said(("min_output_kw", True))


def test_a_list_name_wants_a_list_and_a_single_name_wants_one_value():
    with pytest.raises(SemanticError, match="목록이다"):
        said(("travel_time_cutoffs_min", 15))
    with pytest.raises(SemanticError, match="값 하나다"):
        said(("origin", ["의왕역", "오송역"]))


def test_an_empty_list_is_refused():
    with pytest.raises(SemanticError, match="빈 목록"):
        said(("travel_time_cutoffs_min", []))


def test_every_list_name_has_a_finite_cap_and_a_longer_list_is_refused():
    """**상한 없는 목록은 폭주한다.** 응답 schema 의 maxItems 와 같은 수를 여기서도 본다."""
    many = [name for name, shape in semantic_catalog.CATALOG.items() if shape.many]
    assert many, "목록 이름이 없으면 이 검사가 무력하다"
    for name in many:
        shape = semantic_catalog.CATALOG[name]
        assert shape.max_items > 0, f"{name} 에 상한이 없다"
        sample = 15 if shape.kind != semantic_catalog.TEXT else "x"
        said((name, [sample] * shape.max_items))
        with pytest.raises(SemanticError, match="칸까지"):
            said((name, [sample] * (shape.max_items + 1)))


@pytest.mark.parametrize(
    "name", ("travel_time_cutoffs_min", "search_radius_m", "list_result_cap",
             "route_alternatives", "recent_snapshot_count", "max_travel_time_min",
             "min_output_kw"),
)
def test_a_time_a_distance_or_a_count_must_be_more_than_zero(name):
    """음수 시간 · 음수 반경 · 0 개는 뜻이 없다. 그대로 도구에 실리면 0건이 오지 오류가 안 온다."""
    shape = semantic_catalog.CATALOG[name]
    for number in (-1, 0):
        with pytest.raises(SemanticError, match="0 보다 커야"):
            said((name, [number] if shape.many else number))


def test_a_closed_choice_is_closed():
    assert said(("travel_mode", "도보"))["travel_mode"] == "도보"
    assert said(("admin_level", "시군구"))["admin_level"] == "시군구"
    with pytest.raises(SemanticError, match="travel_mode"):
        said(("travel_mode", "걸어서"))
    with pytest.raises(SemanticError, match="admin_level"):
        said(("admin_level", "구"))


def test_a_tool_word_is_not_a_spoken_value():
    """도구가 쓰는 말(WALK)은 사람이 말한 값이 아니다. 「도보」가 WALK 가 되는 것은 execution 의 map 이 안다."""
    with pytest.raises(SemanticError, match="travel_mode"):
        said(("travel_mode", "WALK"))


@pytest.mark.parametrize(
    "name", ("political_party", "elected_person", "pledge_category", "document_hint",
             "charger_type", "charger_availability", "population_metric",
             "ranking_order", "time_anchor", "trip_date", "trip_time"),
)
def test_a_free_value_is_not_closed_for_no_reason(name):
    """사람이 말하는 대로 들어오는 값을 억지로 닫지 않는다. 닫으면 멀쩡한 발화가 오류가 된다."""
    assert said((name, "사람이 말한 그대로"))[name] == "사람이 말한 그대로"


def test_an_empty_string_is_not_a_value():
    with pytest.raises(SemanticError, match="빈 곳이 없는 문자열"):
        said(("place_name", ""))


def test_the_value_is_not_filled_in_or_fixed():
    """기본값을 넣지 않는다. 기본값은 게시된 execution 이 갖는다."""
    assert validate(normalize({"place_name": "의왕역"})) == {"place_name": "의왕역"}
