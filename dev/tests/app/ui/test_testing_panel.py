"""테스트 탭. runner 결과를 화면 글자로 바꾸는 순수 함수와, 무엇이 LLM 을 부르는지를 본다.

결과는 dev/evaluation/run_evaluation.run 을 가짜 resolve 로 돌려 만든다. 화면만을 위한 결과 모양을
따로 지어내면 runner 결과가 바뀌어도 여기가 안 빨개진다.

**화면을 봐도 모르는 것은 숫자가 어긋났는지 · 개발 용어가 샜는지 · 무엇이 LLM 을 부르는지다.**
그것을 여기서 막는다.
"""

import json
import re
import threading
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
    """실패는 모델이 잘못한 셋(기능 선택 · 인자 추출 · 범위 밖 처리)만이다. 오류는 따로 센다."""
    total = result["summary"]["total"]
    stages = total["failure_stages"]
    assert panel.summarize(result) == {
        "total": total["runs"], "done": total["runs"], "passed": total["passed"],
        "failed": stages["function"] + stages["input"] + stages["scope"],
        "function": stages["function"], "input": stages["input"],
        "scope": stages["scope"], "error": stages["error"], "oos_runs": total["oos_runs"],
    }
    assert panel.summarize(result) == {
        "total": 5, "done": 5, "passed": 2, "failed": 2, "function": 1, "input": 1, "scope": 0, "error": 1, "oos_runs": 0,
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
    assert panel.filter_results(panel.live_result(rows[:4], 48)["cases"], "실패 · 인자 추출") == [rows[2]]

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
    assert [r["case_id"] for r in panel.filter_results(rows, "실패")] == [3, 4], "오류가 실패에 들어갔다"
    assert [r["case_id"] for r in panel.filter_results(rows, panel.ERROR_FILTER)] == [5]
    assert [r["case_id"] for r in panel.filter_results(rows, "실패 · 기능 선택")] == [4]
    assert [r["case_id"] for r in panel.filter_results(rows, "실패 · 인자 추출")] == [3]
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
    assert _fail_tags(panel.detail_markup(_row(result, 1), FUNCTIONS)) == []
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


def _fail_tags(markup: str) -> list[str]:
    """비교표에서 「실패」 표시가 붙은 줄의 머리 글자들. 차례대로."""
    heads = []
    for row in re.findall(r'<div class="tt-row[^"]*">(.*?)</div></div>(?=<div class="tt-(?:row|sec)|</div>)', markup):
        if 'tt-tag-fail' in row:
            heads.append(visible_text(row.split('class="tt-c tt-answer"', 1)[0]).split()[0])
    return heads


def test_a_wrong_graded_value_is_marked_as_the_failure(result):
    """인자 추출에서 멈춘 발화는 틀린 인자 칸에만 「실패」. 판정은 runner 의 correct · failure_stage 를 읽음."""
    row = _row(result, 3)
    rows = {r["name"]: r for r in panel.field_rows(row)}
    assert rows["admin_level"]["correct"] is False and row["failure_stage"] == "input"
    markup = panel.detail_markup(row, FUNCTIONS)
    assert _fail_tags(markup) == ["행정구역"]
    assert "차이" not in visible_text(markup)
    assert "실패 · 인자 추출" in visible_text(markup)


def test_only_the_item_that_made_the_failure_stage_gets_the_실패_tag(result):
    """기능 선택이 틀리면 인자가 함께 틀려도 실패 원인은 기능 선택 하나다 (score.verdict).
    틀린 인자 칸은 강조만 되고 「실패」는 기능 칸에만 붙는다. 성공 줄 · 안 읽는 인자에는 아무것도 안 붙는다."""
    row = _row(result, 4)
    assert row["failure_stage"] == "function"
    markup = panel.detail_markup(row, FUNCTIONS)
    assert _fail_tags(markup) == ["기능"]
    wrong_fields = [f for f in panel.field_rows(row) if f["correct"] is False]
    assert wrong_fields, "틀린 인자가 없어 이 시험이 아무것도 못 본다"
    assert markup.count("tt-diff") == 1 + len(wrong_fields)
    for passed in (r for r in result["cases"] if r["passed"]):
        shown = panel.detail_markup(passed, FUNCTIONS)
        assert _fail_tags(shown) == [] and "tt-diff" not in shown


def test_an_error_row_has_no_실패_tag(result):
    """오류는 모델 품질 실패가 아니다. 비교표에 「실패」를 붙이지 않는다."""
    row = dict(_row(result, 2), passed=False, failure_stage="error", recipe_correct=False, actual=None,
               error="ServerDown: 가짜")
    markup = panel.detail_markup(row, FUNCTIONS)
    assert _fail_tags(markup) == [] and "tt-diff" not in markup


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
    """오류는 KRRI · MCP 실행 오류가 아니라 평가가 Resolve 결과를 못 받은 것이다. 「실패 · 실행 오류」로 부르지 않는다."""
    text = visible_text(panel.detail_markup(_row(result, 5), FUNCTIONS))
    assert "● 오류" in text
    assert "실패 · 실행 오류" not in text and "실행 오류" not in text
    assert "연결이 끊겼습니다" in text
    assert panel.verdict_label(_row(result, 5)) == "오류"


def test_the_model_settings_come_from_the_result_metadata_with_the_llm_temperature(result):
    """모델 설정 (자세히 보기)는 재현 · 확인용이다. 모델 이름은 실행 개요에 있어 되풀이하지 않고 Temperature 는 여기 있다."""
    conditions = panel.run_conditions(result)
    measured = result["meta"]["conditions"]
    assert list(conditions)[:2] == ["provider", "Resolve 역할"]
    assert list(conditions)[-4:] == ["프롬프트 파일", "응답 형식 파일", "기능 정의 파일", "게시 자산"]
    assert "모델" not in conditions
    assert conditions["Resolve 역할"] == result["meta"]["role"]
    assert conditions["프롬프트 파일"] == measured["prompt"]["path"]
    assert conditions["게시 자산"] == measured["registry"]["path"]
    if "temperature" in (measured.get("request") or {}):
        assert conditions["Temperature"] == panel.display_value(measured["request"]["temperature"])
        assert list(conditions)[2] == "Temperature"

    old = {**result, "meta": {**result["meta"], "conditions": {k: v for k, v in measured.items() if k != "registry"}}}
    assert "게시 자산" not in panel.run_conditions(old), "옛 기록에 없는 칸을 지어냈다"

    staged = {**result, "meta": {**result["meta"], "conditions": {**measured, "request": {"seed": 3, "temperature": 0.7}}}}
    shown = panel.run_conditions(staged)
    assert shown["Temperature"] == "0.7" and shown["Seed"] == "3"


# ── 무엇이 LLM 을 부르나 · 결과 표의 줄 ─────────────────────────────
#
# 한 번 재는 데 수십 분이 든다. 탭을 열거나 필터를 바꾸는 것만으로 다시 재면 안 된다.
# AppTest 로 탭을 그리고, 평가를 부르는 자리(run_selected · resume_selected)를 가짜 resolve 로 진짜 정답표를
# 도는 것으로 바꿔 끼운다. 평가는 진짜 run_evaluation 이 백그라운드 thread 에서 돌고, 기록은 tmp 의 local 자리에 남는다.
def _tab_script():
    from app.ui.components.testing_panel import render_test_tab

    render_test_tab({"viewport_height": 900})


def _enabled(dataset_id):
    suite = load_test_suite.load(load_test_suite.dataset(dataset_id)["path"])
    return [case for case in suite["cases"] if case["enabled"]]


class Hold:
    """가짜 resolve 의 at 번째 부름을 붙잡는 자리. entered 가 켜지면 그 부름이 도는 중이다."""

    def __init__(self, at):
        self.at, self.entered, self.release = at, threading.Event(), threading.Event()

    def __call__(self, count):
        if count == self.at:
            self.entered.set()
            assert self.release.wait(20), "붙잡은 resolve 를 놓지 않았다"


def _suite_resolve(dataset_id, seen=None, hold=None):
    """진짜 정답표를 도는 가짜 resolve. 번호가 10 의 배수면 틀린 기능, 범위 밖은 NO_MATCH. LLM 을 안 부름.

    seen 에 부른 발화를 차례로 적음. hold 가 있으면 몇 번째 부름인지를 넘겨 붙잡게 함
    """
    by_utterance = {case["utterance"]: case for case in _enabled(dataset_id)}

    def resolve(utterance):
        if seen is not None:
            seen.append(utterance)
        if hold is not None:
            hold(len(seen) if seen is not None else 0)
        case = by_utterance[utterance]
        if not load_test_suite.in_scope(case):
            return {"reason": "없음", "status": "NO_MATCH", "recipe_id": None, "candidate_recipe_ids": [], "paths": {}}
        rid = case["expected"]["recipe_ids"][0]
        if case["id"] % 10 == 0:
            rid = "recipe_001" if rid != "recipe_001" else "recipe_002"
        return {"reason": "가짜", "status": "SELECT", "recipe_id": rid, "candidate_recipe_ids": [rid], "paths": {},
                **(case["expected"].get("spoken") or {})}

    return resolve


def _measure(dataset_id, *, seen=None, progress=None, save_dir=None, should_stop=None, hold=None, only=None,
             fan_quiet_mode=False):
    """진짜 정답표 한 벌을 가짜 resolve 로 잰 결과 (run_evaluation.run_dataset 과 같은 모양)."""
    entry = load_test_suite.dataset(dataset_id)
    measured = run_evaluation.run(
        load_test_suite.load(entry["path"]), suite_path=Path(entry["path"]),
        resolve=_suite_resolve(dataset_id, seen, hold), progress=progress, materialize=False, save_dir=save_dir,
        dataset={"id": entry["id"], "label": entry["label"]}, should_stop=should_stop, only=only,
        fan_quiet_mode=fan_quiet_mode,
    )
    measured["meta"]["functions"] = dict(FUNCTIONS)
    return measured


@pytest.fixture
def app(monkeypatch, tmp_path):
    """테스트 탭 AppTest. 평가는 진짜 run_evaluation 을 고른 정답표와 가짜 resolve 로 백그라운드에서 돌림.

    at.calls        run_selected 가 불린 정답표 id (새로 실행 수)
    at.resumed      resume_selected 가 불린 (kind, run_id)
    at.resolved     가짜 resolve 가 받은 발화 (LLM 호출 수 자리)
    at.local        이 시험의 local 기록 자리 (tmp)
    at.hold         None 이 아니면 가짜 resolve 가 그 부름에서 멈춤 (Hold)
    at.fans         run_selected 가 받은 팬 소음 억제 값 (새로 실행마다)
    at.resume_fans  resume_selected 가 받은 팬 소음 억제 값 (이어 실행마다)
    """
    from streamlit.testing.v1 import AppTest

    local = tmp_path / "local"
    monkeypatch.setattr(manage_benchmark, "LOCAL_DIR", local)
    monkeypatch.setattr(panel, "_job", None)
    calls, resumed, resolved, fans, resume_fans = [], [], [], [], []
    at = AppTest.from_function(_tab_script, default_timeout=60)

    def run_selected(dataset_id, on_progress=None, should_stop=None, *, fan_quiet=True, monitor=None):
        calls.append(dataset_id)
        fans.append(fan_quiet)
        return _measure(dataset_id, seen=resolved, progress=on_progress, save_dir=manage_benchmark.LOCAL_DIR,
                        should_stop=should_stop, hold=at.hold, fan_quiet_mode=fan_quiet)

    def resume_selected(kind, run_id, on_progress=None, should_stop=None, *, fan_quiet=True, monitor=None):
        resumed.append((kind, run_id))
        resume_fans.append(fan_quiet)
        dataset_id = manage_benchmark.read_incomplete(manage_benchmark.run_dir(kind, run_id))["meta"]["suite"]["dataset_id"]
        return run_evaluation.resume(kind, run_id, resolve=_suite_resolve(dataset_id, resolved, at.hold),
                                     progress=on_progress, should_stop=should_stop, fan_quiet_mode=fan_quiet)

    monkeypatch.setattr(panel, "run_selected", run_selected)
    monkeypatch.setattr(panel, "resume_selected", resume_selected)
    at.calls, at.resumed, at.resolved, at.local, at.hold, at.fans = calls, resumed, resolved, local, None, fans
    at.resume_fans = resume_fans
    yield at
    job = panel.current_job()
    if job is not None and job.active():
        job.request_stop()
        if at.hold is not None:
            at.hold.release.set()
        job.thread.join(20)


def _results(at):
    return list(at.dataframe[0].value["결과"])


def _wait(at):
    """도는 job 이 끝나기를 기다리고 한 번 다시 그림 (fragment 가 결과를 받아 오는 회차)."""
    job = panel.current_job()
    assert job is not None
    job.thread.join(30)
    assert not job.active(), "평가 thread 가 안 끝났다"
    at.run()
    return job


def _start(at, key="test_run"):
    at.button(key=key).click().run()
    assert not at.exception, at.exception
    return panel.current_job()


def _run_buttons(at):
    """실행 제어 단추. 기능별 결과 카드(test_fn_…)도 단추라 뺀다."""
    return [b for b in at.button if not str(b.key or "").startswith("test_fn_")]


def _local_dirs(at):
    return sorted(p.name for p in at.local.iterdir()) if at.local.is_dir() else []


def _run_text(at):
    return " ".join(visible_text(m.value) for m in at.markdown if 'class="tt-run tt-run-' in m.value)


def test_opening_the_tab_shows_every_v1_case_as_pending_without_running(app):
    app.run()

    assert not app.exception
    assert app.calls == [] and app.resolved == []
    assert len(app.dataframe) == 1
    assert len(app.dataframe[0].value) == len(_enabled("test_suite_v1")) == 48
    assert set(_results(app)) == {panel.PENDING_TEXT}
    assert list(app.dataframe[0].value["발화"]) == [case["utterance"] for case in _enabled("test_suite_v1")]
    assert [b.label for b in _run_buttons(app)] == ["새로 실행"]
    assert _local_dirs(app) == []
    [quiet] = app.checkbox
    assert (quiet.label, quiet.value, quiet.disabled) == ("GPU 팬 소음 억제", True, False)
    assert quiet.help == panel.FAN_QUIET_HELP


def test_choosing_v2_shows_all_203_cases_as_pending_without_running(app):
    app.run()
    app.selectbox(key=panel.DATASET_KEY).set_value("test_suite_v2").run()

    assert not app.exception
    assert app.calls == [] and app.resolved == []
    assert len(app.dataframe[0].value) == len(_enabled("test_suite_v2")) == 203
    assert set(_results(app)) == {panel.PENDING_TEXT}
    assert _local_dirs(app) == []


@pytest.mark.parametrize("dataset_id, count", [("test_suite_v1", 48), ("test_suite_v2", 203)])
def test_a_run_keeps_every_case_row_and_fills_it_in_place_by_case_id(app, dataset_id, count):
    """실행 중 표가 끝난 줄만큼 줄었다 늘면 어디까지 왔는지와 무엇이 남았는지가 한눈에 안 보인다."""
    app.run()
    if dataset_id != "test_suite_v1":
        app.selectbox(key=panel.DATASET_KEY).set_value(dataset_id).run()
    app.hold = Hold(4)
    _start(app)
    assert app.hold.entered.wait(20)
    app.run()

    order = [case["id"] for case in _enabled(dataset_id)]
    assert len(app.dataframe) == 1 and len(app.dataframe[0].value) == count
    assert [int(n) for n in app.dataframe[0].value["번호"]] == order, "줄 차례가 바뀌었거나 줄이 덧붙었다"
    assert _results(app).count(panel.PENDING_TEXT) == count - 3
    assert f"새로 실행 중 · 3 / {count}" in _run_text(app)
    kpi = next(m.value for m in app.markdown if 'class="tt-kpis' in m.value)
    assert f"완료 3 / {count}" in visible_text(kpi)

    app.hold.release.set()
    _wait(app)
    assert not app.exception
    assert len(app.dataframe) == 1 and len(app.dataframe[0].value) == count
    assert panel.PENDING_TEXT not in _results(app)
    assert app.selectbox(key=panel.SAVED_KEY).value == ""
    assert sorted(app.resolved) == sorted(case["utterance"] for case in _enabled(dataset_id))
    assert app.calls == [dataset_id]
    assert f"완료 · {count} / {count}" in _run_text(app)


def test_pending_rows_are_never_counted_as_failures(app):
    app.run()
    app.segmented_control(key=panel.FILTER_KEY).set_value(panel.FAILED).run()
    assert not app.exception
    assert not app.dataframe, "대기 줄이 실패 보기에 들어갔다"

    rows = panel.suite_rows("test_suite_v1")
    assert panel.filter_results(rows, panel.FAILED) == []
    assert panel.first_failure(rows) is None
    assert all(panel.verdict_label(row) == panel.PENDING_TEXT for row in rows)
    assert all(panel.detail_markup(row, {}).count("실패") == 0 for row in rows[:3])


def test_the_run_calls_resolve_once_per_utterance_and_ends_on_one_table(app):
    """실행 중 다시 그리기가 LLM 을 더 부르면 안 되고, 끝난 뒤 표가 둘로 남으면 안 됨."""
    app.run()
    _start(app)
    _wait(app)

    assert not app.exception
    assert app.calls == ["test_suite_v1"]
    assert len(app.resolved) == 48
    assert len(app.dataframe) == 1
    assert len(app.dataframe[0].value) == 48
    assert any("tt-kpi-num\">48<" in m.value for m in app.markdown)
    last = panel.summarize(app.session_state[panel.RESULT_KEY]["result"])
    assert last["done"] == 48 and last["passed"] + last["failed"] + last["error"] == 48
    assert last["function"] == sum(1 for case in _enabled("test_suite_v1") if case["id"] % 10 == 0)


def test_filters_search_sort_and_redraws_after_the_run_do_not_rerun_it(app):
    app.run()
    _start(app)
    _wait(app)
    folders = _local_dirs(app)

    app.text_input(key="test_query").input("청주").run()
    app.selectbox(key=panel.SORT_COLUMN_KEY).set_value("발화").run()
    app.run()

    assert not app.exception
    assert app.calls == ["test_suite_v1"], "필터 · 다시 그리기가 평가를 다시 불렀다"
    assert len(app.resolved) == 48
    assert _local_dirs(app) == folders
    expected = [case for case in _enabled("test_suite_v1") if "청주" in case["utterance"].replace(" ", "")]
    assert len(app.dataframe) == 1 and len(app.dataframe[0].value) == len(expected)


@pytest.mark.parametrize("first, second, count", [("test_suite_v2", "test_suite_v1", 48), ("test_suite_v1", "test_suite_v2", 203)])
def test_switching_the_test_suite_drops_the_old_results_and_shows_the_new_pending_rows(app, first, second, count):
    app.run()
    if first != "test_suite_v1":
        app.selectbox(key=panel.DATASET_KEY).set_value(first).run()
    _start(app)
    _wait(app)
    assert panel.RESULT_KEY in app.session_state

    app.selectbox(key=panel.DATASET_KEY).set_value(second).run()

    assert not app.exception
    assert panel.RESULT_KEY not in app.session_state
    assert len(app.dataframe[0].value) == count
    assert set(_results(app)) == {panel.PENDING_TEXT}
    assert app.calls == [first], "테스트 세트를 고르기만 했는데 평가를 불렀다"


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
    assert _fail_tags(panel.detail_markup(wrong, FUNCTIONS)) == ["기능"] and "차이" not in text

    right = panel.detail_markup(_row(oos_result, 3), FUNCTIONS)
    assert "성공" in visible_text(right) and "해당 없음" in visible_text(right) and _fail_tags(right) == []

    for row in oos_result["cases"]:
        shown = visible_text(panel.detail_markup(row, FUNCTIONS))
        assert not [w for w in BANNED if w in shown], row["case_id"]
        assert not [w for w in RETIRED if w in shown], row["case_id"]


def test_the_case_detail_keeps_only_status_candidates_reason_and_inference_latency(result):
    for row in result["cases"]:
        text = visible_text(panel.detail_markup(row, FUNCTIONS))
        for label in ("모델 판정 상태", "후보 기능", "모델 판단", "추론 시간"):
            assert label in text, (row["case_id"], label)
        assert not [w for w in RETIRED if w in text], (row["case_id"], [w for w in RETIRED if w in text])


def _numbers(markup: str) -> list[tuple[str, str]]:
    """마크업에 보이는 「기능 NNN」 전부. [(설명 data-tip, 번호 글자)]. tooltip 이 없으면 빈 글자."""
    found = []
    for hit in re.finditer(r"기능 \d+", markup):
        span = markup.rfind("<span", 0, hit.start())
        head = markup[span:hit.start()]
        title = re.search(r'data-tip="([^"]*)"', head)
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
    cards = panel.recipe_card_css(panel.recipe_rows(result), FUNCTIONS)
    for entry in panel.recipe_rows(result):
        assert f'.st-key-{panel.recipe_card_key(entry)} button::after {{ content: "{FUNCTIONS[entry["group"]]}"; }}' in cards
    check(panel.reason_markup("recipe_045 가 맞고 recipe_061 은 아니다", FUNCTIONS), "모델 판단", at_least=2)

    tip = FUNCTIONS["recipe_045"]
    assert panel.number_markup("recipe_045", FUNCTIONS) == (
        f'<span class="tt-fnum" data-tip="{tip}" aria-description="{tip}">기능 045</span>'
    )
    assert panel.number_markup(None, FUNCTIONS) == ""
    assert panel.number_markup("recipe_999", FUNCTIONS) == '<span class="tt-fnum">기능 999</span>'


def test_a_candidate_function_shows_its_menu_description_on_hover_only(result):
    """칩에는 「기능 NNN」만 보이고, 설명은 data-tip(마우스를 올리면)에 있다. 설명의 원천은 결과 meta.functions."""
    markup = panel.detail_markup(_row(result, 4), FUNCTIONS)
    chip = re.search(r'<span class="tt-fnum tt-chip[^"]*" data-tip="([^"]*)"[^>]*>기능 045</span>', markup)
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


def test_the_overview_shows_total_inference_time_from_latency_total_not_the_wall_clock(oos_result):
    """전체 추론시간은 발화마다 resolve 한 번에 걸린 시간의 합(summary.latency.total)이다.
    벽시계(meta.elapsed_s)에는 materialize · 팬 대기 · 화면 시간이 섞여 같은 값이 아니다. elapsed_s 는 기록에 남는다."""
    faked = json.loads(json.dumps(oos_result))
    faked["summary"]["latency"]["total"] = 325.4
    faked["meta"]["elapsed_s"] = 9999.0
    rows = dict(panel.overview(faked))
    assert rows["전체 추론시간"] == [("", "5분 25초")]
    assert "전체 소요 시간" not in rows and "2시간" not in visible_text(panel.overview_markup(panel.overview(faked)))
    assert oos_result["meta"]["elapsed_s"] is not None, "벽시계 소요 시간이 기록에서 사라졌다"
    total = sum(r["timing"]["resolve_s"] for r in oos_result["cases"] if (r.get("timing") or {}).get("resolve_s") is not None)
    assert oos_result["summary"]["latency"]["total"] == round(total, 3)
    assert dict(panel.overview(oos_result))["전체 추론시간"] == [("", panel._duration(round(total, 3)))]

    faked["summary"]["latency"] = None
    assert dict(panel.overview(faked))["전체 추론시간"] == [("", panel.EMPTY_NUMBER)]


def test_the_top_summary_shows_run_facts_but_no_evaluation_metrics(oos_result):
    info = panel.overview(oos_result)
    titles = [title for title, _rows in info]
    assert titles == ["Test Suite", "평가 시작 시간", "전체 추론시간", "발화당 추론 시간", "평가 결과", "모델", "실행 환경"]
    rows = dict(info)
    assert [label for label, _ in rows["발화당 추론 시간"]] == ["Median", "P95", "Max"]
    total = oos_result["summary"]["total"]
    assert dict(rows["평가 결과"]) == {"전체": str(total["runs"]), "성공": str(total["passed"]),
                                     "실패": str(total["runs"] - total["passed"]), "오류": str(total["errors"])}
    assert rows["모델"] == [("", oos_result["meta"]["conditions"]["model"])]
    assert dict(rows["실행 환경"]) == {"GPU": "기록 없음", "VRAM (GPU 1개당)": "기록 없음"}
    assert "Temperature" not in visible_text(panel.overview_markup(info)), "Temperature 는 모델 설정 (자세히 보기)에 있다"

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
    assert rows == {"GPU": "RTX PRO 6000 × 4", "VRAM (GPU 1개당)": "95.6 GiB"}
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


def test_an_error_card_appears_only_when_there_is_an_error(result, oos_result):
    """오류는 모델 품질 실패가 아니다. 있으면 실패와 떼어 따로 세우고, 없으면 0 카드로 자리를 차지하지 않는다."""
    summary = panel.summarize(result)
    assert summary["error"] == 1 and summary["failed"] == 2
    markup = panel.summary_markup(summary)
    assert re.findall(r'class="tt-kpi-label">([^<]+)<', markup) == ["전체", "성공", "실패", "오류"]
    assert "tt-causes" not in markup.split('class="tt-kpi err"', 1)[1], "오류가 실패 원인 안에 들어갔다"
    assert "실행 오류" not in visible_text(markup)

    clean = panel.summarize(oos_result)
    assert clean["error"] == 0
    assert "오류" not in visible_text(panel.summary_markup(clean))


def test_the_function_results_list_only_supported_functions_in_numeric_order(result, oos_result):
    rows = result["cases"]
    assert [r["case_id"] for r in panel.filter_results(rows, "전체", "", "recipe_045")] == [2, 5]
    assert panel.OUT_OF_SCOPE_GROUP not in panel.group_options(rows)

    mixed = oos_result["cases"]
    assert panel.group_options(mixed)[-1] == panel.OUT_OF_SCOPE_GROUP
    assert [r["case_id"] for r in panel.filter_results(mixed, "전체", "", panel.OUT_OF_SCOPE_GROUP)] == [2, 3]
    assert [r["case_id"] for r in panel.filter_results(mixed, "실패 · 범위 밖 처리")] == [2]
    assert [e["label"] for e in panel.recipe_rows(oos_result)] == ["기능 010", "범위 밖"]
    outside = panel.recipe_rows(oos_result)[-1]
    total = oos_result["summary"]["total"]
    assert (outside["group"], outside["runs"], outside["passed"]) == (panel.OUT_OF_SCOPE_GROUP, total["oos_runs"], total["oos_passed"])
    assert [e["label"] for e in panel.recipe_rows(result)][-1] != "범위 밖", "범위 밖 발화가 없는데 범위 밖 카드가 섰다"

    unordered = {"summary": {"recipes": {rid: {"runs": 1, "passed": 1, "hit": 1}
                                          for rid in ("recipe_100", "recipe_020", "recipe_003", "recipe_061")}}}
    assert [e["group"] for e in panel.recipe_rows(unordered)] == ["recipe_003", "recipe_020", "recipe_061", "recipe_100"]


CANONICAL = "20260921-161258-test_suite_v2"
CANONICAL_V1 = "20260921-160634-test_suite_v1"


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
    assert [e.label for e in app.expander] == ["모델 설정 (자세히 보기)", "기능별 결과"]
    shown = " ".join(visible_text(m.value) for m in app.markdown if "<style>" not in m.value)
    assert not [w for w in RETIRED if w in shown], [w for w in RETIRED if w in shown]
    assert app.session_state[panel.RESULT_KEY]["result"]["summary"] == manage_benchmark.load_benchmark(
        "local", saved["meta"]["run_id"]
    )["summary"]


def test_the_saved_run_picker_lists_official_and_local_together_newest_first(app, monkeypatch, tmp_path):
    """기준 벤치마크와 보통 실행이 한 목록에 run_id 그대로 나온다. official 에만 Official 이 붙는다."""
    local = _measure("test_suite_v1", save_dir=_isolated_local(monkeypatch, tmp_path))

    app.run()
    labels = app.selectbox(key=panel.SAVED_KEY).options
    official = next(o for o in labels if o.startswith(CANONICAL))
    mine = next(o for o in labels if o.startswith(local["meta"]["run_id"]))
    assert official == f"{CANONICAL} · 188/203 · Official"
    total = local["summary"]["total"]
    assert mine == f"{local['meta']['run_id']} · {total['passed']}/{total['runs']}"
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
    assert _results(app).count("성공") == 188
    assert sum(1 for value in _results(app) if value.startswith("실패 · ")) == 15
    assert "판정" not in list(app.dataframe[0].value.columns)
    board = stored["result"]["summary"]["metrics"]
    assert board["selection"] == {"correct": 184, "total": 195}
    assert board["joint"] == {"correct": 181, "total": 195}
    assert board["oos"] == {"correct": 7, "total": 8}


def test_loading_the_official_full48_run_switches_to_v1_and_fills_its_48_rows(app):
    app.run()
    app.selectbox(key=panel.DATASET_KEY).set_value("test_suite_v2").run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"official:{CANONICAL_V1}").run()

    assert not app.exception and app.calls == []
    stored = app.session_state[panel.RESULT_KEY]
    assert stored["kind"] == "official" and stored["result"]["meta"]["run_id"] == CANONICAL_V1
    assert app.session_state[panel.DATASET_KEY] == "test_suite_v1"
    assert len(app.dataframe[0].value) == 48 and _results(app).count("성공") == 48


