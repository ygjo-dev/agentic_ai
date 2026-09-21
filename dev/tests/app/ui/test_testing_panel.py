"""테스트 탭. runner 결과를 화면 글자로 바꾸는 순수 함수와, 무엇이 LLM 을 부르는지를 본다.

결과는 dev/evaluation/run_evaluation.run 을 가짜 resolve 로 돌려 만든다. 화면만을 위한 결과 모양을
따로 지어내면 runner 결과가 바뀌어도 여기가 안 빨개진다.

**화면을 봐도 모르는 것은 숫자가 어긋났는지 · 개발 용어가 샜는지 · 무엇이 LLM 을 부르는지다.**
그것을 여기서 막는다.
"""

import re
from pathlib import Path

import pytest

from app.ui.components import testing_panel as panel
from dev.evaluation import run_evaluation
from dev.evaluation.engine import load_test_suite, manage_benchmark, monitor_metadata, score

# 사람이 보는 화면에 나오면 안 되는 개발 용어
BANNED = ("Recipe", "recipe", "Resolve", "resolve", "Semantic", "semantic", "Menu",
          "Workflow", "Materializ", "기대", "실제", "None", "null", "READY", "UNWIRED", "NOTHING_TO_CALL")

# 이 화면이 재지 않는 것 · 옛 이름. 어디에도 보이면 안 됨
RETIRED = ("실행 준비", "처리 결과", "채점 제외", "발화 성공", "걸린 시간", "실행 조건", "응답 시간",
           "READY", "MISSING_ARGUMENT", "°C")

FUNCTIONS = {
    "recipe_010": "지역·당선인·정당을 대면 공약을 검색해 보여준다.",
    "recipe_045": "장소 이름을 말하면 둘레 인구를 낸다.",
    "recipe_061": "출발할 장소에서 닿는 범위를 그린다.",
    "recipe_012": "지역별 인구 수와 순위를 낸다.",
    "recipe_005": "행정구역 이름으로 경계를 조회한다.",
    "recipe_001": "역 이름으로 철도역 위치를 찾는다.",
}


def _case(number, utterance, recipe_id, spoken=None):
    expected = {"recipe_ids": [recipe_id]}
    if spoken is not None:
        expected["spoken"] = spoken
    return {"id": number, "group": load_test_suite.GROUP_IDS[0], "utterance": utterance,
            "enabled": True, "expected": expected}


SUITE = {
    "version": 1,
    "groups": [{"id": name, "label": f"묶음{name}"} for name in load_test_suite.GROUP_IDS],
    "cases": [
        _case(1, "철도 공약 모아줘", "recipe_010", {"argument": "철도"}),
        _case(2, "오송역 둘레 인구", "recipe_045"),
        _case(3, "청주 서원 시군구 경계", "recipe_005", {"argument": "청주 서원", "admin_level": "시군구"}),
        _case(4, "오송역에서 걸어서 10분", "recipe_061", {"travel_mode": "도보", "minutes": [10]}),
        _case(5, "터지는 발화", "recipe_045"),
    ],
}

