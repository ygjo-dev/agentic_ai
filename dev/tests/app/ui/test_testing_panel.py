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
        "total": total["runs"], "done": total["runs"], "passed": total["passed"], "failed": total["runs"] - total["passed"],
        "function": total["failure_stages"]["function"], "input": total["failure_stages"]["input"],
        "error": total["failure_stages"]["error"],
    }
    assert panel.summarize(result) == {
        "total": 5, "done": 5, "passed": 2, "failed": 3, "function": 1, "input": 1, "error": 1,
    }


def test_while_running_only_the_finished_rows_are_counted(result):
    """아직 안 끝난 발화를 성공으로도 실패로도 세지 않는다. 전체만 잴 수 전체다."""
    rows = result["cases"]

    first = panel.summarize(panel.live_result(rows[:1], 48))
    assert first == {"total": 48, "done": 1, "passed": 1, "failed": 0, "function": 0, "input": 0, "error": 0}

    four = panel.summarize(panel.live_result(rows[:4], 48))
    assert four == {"total": 48, "done": 4, "passed": 2, "failed": 2, "function": 1, "input": 1, "error": 0}
    assert panel.filter_results(panel.live_result(rows[:4], 48)["cases"], "인자 추출") == [rows[2]]

    text = visible_text(panel.summary_markup(four))
    assert "완료 4 / 48" in text
    assert "완료" not in visible_text(panel.summary_markup(panel.summarize(result)))


def test_the_live_result_carries_the_runner_rows_unchanged(result):
    """실행 중 화면이 줄을 다시 채점하면 끝난 화면과 갈린다."""
    rows = result["cases"][:3]
    live = panel.live_result(rows, 5)

    assert live["cases"] == rows
    assert all(a is b for a, b in zip(live["cases"], rows))


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
def app(monkeypatch):
    """테스트 탭 AppTest. 평가는 진짜 runner.run 을 SUITE 와 가짜 resolve 로 돌림.

    at.calls        run_selected 가 불린 정답표 id
    at.resolved     가짜 resolve 가 받은 발화 (LLM 호출 수 자리)
    at.live         실행 중 화면을 그릴 때마다 (그린 줄 수, 요약 숫자)
    """
    from streamlit.testing.v1 import AppTest

    calls, resolved, live = [], [], []

    def resolve(utterance):
        resolved.append(utterance)
        return _resolve(utterance)

    def run_selected(dataset_id, on_progress=None):
        calls.append(dataset_id)
        measured = runner.run(SUITE, resolve=resolve, progress=on_progress, materialize=False)
        measured["meta"]["functions"] = dict(FUNCTIONS)
        return measured

    render_live = panel._render_live

    def spy(slots, rows, planned, functions, height):
        live.append((len(rows), panel.summarize(panel.live_result(rows, planned))))
        render_live(slots, rows, planned, functions, height)

    monkeypatch.setattr(panel, "run_selected", run_selected)
    monkeypatch.setattr(panel, "_render_live", spy)
    at = AppTest.from_function(_tab_script, default_timeout=30)
    at.calls, at.resolved, at.live = calls, resolved, live
    return at


def test_opening_the_tab_does_not_run_the_evaluation(app):
    app.run()

    assert not app.exception
    assert app.calls == [] and app.resolved == [] and app.live == []
    assert any("테스트 세트를 선택하고 실행하면" in m.value for m in app.markdown)


def test_each_finished_utterance_is_drawn_at_once_while_the_run_goes_on(app):
    """0건 화면부터 시작해 발화 하나가 끝날 때마다 한 줄씩 쌓이고 요약이 따라감."""
    app.run()
    app.button(key="test_run").click().run()

    assert not app.exception
    assert [count for count, _ in app.live] == [0, 1, 2, 3, 4, 5]
    assert app.live[0][1]["passed"] == 0 and app.live[0][1]["failed"] == 0
    assert [(s["passed"], s["function"], s["input"], s["error"]) for _, s in app.live[1:]] == [
        (1, 0, 0, 0), (2, 0, 0, 0), (2, 0, 1, 0), (2, 1, 1, 0), (2, 1, 1, 1),
    ]
    assert {s["total"] for _, s in app.live[1:]} == {5}