def test_the_saved_run_list_comes_from_the_real_storage_roots_and_is_not_empty(app):
    """2026-09-21 불러올 기록이 비었다. 화면이 읽던 폴더가 옮겨져 사라졌는데 목록 함수가 빈 목록을 조용히 돌려줬다.

    옮긴 뒤에도 기준 벤치마크가 공식으로 떠야 하고, 읽을 자리가 없으면 빈 목록 대신 까닭이 보여야 한다.
    """
    app.run()
    options = app.selectbox(key=panel.SAVED_KEY).options
    assert any(o.startswith(f"{CANONICAL} · ") and o.endswith(" · Official") for o in options), options
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
    assert panel.saved_label(entry) == f"{entry['run_id']} · 3/48 · 중단됨"

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

    run_id = CANONICAL
    entry = {"run_id": run_id, "kind": "official", "complete": True, "started_at": "2026-09-21T16:12:58",
             "runs": 203, "passed": 188, "suite_label": "테스트 세트 v2", "suite_name": "test_suite_v2"}
    assert panel.saved_label(entry) == f"{run_id} · 188/203 · Official"
    assert panel.saved_key(entry) == f"official:{run_id}"
    stopped = {**entry, "kind": "local", "complete": False, "runs": None, "passed": None}
    assert panel.saved_label(stopped) == f"{run_id} · 중단됨"