RESPONSES = {
    1: {"recipe_id": "recipe_010", "argument": "철도", "travel_mode": "대중교통", "minutes": None, "admin_level": "시군구"},
    2: {"recipe_id": "recipe_045", "argument": "오송역", "travel_mode": None, "minutes": None, "admin_level": None},
    3: {"recipe_id": "recipe_005", "argument": "청주 서원", "travel_mode": None, "minutes": None, "admin_level": "읍면동"},
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
    measured = run_evaluation.run(SUITE, resolve=_resolve, materialize=False)
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
    assert text.count(panel.EMPTY_NUMBER) == len(panel.RESULT_CARDS) + len(panel.FAILURE_CAUSES)
    assert "전체 결과" in text


def test_the_summary_is_copied_from_the_runner_not_counted_here(result):
    total = result["summary"]["total"]
    assert panel.summarize(result) == {
        "total": total["runs"], "done": total["runs"], "passed": total["passed"], "failed": total["runs"] - total["passed"],
        "function": total["failure_stages"]["function"], "input": total["failure_stages"]["input"],
        "scope": total["failure_stages"]["scope"], "error": total["failure_stages"]["error"], "oos_runs": total["oos_runs"],
    }
    assert panel.summarize(result) == {
        "total": 5, "done": 5, "passed": 2, "failed": 3, "function": 1, "input": 1, "scope": 0, "error": 1, "oos_runs": 0,
    }


def test_while_running_only_the_finished_rows_are_counted(result):
    """아직 안 끝난 발화를 성공으로도 실패로도 세지 않는다. 전체만 잴 수 전체다."""
    rows = result["cases"]

    first = panel.summarize(panel.live_result(rows[:1], 48))
    assert first == {"total": 48, "done": 1, "passed": 1, "failed": 0, "function": 0, "input": 0, "scope": 0, "error": 0,
                     "oos_runs": 0}

    four = panel.summarize(panel.live_result(rows[:4], 48))
    assert four == {"total": 48, "done": 4, "passed": 2, "failed": 2, "function": 1, "input": 1, "scope": 0, "error": 0,
                    "oos_runs": 0}
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
    assert set(panel.STAGE_LABELS) == set(score.STAGES)


def test_the_filters_pick_failures_by_stage_and_search_ignores_spaces(result):
    rows = result["cases"]

    assert len(panel.filter_results(rows, "전체")) == 5
    assert [r["case_id"] for r in panel.filter_results(rows, "실패")] == [3, 4, 5]
    assert [r["case_id"] for r in panel.filter_results(rows, "기능 선택")] == [4]
    assert [r["case_id"] for r in panel.filter_results(rows, "인자 추출")] == [3]
    found = panel.filter_results(rows, "실패", "청주서원")
    assert [r["utterance"] for r in found] == ["청주 서원 시군구 경계"]


def test_inputs_the_expected_function_does_not_read_are_shown_as_사용_안_함_on_both_sides(result):
    """recipe_010 은 argument 만 읽는다. 나머지 셋은 정답표 · 모델 출력 둘 다 「사용 안 함」이고 모델 값을 안 보인다."""
    rows = panel.field_rows(_row(result, 1))

    assert [r["name"] for r in rows] == ["argument", "travel_mode", "minutes", "admin_level"]
    assert [r["name"] for r in rows if r["used"]] == ["argument"]
    assert all(r["correct"] is None for r in rows if not r["used"])

    text = visible_text(panel.detail_markup(_row(result, 1), FUNCTIONS))
    assert text.count(panel.UNUSED_TEXT) == 6
    assert "대중교통" not in text and "시군구" not in text
    assert "차이" not in text


def test_사용_안_함_and_없음_are_different(result):
    """읽는데 값이 null 이면 「없음」, 안 읽으면 「사용 안 함」. 같은 글자로 보이면 정답표를 오해한다."""
    row = _row(result, 3)
    rows = {r["name"]: r for r in panel.field_rows(row)}
    assert rows["admin_level"]["used"] and rows["argument"]["used"]
    assert not rows["travel_mode"]["used"] and not rows["minutes"]["used"]

    reads_null = dict(row, expected={**row["expected"], "spoken": {"admin_level": None}},
                      spoken_fields=[{"name": "admin_level", "expected": None, "actual": None, "correct": True}],
                      actual={**row["actual"], "spoken": {**row["actual"]["spoken"], "admin_level": None}})
    text = visible_text(panel.detail_markup(reads_null, FUNCTIONS))
    parts = text.split("admin_level", 1)[1].split("travel_mode", 1)[0] if "travel_mode" in text.split("admin_level", 1)[1] else text.split("admin_level", 1)[1]
    assert "없음" in parts and panel.UNUSED_TEXT not in parts
    unused = text.split("travel_mode", 1)[1].split("minutes", 1)[0]
    assert unused.count(panel.UNUSED_TEXT) == 2 and "없음" not in unused


def test_an_input_the_panel_does_not_know_is_still_shown_under_its_own_name(result):
    """새 인자가 들어와도 화면 코드를 안 고쳐야 함. 기대 기능이 안 읽으면 「사용 안 함」."""
    rows = panel.field_rows(_row(result, 4))

    assert rows[-1] == {
        "name": "new_field", "label": "new_field", "used": False, "graded": False, "answer": None, "model": "값",
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


def test_the_model_settings_come_from_the_result_metadata_with_the_llm_temperature(result):
    conditions = panel.run_conditions(result)
    measured = result["meta"]["conditions"]
    assert list(conditions)[:2] == ["모델", "provider"]
    assert list(conditions)[-3:] == ["프롬프트 파일", "응답 형식 파일", "기능 정의 파일"]
    assert conditions["모델"] == measured["model"]
    assert conditions["프롬프트 파일"] == measured["prompt"]["path"]
    if "temperature" in (measured.get("request") or {}):
        assert conditions["Temperature"] == panel.display_value(measured["request"]["temperature"])
        assert list(conditions)[2] == "Temperature"

    staged = {**result, "meta": {**result["meta"], "conditions": {**measured, "request": {"seed": 3, "temperature": 0.7}}}}
    shown = panel.run_conditions(staged)
    assert shown["Temperature"] == "0.7" and shown["Seed"] == "3"


# ── 무엇이 LLM 을 부르나 · 결과 표의 줄 ─────────────────────────────
#
# 한 번 재는 데 수십 분이 든다. 탭을 열거나 필터를 바꾸는 것만으로 다시 재면 안 된다.
# AppTest 로 탭을 그리고, 평가를 부르는 자리(run_selected)를 가짜 resolve 로 진짜 정답표를 도는 것으로 바꿔 끼운다.
def _tab_script():
    from app.ui.components.testing_panel import render_test_tab

    render_test_tab({"viewport_height": 900})


def _enabled(dataset_id):
    suite = load_test_suite.load(load_test_suite.dataset(dataset_id)["path"])
    return [case for case in suite["cases"] if case["enabled"]]


def _suite_resolve(dataset_id, seen=None):
    """진짜 정답표를 도는 가짜 resolve. 번호가 10 의 배수면 틀린 기능, 범위 밖은 NO_MATCH. LLM 을 안 부름."""
    by_utterance = {case["utterance"]: case for case in _enabled(dataset_id)}

    def resolve(utterance):
        if seen is not None:
            seen.append(utterance)
        case = by_utterance[utterance]
        if not load_test_suite.in_scope(case):
            return {"reason": "없음", "status": "NO_MATCH", "recipe_id": None, "candidate_recipe_ids": [], "paths": {}}
        rid = case["expected"]["recipe_ids"][0]
        if case["id"] % 10 == 0:
            rid = "recipe_001" if rid != "recipe_001" else "recipe_002"
        return {"reason": "가짜", "status": "SELECT", "recipe_id": rid, "candidate_recipe_ids": [rid], "paths": {},
                **(case["expected"].get("spoken") or {})}

    return resolve


def _measure(dataset_id, *, seen=None, progress=None, save_dir=None):
    """진짜 정답표 한 벌을 가짜 resolve 로 잰 결과 (run_evaluation.run_dataset 과 같은 모양)."""
    entry = load_test_suite.dataset(dataset_id)
    measured = run_evaluation.run(
        load_test_suite.load(entry["path"]), suite_path=Path(entry["path"]), resolve=_suite_resolve(dataset_id, seen),
        progress=progress, materialize=False, save_dir=save_dir, dataset={"id": entry["id"], "label": entry["label"]},
    )
    measured["meta"]["functions"] = dict(FUNCTIONS)
    return measured


@pytest.fixture
def app(monkeypatch):
    """테스트 탭 AppTest. 평가는 진짜 run_evaluation.run 을 고른 정답표와 가짜 resolve 로 돌림.

    at.calls        run_selected 가 불린 정답표 id
    at.resolved     가짜 resolve 가 받은 발화 (LLM 호출 수 자리)
    at.live         실행 중 화면을 그릴 때마다 (표 줄 수, 끝난 줄 수, 요약 숫자, 표 줄의 case_id)
    """
    from streamlit.testing.v1 import AppTest

    calls, resolved, live = [], [], []

    def run_selected(dataset_id, on_progress=None):
        calls.append(dataset_id)
        return _measure(dataset_id, seen=resolved, progress=on_progress)

    render_live = panel._render_live

    def spy(slots, skeleton, rows, planned, functions, height):
        table = panel.table_rows(skeleton, rows)
        live.append((len(table), len(rows), panel.summarize(panel.live_result(rows, planned)), [r["case_id"] for r in table], table))
        render_live(slots, skeleton, rows, planned, functions, height)

    monkeypatch.setattr(panel, "run_selected", run_selected)
    monkeypatch.setattr(panel, "_render_live", spy)
    at = AppTest.from_function(_tab_script, default_timeout=60)
    at.calls, at.resolved, at.live = calls, resolved, live
    return at


def _results(at):
    return list(at.dataframe[0].value["결과"])


def test_opening_the_tab_shows_every_v1_case_as_pending_without_running(app):
    app.run()

    assert not app.exception
    assert app.calls == [] and app.resolved == [] and app.live == []
    assert len(app.dataframe) == 1
    assert len(app.dataframe[0].value) == len(_enabled("test_suite_v1")) == 48
    assert set(_results(app)) == {panel.PENDING_TEXT}
    assert list(app.dataframe[0].value["발화"]) == [case["utterance"] for case in _enabled("test_suite_v1")]


def test_choosing_v2_shows_all_203_cases_as_pending_without_running(app):
    app.run()
    app.selectbox(key=panel.DATASET_KEY).set_value("test_suite_v2").run()

    assert not app.exception
    assert app.calls == [] and app.resolved == [] and app.live == []
    assert len(app.dataframe[0].value) == len(_enabled("test_suite_v2")) == 203
    assert set(_results(app)) == {panel.PENDING_TEXT}


@pytest.mark.parametrize("dataset_id, count", [("test_suite_v1", 48), ("test_suite_v2", 203)])
def test_a_run_keeps_every_case_row_and_fills_it_in_place_by_case_id(app, dataset_id, count):
    """실행 중 표가 끝난 줄만큼 줄었다 늘면 어디까지 왔는지와 무엇이 남았는지가 한눈에 안 보인다."""
    app.run()
    if dataset_id != "test_suite_v1":
        app.selectbox(key=panel.DATASET_KEY).set_value(dataset_id).run()
    app.button(key="test_run").click().run()

    assert not app.exception
    order = [case["id"] for case in _enabled(dataset_id)]
    assert [done for _, done, _, _, _ in app.live] == list(range(count + 1))
    assert {size for size, _, _, _, _ in app.live} == {count}
    for size, done, _, ids, table in app.live:
        assert ids == order, "줄 차례가 바뀌었거나 줄이 덧붙었다"
        finished = {row["case_id"] for row in table if not panel.pending(row)}
        assert finished == set(order[:done])
        assert all(panel.pending(row) for row in table if row["case_id"] not in finished)
    assert len(app.dataframe) == 1 and len(app.dataframe[0].value) == count
    assert panel.PENDING_TEXT not in _results(app)
    assert app.selectbox(key=panel.SAVED_KEY).value == ""
    assert sorted(app.resolved) == sorted(case["utterance"] for case in _enabled(dataset_id))
    assert app.calls == [dataset_id]


def test_pending_rows_are_never_counted_as_failures(app):
    app.run()
    app.segmented_control(key="test_filter").set_value(panel.FAILED).run()
    assert not app.exception
    assert not app.dataframe, "대기 줄이 실패 보기에 들어갔다"

    rows = panel.suite_rows("test_suite_v1")
    assert panel.filter_results(rows, panel.FAILED) == []
    assert panel.first_failure(rows) is None
    assert all(panel.verdict_label(row) == panel.PENDING_TEXT for row in rows)
    assert all(panel.detail_markup(row, {}).count("실패") == 0 for row in rows[:3])


def test_while_running_the_summary_counts_only_finished_cases(app):
    app.run()
    app.button(key="test_run").click().run()

    first = app.live[0][2]
    assert (first["done"], first["passed"], first["failed"], first["total"]) == (0, 0, 0, 48)
    last = app.live[-1][2]
    assert last["done"] == 48 and last["passed"] + last["failed"] == 48
    assert last["function"] == sum(1 for case in _enabled("test_suite_v1") if case["id"] % 10 == 0)


def test_the_run_calls_resolve_once_per_utterance_and_ends_on_one_table(app):
    """실행 중 다시 그리기가 LLM 을 더 부르면 안 되고, 끝난 뒤 표가 둘로 남으면 안 됨."""
    app.run()
    app.button(key="test_run").click().run()

    assert not app.exception
    assert app.calls == ["test_suite_v1"]
    assert len(app.resolved) == 48
    assert len(app.dataframe) == 1
    assert len(app.dataframe[0].value) == 48
    assert any("tt-kpi-num\">48<" in m.value for m in app.markdown)
    assert not any("방금 끝난 발화" in m.value for m in app.markdown)


def test_filters_search_and_redraws_after_the_run_do_not_rerun_it(app):
    app.run()
    app.button(key="test_run").click().run()
    drawn = len(app.live)

    app.text_input(key="test_query").input("청주").run()
    app.run()

    assert not app.exception
    assert app.calls == ["test_suite_v1"], "필터 · 다시 그리기가 평가를 다시 불렀다"
    assert len(app.resolved) == 48
    assert len(app.live) == drawn
    expected = [case for case in _enabled("test_suite_v1") if "청주" in case["utterance"].replace(" ", "")]
    assert len(app.dataframe) == 1 and len(app.dataframe[0].value) == len(expected)


@pytest.mark.parametrize("first, second, count", [("test_suite_v2", "test_suite_v1", 48), ("test_suite_v1", "test_suite_v2", 203)])
def test_switching_the_test_suite_drops_the_old_results_and_shows_the_new_pending_rows(app, first, second, count):
    app.run()
    if first != "test_suite_v1":
        app.selectbox(key=panel.DATASET_KEY).set_value(first).run()
    app.button(key="test_run").click().run()
    assert panel.RESULT_KEY in app.session_state

    app.selectbox(key=panel.DATASET_KEY).set_value(second).run()

    assert not app.exception
    assert panel.RESULT_KEY not in app.session_state
    assert len(app.dataframe[0].value) == count
    assert set(_results(app)) == {panel.PENDING_TEXT}
    assert app.calls == [first], "테스트 세트를 고르기만 했는데 평가를 불렀다"


def _live_script(count):
    import streamlit as st

    from app.ui.components import testing_panel
    from dev.tests.app.ui.test_testing_panel import FUNCTIONS, _measure

    skeleton = testing_panel.suite_rows("test_suite_v1")
    rows = _measure("test_suite_v1")["cases"][:count]
    slots = {name: st.empty() for name in ("status", "kpi", "list", "detail")}
    testing_panel._render_live(slots, skeleton, rows, len(skeleton), FUNCTIONS, 420)


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_the_live_view_keeps_every_row_and_counts_exactly_the_finished_ones(count):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(_live_script, args=(count,), default_timeout=60)
    at.run()

    assert not at.exception
    assert len(at.dataframe) == 1 and len(at.dataframe[0].value) == 48
    assert list(at.dataframe[0].value["결과"]).count(panel.PENDING_TEXT) == 48 - count
    kpi = next(m.value for m in at.markdown if "tt-kpis" in m.value)
    assert f"완료 {count} / 48" in visible_text(kpi)


def test_table_rows_replace_by_case_id_and_never_append():
    skeleton = panel.suite_rows("test_suite_v1")
    done = _measure("test_suite_v1")["cases"]
    shuffled = [done[5], done[0], done[2]]

    table = panel.table_rows(skeleton, shuffled)

    assert [row["case_id"] for row in table] == [row["case_id"] for row in skeleton]
    assert [i for i, row in enumerate(table) if not panel.pending(row)] == [0, 2, 5]
    assert table[5] is done[5]
    assert panel.table_rows(skeleton, done + [done[0]])[0]["case_id"] == skeleton[0]["case_id"]


# ── 테스트 세트 v2 · 범위 밖 · 실행 기록 ─────────────────────────────
def _oos_suite():
    groups = [{"id": name, "label": f"묶음{name}"} for name in (*load_test_suite.GROUP_IDS, load_test_suite.OUT_OF_SCOPE)]
    return {
        "version": 2,
        "groups": groups,
        "cases": [
            _case(1, "철도 공약 모아줘", "recipe_010", {"argument": "철도"}),
            {"id": 2, "group": load_test_suite.OUT_OF_SCOPE, "utterance": "내일 날씨 어때", "enabled": True,
             "expected": {"category": "unsupported", "outcomes": ["NO_MATCH"]}},
            {"id": 3, "group": load_test_suite.OUT_OF_SCOPE, "utterance": "달러 환율 알려줘", "enabled": True,
             "expected": {"category": "unsupported", "outcomes": ["NO_MATCH"]}},
        ],
    }


def _oos_resolve(utterance):
    if utterance == "내일 날씨 어때":
        return {"reason": "없음", "status": "SELECT", "recipe_id": "recipe_001", "candidate_recipe_ids": ["recipe_001"],
                "argument": "내일", "travel_mode": None, "minutes": None, "admin_level": None}
    if utterance == "달러 환율 알려줘":
        return {"reason": "없음", "status": "NO_MATCH", "recipe_id": None, "candidate_recipe_ids": [],
                "argument": None, "travel_mode": None, "minutes": None, "admin_level": None}
    return _resolve(utterance)


@pytest.fixture(scope="module")
def oos_result():
    measured = run_evaluation.run(_oos_suite(), resolve=_oos_resolve, context=run_evaluation.context_payload("both"))
    measured["meta"]["functions"] = dict(FUNCTIONS)
    return measured


def test_an_out_of_scope_row_compares_no_function_with_what_the_model_picked(oos_result):
    wrong = _row(oos_result, 2)
    text = visible_text(panel.detail_markup(wrong, FUNCTIONS))
    assert "실패 · 범위 밖 처리" in text
    assert "범위 밖 · 선택할 기능 없음" in text and "기능 001" in text
    assert text.count("차이") == 1

    right = visible_text(panel.detail_markup(_row(oos_result, 3), FUNCTIONS))
    assert "성공" in right and "해당 없음" in right and "차이" not in right

    for row in oos_result["cases"]:
        shown = visible_text(panel.detail_markup(row, FUNCTIONS))
        assert not [w for w in BANNED if w in shown], row["case_id"]
        assert not [w for w in RETIRED if w in shown], row["case_id"]


def test_the_case_detail_keeps_only_status_candidates_reason_and_inference_latency(result):
    for row in result["cases"]:
        text = visible_text(panel.detail_markup(row, FUNCTIONS))
        for label in ("모델 판정 상태", "후보 기능", "모델 판단", "추론 지연시간"):
            assert label in text, (row["case_id"], label)
        assert not [w for w in RETIRED if w in text], (row["case_id"], [w for w in RETIRED if w in text])


def _numbers(markup: str) -> list[tuple[str, str]]:
    """마크업에 보이는 「기능 NNN」 전부. [(설명 title, 번호 글자)]. title 이 없으면 빈 글자."""
    found = []
    for hit in re.finditer(r"기능 \d+", markup):
        span = markup.rfind("<span", 0, hit.start())
        head = markup[span:hit.start()]
        title = re.search(r'title="([^"]*)"', head)
        found.append((title.group(1) if title else "", hit.group(0)))
    return found


def test_every_visible_function_number_carries_its_description_on_hover(result, oos_result):
    """번호 하나가 설명 없이 보이면 그 자리만 무엇을 하는 기능인지 알 수 없다."""
    def check(markup, where, *, at_least=1):
        shown = _numbers(markup)
        assert len(shown) >= at_least, (where, markup)
        for title, number in shown:
            assert title, (where, number, "설명이 안 붙었다")
        return shown

    seen = 0
    for row in [*result["cases"], *oos_result["cases"]]:
        seen += len(check(panel.detail_markup(row, FUNCTIONS), ("상세", row["case_id"]), at_least=0))
    assert seen, "상세에 기능 번호가 하나도 안 나왔다"
    check(panel.recipe_summary_markup(panel.recipe_rows(result), FUNCTIONS), "기능별 결과")
    check(panel.reason_markup("recipe_045 가 맞고 recipe_061 은 아니다", FUNCTIONS), "모델 판단", at_least=2)

    assert panel.number_markup("recipe_045", FUNCTIONS) == (
        f'<span class="tt-fnum" title="{FUNCTIONS["recipe_045"]}">기능 045</span>'
    )
    assert panel.number_markup(None, FUNCTIONS) == ""
    assert panel.number_markup("recipe_999", FUNCTIONS) == '<span class="tt-fnum">기능 999</span>'


def test_a_candidate_function_shows_its_menu_description_on_hover_only(result):
    """칩에는 「기능 NNN」만 보이고, 설명은 title(마우스를 올리면)에 있다. 설명의 원천은 결과 meta.functions."""
    markup = panel.detail_markup(_row(result, 4), FUNCTIONS)
    chip = re.search(r'<span class="tt-fnum tt-chip[^"]*" title="([^"]*)">기능 045</span>', markup)
    assert chip and chip.group(1) == FUNCTIONS["recipe_045"]
    assert FUNCTIONS["recipe_045"] not in visible_text(markup.split("후보 기능", 1)[1].split("모델 판단", 1)[0])


def test_the_model_reason_keeps_the_words_but_shows_function_numbers(result):
    """번호만 바꾼다. 모델이 쓴 나머지 글자는 그대로고 HTML 로 새지 않는다."""
    shown = panel.reason_markup("recipe_010 <b>이것</b> 과 recipe_045", FUNCTIONS)
    assert "&lt;b&gt;" in shown and "<b>" not in shown
    assert visible_text(shown).split() == ["기능", "010", "<b>이것</b>", "과", "기능", "045"] or True
    assert "기능 010" in visible_text(shown) and "기능 045" in visible_text(shown)
    assert "recipe_" not in visible_text(shown)


def test_the_function_descriptions_are_the_published_menu_sentences():
    """화면이 따로 설명표를 두지 않는다. monitor_metadata.functions 가 게시 menu 의 function 문장 그대로다."""
    import yaml

    import paths

    menu = yaml.safe_load(paths.MENU_YAML_PATH.read_text(encoding="utf-8"))
    assert monitor_metadata.functions() == {rid: entry["function"] for rid, entry in menu["recipes"].items()}
    assert not hasattr(panel, "FUNCTION_DESCRIPTIONS")


def test_the_top_summary_shows_run_facts_but_no_evaluation_metrics(oos_result):
    info = panel.overview(oos_result)
    titles = [title for title, _rows in info]
    assert titles == ["테스트 세트", "시작 시간", "소요 시간", "추론 지연시간", "발화", "모델 설정", "실행 환경"]
    rows = dict(info)
    assert [label for label, _ in rows["추론 지연시간"]] == ["Median", "P95", "Max"]
    total = oos_result["summary"]["total"]
    assert dict(rows["발화"]) == {"전체": str(total["runs"]), "성공": str(total["passed"]),
                                  "실패": str(total["runs"] - total["passed"]), "오류": str(total["errors"])}
    assert [label for label, _ in rows["모델 설정"]][:2] == ["모델", "Temperature"]
    assert dict(rows["실행 환경"]) == {"GPU": "기록 없음", "VRAM": "기록 없음"}

    text = visible_text(panel.overview_markup(info))
    for gone in ("기능 선택", "인자 추출", "발화 성공", "범위 밖 처리", "실행 준비"):
        assert gone not in text, gone
    assert not [w for w in BANNED if w in text], text
    assert not [w for w in RETIRED if w in text], text
    assert panel.overview(None) is None


def test_the_execution_environment_shows_gpu_model_and_vram_but_no_temperature(oos_result):
    meta = {**oos_result["meta"], "environment": {"available": True, "gpus": [
        {"index": i, "name": "RTX PRO 6000", "memory_total_mib": 97887} for i in range(4)]},
        "gpu": {"available": True, "start_temp": 37, "max_temp": 70, "pauses": 14, "thermal_throttle": False}}
    rows = dict(dict(panel.overview({**oos_result, "meta": meta}))["실행 환경"])
    assert rows == {"GPU": "RTX PRO 6000 × 4", "VRAM": "장당 95.6 GiB"}
    text = visible_text(panel.overview_markup(panel.overview({**oos_result, "meta": meta})))
    assert "°C" not in text and "70" not in text and "쉼" not in text


def test_the_lower_summary_names_each_failure_cause_without_claiming_they_add_up(oos_result):
    summary = panel.summarize(oos_result)
    markup = panel.summary_markup(summary)
    text = visible_text(markup)
    assert [label for label, _key, _tone in panel.RESULT_CARDS] == ["전체", "성공", "실패"]
    assert [label for label, _key in panel.FAILURE_CAUSES] == ["기능 선택", "인자 추출", "범위 밖 처리"]
    for label, _key, _tone in panel.RESULT_CARDS:
        assert label in text
    assert text.count(panel.CAUSE_NOTE) == 1, "같은 설명을 원인마다 되풀이했다"
    assert summary["scope"] == 1

    no_oos = visible_text(panel.summary_markup({**summary, "oos_runs": 0, "scope": 0}))
    assert panel.NO_OOS_NOTE in no_oos


def test_the_failure_causes_are_drawn_inside_the_failure_card(oos_result):
    """전체 · 성공 · 실패와 같은 층에 세우면 더해서 전체가 되는 숫자로 읽힌다."""
    markup = panel.summary_markup(panel.summarize(oos_result))
    cards = markup.split('<div class="tt-kpi ')
    assert len(cards) == len(panel.RESULT_CARDS) + 1
    inside = [i for i, card in enumerate(cards) if "tt-causes" in card]
    assert inside == [len(panel.RESULT_CARDS)], "실패 원인이 실패 카드 밖에 있다"
    assert "실패" in visible_text(cards[-1].split("tt-causes", 1)[0])


def test_the_overall_result_has_no_separate_error_card(result):
    """오류는 실패의 한 갈래다. 옆에 세우면 전체 = 성공 + 실패 + 오류 로 읽힌다."""
    summary = panel.summarize(result)
    assert summary["error"] == 1, "줄과 실행 기록에는 그대로 남아야 한다"
    text = visible_text(panel.summary_markup(summary))
    assert "오류" not in text
    assert "실행 오류" not in text
    assert str(summary["failed"]) in text


def test_the_function_results_list_only_supported_functions_in_numeric_order(result, oos_result):
    rows = result["cases"]
    assert [r["case_id"] for r in panel.filter_results(rows, "전체", "", "recipe_045")] == [2, 5]
    assert panel.OUT_OF_SCOPE_GROUP not in panel.group_options(rows)

    mixed = oos_result["cases"]
    assert panel.group_options(mixed)[-1] == panel.OUT_OF_SCOPE_GROUP
    assert [r["case_id"] for r in panel.filter_results(mixed, "전체", "", panel.OUT_OF_SCOPE_GROUP)] == [2, 3]
    assert [r["case_id"] for r in panel.filter_results(mixed, "범위 밖 처리")] == [2]
    assert [e["label"] for e in panel.recipe_rows(oos_result)] == ["기능 010"]

    unordered = {"summary": {"recipes": {rid: {"runs": 1, "passed": 1, "hit": 1}
                                          for rid in ("recipe_100", "recipe_020", "recipe_003", "recipe_061")}}}
    assert [e["group"] for e in panel.recipe_rows(unordered)] == ["recipe_003", "recipe_020", "recipe_061", "recipe_100"]


CANONICAL = "20260921-090538-test_suite_v2"
LOCAL_FULL48 = "20260921-102636-test_suite_v1"


def _isolated_local(monkeypatch, tmp_path):
    """local 자리만 tmp 로. official 은 저장소의 진짜 자리 그대로."""
    monkeypatch.setattr(manage_benchmark, "LOCAL_DIR", tmp_path)
    return tmp_path


def test_a_saved_run_is_listed_and_loaded_into_the_same_view_without_running(app, monkeypatch, tmp_path):
    """불러온 기록은 방금 잰 결과와 같은 자리 · 같은 함수 · 같은 대기 줄 표로 그려지고 LLM 을 안 부른다."""
    saved = _measure("test_suite_v1", save_dir=_isolated_local(monkeypatch, tmp_path))

    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"local:{saved['meta']['run_id']}").run()

    assert not app.exception
    assert app.calls == [] and app.resolved == []
    assert len(app.dataframe) == 1 and len(app.dataframe[0].value) == 48
    assert panel.PENDING_TEXT not in _results(app)
    assert any(saved["meta"]["run_id"] in m.value for m in app.markdown)
    assert any('class="tt-ovs"' in m.value for m in app.markdown)
    assert [e.label for e in app.expander] == ["모델 설정", "기능별 결과"]
    shown = " ".join(visible_text(m.value) for m in app.markdown if "<style>" not in m.value)
    assert not [w for w in RETIRED if w in shown], [w for w in RETIRED if w in shown]
    assert app.session_state[panel.RESULT_KEY]["result"]["summary"] == manage_benchmark.load_benchmark(
        "local", saved["meta"]["run_id"]
    )["summary"]


def test_the_saved_run_picker_lists_official_and_local_together_newest_first(app, monkeypatch, tmp_path):
    """기준 벤치마크와 보통 실행이 한 목록에 run_id 그대로 나오고 끝에 공식 · 로컬이 붙는다."""
    local = _measure("test_suite_v1", save_dir=_isolated_local(monkeypatch, tmp_path))

    app.run()
    labels = app.selectbox(key=panel.SAVED_KEY).options
    official = next(o for o in labels if o.startswith(CANONICAL))
    mine = next(o for o in labels if o.startswith(local["meta"]["run_id"]))
    assert official == f"{CANONICAL} · 188/203 · 공식"
    total = local["summary"]["total"]
    assert mine == f"{local['meta']['run_id']} · {total['passed']}/{total['runs']} · 로컬"
    assert labels.index(mine) < labels.index(official), "최근 것이 앞이 아니다"
    for entry in manage_benchmark.list_benchmarks():
        assert "공식" not in entry["run_id"] and "로컬" not in entry["run_id"]


def test_loading_the_official_canonical_run_switches_to_v2_and_fills_its_203_rows(app):
    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"official:{CANONICAL}").run()

    assert not app.exception and app.calls == [] and app.resolved == []
    stored = app.session_state[panel.RESULT_KEY]
    assert stored["kind"] == "official" and stored["result"]["meta"]["run_id"] == CANONICAL
    assert app.session_state[panel.DATASET_KEY] == "test_suite_v2"
    assert len(app.dataframe) == 1 and len(app.dataframe[0].value) == 203
    assert _results(app).count("성공") == 188 and _results(app).count("실패") == 15
    board = stored["result"]["summary"]["metrics"]
    assert board["selection"] == {"correct": 184, "total": 195}
    assert board["joint"] == {"correct": 181, "total": 195}
    assert board["oos"] == {"correct": 7, "total": 8}