def test_the_run_calls_resolve_once_per_utterance_and_ends_on_one_table(app):
    """실행 중 다시 그리기가 LLM 을 더 부르면 안 되고, 끝난 뒤 표가 둘로 남으면 안 됨."""
    app.run()
    app.button(key="test_run").click().run()

    assert not app.exception
    assert app.calls == ["resolve_regression"]
    assert sorted(app.resolved) == sorted(case["utterance"] for case in SUITE["cases"])
    assert len(app.dataframe) == 1
    assert len(app.dataframe[0].value) == 5
    assert any("tt-kpi-num\">5<" in m.value for m in app.markdown)
    assert not any("방금 끝난 발화" in m.value for m in app.markdown)


def test_filters_search_and_redraws_after_the_run_do_not_rerun_it(app):
    app.run()
    app.button(key="test_run").click().run()
    drawn = len(app.live)

    app.text_input(key="test_query").input("청주").run()
    app.run()

    assert not app.exception
    assert app.calls == ["resolve_regression"], "필터 · 다시 그리기가 평가를 다시 불렀다"
    assert len(app.resolved) == len(SUITE["cases"])
    assert len(app.live) == drawn
    assert len(app.dataframe) == 1 and len(app.dataframe[0].value) == 1


def _live_script(count):
    import streamlit as st

    from app.ui.components import testing_panel
    from dev.tests.app.ui.test_testing_panel import FUNCTIONS, SUITE, _resolve
    from dev.evaluation import runner as evaluation_runner

    rows = evaluation_runner.run(SUITE, resolve=_resolve, materialize=False)["cases"][:count]
    slots = {name: st.empty() for name in ("status", "kpi", "list", "detail")}
    testing_panel._render_live(slots, rows, 48, FUNCTIONS, 420)


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_the_live_view_shows_exactly_the_finished_rows(count):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(_live_script, args=(count,), default_timeout=30)
    at.run()

    assert not at.exception
    assert len(at.dataframe) == (1 if count else 0)
    if count:
        assert len(at.dataframe[0].value) == count
    kpi = next(m.value for m in at.markdown if "tt-kpis" in m.value)
    assert f"완료 {count} / 48" in visible_text(kpi)


# ── 테스트 세트 v2 · 범위 밖 · 실행 기록 ─────────────────────────────
def _oos_suite():
    groups = [{"id": name, "label": f"묶음{name}"} for name in (*suite_module.GROUP_IDS, suite_module.OUT_OF_SCOPE)]
    return {
        "version": 2,
        "groups": groups,
        "cases": [
            _case(1, "철도 공약 모아줘", "recipe_010", {"argument": "철도"}),
            {"id": 2, "group": suite_module.OUT_OF_SCOPE, "utterance": "내일 날씨 어때", "enabled": True,
             "expected": {"category": "unsupported", "outcomes": ["NO_MATCH"]}},
            {"id": 3, "group": suite_module.OUT_OF_SCOPE, "utterance": "그 역 좌표 줘", "enabled": True,
             "expected": {"category": "insufficient", "outcomes": ["CLARIFY", "MISSING_ARGUMENT"]}},
        ],
    }


def _oos_resolve(utterance):
    if utterance == "내일 날씨 어때":
        return {"reason": "없음", "status": "SELECT", "recipe_id": "recipe_001", "candidate_recipe_ids": ["recipe_001"],
                "argument": "내일", "travel_mode": None, "minutes": None, "admin_level": None}
    if utterance == "그 역 좌표 줘":
        return {"reason": "없음", "status": "CLARIFY", "recipe_id": None, "candidate_recipe_ids": ["recipe_001", "recipe_034"],
                "argument": None, "travel_mode": None, "minutes": None, "admin_level": None}
    return _resolve(utterance)