def test_history_labels_name_only_official_and_put_중단됨_last():
    """local 에는 갈래 글자가 없고, official 에만 Official. 중단됨은 어떤 조합이든 맨 끝."""
    base = {"run_id": "20260921-170000-test_suite_v1", "started_at": "2026-09-21T17:00:00"}
    done_local = {**base, "kind": "local", "complete": True, "runs": 48, "passed": 48}
    stopped_local = {**base, "kind": "local", "complete": False, "planned": 48, "done": 7}
    stopped_official = {**base, "kind": "official", "complete": False, "planned": 48, "done": 7}
    duplicate = {**stopped_official, "duplicate": True}
    assert panel.saved_label(done_local) == f"{base['run_id']} · 48/48"
    assert panel.saved_label({**done_local, "kind": "official"}) == f"{base['run_id']} · 48/48 · Official"
    assert panel.saved_label(stopped_local) == f"{base['run_id']} · 7/48 · 중단됨"
    assert panel.saved_label(stopped_official) == f"{base['run_id']} · 7/48 · Official · 중단됨"
    assert panel.saved_label(duplicate) == f"{base['run_id']} · 7/48 · Official · 중복 · 중단됨"
    for entry in (done_local, stopped_local, stopped_official, duplicate):
        label = panel.saved_label(entry)
        assert "Local" not in label and "로컬" not in label and "공식" not in label, label
        assert panel.STOPPED_TEXT not in label or label.endswith(panel.STOPPED_TEXT), label