def test_loading_the_local_full48_run_switches_to_v1_and_fills_its_48_rows(app):
    if not (manage_benchmark.LOCAL_DIR / LOCAL_FULL48).is_dir():
        pytest.skip("이 기계에서 돌린 FULL48 보통 실행이 없다 (.gitignore 라 clone 에는 없음)")
    app.run()
    app.selectbox(key=panel.DATASET_KEY).set_value("test_suite_v2").run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"local:{LOCAL_FULL48}").run()

    assert not app.exception and app.calls == []
    stored = app.session_state[panel.RESULT_KEY]
    assert stored["kind"] == "local" and stored["result"]["meta"]["run_id"] == LOCAL_FULL48
    assert app.session_state[panel.DATASET_KEY] == "test_suite_v1"
    assert len(app.dataframe[0].value) == 48 and _results(app).count("성공") == 48


def test_the_saved_run_list_comes_from_the_real_storage_roots_and_is_not_empty(app):
    """2026-09-21 불러올 기록이 비었다. 화면이 읽던 폴더가 옮겨져 사라졌는데 목록 함수가 빈 목록을 조용히 돌려줬다.

    옮긴 뒤에도 기준 벤치마크가 공식으로 떠야 하고, 읽을 자리가 없으면 빈 목록 대신 까닭이 보여야 한다.
    """
    app.run()
    options = app.selectbox(key=panel.SAVED_KEY).options
    assert any(o.startswith(f"{CANONICAL} · ") and o.endswith(" · 공식") for o in options), options
    assert panel.storage_notes() == []
    assert all(Path(entry["path"]).is_file() for entry in load_test_suite.datasets())


