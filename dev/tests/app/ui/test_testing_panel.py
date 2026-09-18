"""테스트 탭. runner 결과를 화면 글자로 바꾸는 순수 함수와, 무엇이 LLM 을 부르는지를 본다.

결과는 dev/evaluation/runner.run 을 가짜 resolve 로 돌려 만든다. 화면만을 위한 결과 모양을
따로 지어내면 runner 결과가 바뀌어도 여기가 안 빨개진다.

**화면을 봐도 모르는 것은 숫자가 어긋났는지 · 개발 용어가 샜는지 · 무엇이 LLM 을 부르는지다.**
그것을 여기서 막는다.
"""

import re

import pytest

from app.ui.components import testing_panel as panel
from dev.evaluation import runner
from dev.evaluation import suite as suite_module

# 사람이 보는 화면에 나오면 안 되는 개발 용어
BANNED = ("Recipe", "recipe", "Resolve", "resolve", "Semantic", "semantic", "Menu",
          "Workflow", "Materializ", "기대", "실제", "None", "null", "READY", "UNWIRED", "NOTHING_TO_CALL")

FUNCTIONS = {
    "recipe_010": "지역·당선인·정당을 대면 공약을 검색해 보여준다.",
    "recipe_045": "장소 이름을 말하면 둘레 인구를 낸다.",
    "recipe_061": "출발할 장소에서 닿는 범위를 그린다.",
    "recipe_012": "지역별 인구 수와 순위를 낸다.",
}


def _case(number, utterance, recipe_id, spoken=None):
    expected = {"recipe_ids": [recipe_id]}
    if spoken is not None:
        expected["spoken"] = spoken
    return {"id": number, "group": suite_module.GROUP_IDS[0], "utterance": utterance,
            "enabled": True, "expected": expected}


SUITE = {
    "version": 1,
    "groups": [{"id": name, "label": f"묶음{name}"} for name in suite_module.GROUP_IDS],
    "cases": [
        _case(1, "철도 공약 모아줘", "recipe_010", {"argument": "철도"}),
        _case(2, "오송역 둘레 인구", "recipe_045"),
        _case(3, "청주 서원 시군구 인구", "recipe_012", {"admin_level": "시군구"}),
        _case(4, "오송역에서 걸어서 10분", "recipe_061", {"travel_mode": "도보", "minutes": [10]}),
        _case(5, "터지는 발화", "recipe_045"),
    ],
}

RESPONSES = {
    1: {"recipe_id": "recipe_010", "argument": "철도", "travel_mode": "대중교통", "minutes": None, "admin_level": "시군구"},
    2: {"recipe_id": "recipe_045", "argument": "오송역", "travel_mode": None, "minutes": None, "admin_level": None},
    3: {"recipe_id": "recipe_012", "argument": "청주", "travel_mode": None, "minutes": None, "admin_level": "읍면동"},
    4: {"recipe_id": "recipe_045", "argument": "오송역", "travel_mode": "승용차", "minutes": [10], "admin_level": None,
        "new_field": "값"},
}


def _resolve(utterance):
    number = next(case["id"] for case in SUITE["cases"] if case["utterance"] == utterance)
    if number not in RESPONSES:
        raise RuntimeError("연결이 끊겼습니다")
    response = RESPONSES[number]
    return {"reason": f"{response['recipe_id']} 이 발화와 맞는다", "status": "SELECT",
            "candidate_recipe_ids": [response["recipe_id"]], "paths": {}, **response}


@pytest.fixture(scope="module")
def result():
    """runner 결과 한 벌. 기능 설명은 고정 글자로 바꿔 둠."""
    measured = runner.run(SUITE, resolve=_resolve, materialize=False)
    measured["meta"]["functions"] = dict(FUNCTIONS)
    return measured


def _row(result, number):
    return next(row for row in result["cases"] if row["case_id"] == number)


def visible_text(markup: str) -> str:
    """마크업에서 태그를 걷어낸 글자."""
    return re.sub(r"<[^>]+>", " ", markup)


def test_before_any_run_the_tab_shows_no_numbers():
    """아직 안 돌렸는데 0 / 0 / 0 이 보이면 돌려서 0 건이 나온 것처럼 읽힘."""
    assert panel.summarize(None) is None
    assert panel.run_conditions(None) is None
    text = visible_text(panel.summary_markup(None))
    assert not re.search(r"\d", text), text
    assert text.count(panel.EMPTY_NUMBER) == 5


def test_the_summary_is_copied_from_the_runner_not_counted_here(result):
    total = result["summary"]["total"]
    assert panel.summarize(result) == {
        "total": total["runs"], "passed": total["passed"], "failed": total["runs"] - total["passed"],
        "function": total["failure_stages"]["function"], "input": total["failure_stages"]["input"],
        "error": total["failure_stages"]["error"],
    }
    assert panel.summarize(result) == {"total": 5, "passed": 2, "failed": 3, "function": 1, "input": 1, "error": 1}


def test_the_stage_names_are_the_runner_stages():
    """화면 글자가 runner 의 실패 단계 값과 하나씩 맞아야 필터가 빠짐없이 걸림."""
    assert set(panel.STAGE_LABELS) == set(runner.STAGES)