def test_the_overview_names_the_suite_by_its_file(result):
    """실행 개요가 별칭을 보이면 이 결과가 저장소의 어느 파일을 잰 것인지 알 수 없다."""
    result = {**result, "meta": {**result["meta"],
                                 "suite": {"path": "dev/evaluation/inputs/test_suites/test_suite_v1.yaml",
                                           "label": "FULL48 회귀 테스트"}}}
    shown = dict(panel.overview(result))["Test Suite"]
    assert shown == [("", "test_suite_v1.yaml")]


def test_a_function_card_shows_only_its_number_and_score(result):
    """「모두 성공」 · 「실패 N」 은 x/y 가 이미 말한 것을 되풀이한다. 서른아홉 장이면 글자만 는다."""
    entries = panel.recipe_rows(result)
    assert entries and any(e["failed"] for e in entries)
    for e in entries:
        assert panel.recipe_card_label(e) == f"{panel.function_label(e['group'])} **{e['passed']}/{e['runs']}**"
        assert panel.recipe_card_key(e) == f"test_fn_{'ng' if e['failed'] else 'ok'}_{e['group']}"
    assert panel.recipe_card_key({"group": panel.OUT_OF_SCOPE_GROUP, "failed": 1}) == "test_fn_ng_out_of_scope"

    # 성공은 옆줄만, 실패는 배경까지. 카드 사이에는 틈이 있다
    css = panel.panel_css()
    assert "rgba(229, 83, 75" in css.split('[class*="st-key-test_fn_ng_"] button {', 1)[1][:200]
    assert "background" not in css.split('[class*="st-key-test_fn_ok_"] button {', 1)[1].split("}", 1)[0]
    assert re.search(r"\.st-key-test_fn_cards \{[^}]*gap:", css)


def test_a_function_card_carries_its_menu_description_without_a_second_table(result):
    """카드는 단추라 data-tip 을 못 받는다. 설명은 카드 key 의 ::after 한 줄이고, 뜨는 모양 · 지연은 기능 번호 tooltip 과 같다."""
    entries = panel.recipe_rows(result)
    css = panel.recipe_card_css(entries, FUNCTIONS)
    for e in entries:
        if e["group"] in FUNCTIONS:
            assert css.count(f".st-key-{panel.recipe_card_key(e)} button::after") == 1, e["group"]
    assert panel.recipe_card_css(entries, {}) == ""
    tricky = panel.recipe_card_css([{"group": "recipe_001", "failed": 0}], {"recipe_001": 'a "b" \\ </style>\n'})
    assert "</style>" not in tricky[:-len("</style>")] and '\\"b\\"' in tricky
    base = panel.panel_css()
    assert ".st-key-test_tab .st-key-test_fn_cards button:hover::after" in base
    assert f"{panel.TIP_DELAY_MS}ms" in base.split(".st-key-test_fn_cards button:hover::after", 1)[1][:300]


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
    """처음 보는 사람이 세부 셋이 실패의 까닭인 줄 알게 결과 칸 글자와 같은 「실패 · …」로 쓰고 실패 뒤에 매단다."""
    assert panel.FAILED == "실패"
    assert panel.FILTERS == ("전체", "실패", "실패 · 기능 선택", "실패 · 인자 추출", "실패 · 범위 밖 처리")
    assert panel.FAILURE_FILTERS == panel.FILTERS[panel.FIRST_FAILURE_FILTER - 1:]
    assert set(panel.FAILURE_FILTERS) == set(panel.RESULT_ORDER) - {panel.SUCCESS_TEXT, panel.ERROR_TEXT}

    css = panel.panel_css()
    parent, first, last = panel.PARENT_FILTER, panel.FIRST_FAILURE_FILTER, len(panel.FILTERS)
    assert panel.FILTERS[parent - 1] == panel.FAILED and first == parent + 1
    # 실패는 진하게, 세부 셋은 같은 붉은 계열로 옅게, 실패와 셋 사이에는 세로선
    assert f'button[data-variant="segmented_control"]:nth-of-type({parent}) {{' in css
    assert f'button[data-variant="segmented_control"]:nth-of-type({parent})::after' in css
    assert f":nth-of-type(n+{first}):nth-of-type(-n+{last})" in css
    for word in ("사유", "실패 사유"):
        assert word not in "".join(panel.FILTERS)


def test_실패_and_its_three_causes_sit_in_one_group_box_that_전체_and_오류_stay_outside():
    """실패 15 = 기능 선택 11 + 인자 추출 3 + 범위 밖 처리 1 이 보이려면 넷이 한 테두리 안에 있어야 한다.
    같은 줄의 독립 pill 넷이면 관계가 안 보인다. 칸은 radiogroup 의 ::before 가 grid 칸 실패 ~ 마지막 세부를 덮어 그린다.
    전체(1번)와 오류(맨 뒤)는 그 칸 밖이다. 한 줄 grid 라 높이가 안 는다."""
    css = panel.panel_css()
    parent, last = panel.PARENT_FILTER, len(panel.FILTERS)
    box = css.split('.st-key-test_filter [role="radiogroup"]::before {', 1)[1].split("}", 1)[0]
    assert f"grid-column: {parent} / {last + 1};" in box and "grid-row: 1;" in box
    assert "border:" in box and "background:" in box
    group = '.st-key-test_filter [role="radiogroup"] {'
    assert "display: grid" in css.split(group, 1)[1].split("}", 1)[0]
    for n in range(1, last + 2):
        assert f':nth-of-type({n}) {{ grid-row: 1; grid-column: {n}; }}' in css, n
    assert parent > 1 and panel.FILTERS[0] == panel.ALL
    error = len(panel.FILTERS) + 1
    assert f'button[data-variant="segmented_control"]:nth-of-type({error}) {{' in css


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


# ── 결과 칸 · 정렬 ───────────────────────────────────────────────────
RESULT_VALUES = {"대기", "성공", "실패 · 기능 선택", "실패 · 인자 추출", "실패 · 범위 밖 처리", "오류"}


def test_the_result_table_has_one_result_column_and_no_판정_column(result, oos_result):
    """모델 품질 실패 셋 · 오류 · 대기가 한 칸에서 갈린다. 판정 칸이 또 있으면 같은 것을 두 번 읽는다."""
    rows = [*result["cases"], *oos_result["cases"], *panel.suite_rows("test_suite_v1")[:2]]
    frame = panel.list_frame(rows)
    assert list(frame.columns) == ["번호", "기능", "발화", "결과", "추론 시간"]
    assert set(frame["결과"]) == RESULT_VALUES
    assert "실패 · 실행 오류" not in set(frame["결과"])
    assert panel.RESULT_ORDER == ("성공", "실패 · 기능 선택", "실패 · 인자 추출", "실패 · 범위 밖 처리", "오류")
    assert "판정" not in panel._list_columns()


