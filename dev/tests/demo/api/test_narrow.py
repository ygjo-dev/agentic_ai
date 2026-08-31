"""좁히기 길(두 번 부르기)과 스위치.

LLM 은 부르지 않는다. 회차마다 다른 답을 내는 대역을 두고, 몇 번 불렸는지와
프롬프트에 무엇이 들어갔는지, 최종 status 와 후보만 본다.

온톨로지 조회(shortlist.candidates)는 대역으로 바꾼다. 후보가 몇 개인지가
이 길의 갈림이고, 진짜 온톨로지의 값은 tools/check_resolve.py 가 잰다.

**recipe id 는 진짜 것을 쓴다.** 조회는 대역이지만 "그 recipe 가 무엇에서
출발하는가" 는 resolve_service 가 온톨로지에 직접 묻는다(_starts_at) —
화면에서 온 값으로 시작하는 것은 문맥이 없으면 후보에서 빠지기 때문이다.
2026-08-28 에 recipe_030 -> recipe_045 · recipe_029 -> recipe_044 로 옮겼다.
같은 사슬의 새 번호다(말한 장소 -> 좌표 -> 충전소 검색 · -> 인구 통계).
"""

import json

import pytest

from demo.api.services import resolve_service
from demo.api.services.resolve_service import (
    FALLBACK_EMPTY,
    FALLBACK_NONE,
    NARROW_ENV,
    resolve,
)
from orchestrator.schemas.response_schema import CLARIFY, NO_MATCH, SELECT

FIRST = {
    "reason": "장소에서 시작해 충전소를 찾는다",
    "given": "spoken_place",
    "want": "item_list",
    "about": "group_ev",
    "argument": "오송역",
}

FULL = {
    **FIRST,
    "candidate_recipe_ids": ["recipe_045"],
    "status": SELECT,
    "recipe_id": "recipe_045",
}


class SequenceLLM:
    """부를 때마다 다음 답을 내는 대역. 프롬프트를 전부 남긴다."""

    def __init__(self, *responses):
        self.responses = [json.dumps(r) for r in responses]
        self.prompts = []
        self.schemas = []

    def generate(self, prompt, response_schema):
        self.prompts.append(prompt)
        self.schemas.append(response_schema)
        return self.responses[len(self.prompts) - 1]


def pick(status=SELECT, recipe_id=None, candidates=()):
    return {
        "reason": "후보 가운데 골랐다",
        "candidate_recipe_ids": list(candidates),
        "status": status,
        "recipe_id": recipe_id,
    }


@pytest.fixture
def lookup(monkeypatch):
    """온톨로지 조회를 정해진 목록으로. 받은 축을 남긴다."""
    state = {"result": [], "axes": []}

    def fake(given=None, want=None, about=None):
        state["axes"].append((given, want, about))
        return list(state["result"])

    monkeypatch.setattr(resolve_service.shortlist, "candidates", fake)
    return state


@pytest.fixture(autouse=True)
def no_env(monkeypatch):
    monkeypatch.delenv(NARROW_ENV, raising=False)


# ── 스위치 ──────────────────────────────────────────────────────────


def test_the_default_is_off_so_the_LLM_is_called_once_with_the_menu(lookup):
    """스위치를 안 주면 지금 길. 응답에 narrow 칸도 없다."""
    lookup["result"] = ["recipe_045"]
    llm = SequenceLLM(FULL)

    result = resolve("오송역 근처 충전소 찾아줘", llm, 200)

    assert len(llm.prompts) == 1
    assert "[Menu]" in llm.prompts[0]
    assert "narrow" not in result
    assert result["recipe_id"] == "recipe_045"


def test_turning_it_off_yields_the_same_keys_as_before(lookup):
    lookup["result"] = ["recipe_045"]
    result = resolve("오송역 근처 충전소 찾아줘", SequenceLLM(FULL), 200, narrow=False)

    assert set(result) == {
        "reason", "given", "want", "about", "argument", "candidate_recipe_ids",
        "status", "recipe_id", "shortlist_recipe_ids", "llm_recipe_id",
        "llm_candidate_recipe_ids", "paths",
    }