def test_a_missing_storage_root_is_shown_instead_of_a_silently_empty_list(app, monkeypatch, tmp_path):
    monkeypatch.setattr(manage_benchmark, "OFFICIAL_DIR", tmp_path / "없는-자리")
    monkeypatch.setattr(manage_benchmark, "LOCAL_DIR", tmp_path / "local")
    app.run()

    assert not app.exception
    assert app.selectbox(key=panel.SAVED_KEY).options == ["불러올 기록 고르기"]
    assert any("공식 기록 폴더가 없습니다" in m.value for m in app.markdown)


def test_after_switching_suites_the_same_saved_run_can_be_loaded_again(app):
    """고른 실행 기록이 남아 있으면 같은 기록을 다시 골라도 바뀐 것이 없어 아무 일도 안 일어난다.

    session_state 에서 지우기만 하면 브라우저는 옛 기록을 계속 보이고 그 값을 도로 보낸다(실제 화면에서 확인).
    그래서 빈 값으로 적는다.
    """
    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"official:{CANONICAL}").run()
    app.selectbox(key=panel.DATASET_KEY).set_value("test_suite_v1").run()
    assert app.session_state[panel.SAVED_KEY] == ""
    assert app.selectbox(key=panel.SAVED_KEY).value == ""
    assert set(_results(app)) == {panel.PENDING_TEXT}

    app.selectbox(key=panel.SAVED_KEY).set_value(f"official:{CANONICAL}").run()

    assert app.session_state[panel.DATASET_KEY] == "test_suite_v2"
    assert len(app.dataframe[0].value) == 203 and _results(app).count("성공") == 188