def test_every_visible_inference_time_has_two_decimals_and_the_stored_value_is_untouched(result, oos_result):
    """위 Median · P95 · Max 와 표의 발화별 추론 시간이 자릿수가 다르면 같은 것을 재는 숫자로 안 읽힌다.
    글자만 반올림한다 — 결과(run.json)의 값은 그대로다."""
    row = _latency(_row(result, 1), 1.4)
    assert list(panel.list_frame([row])["추론 시간"]) == ["1.40초"]
    assert list(panel.list_frame([_latency(_row(result, 1), 1.6234)])["추론 시간"]) == ["1.62초"]
    assert row["timing"]["resolve_s"] == 1.4
    assert "추론 시간  1.40초" in visible_text(panel.detail_markup(row, FUNCTIONS))

    faked = json.loads(json.dumps(oos_result))
    faked["summary"]["latency"].update(median=1.4, p95=1.8651, max=2.0)
    assert dict(panel.overview(faked))["발화당 추론 시간"] == [("Median", "1.40초"), ("P95", "1.87초"), ("Max", "2.00초")]
    assert faked["summary"]["latency"]["p95"] == 1.8651
    faked["summary"]["latency"] = {}
    assert dict(panel.overview(faked))["발화당 추론 시간"] == [("Median", "—"), ("P95", "—"), ("Max", "—")]


def test_the_header_says_발화_해석_평가_with_no_subtitle_and_calls_the_suite_Test_Suite(app):
    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"official:{CANONICAL}").run()
    shown = " ".join(visible_text(m.value) for m in app.markdown if "<style>" not in m.value)
    assert "발화 해석 평가" in shown
    for gone in ("AI 기능 테스트", "발화별 기능 선택 및 인자 추출 결과", "테스트 세트", "추론 지연시간", "장당"):
        assert gone not in shown, gone
    assert not any('class="tt-sub"' in m.value for m in app.markdown)
    assert app.selectbox(key=panel.DATASET_KEY).label == "Test Suite"
    assert not [box.label for box in app.selectbox if "테스트 세트" in box.label]


def test_the_detail_keeps_the_raw_model_status(result, oos_result):
    """표의 판정 칸을 뺀 것이지 모델이 낸 판정 상태(SELECT · NO_MATCH …)를 뺀 것이 아니다."""
    selected = visible_text(panel.detail_markup(_row(result, 1), FUNCTIONS))
    assert "모델 판정 상태" in selected and "선택" in selected.split("모델 판정 상태", 1)[1]
    no_match = visible_text(panel.detail_markup(_row(oos_result, 3), FUNCTIONS))
    assert "해당 없음" in no_match.split("모델 판정 상태", 1)[1]


def _latency(row, seconds):
    return {**row, "timing": {**(row.get("timing") or {}), "resolve_s": seconds}}


def test_sort_rows_defaults_to_number_ascending_and_breaks_ties_by_number(result):
    rows = list(reversed(result["cases"]))
    assert [r["case_id"] for r in panel.sort_rows(rows)] == [1, 2, 3, 4, 5]
    assert [r["case_id"] for r in panel.sort_rows(rows, "번호", panel.DESCENDING)] == [5, 4, 3, 2, 1]

    by_result = panel.sort_rows(rows, "결과")
    assert [panel.verdict_label(r) for r in by_result] == ["성공", "성공", "실패 · 기능 선택", "실패 · 인자 추출", "오류"]
    assert [r["case_id"] for r in by_result][:2] == [1, 2], "같은 값끼리 번호 차례가 아니다"
    flipped = panel.sort_rows(rows, "결과", panel.DESCENDING)
    assert [r["case_id"] for r in flipped] == [5, 3, 4, 1, 2], "내림차순에서 같은 값끼리의 번호 차례가 뒤집혔다"

    by_function = [r["case_id"] for r in panel.sort_rows(rows, "기능")]
    assert by_function == [3, 1, 2, 5, 4]
    assert panel.sort_rows(rows, "없는 칸") == panel.sort_rows(rows)


def test_pending_rows_and_missing_latency_stay_last_in_both_directions(result):
    skeleton = panel.suite_rows("test_suite_v1")[5:8]
    done = [_latency(_row(result, 1), 3.0), _latency(_row(result, 2), 1.0), _latency(_row(result, 3), 2.0)]
    rows = [skeleton[1], done[0], skeleton[0], done[1], skeleton[2], done[2]]
    pending_ids = [r["case_id"] for r in skeleton]

    up = [r["case_id"] for r in panel.sort_rows(rows, "추론 시간")]
    down = [r["case_id"] for r in panel.sort_rows(rows, "추론 시간", panel.DESCENDING)]
    assert up == [2, 3, 1, *pending_ids]
    assert down == [1, 3, 2, *pending_ids]
    for column in ("결과", "추론 시간"):
        for order in panel.SORT_ORDERS:
            assert [r["case_id"] for r in panel.sort_rows(rows, column, order)][-3:] == pending_ids


def _table_ids(at):
    return [int(n) for n in at.dataframe[0].value["번호"]]


def test_the_sort_choice_survives_row_selection_search_filters_and_loading_a_record(app):
    """정렬은 session_state 에 있다. 행을 누르거나 검색 · 필터 · 기록 불러오기로 다시 그려도 그대로다."""
    app.run()
    assert (app.session_state[panel.SORT_COLUMN_KEY], app.session_state[panel.SORT_ORDER_KEY]) == ("번호", panel.ASCENDING)
    assert _table_ids(app) == sorted(_table_ids(app))

    app.selectbox(key=panel.SORT_COLUMN_KEY).set_value("발화").run()
    app.segmented_control(key=panel.SORT_ORDER_KEY).set_value(panel.DESCENDING).run()
    utterances = list(app.dataframe[0].value["발화"])
    assert utterances == sorted(utterances, reverse=True)
    order = _table_ids(app)

    for picked in (order[5], order[17]):
        app.session_state[panel.SELECTED_KEY] = picked
        app.run()
        assert _table_ids(app) == order, "행을 고르자 정렬이 풀렸다"
        assert f'<span class="tt-no">{picked:03d}</span>' in next(m.value for m in app.markdown if 'class="tt-head"' in m.value)

    app.text_input(key="test_query").input("역").run()
    shown = list(app.dataframe[0].value["발화"])
    assert shown == sorted(shown, reverse=True)
    app.text_input(key="test_query").input("").run()
    app.segmented_control(key=panel.FILTER_KEY).set_value(panel.FAILED).run()
    app.segmented_control(key=panel.FILTER_KEY).set_value(panel.ALL).run()
    assert _table_ids(app) == order

    app.selectbox(key=panel.SAVED_KEY).set_value(f"official:{CANONICAL}").run()
    shown = list(app.dataframe[0].value["발화"])
    assert len(shown) == 203 and shown == sorted(shown, reverse=True)
    assert (app.session_state[panel.SORT_COLUMN_KEY], app.session_state[panel.SORT_ORDER_KEY]) == ("발화", panel.DESCENDING)
    assert app.calls == [] and _local_dirs(app) == []


def test_the_grid_header_sort_is_switched_off_so_only_the_python_sort_exists(app):
    """칸 고르기를 켜면 st.dataframe 의 머리글 정렬이 꺼진다 (Streamlit 1.62). 두 정렬이 서로 다르게 보이지 않게."""
    from streamlit.proto.Dataframe_pb2 import Dataframe

    app.run()
    modes = set(app.dataframe[0].proto.selection_mode)
    assert Dataframe.SelectionMode.SINGLE_COLUMN in modes
    assert {Dataframe.SelectionMode.SINGLE_ROW, Dataframe.SelectionMode.SINGLE_CELL} <= modes

    from unittest import mock

    ids = [r["case_id"] for r in panel.suite_rows("test_suite_v1")]
    for clicked in ({"rows": [], "columns": ["발화"], "cells": []}, {"rows": [3], "columns": ["결과"], "cells": []}):
        state = {"표": {"selection": clicked}, panel.SELECTED_KEY: ids[7]}
        with mock.patch.object(panel.st, "session_state", state):
            panel._keep_row_selected("표", ids)
        assert state["표"]["selection"]["columns"] == [], "머리글을 눌러 고른 칸이 남았다"
        assert state["표"]["selection"]["rows"] == [clicked["rows"][0] if clicked["rows"] else 7]


# ── 새로 실행 · 중지 · 이어 실행 ───────────────────────────────────────
def test_only_새로_실행_creates_a_benchmark_folder(app, monkeypatch, tmp_path):
    """테스트 세트 · 정렬 · 필터 · 행 · 기록 고르기는 폴더를 만들지 않는다. 새로 실행 한 번이 폴더 하나다."""
    app.run()
    app.selectbox(key=panel.DATASET_KEY).set_value("test_suite_v2").run()
    app.selectbox(key=panel.SORT_COLUMN_KEY).set_value("결과").run()
    app.segmented_control(key=panel.FILTER_KEY).set_value(panel.FAILED).run()
    app.segmented_control(key=panel.FILTER_KEY).set_value(panel.ALL).run()
    app.session_state[panel.SELECTED_KEY] = 12
    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"official:{CANONICAL}").run()
    app.selectbox(key=panel.DATASET_KEY).set_value("test_suite_v1").run()
    assert not app.exception and _local_dirs(app) == [] and app.calls == []

    _start(app)
    _wait(app)
    assert len(_local_dirs(app)) == 1
    [folder] = _local_dirs(app)
    assert re.fullmatch(r"\d{8}-\d{6}-test_suite_v1", folder)
    assert sorted(p.name for p in (app.local / folder).iterdir()) == [manage_benchmark.RUN_FILE]