def test_the_env_var_being_1_makes_the_default_on(lookup, monkeypatch):
    monkeypatch.setenv(NARROW_ENV, "1")
    lookup["result"] = ["recipe_045"]

    result = resolve("오송역 근처 충전소 찾아줘", SequenceLLM(FIRST), 200)

    assert result["narrow"]["enabled"] is True


def test_the_env_var_not_being_1_means_off(lookup, monkeypatch):
    monkeypatch.setenv(NARROW_ENV, "true")
    lookup["result"] = ["recipe_045"]

    result = resolve("오송역 근처 충전소 찾아줘", SequenceLLM(FULL), 200)

    assert "narrow" not in result


def test_the_argument_takes_precedence_over_the_env_var(lookup, monkeypatch):
    monkeypatch.setenv(NARROW_ENV, "1")
    lookup["result"] = ["recipe_045"]

    result = resolve("오송역 근처 충전소 찾아줘", SequenceLLM(FULL), 200, narrow=False)

    assert "narrow" not in result


# ── 1차 ──────────────────────────────────────────────────────────────


def test_the_first_pass_prompt_has_no_menu_but_has_the_axis_choices(lookup):
    lookup["result"] = ["recipe_045"]
    llm = SequenceLLM(FIRST)

    resolve("오송역 근처 충전소 찾아줘", llm, 200, narrow=True)

    prompt = llm.prompts[0]
    assert "[Menu]" not in prompt
    assert "recipe_001" not in prompt
    assert "spoken_place" in prompt and "group_ev" in prompt
    assert "오송역 근처 충전소 찾아줘" in prompt


def test_the_first_pass_schema_takes_only_the_axes_and_the_argument(lookup):
    lookup["result"] = ["recipe_045"]
    llm = SequenceLLM(FIRST)

    resolve("오송역 근처 충전소 찾아줘", llm, 200, narrow=True)

    assert llm.schemas[0]["required"] == ["reason", "given", "want", "about", "argument"]


def test_the_ontology_is_looked_up_with_the_three_axes_the_first_pass_wrote(lookup):
    lookup["result"] = ["recipe_045"]

    resolve("오송역 근처 충전소 찾아줘", SequenceLLM(FIRST), 200, narrow=True)

    assert lookup["axes"] == [("spoken_place", "item_list", "group_ev")]


# ── 후보 하나 ────────────────────────────────────────────────────────


def test_a_single_candidate_skips_the_second_pass_and_selects_it(lookup):
    lookup["result"] = ["recipe_045"]
    llm = SequenceLLM(FIRST)

    result = resolve("오송역 근처 충전소 찾아줘", llm, 200, narrow=True)

    assert len(llm.prompts) == 1
    assert result["status"] == SELECT
    assert result["recipe_id"] == "recipe_045"
    assert result["candidate_recipe_ids"] == ["recipe_045"]
    assert result["shortlist_recipe_ids"] == ["recipe_045"]
    assert result["narrow"]["second_called"] is False
    assert result["narrow"]["shortlist_count"] == 1
    assert result["narrow"]["fallback"] is None
    assert result["narrow"]["second_seconds"] is None


def test_the_raw_LLM_fields_are_empty_when_the_second_pass_was_not_called(lookup):
    lookup["result"] = ["recipe_045"]

    result = resolve("오송역 근처 충전소 찾아줘", SequenceLLM(FIRST), 200, narrow=True)

    assert result["llm_recipe_id"] is None
    assert result["llm_candidate_recipe_ids"] == []


def test_the_axes_and_argument_are_carried_verbatim_from_the_first_pass(lookup):
    lookup["result"] = ["recipe_045"]

    result = resolve("오송역 근처 충전소 찾아줘", SequenceLLM(FIRST), 200, narrow=True)

    assert (result["given"], result["want"], result["about"], result["argument"]) == (
        "spoken_place", "item_list", "group_ev", "오송역"
    )
    assert result["paths"].keys() == {"recipe_045"}


# ── 2차 ──────────────────────────────────────────────────────────────