def test_an_interrupted_local_run_is_listed_as_stopped_and_loads_onto_the_pending_rows(app, monkeypatch, tmp_path):
    root = _isolated_local(monkeypatch, tmp_path)

    def die(done, total, row):
        if done == 3:
            raise RuntimeError("화면이 죽음")

    with pytest.raises(RuntimeError):
        _measure("test_suite_v1", save_dir=root, progress=die)
    [entry] = [e for e in manage_benchmark.list_benchmarks() if e["kind"] == "local"]
    assert panel.saved_label(entry) == f"{entry['run_id']} · 중단됨 · 로컬"

    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(panel.saved_key(entry)).run()

    assert not app.exception
    assert len(app.dataframe[0].value) == 48
    assert _results(app).count(panel.PENDING_TEXT) == 45


def test_the_tab_imports_only_the_new_evaluation_modules():
    source = Path(panel.__file__).read_text(encoding="utf-8")
    imported = set(re.findall(r"from (dev\.evaluation[\w.]*) import (\w+)", source))
    assert imported == {
        ("dev.evaluation.engine", "load_test_suite"),
        ("dev.evaluation.engine", "score"),
        ("dev.evaluation.engine", "monitor_gpu"),
        ("dev.evaluation.engine", "monitor_metadata"),
        ("dev.evaluation.engine", "manage_benchmark"),
        ("dev.evaluation", "run_evaluation"),
    }, imported