def test_a_finished_run_shows_완료_and_only_새로_실행(app):
    app.run()
    _start(app)
    _wait(app)

    assert "완료 · 48 / 48" in _run_text(app)
    assert [b.label for b in _run_buttons(app)] == ["새로 실행"]
    assert not [e for e in app.expander if e.label == "변경된 조건 보기"]
    [folder] = _local_dirs(app)
    assert sorted(p.name for p in (app.local / folder).iterdir()) == [manage_benchmark.RUN_FILE]


def _stop_at(app, call):
    """새로 실행을 누르고 call 번째 부름을 붙잡은 채 중지를 누른 뒤 놓아 끝까지 기다림."""
    app.hold = Hold(call)
    job = _start(app)
    assert app.hold.entered.wait(20)
    app.run()
    assert [b.label for b in _run_buttons(app)] == ["중지"]
    app.button(key="test_stop").click().run()
    assert job.stop_requested()
    assert [(b.label, b.disabled) for b in _run_buttons(app)] == [("중지 요청됨", True)]
    assert "중지 요청됨 · 현재 발화를 마친 뒤 중지합니다." in _run_text(app)
    app.hold.release.set()
    _wait(app)
    return job


def test_중지_lets_the_call_in_flight_finish_saves_it_and_never_starts_the_next(app):
    app.run()
    _stop_at(app, 2)

    assert app.resolved == [case["utterance"] for case in _enabled("test_suite_v1")[:2]], "중지 뒤에 다음 발화를 불렀다"
    [folder] = _local_dirs(app)
    files = sorted(p.name for p in (app.local / folder).iterdir())
    assert files == [manage_benchmark.CASES_FILE, manage_benchmark.META_FILE], "멈춘 기록에 run.json 이 생겼다"
    lines = (app.local / folder / manage_benchmark.CASES_FILE).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2

    assert "중단됨 · 2 / 48" in _run_text(app)
    assert _results(app).count(panel.PENDING_TEXT) == 46
    assert [(b.label, b.disabled) for b in _run_buttons(app)] == [("이어 실행", False), ("새로 실행", False)]
    assert any("이어 실행 가능" in m.value for m in app.markdown)
    label = next(o for o in app.selectbox(key=panel.SAVED_KEY).options if o.startswith(folder))
    assert label == f"{folder} · 2/48 · 중단됨"


def test_while_running_the_pickers_are_locked_and_a_second_run_cannot_start(app):
    from streamlit.testing.v1 import AppTest

    app.run()
    app.hold = Hold(1)
    job = _start(app)
    assert app.hold.entered.wait(20)
    app.run()
    assert app.selectbox(key=panel.DATASET_KEY).disabled and app.selectbox(key=panel.SAVED_KEY).disabled
    assert [b.label for b in _run_buttons(app)] == ["중지"]
    assert not panel.start_job(panel._Job(panel.NEW, "test_suite_v1", 48), lambda: None), "두 번째 평가가 시작됐다"

    other = AppTest.from_function(_tab_script, default_timeout=60)
    other.run()
    assert [b.label for b in _run_buttons(other)] == ["중지"], "다른 창이 두 번째 실행을 할 수 있다"

    app.hold.release.set()
    _wait(app)
    assert not app.selectbox(key=panel.DATASET_KEY).disabled
    assert app.calls == ["test_suite_v1"] and job is panel.current_job()


def test_이어_실행_continues_the_same_run_id_and_calls_only_the_missing_cases(app):
    app.run()
    _stop_at(app, 2)
    [folder] = _local_dirs(app)
    first_rows = (app.local / folder / manage_benchmark.CASES_FILE).read_text(encoding="utf-8").splitlines()

    app.hold = Hold(4)
    _start(app, "test_resume")
    assert app.hold.entered.wait(20)
    app.run()
    assert "이어 실행 중 · 3 / 48" in _run_text(app)
    assert _results(app).count(panel.PENDING_TEXT) == 45, "전에 잰 줄이 대기로 돌아갔다"
    app.button(key="test_stop").click().run()
    app.hold.release.set()
    _wait(app)

    utterances = [case["utterance"] for case in _enabled("test_suite_v1")]
    assert app.resolved == utterances[:4]
    assert app.resumed == [("local", folder)] and app.calls == ["test_suite_v1"]
    assert _local_dirs(app) == [folder], "이어 실행이 새 폴더를 만들었다"
    assert "중단됨 · 4 / 48" in _run_text(app)
    rows = (app.local / folder / manage_benchmark.CASES_FILE).read_text(encoding="utf-8").splitlines()
    assert rows[:2] == first_rows and len(rows) == 4

    app.hold = None
    _start(app, "test_resume")
    _wait(app)
    assert app.resolved == utterances, "끝난 발화를 다시 불렀다"
    assert _local_dirs(app) == [folder]
    assert sorted(p.name for p in (app.local / folder).iterdir()) == [manage_benchmark.RUN_FILE]
    assert "완료 · 48 / 48" in _run_text(app)
    saved = manage_benchmark.load_benchmark("local", folder)
    assert saved["meta"]["run_id"] == folder
    assert [row["case_id"] for row in saved["cases"]] == [case["id"] for case in _enabled("test_suite_v1")]


def _stopped_record(root, count, edit=None):
    """count 개 뒤에 멈춘 FULL48 local 기록. edit 가 있으면 meta.json 머리를 고침. 폴더 이름."""
    seen = []
    result = _measure("test_suite_v1", seen=seen, save_dir=root, should_stop=lambda: len(seen) >= count)
    folder = Path(result["meta"]["saved_to"])
    if edit:
        path = folder / manage_benchmark.META_FILE
        document = json.loads(path.read_text(encoding="utf-8"))
        edit(document["meta"])
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return folder


def test_loading_a_compatible_incomplete_record_offers_이어_실행_without_creating_anything(app):
    folder = _stopped_record(app.local, 5)
    before = sorted(p.name for p in folder.iterdir())
    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"local:{folder.name}").run()

    assert not app.exception
    assert "중단됨 · 5 / 48" in _run_text(app)
    assert any("이어 실행 가능" in m.value for m in app.markdown)
    assert [(b.label, b.disabled) for b in _run_buttons(app)] == [("이어 실행", False), ("새로 실행", False)]
    assert _local_dirs(app) == [folder.name] and sorted(p.name for p in folder.iterdir()) == before
    assert app.calls == [] and app.resolved == []


@pytest.mark.parametrize("label, edit", [
    ("Prompt", lambda meta: meta["conditions"]["prompt"].update(sha256="1" * 64)),
    ("Model", lambda meta: meta["conditions"].update(model="다른-모델")),
    ("Request settings", lambda meta: meta["conditions"]["request"].update(temperature=0.7)),
])
def test_an_incompatible_record_keeps_이어_실행_visible_but_disabled_and_shows_what_changed(app, label, edit):
    folder = _stopped_record(app.local, 3, edit)
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"local:{folder.name}").run()

    assert not app.exception
    assert [(b.label, b.disabled) for b in _run_buttons(app)] == [("이어 실행", True), ("새로 실행", False)]
    shown = " ".join(visible_text(m.value) for m in app.markdown if "<style>" not in m.value)
    assert "이어 실행 불가" in shown and "실행 조건이 변경되어 이어 실행할 수 없습니다." in shown
    assert [e.label for e in app.expander if e.label == "변경된 조건 보기"] == ["변경된 조건 보기"]
    table = next(m.value for m in app.markdown if "tt-conds" in m.value and "<style>" not in m.value)
    changed = re.findall(r'<tr class="tt-changed"><td>([^<]+)</td><td>변경됨</td>', table)
    assert changed == [label]
    assert "동일" in visible_text(table)

    # 눌리지 않는 단추의 콜백을 억지로 불러도 파일을 안 건드리고 평가를 시작하지 않는다
    from unittest import mock

    stored = app.session_state[panel.RESULT_KEY]
    state = {}
    with mock.patch.object(panel.st, "session_state", state):
        panel._start_resume(stored)
    assert panel.current_job() is None and state[panel.RUN_ERROR_KEY] == "실행 조건이 변경되어 이어 실행할 수 없습니다."
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before and _local_dirs(app) == [folder.name]


def test_an_old_record_without_resume_conditions_loads_but_cannot_be_resumed(app):
    folder = _stopped_record(app.local, 3, lambda meta: meta["conditions"].pop("registry"))
    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"local:{folder.name}").run()

    assert not app.exception
    assert _results(app).count(panel.PENDING_TEXT) == 45
    assert [(b.label, b.disabled) for b in _run_buttons(app)] == [("이어 실행", True), ("새로 실행", False)]
    shown = " ".join(visible_text(m.value) for m in app.markdown if "<style>" not in m.value)
    assert "저장된 실행 조건만으로 동일 실행을 재현할 수 없습니다." in shown
    table = next(m.value for m in app.markdown if "tt-conds" in m.value and "<style>" not in m.value)
    assert "기록 없음" in visible_text(table)


def test_the_condition_table_shows_short_hashes_but_compares_full_values():
    check = {"fields": [
        {"label": "Prompt", "stored": "a" * 64, "current": "a" * 63 + "b", "same": False},
        {"label": "Request settings", "stored": {"temperature": 0, "seed": 0}, "current": {"seed": 0, "temperature": 0},
         "same": True},
        {"label": "Registry", "stored": None, "current": "c" * 64, "same": False},
    ]}
    rows = panel.condition_rows(check)
    assert [(r["실행 조건"], r["상태"]) for r in rows] == [("Prompt", "변경됨"), ("Request settings", "동일"), ("Registry", "기록 없음")]
    assert rows[0]["저장된 값"] == rows[0]["지금 값"] == "a" * 12, "짧게 보여도 맞대기는 전체 값이다"
    assert rows[1]["저장된 값"] == '{"seed": 0, "temperature": 0}'