def test_several_candidates_show_the_second_pass_only_those_lines(lookup):
    lookup["result"] = ["recipe_045", "recipe_040"]
    llm = SequenceLLM(FIRST, pick(recipe_id="recipe_045", candidates=["recipe_045"]))

    resolve("오송역 근처 충전소 찾아줘", llm, 200, narrow=True)

    assert len(llm.prompts) == 2
    second = llm.prompts[1]
    assert "recipe_045" in second and "recipe_040" in second
    assert "recipe_001" not in second  # menu 전체가 아니다
    assert "[Menu]" not in second
    assert "오송역 근처 충전소 찾아줘" in second


def test_the_second_pass_schema_blocks_ids_outside_the_candidates(lookup):
    lookup["result"] = ["recipe_045", "recipe_040"]
    llm = SequenceLLM(FIRST, pick(recipe_id="recipe_045", candidates=["recipe_045"]))

    resolve("오송역 근처 충전소 찾아줘", llm, 200, narrow=True)

    schema = llm.schemas[1]
    assert schema["properties"]["recipe_id"]["enum"] == ["recipe_045", "recipe_040", None]
    assert schema["properties"]["candidate_recipe_ids"]["items"]["enum"] == ["recipe_045", "recipe_040"]


def test_the_second_pass_picking_one_selects_it(lookup):
    lookup["result"] = ["recipe_045", "recipe_040"]
    llm = SequenceLLM(FIRST, pick(recipe_id="recipe_040", candidates=["recipe_040"]))

    result = resolve("오송역 근처 충전소 자세히 알려줘", llm, 200, narrow=True)

    assert result["status"] == SELECT
    assert result["recipe_id"] == "recipe_040"
    assert result["candidate_recipe_ids"] == ["recipe_040"]
    assert result["shortlist_recipe_ids"] == ["recipe_045", "recipe_040"]
    assert result["llm_recipe_id"] == "recipe_040"
    assert result["narrow"]["second_called"] is True
    assert result["narrow"]["shortlist_count"] == 2
    assert result["narrow"]["fallback"] is None
    assert result["narrow"]["second_seconds"] is not None


def test_the_second_pass_leaving_several_clarifies_in_lookup_order(lookup):
    """되묻기 후보 목록이 여기서 만들어진다. 차례는 조회 후보(파일 이름 순)."""
    lookup["result"] = ["recipe_011", "recipe_044", "recipe_038"]
    llm = SequenceLLM(FIRST, pick(status=CLARIFY, candidates=["recipe_038", "recipe_011"]))

    result = resolve("청주시 인구 알려줘", llm, 200, narrow=True)

    assert result["status"] == CLARIFY
    assert result["recipe_id"] is None
    assert result["candidate_recipe_ids"] == ["recipe_011", "recipe_038"]
    assert result["paths"].keys() == {"recipe_011", "recipe_038"}


def test_the_second_pass_reason_is_carried(lookup):
    lookup["result"] = ["recipe_045", "recipe_040"]
    llm = SequenceLLM(FIRST, pick(recipe_id="recipe_045", candidates=["recipe_045"]))

    result = resolve("오송역 근처 충전소 찾아줘", llm, 200, narrow=True)

    assert result["reason"] == "후보 가운데 골랐다"


def test_the_second_pass_writing_outside_the_candidates_is_discarded(lookup):
    lookup["result"] = ["recipe_045", "recipe_040"]
    llm = SequenceLLM(FIRST, pick(status=CLARIFY, candidates=["recipe_045", "recipe_099"]))

    result = resolve("오송역 근처 충전소 찾아줘", llm, 200, narrow=True)

    assert result["status"] == SELECT
    assert result["candidate_recipe_ids"] == ["recipe_045"]


# ── 폴백 가 · 나 ─────────────────────────────────────────────────────