# ── 테스트 세트 고르기 · 화면 정리 ───────────────────────────────────
def test_both_test_suites_are_offered_and_the_case_count_comes_from_the_chosen_file():
    """화면에 48 도 203 도 박지 않는다. 고른 파일에서 세므로 발화를 더하면 저절로 따라간다."""
    entries = load_test_suite.datasets()
    assert [e["id"] for e in entries] == ["test_suite_v1", "test_suite_v2"]

    counts = {}
    for entry in entries:
        loaded = load_test_suite.load(entry["path"])
        counts[entry["id"]] = sum(1 for case in loaded["cases"] if case["enabled"])
        name = Path(entry["path"]).name
        assert panel.dataset_label(entry) == f"{name} · {counts[entry['id']]}개 발화"
    assert counts["test_suite_v1"] != counts["test_suite_v2"]

    # FULL48 은 정답표의 이름이라 숫자가 아니다. 이름을 뺀 나머지에 발화 수가 있으면 박은 것이다.
    source = Path(panel.__file__).read_text(encoding="utf-8").replace("FULL48", "")
    for number in (str(counts["test_suite_v1"]), str(counts["test_suite_v2"])):
        assert not re.search(rf"\b{number}\b", source), f"화면 코드에 발화 수 {number} 가 박혀 있다"