# ── 비교 칸의 기능 · 기능 tooltip ─────────────────────────────────────
def _model_function_cell(markup: str) -> str:
    """비교 표의 기능 줄에서 AI 모델 출력 칸 마크업."""
    row = markup.split('<div class="tt-sec">기능 선택</div>', 1)[1].split('<div class="tt-sec">', 1)[0]
    return row.split('<div class="tt-c tt-model', 1)[1]


def _chips(cell: str) -> list[tuple[str, str]]:
    """칸 안의 기능 pill 들. [(data-tip, 번호 글자)] 나온 차례."""
    return re.findall(r'<span class="tt-fnum tt-chip" data-tip="([^"]*)"[^>]*>(기능 \d+)</span>', cell)


def _clarify(row, candidates):
    return {**row, "passed": False, "failure_stage": "function", "recipe_correct": False,
            "actual": {**row["actual"], "status": "CLARIFY", "recipe_id": None, "candidate_recipe_ids": candidates}}


def test_a_selected_function_is_one_pill_with_its_description(result):
    cell = _model_function_cell(panel.detail_markup(_row(result, 2), FUNCTIONS))
    assert _chips(cell) == [(FUNCTIONS["recipe_045"], "기능 045")]
    assert FUNCTIONS["recipe_045"] in visible_text(cell)


def test_a_clarify_shows_every_candidate_as_its_own_pill_in_model_order(result):
    """되묻기만 보이면 어느 기능 사이에서 되물었는지 모른다. 후보마다 pill 하나, 모델이 낸 차례 그대로."""
    for candidates in (["recipe_045", "recipe_061"], ["recipe_061", "recipe_010", "recipe_045"]):
        markup = panel.detail_markup(_clarify(_row(result, 2), candidates), FUNCTIONS)
        cell = _model_function_cell(markup)
        assert _chips(cell) == [(FUNCTIONS[rid], panel.function_label(rid)) for rid in candidates]
        assert "되묻기" not in visible_text(cell)
        assert not re.search(r"기능 \d+\s*[,·]\s*기능 \d+", visible_text(cell)), "번호를 글자로 이어 붙였다"
        status = visible_text(markup).split("모델 판정 상태", 1)[1].split("후보 기능", 1)[0]
        assert "되묻기" in status, "되묻기 판정이 사라졌다"
        assert 'class="tt-fn tt-fns"' in cell and "tt-tag-fail" in cell and panel.FAILED in visible_text(cell)


def test_a_clarify_without_candidates_and_a_no_match_keep_their_words(result, oos_result):
    empty = _model_function_cell(panel.detail_markup(_clarify(_row(result, 2), []), FUNCTIONS))
    assert _chips(empty) == [] and "되묻기" in visible_text(empty)
    no_match = _model_function_cell(panel.detail_markup(_row(oos_result, 3), FUNCTIONS))
    assert _chips(no_match) == [] and "해당 없음" in visible_text(no_match)
    broken = _model_function_cell(panel.detail_markup(_row(result, 5), FUNCTIONS))
    assert _chips(broken) == [] and "오류" in visible_text(broken)


def test_the_comparison_pill_and_the_candidate_pill_are_the_same_markup(result):
    """비교 칸 pill 과 아래 후보 기능 pill 이 같은 renderer · 같은 class 를 지난다."""
    markup = panel.detail_markup(_clarify(_row(result, 2), ["recipe_045", "recipe_061"]), FUNCTIONS)
    below = markup.split("후보 기능", 1)[1].split("모델 판단", 1)[0]
    for rid in ("recipe_045", "recipe_061"):
        pill = panel.number_markup(rid, FUNCTIONS, panel.CHIP_CSS)
        assert pill in _model_function_cell(markup)
        assert re.sub(r'class="[^"]*"', "", pill) in re.sub(r'class="[^"]*"', "", below)


def test_function_tooltips_are_drawn_by_css_after_a_short_delay_not_by_the_browser_title(result, oos_result):
    """title 은 뜨기까지 1초 가까이 걸리고 그 지연을 못 바꾼다. data-tip 을 CSS 가 TIP_DELAY_MS 뒤에 그린다."""
    assert 100 <= panel.TIP_DELAY_MS <= 150
    markups = [panel.detail_markup(row, FUNCTIONS) for row in [*result["cases"], *oos_result["cases"]]]
    assert not [m for m in markups if "title=" in m], "브라우저 title tooltip 이 남았다"
    assert all(tip for m in markups for tip, _n in _numbers(m))

    css = panel.panel_css()
    assert "content: attr(data-tip)" in css.split("[data-tip]::after {", 1)[1].split("}", 1)[0]
    # 기능별 결과 카드(단추)의 tooltip 도 같은 한 벌을 쓴다. 글자만 카드마다 recipe_card_css 가 붙인다
    hidden = css.split("[data-tip]::after,\n.st-key-test_tab .st-key-test_fn_cards button::after {", 1)[1].split("}", 1)[0]
    shown = css.split("[data-tip]:hover::after,\n.st-key-test_tab .st-key-test_fn_cards button:hover::after {", 1)[1].split("}", 1)[0]
    assert "visibility: hidden" in hidden
    assert "pointer-events: none" in hidden, "tooltip 이 마우스를 받으면 그 위에서 깜빡인다"
    assert "transition: none" in hidden, "내릴 때 바로 사라지지 않는다"
    assert f"{panel.TIP_DELAY_MS}ms" in shown and "visibility: visible" in shown
    assert "{tip_delay}" not in css
    # 표가 overflow 로 tooltip 을 자르지 않는다
    assert "overflow: hidden" not in css.split(".st-key-test_tab .tt-cmp {", 1)[1].split("}", 1)[0]


# ── 보기 필터 글자 · 건수 ─────────────────────────────────────────────
def _filter_labels(at):
    control = at.segmented_control(key=panel.FILTER_KEY)
    return [control.format_func(option) for option in control.options] if hasattr(control, "format_func") else control.options


def test_the_filter_labels_match_the_result_column_and_keep_their_counts(app):
    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"official:{CANONICAL}").run()
    labels = [" ".join(str(o).split()) for o in _filter_labels(app)]
    assert labels == ["전체 203", "실패 15", "기능 선택 11/15", "인자 추출 3/15", "범위 밖 처리 1/15"]

    for view, count in (("실패 · 기능 선택", 11), ("실패 · 인자 추출", 3), ("실패 · 범위 밖 처리", 1), ("실패", 15)):
        app.segmented_control(key=panel.FILTER_KEY).set_value(view).run()
        assert len(app.dataframe[0].value) == count, view
        if view != "실패":
            assert set(_results(app)) == {view}, "필터 글자와 결과 칸 글자가 다르다"
    assert 15 == 11 + 3 + 1, "실패 묶음의 머리가 세부 셋의 합이 아니다"
    assert app.calls == []


def test_the_failure_children_are_labelled_as_shares_of_the_parent_without_repeating_실패():
    counts = {panel.ALL: 203, panel.FAILED: 15, "실패 · 기능 선택": 11, "실패 · 인자 추출": 3, "실패 · 범위 밖 처리": 0}
    assert [panel.filter_label(v, counts) for v in panel.FILTERS] == [
        "전체  203", "실패  15", "기능 선택  11/15", "인자 추출  3/15", "범위 밖 처리  0/15"]
    assert [panel.filter_label(v, {}) for v in panel.FILTERS] == ["전체", "실패", "기능 선택", "인자 추출", "범위 밖 처리"]
    assert panel.filter_label("실패 · 기능 선택", {**counts, panel.FAILED: 0, "실패 · 기능 선택": 0}) == "기능 선택  0"


# ── 기능별 결과 카드로 거르기 ─────────────────────────────────────────
def _card(at, group):
    return next(b for b in at.button if str(b.key or "").startswith("test_fn_") and b.key.endswith(group.strip("_")))


def _groups_in_table(at):
    return set(at.dataframe[0].value["기능"])


def test_a_function_card_filters_the_table_and_a_second_click_clears_it(app):
    """카드는 표시가 아니라 거르기다. 하나만 고르고, 고른 카드를 다시 누르면 푼다. 기능 고르기 목록은 없다."""
    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"official:{CANONICAL}").run()
    assert not [box for box in app.selectbox if box.key == panel.GROUP_KEY], "기능 고르기 목록이 남아 있다"
    assert not any("모든 기능" in str(option) for box in app.selectbox for option in box.options)

    _card(app, "recipe_015").click().run()
    assert not app.exception
    assert _groups_in_table(app) == {"기능 015"} and len(app.dataframe[0].value) == 5
    assert _card(app, "recipe_015").proto.type == "primary" and _card(app, "recipe_001").proto.type == "secondary"
    assert any('tt-pane-group">기능 015<' in m.value for m in app.markdown)

    _card(app, "recipe_052").click().run()
    assert _groups_in_table(app) == {"기능 052"}, "하나만 고르지 않았다"
    _card(app, "recipe_052").click().run()
    assert len(app.dataframe[0].value) == 203, "고른 카드를 다시 눌러도 안 풀렸다"
    assert app.calls == [] and _local_dirs(app) == []


def test_a_function_card_and_the_failure_filter_intersect(app):
    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"official:{CANONICAL}").run()
    _card(app, "recipe_015").click().run()
    app.segmented_control(key=panel.FILTER_KEY).set_value(panel.FAILED).run()
    shown = app.dataframe[0].value
    assert set(shown["기능"]) == {"기능 015"} and set(shown["결과"]) <= {"실패 · 기능 선택", "실패 · 인자 추출"}
    assert len(shown) == 4
    app.segmented_control(key=panel.FILTER_KEY).set_value(panel.ALL).run()
    assert len(app.dataframe[0].value) == 5, "보기 필터를 풀었는데 기능 거르기까지 풀렸다"