def test_an_empty_lookup_candidate_set_goes_to_the_current_path(lookup):
    """폴백 가. 2차 없이 지금 길(menu 전체)을 한 번 더 부른다."""
    lookup["result"] = []
    llm = SequenceLLM(FIRST, FULL)

    result = resolve("오송역 근처 충전소 찾아줘", llm, 200, narrow=True)

    assert len(llm.prompts) == 2
    assert "[Menu]" in llm.prompts[1]
    assert result["narrow"]["fallback"] == FALLBACK_EMPTY
    assert result["narrow"]["second_called"] is False
    assert result["narrow"]["fallback_seconds"] is not None
    assert result["status"] == SELECT and result["recipe_id"] == "recipe_045"


def test_all_three_axes_being_null_skips_the_lookup_and_goes_to_the_current_path(lookup):
    """지금 길과 같은 이유 — 전체를 후보로 삼으면 영역 밖 발화가 되묻기가 된다."""
    blank = {**FIRST, "given": None, "want": None, "about": None, "argument": None}
    lookup["result"] = ["recipe_001"]  # 부르면 이것이 나오지만 안 불러야 한다
    full_blank = {**blank, "status": NO_MATCH, "recipe_id": None, "candidate_recipe_ids": []}
    llm = SequenceLLM(blank, full_blank)

    result = resolve("오늘 날씨 알려줘", llm, 200, narrow=True)

    assert lookup["axes"] == []  # 1차도 폴백(지금 길)도 안 불렀다
    assert result["narrow"]["fallback"] == FALLBACK_EMPTY
    assert result["status"] == NO_MATCH


def test_the_second_pass_saying_no_match_goes_to_the_current_path(lookup):
    """폴백 나. LLM 을 세 번 부르게 된다."""
    lookup["result"] = ["recipe_045", "recipe_040"]
    llm = SequenceLLM(FIRST, pick(status=NO_MATCH), FULL)

    result = resolve("오송역 근처 충전소 찾아줘", llm, 200, narrow=True)

    assert len(llm.prompts) == 3
    assert "[Menu]" in llm.prompts[2]
    assert result["narrow"]["fallback"] == FALLBACK_NONE
    assert result["narrow"]["second_called"] is True
    assert result["status"] == SELECT and result["recipe_id"] == "recipe_045"


def test_the_second_pass_writing_only_outside_the_candidates_counts_as_no_match(lookup):
    lookup["result"] = ["recipe_045", "recipe_040"]
    llm = SequenceLLM(FIRST, pick(recipe_id="recipe_099", candidates=["recipe_099"]), FULL)

    result = resolve("오송역 근처 충전소 찾아줘", llm, 200, narrow=True)

    assert len(llm.prompts) == 3
    assert result["narrow"]["fallback"] == FALLBACK_NONE


def test_the_first_pass_axes_stay_in_narrow_even_when_the_fallback_runs(lookup):
    """폴백 결과의 축은 지금 길 것으로 덮인다. 1차 것은 따로 있어야 왜 빠졌는지 읽힌다."""
    lookup["result"] = []
    other = {**FULL, "given": "spoken_keyword"}
    llm = SequenceLLM(FIRST, other)

    result = resolve("오송역 근처 충전소 찾아줘", llm, 200, narrow=True)

    assert result["given"] == "spoken_keyword"
    assert result["narrow"]["first"]["given"] == "spoken_place"
    assert result["narrow"]["first"]["argument"] == "오송역"


def test_the_fallback_result_has_every_key_of_the_current_path(lookup):
    lookup["result"] = []
    result = resolve("오송역 근처 충전소 찾아줘", SequenceLLM(FIRST, FULL), 200, narrow=True)

    assert {"shortlist_recipe_ids", "llm_recipe_id", "llm_candidate_recipe_ids", "paths"} <= set(result)


# ── 후보 문장 ────────────────────────────────────────────────────────


def test_candidate_lines_record_the_menu_function_along_with_the_id():
    lines = resolve_service._candidate_lines(["recipe_001", "recipe_045"]).splitlines()

    assert lines[0].startswith("- recipe_001: 말한 장소로 좌표를 찾는다")
    assert lines[1].startswith("- recipe_045: ")
    assert len(lines) == 2


def test_an_id_absent_from_the_menu_records_only_the_id():
    assert resolve_service._candidate_lines(["recipe_999"]) == "- recipe_999"