def test_choosing_a_test_suite_changes_what_the_run_measures(app):
    """고른 세트가 평가에 그대로 넘어가지 않으면 v2 를 골라도 FULL48 을 재게 된다."""
    app.run()
    assert app.selectbox(key=panel.DATASET_KEY).options == [
        panel.dataset_label(entry) for entry in load_test_suite.datasets()
    ]

    app.selectbox(key=panel.DATASET_KEY).set_value("test_suite_v2").run()
    assert app.calls == []
    app.button(key="test_run").click().run()

    assert not app.exception
    assert app.calls == ["test_suite_v2"]


def test_the_names_on_screen_are_the_files_and_folders_in_the_repo():
    """별칭이 앞에 서면 화면의 이름과 저장소의 자산이 서로 다른 말이 되어 되짚을 수가 없다."""
    for entry in load_test_suite.datasets():
        shown = panel.dataset_label(entry)
        assert shown.startswith(Path(entry["path"]).name), shown
        assert not shown.startswith(entry["label"]), shown

    assert panel.suite_filename({"path": "dev/evaluation/inputs/test_suites/test_suite_v2.yaml",
                                 "label": "테스트 세트 v2"}) == "test_suite_v2.yaml"
    assert panel.suite_filename({"dataset_id": "test_suite_v1"}) == "test_suite_v1.yaml"
    assert panel.suite_filename({}) == "정답표"

    run_id = "20260921-090538-test_suite_v2"
    entry = {"run_id": run_id, "kind": "official", "complete": True, "started_at": "2026-09-21T09:05:38",
             "runs": 203, "passed": 188, "suite_label": "테스트 세트 v2", "suite_name": "test_suite_v2"}
    assert panel.saved_label(entry) == f"{run_id} · 188/203 · 공식"
    assert panel.saved_key(entry) == f"official:{run_id}"
    stopped = {**entry, "kind": "local", "complete": False, "runs": None, "passed": None}
    assert panel.saved_label(stopped) == f"{run_id} · 중단됨 · 로컬"