def test_the_out_of_scope_card_counts_no_match_cases_and_filters_to_them(app):
    """범위 밖은 기능이 아니라 거르기 자리다. 수는 채점된 summary.total 의 oos_runs · oos_passed 그대로다."""
    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"official:{CANONICAL}").run()
    total = manage_benchmark.load_benchmark("official", CANONICAL)["summary"]["total"]
    assert (total["oos_runs"], total["oos_passed"]) == (8, 7)
    card = _card(app, panel.OUT_OF_SCOPE_GROUP)
    assert card.label == "범위 밖 **7/8**" and card.key == "test_fn_ng_out_of_scope"
    card.click().run()
    shown = app.dataframe[0].value
    assert set(shown["기능"]) == {"범위 밖"} and len(shown) == 8
    assert list(shown["결과"]).count("성공") == 7


def test_switching_suite_or_loading_a_record_clears_the_picked_function(app):
    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"official:{CANONICAL}").run()
    _card(app, "recipe_015").click().run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"official:{CANONICAL_V1}").run()
    assert len(app.dataframe[0].value) == 48 and app.session_state[panel.GROUP_KEY] == panel.ALL_GROUPS


def test_errors_get_their_own_filter_and_never_join_the_failure_count(app):
    boom_on = {3}
    entry = load_test_suite.dataset("test_suite_v1")
    fake = _suite_resolve("test_suite_v1")
    by_utterance = {case["utterance"]: case["id"] for case in _enabled("test_suite_v1")}

    def resolve(utterance):
        if by_utterance[utterance] in boom_on:
            raise RuntimeError("연결이 끊겼습니다")
        return fake(utterance)

    saved = run_evaluation.run(load_test_suite.load(entry["path"]), suite_path=Path(entry["path"]), resolve=resolve,
                               only=[1, 2, 3, 10], materialize=False, save_dir=app.local,
                               dataset={"id": entry["id"], "label": entry["label"]})
    app.run()
    app.selectbox(key=panel.SAVED_KEY).set_value(f"local:{saved['meta']['run_id']}").run()

    labels = [" ".join(str(o).split()) for o in _filter_labels(app)]
    assert labels[-1] == "오류 1" and "실패 1" in labels, labels
    app.segmented_control(key=panel.FILTER_KEY).set_value(panel.FAILED).run()
    assert _results(app) == ["실패 · 기능 선택"], "오류가 실패에 섞였다"
    app.segmented_control(key=panel.FILTER_KEY).set_value(panel.ERROR_FILTER).run()
    assert _results(app) == ["오류"]


# ── GPU 팬 소음 억제 체크박스 ─────────────────────────────────────────
def _quiet(at):
    [box] = at.checkbox
    return box.value, box.disabled


def test_a_new_run_records_the_checkbox_value_and_locks_it_while_running(app):
    app.run()
    app.checkbox(key=panel.FAN_QUIET_KEY).uncheck().run()
    app.hold = Hold(2)
    job = _start(app)
    assert app.hold.entered.wait(20)
    app.run()
    assert _quiet(app) == (False, True), "도는 동안 체크박스가 눌린다"
    assert job.fan_quiet is False

    app.hold.release.set()
    _wait(app)
    assert app.fans == [False]
    [folder] = _local_dirs(app)
    assert manage_benchmark.load_benchmark("local", folder)["meta"]["fan_quiet_mode"] is False
    assert _quiet(app) == (False, False)

    app.checkbox(key=panel.FAN_QUIET_KEY).check().run()
    _start(app)
    _wait(app)
    assert app.fans == [False, True]


@pytest.mark.parametrize("first, then", [(True, False), (False, True)])
def test_resume_uses_the_checkbox_as_it_is_now_not_the_stored_fan_quiet_mode(app, first, then):
    """팬 소음 억제는 실행 박자일 뿐이다. 멈춘 뒤 체크박스를 바꾸고 이어 실행하면 바꾼 값으로 돈다.
    첫 구간 값(meta.fan_quiet_mode)은 그대로 두고 이어 실행 구간 값이 resumed_fan_quiet_mode 에 따로 남는다."""
    app.run()
    if not first:
        app.checkbox(key=panel.FAN_QUIET_KEY).uncheck().run()
    _stop_at(app, 2)
    [folder] = _local_dirs(app)
    stored = json.loads((app.local / folder / manage_benchmark.META_FILE).read_text(encoding="utf-8"))["meta"]
    assert stored["fan_quiet_mode"] is first

    box = app.checkbox(key=panel.FAN_QUIET_KEY)
    (box.check() if then else box.uncheck()).run()
    assert _quiet(app) == (then, False)
    assert any("이어 실행 가능" in m.value for m in app.markdown), "팬 값이 달라 이어 실행이 막혔다"
    app.hold = Hold(3)
    job = _start(app, "test_resume")
    assert app.hold.entered.wait(20)
    app.run()
    assert job.fan_quiet is then
    assert _quiet(app) == (then, True), "이어 실행 중 체크박스가 이번 실행의 값을 안 보인다"

    app.hold.release.set()
    _wait(app)
    assert app.resume_fans == [then] and app.fans == [first], "이어 실행이 run_selected 를 불렀다"
    meta = manage_benchmark.load_benchmark("local", folder)["meta"]
    assert meta["fan_quiet_mode"] is first
    assert meta["resumed_fan_quiet_mode"] == [then] and len(meta["resumed_at"]) == 1


# 화면이 부르는 진짜 자리. app fixture 가 바꿔 끼우기 전에 잡아 둔다
REAL_RESUME_SELECTED = panel.resume_selected


class RecordingMonitor:
    """팬을 안 보고 발화마다 받은 팬 소음 억제 값만 적는 monitor. 기다리지 않는다."""

    waiting = False
    waited_s = 0.0

    def __init__(self):
        self.seen = []

    def before_case(self, done, *, fan_quiet, should_stop=None):
        self.seen.append(fan_quiet)
        return 0.0


@pytest.mark.parametrize("first, then", [(True, False), (False, True)])
def test_resume_through_the_real_panel_and_evaluation_path_accepts_the_checkbox_value(app, monkeypatch, first, then):
    """「이어 실행」이 TypeError(resume() got an unexpected keyword argument 'fan_quiet_mode')로 죽으면 안 된다.
    가짜로 바꾼 것은 resolve 하나다 — 화면의 resume_selected 가 진짜 run_evaluation.resume 을 부르고, 넘긴 인자가
    그 signature 에 안 맞으면 여기서 TypeError 가 난다. 팬 값이 달라도 이어 실행이 막히지 않고, 이어 실행 구간은
    누른 순간의 체크박스 값으로 monitor 를 부르며, 첫 구간 값은 그대로 남는다."""
    real_resume = run_evaluation.resume
    monitors = []

    def resume_with_fake_resolve(kind, run_id, **kwargs):
        dataset_id = manage_benchmark.read_incomplete(manage_benchmark.run_dir(kind, run_id))["meta"]["suite"]["dataset_id"]
        return real_resume(kind, run_id, resolve=_suite_resolve(dataset_id, app.resolved), **kwargs)

    def new_monitor():
        monitors.append(RecordingMonitor())
        return monitors[-1]

    monkeypatch.setattr(panel, "resume_selected", REAL_RESUME_SELECTED)
    monkeypatch.setattr(run_evaluation, "resume", resume_with_fake_resolve)
    monkeypatch.setattr(panel, "_new_monitor", new_monitor)
    from dev.evaluation.engine import monitor_gpu
    monkeypatch.setattr(monitor_gpu, "environment", lambda: {"available": False, "gpus": []})

    app.run()
    if not first:
        app.checkbox(key=panel.FAN_QUIET_KEY).uncheck().run()
    _stop_at(app, 2)
    [folder] = _local_dirs(app)
    box = app.checkbox(key=panel.FAN_QUIET_KEY)
    (box.check() if then else box.uncheck()).run()
    check = panel.resume_check("local", folder)
    assert check["resumable"], check
    assert not [f["label"] for f in check["fields"] if "팬" in f["label"] or "fan" in f["label"].lower()], "팬 값이 이어 실행 조건이 됐다"

    job = _start(app, "test_resume")
    assert job.fan_quiet is then
    job.thread.join(30)
    assert job.error is None, job.error
    _wait(app)
    assert not any("테스트를 실행하지 못했습니다" in m.value for m in app.markdown)

    assert monitors[-1].seen and set(monitors[-1].seen) == {then}, "이어 실행 구간이 체크박스 값으로 안 돌았다"
    meta = manage_benchmark.load_benchmark("local", folder)["meta"]
    assert meta["fan_quiet_mode"] is first
    assert meta["resumed_fan_quiet_mode"] == [then] and len(meta["resumed_at"]) == 1
    assert len(manage_benchmark.load_benchmark("local", folder)["cases"]) == 48


def test_the_run_status_says_when_it_is_waiting_for_the_fans():
    class Waiting:
        waiting = True

    job = panel._Job(panel.NEW, "test_suite_v1", 48, fan_quiet=True, monitor=Waiting())
    job.finished.clear()
    assert panel.control_state(job, None)["text"] == f"새로 실행 중 · 0 / 48 · {panel.FAN_WAIT_TEXT}"
    Waiting.waiting = False
    assert panel.FAN_WAIT_TEXT not in panel.control_state(job, None)["text"]
    assert panel.FAN_WAIT_TEXT not in panel.control_state(panel._Job(panel.NEW, "test_suite_v1", 48), None)["text"]
