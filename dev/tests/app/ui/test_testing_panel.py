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

# 이 화면이 재지 않는 것 · 옛 이름. 어디에도 보이면 안 됨
RETIRED = ("실행 준비", "처리 결과", "채점 제외", "발화 성공", "걸린 시간", "실행 조건", "응답 시간",
           "READY", "MISSING_ARGUMENT", "°C")

FUNCTIONS = {
    "recipe_010": "지역·당선인·정당을 대면 공약을 검색해 보여준다.",
    "recipe_045": "장소 이름을 말하면 둘레 인구를 낸다.",
    "recipe_061": "출발할 장소에서 닿는 범위를 그린다.",
    "recipe_012": "지역별 인구 수와 순위를 낸다.",
    "recipe_005": "행정구역 이름으로 경계를 조회한다.",
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
    assert text.count(panel.EMPTY_NUMBER) == len(panel.RESULT_CARDS)
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
    assert set(panel.STAGE_LABELS) == set(runner.STAGES)


def test_the_filters_pick_failures_by_stage_and_search_ignores_spaces(result):
    rows = result["cases"]

    assert len(panel.filter_results(rows, "전체")) == 5
    assert [r["case_id"] for r in panel.filter_results(rows, "실패만")] == [3, 4, 5]
    assert [r["case_id"] for r in panel.filter_results(rows, "기능 선택")] == [4]
    assert [r["case_id"] for r in panel.filter_results(rows, "인자 추출")] == [3]
    found = panel.filter_results(rows, "실패만", "청주서원")
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
            {"id": 3, "group": suite_module.OUT_OF_SCOPE, "utterance": "달러 환율 알려줘", "enabled": True,
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
    measured = runner.run(_oos_suite(), resolve=_oos_resolve, context=runner.context_payload("both"))
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


def test_a_candidate_function_shows_its_menu_description_on_hover_only(result):
    """칩에는 「기능 NNN」만 보이고, 설명은 title(마우스를 올리면)에 있다. 설명의 원천은 결과 meta.functions."""
    markup = panel.detail_markup(_row(result, 4), FUNCTIONS)
    chip = re.search(r'<span class="tt-chip[^"]*" title="([^"]*)">기능 045</span>', markup)
    assert chip and chip.group(1) == FUNCTIONS["recipe_045"]
    assert FUNCTIONS["recipe_045"] not in visible_text(markup.split("후보 기능", 1)[1].split("모델 판단", 1)[0])


def test_the_function_descriptions_are_the_published_menu_sentences():
    """화면이 따로 설명표를 두지 않는다. runner.functions 가 게시 menu 의 function 문장 그대로다."""
    import yaml

    import paths

    menu = yaml.safe_load(paths.MENU_YAML_PATH.read_text(encoding="utf-8"))
    assert runner.functions() == {rid: entry["function"] for rid, entry in menu["recipes"].items()}
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
    text = visible_text(panel.summary_markup(summary))
    for label, _key, _tone in panel.RESULT_CARDS:
        assert label in text
    assert [label for label, _key, _tone in panel.RESULT_CARDS] == [
        "전체", "성공", "실패", "오류", "기능 선택 실패", "인자 추출 실패", "범위 밖 처리 실패"]
    assert text.count("먼저 걸린 것") == 3
    assert summary["scope"] == 1

    no_oos = visible_text(panel.summary_markup({**summary, "oos_runs": 0, "scope": 0}))
    assert "해당 발화 없음" in no_oos


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
    assert [e.label for e in app.expander] == ["모델 설정", "기능별 결과"]
    shown = " ".join(visible_text(m.value) for m in app.markdown if "<style>" not in m.value)
    assert not [w for w in RETIRED if w in shown], [w for w in RETIRED if w in shown]
    assert app.session_state[panel.RESULT_KEY]["result"]["summary"] == test_runs.load_run(
        saved["meta"]["run_id"], tmp_path
    )["summary"]