@pytest.fixture(scope="module")
def oos_result():
    measured = runner.run(_oos_suite(), resolve=_oos_resolve, context=runner.context_payload("both"))
    measured["meta"]["functions"] = dict(FUNCTIONS)
    return measured


def test_an_out_of_scope_row_compares_the_accepted_outcome_without_developer_words(oos_result):
    wrong = _row(oos_result, 2)
    text = visible_text(panel.detail_markup(wrong, FUNCTIONS))
    assert "실패 · 범위 밖 처리" in text
    assert "범위 밖 · 지원 안 함" in text and "해당 없음" in text and "실행 준비됨" in text
    assert text.count("차이") == 1

    right = visible_text(panel.detail_markup(_row(oos_result, 3), FUNCTIONS))
    assert "성공" in right and "되묻기 또는 인자 부족" in right and "차이" not in right

    for row in oos_result["cases"]:
        leaked = [w for w in BANNED if w in visible_text(panel.detail_markup(row, FUNCTIONS))]
        assert not leaked, (row["case_id"], leaked)


def test_the_overview_copies_the_run_metrics_and_shows_no_developer_words(oos_result):
    info = panel.overview(oos_result)
    board = oos_result["summary"]["metrics"]

    assert info["기능 선택"].startswith(f"{board['selection']['correct']}/{board['selection']['total']}")
    assert info["범위 밖 처리"].startswith(f"{board['oos']['correct']}/{board['oos']['total']}")
    assert info["인자 추출"].startswith(f"{board['semantic_fields']['correct']}/{board['semantic_fields']['total']}")
    assert info["GPU"] == "기록 없음"
    text = visible_text(panel.overview_markup(info))
    assert not [w for w in BANNED if w in text], text
    assert panel.overview(None) is None


def test_the_function_picker_groups_rows_by_expected_function_and_keeps_out_of_scope_apart(result, oos_result):
    rows = result["cases"]
    assert [r["case_id"] for r in panel.filter_results(rows, "전체", "", "recipe_045")] == [2, 5]
    assert panel.group_options(rows)[0] == panel.ALL_GROUPS
    assert panel.OUT_OF_SCOPE_GROUP not in panel.group_options(rows)

    mixed = oos_result["cases"]
    assert panel.group_options(mixed)[-1] == panel.OUT_OF_SCOPE_GROUP
    assert [r["case_id"] for r in panel.filter_results(mixed, "전체", "", panel.OUT_OF_SCOPE_GROUP)] == [2, 3]
    assert [r["case_id"] for r in panel.filter_results(mixed, "범위 밖 처리")] == [2]
    assert panel.first_failure(mixed) == 1
    assert [e["label"] for e in panel.recipe_rows(oos_result)] == ["범위 밖", "기능 010"]


def test_a_saved_run_is_listed_and_loaded_into_the_same_view_without_running(app, monkeypatch, tmp_path):
    """불러온 기록은 방금 잰 결과와 같은 자리 · 같은 함수로 그려지고 LLM 을 안 부른다."""
    from dev.evaluation import test_runs

    monkeypatch.setattr(test_runs, "RUNS_DIR", tmp_path)
    saved = runner.run(SUITE, resolve=_resolve, materialize=False, save_dir=tmp_path,
                       dataset={"id": "resolve_regression", "label": "FULL48 회귀 테스트"})

    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(saved["meta"]["run_id"]).run()

    assert not app.exception
    assert app.calls == [] and app.resolved == []
    assert len(app.dataframe) == 1 and len(app.dataframe[0].value) == len(SUITE["cases"])
    assert any(saved["meta"]["run_id"] in m.value for m in app.markdown)
    assert any('class="tt-ovs"' in m.value for m in app.markdown)
    assert app.session_state[panel.RESULT_KEY]["result"]["summary"] == test_runs.load_run(
        saved["meta"]["run_id"], tmp_path
    )["summary"]