def test_the_filters_pick_failures_by_stage_and_search_ignores_spaces(result):
    rows = result["cases"]

    assert len(panel.filter_results(rows, "전체")) == 5
    assert [r["case_id"] for r in panel.filter_results(rows, "실패만")] == [3, 4, 5]
    assert [r["case_id"] for r in panel.filter_results(rows, "기능 선택")] == [4]
    assert [r["case_id"] for r in panel.filter_results(rows, "인자 추출")] == [3]
    found = panel.filter_results(rows, "실패만", "청주서원")
    assert [r["utterance"] for r in found] == ["청주 서원 시군구 인구"]


def test_only_the_values_written_in_the_answer_sheet_are_graded_and_the_rest_are_shown(result):
    """정답표에 argument 만 적었어도 모델이 낸 넷을 다 보이고, 셋은 채점 제외다."""
    rows = panel.field_rows(_row(result, 1))

    assert [r["name"] for r in rows] == ["argument", "travel_mode", "minutes", "admin_level"]
    assert [r["name"] for r in rows if r["graded"]] == ["argument"]
    assert all(r["correct"] is None for r in rows if not r["graded"])

    text = visible_text(panel.detail_markup(_row(result, 1), FUNCTIONS))
    assert text.count(panel.UNGRADED_TEXT) == 3
    assert "대중교통" in text and "시군구" in text
    assert "차이" not in text


def test_an_input_the_panel_does_not_know_is_still_shown_under_its_own_name(result):
    """새 인자가 들어와도 화면 코드를 안 고쳐야 함."""
    rows = panel.field_rows(_row(result, 4))

    assert rows[-1] == {
        "name": "new_field", "label": "new_field", "graded": False, "answer": None, "model": "값",
        "in_model": True, "correct": None,
    }


def test_a_wrong_graded_value_is_marked_as_a_difference(result):
    """틀린 칸만 「차이」. 판정은 runner 의 correct 를 읽음."""
    rows = {r["name"]: r for r in panel.field_rows(_row(result, 3))}
    assert rows["admin_level"]["correct"] is False
    text = visible_text(panel.detail_markup(_row(result, 3), FUNCTIONS))
    assert text.count("차이") == 1
    assert "실패 · 인자 추출" in text


def test_a_wrong_function_is_shown_as_a_function_failure_even_with_wrong_values(result):
    text = visible_text(panel.detail_markup(_row(result, 4), FUNCTIONS))
    assert "실패 · 기능 선택" in text
    assert "기능 061" in text and "기능 045" in text
    assert FUNCTIONS["recipe_061"] in text and FUNCTIONS["recipe_045"] in text


def test_missing_values_read_as_없음():
    assert panel.display_value(None) == "없음"
    assert panel.display_value([]) == "없음"
    assert panel.display_value([15, 30]) == "15 · 30"


def test_every_detail_compares_정답표_with_ai_model_output_without_developer_words(result):
    """성공 · 실패 · 오류가 같은 틀이고, 내부 번호 대신 「기능 NNN」이 보여야 함."""
    for row in result["cases"]:
        text = visible_text(panel.detail_markup(row, FUNCTIONS))
        assert "정답표" in text and "AI 모델 출력" in text, row["case_id"]
        assert "모델 판단" in text and "후보 기능" in text and "모델 판정 상태" in text, row["case_id"]
        leaked = [w for w in BANNED if w in text]
        assert not leaked, (row["case_id"], leaked)


def test_an_error_row_shows_the_error_instead_of_a_model_output(result):
    text = visible_text(panel.detail_markup(_row(result, 5), FUNCTIONS))
    assert "실패 · 실행 오류" in text
    assert "연결이 끊겼습니다" in text


def test_the_run_conditions_come_from_the_result_metadata(result):
    conditions = panel.run_conditions(result)
    assert list(conditions) == ["모델", "프롬프트 파일", "응답 형식 파일", "기능 정의 파일"]
    measured = result["meta"]["conditions"]
    assert conditions["모델"] == measured["model"]
    assert conditions["프롬프트 파일"] == measured["prompt"]["path"]
    assert conditions["기능 정의 파일"] == measured["menu"]["path"]


# ── 무엇이 LLM 을 부르나 ─────────────────────────────────────────────
#
# 한 번 재는 데 수십 분이 든다. 탭을 열거나 필터를 바꾸는 것만으로 다시 재면 안 된다.
# AppTest 로 탭을 그리고, 평가를 부르는 자리(run_selected)를 세는 것으로 바꿔 끼운다.
def _tab_script():
    from app.ui.components.testing_panel import render_test_tab

    render_test_tab({"viewport_height": 900})


@pytest.fixture
def app(monkeypatch, result):
    from streamlit.testing.v1 import AppTest

    calls = []

    def run_selected(dataset_id, on_progress=None):
        calls.append(dataset_id)
        if on_progress:
            on_progress(1, 1, result["cases"][0])
        return result

    monkeypatch.setattr(panel, "run_selected", run_selected)
    at = AppTest.from_function(_tab_script, default_timeout=30)
    at.calls = calls
    return at


def test_opening_the_tab_does_not_run_the_evaluation(app):
    app.run()

    assert not app.exception
    assert app.calls == []
    assert any("테스트 세트를 선택하고 실행하면" in m.value for m in app.markdown)


def test_only_the_run_button_runs_the_evaluation_and_filters_do_not_rerun_it(app):
    app.run()
    app.button(key="test_run").click().run()

    assert not app.exception
    assert app.calls == ["resolve_regression"]
    assert any("tt-kpi-num\">5<" in m.value for m in app.markdown)

    app.text_input(key="test_query").input("청주").run()
    app.run()

    assert not app.exception
    assert app.calls == ["resolve_regression"], "필터 · 다시 그리기가 평가를 다시 불렀다"