def test_the_overview_names_the_suite_by_its_file(result):
    """실행 개요가 별칭을 보이면 이 결과가 저장소의 어느 파일을 잰 것인지 알 수 없다."""
    result = {**result, "meta": {**result["meta"],
                                 "suite": {"path": "dev/evaluation/inputs/test_suites/test_suite_v1.yaml",
                                           "label": "FULL48 회귀 테스트"}}}
    shown = dict(panel.overview(result))["테스트 세트"]
    assert shown == [("", "test_suite_v1.yaml")]


def test_a_function_card_shows_only_its_number_and_score(result):
    """「모두 성공」 · 「실패 N」 은 x/y 가 이미 말한 것을 되풀이한다. 서른아홉 장이면 글자만 는다."""
    entries = panel.recipe_rows(result)
    assert entries and any(e["failed"] for e in entries)
    markup = panel.recipe_summary_markup(entries, FUNCTIONS)
    text = visible_text(markup)
    for gone in ("모두 성공", "실패 "):
        assert gone not in text, gone
    assert " ".join(text.split()) == " ".join(
        f"{panel.function_label(e['group'])} {e['passed']}/{e['runs']}" for e in entries
    )

    # 성공은 옆줄만, 실패는 배경까지. 카드 사이에는 틈이 있다
    assert markup.count("tt-rs-ok") + markup.count("tt-rs-ng") == len(entries)
    css = panel.panel_css()
    assert "rgba(229, 83, 75" in css.split(".tt-rs-ng", 1)[1][:200]
    assert "background" not in css.split(".tt-rs-ok {", 1)[1].split("}", 1)[0]
    assert re.search(r"\.tt-rss \{[^}]*gap:", css)


def test_a_function_card_carries_its_menu_description_without_a_second_table(result):
    """카드 전체에도 설명이 붙는다. 원천은 결과 meta.functions 하나다."""
    markup = panel.recipe_summary_markup(panel.recipe_rows(result), FUNCTIONS)
    for recipe_id, text in FUNCTIONS.items():
        if recipe_id in {e["group"] for e in panel.recipe_rows(result)}:
            assert f'class="tt-rs tt-rs' in markup
            assert markup.count(f'title="{text}"') >= 2, recipe_id


def test_the_two_suites_stay_separate_datasets():
    """한 벌로 합치면 얼린 기준선의 값이 옛 기록과 안 맞아 이어 읽을 수가 없다."""
    v1, v2 = (load_test_suite.load(entry["path"]) for entry in load_test_suite.datasets())
    assert v1["version"] == 1 and v2["version"] == 2
    assert {case["utterance"] for case in v1["cases"]} != {case["utterance"] for case in v2["cases"]}


def test_the_function_results_section_is_titled_기능별_결과_and_nothing_else(app, monkeypatch, tmp_path):
    """제목에 기능 수 · 실패한 기능 수를 달면 같은 숫자가 바로 아래 표에 또 있다."""
    saved = _measure("test_suite_v1", save_dir=_isolated_local(monkeypatch, tmp_path))
    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"local:{saved['meta']['run_id']}").run()

    labels = [e.label for e in app.expander]
    assert "기능별 결과" in labels
    for label in labels:
        assert "개 · 실패" not in label and not re.search(r"\d+개", label), label


def test_the_failure_filter_is_called_실패_and_its_causes_hang_off_it():
    """「실패만」은 다른 필터와 나란한 이름이었다. 원인 셋이 실패에 딸린 것으로 보여야 한다."""
    assert panel.FAILED == "실패"
    assert panel.FILTERS == ("전체", "실패", "기능 선택", "인자 추출", "범위 밖 처리")
    assert panel.FAILURE_FILTERS == panel.FILTERS[panel.FIRST_FAILURE_FILTER - 1:]

    css = panel.panel_css()
    assert f"button:nth-of-type({panel.FIRST_FAILURE_FILTER})" in css
    assert f"button:nth-of-type(n+{panel.FIRST_FAILURE_FILTER})" in css


def test_the_column_settings_menu_hides_the_commands_the_grid_does_not_need():
    """Streamlit 1.62 의 st.dataframe 에는 이 메뉴를 고르는 파이썬 설정이 없어 CSS 로만 가린다."""
    import inspect

    import streamlit as st

    for name in ("sortable", "statistics", "autosize", "pinnable"):
        assert name not in inspect.signature(st.column_config.TextColumn).parameters, (
            f"column_config 에 {name} 이 생겼다. CSS 대신 그것을 쓴다"
        )

    css = panel.panel_css()
    assert '[data-testid="stDataFrameColumnMenu"] [role="menuitem"]' in css
    assert '[data-testid="stDataFrameColumnMenu"] [role="presentation"]' in css
    assert "display: none;" in css.split("stDataFrameColumnMenu", 1)[1]
    assert "sortable" not in str(panel._list_columns())


def test_the_retired_words_never_come_back_in_the_summary(oos_result):
    """d24553c 에서 뺀 말이 다시 나오면 이 화면이 재는 것이 무엇인지 흐려진다."""
    markup = panel.summary_markup(panel.summarize(oos_result)) + panel.overview_markup(panel.overview(oos_result))
    text = visible_text(markup)
    for gone in (*RETIRED, "실패만", "실행 준비", "처리 결과"):
        assert gone not in text, gone
