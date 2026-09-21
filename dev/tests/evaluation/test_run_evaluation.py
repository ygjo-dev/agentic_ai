"""대상 : dev/evaluation/run_evaluation.py 와 engine/ — 벤치마크 한 번의 흐름 · 채점 · 저장 · GPU 박자

서버 · LLM · Gateway 를 안 부른다. Resolve 는 전부 가짜 함수로 바꿔 끼운다.
채점 규칙이 check_resolve 와 어긋나거나, 쉬는 것이 재는 값에 섞이거나, 저장한 기록이
다시 읽을 때 달라지면 여기서 빨간불.
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import check_resolve  # noqa: E402

from dev.evaluation import run_evaluation  # noqa: E402
from dev.evaluation.engine import (  # noqa: E402
    load_test_suite,
    manage_benchmark,
    monitor_gpu,
    monitor_metadata,
    score,
)


def _selfcheck_suite(suite: dict, anchor: bool) -> None:
    """가짜 resolve 셋으로 정답표 한 벌을 끝까지 돌려 판정 · 합계를 맞댐. 틀리면 죽음.

    규칙  기대 recipe 와 기대 값(범위 밖이면 받아들이는 status)을 그대로 돌려주는 것 · 틀린 recipe 와
          틀린 값을 돌려주는 것 · 터지는 것
          이름 있는 값 판정이 check_resolve._spoken_value_verdict 와 발화마다 같은지 맞댐 (FULL48)
          지표 넷이 줄에서 다시 센 값과 같은지 봄. materialize 는 끔. 결과가 json 한 벌로 써지는지 봄
    """
    by_id = {case["id"]: case for case in suite["cases"]}
    by_utterance = {case["utterance"]: case for case in suite["cases"]}

    def echo(utterance):
        case = by_utterance[utterance]
        if not load_test_suite.in_scope(case):
            status = next(name for name in case["expected"]["outcomes"] if name != "MISSING_ARGUMENT")
            picked = ["recipe_001", "recipe_002"] if status == "CLARIFY" else []
            return {"status": status, "recipe_id": None, "candidate_recipe_ids": picked, "argument": None,
                    **{name: None for name in check_resolve.SPOKEN_VALUE_NAMES[1:]}}
        rid = case["expected"]["recipe_ids"][0]
        return {"status": "SELECT", "recipe_id": rid, "candidate_recipe_ids": [rid], "argument": "오송역",
                **{name: None for name in check_resolve.SPOKEN_VALUE_NAMES[1:]}, **(case["expected"].get("spoken") or {})}

    def wrong(_utterance):
        return {"status": "SELECT", "recipe_id": "recipe_000", "candidate_recipe_ids": [], "argument": None,
                "travel_mode": "틀림", "minutes": [999], "admin_level": "틀림"}

    def boom(_utterance):
        raise RuntimeError("터짐")

    cases = (
        (echo, "HIT", True, None, None),
        (wrong, "MISS", False, score.STAGE_FUNCTION, score.STAGE_SCOPE),
        (boom, "UNATTACHED", False, score.STAGE_ERROR, score.STAGE_ERROR),
    )
    for resolve, grade, spoken, stage, outside_stage in cases:
        result = run_evaluation.run(suite, resolve=resolve, resolver=resolve.__name__, materialize=False)
        json.dumps(result, ensure_ascii=False)
        rows = result["cases"]
        inside = [row for row in rows if row["scope"] == score.SCOPE_IN]
        outside = [row for row in rows if row["scope"] == score.SCOPE_OUT]
        assert len(rows) == sum(1 for case in suite["cases"] if case["enabled"]), resolve.__name__
        assert {row["grade"] for row in inside} == {grade}, (resolve.__name__, Counter(row["grade"] for row in inside))
        assert {row["grade"] for row in outside} <= {None}, resolve.__name__
        assert {(row["passed"], row["failure_stage"]) for row in inside} == {(stage is None, stage)}, resolve.__name__
        assert {(row["passed"], row["failure_stage"]) for row in outside} <= {(outside_stage is None, outside_stage)}, resolve.__name__
        total = result["summary"]["total"]
        assert sum(total[name] for name in score.GRADES.values()) == total["in_scope_runs"] == len(inside)
        assert total["passed"] + sum(total["failure_stages"].values()) == total["runs"] == len(rows)
        board = result["summary"]["metrics"]
        assert board["selection"] == {"correct": sum(row["grade"] == "HIT" for row in inside), "total": len(inside)}
        assert board["joint"] == {"correct": sum(row["passed"] for row in inside), "total": len(inside)}
        assert board["oos"] == {"correct": sum(row["passed"] for row in outside), "total": len(outside)}
        fields = [field["correct"] for row in inside for field in row["spoken_fields"]]
        assert board["semantic_fields"] == {"correct": sum(fields), "total": len(fields)}
        for row in inside:
            if by_id[row["case_id"]]["expected"].get("spoken"):
                assert row["spoken_correct"] is spoken, (resolve.__name__, row["case_id"])
            if not anchor or row["actual"] is None:
                continue
            said = check_resolve._spoken_values_of({name: row["actual"]["spoken"][name] for name in check_resolve.SPOKEN_VALUE_NAMES})
            verdict = check_resolve._spoken_value_verdict(row["case_id"], Counter({said: 1}))
            if verdict is not None:
                assert (verdict[0] == 1) is row["spoken_correct"], (resolve.__name__, row["case_id"], verdict)


def _selfcheck_all_suites() -> None:
    """등록된 정답표 전부를 _selfcheck_suite 로 돌림."""
    for entry in load_test_suite.datasets():
        suite = load_test_suite.load(entry["path"])
        _selfcheck_suite(suite, entry["path"] == load_test_suite.SUITE_PATH)


def test_the_evaluation_runner_runs_the_whole_suite_to_the_end_and_grades_like_check_resolve():
    """run_evaluation 은 check_resolve 의 판정을 그대로 부른다. 정답표 전체를 가짜 resolve 로 돌려 판정이 어긋나면 여기서 빨간불.

    정답표가 YAML 로 바뀌어도 계기판과 run_evaluation 이 같은 파일 · 같은 판정을 쓰는지를 커밋마다 본다.
    """
    _selfcheck_all_suites()


# ── 오래 도는 회귀평가의 쉼표 ────────────────────────────────────────
#
# 48 × 3 을 쉬지 않고 돌리면 GPU 넷이 계속 물려 있어 팬이 시끄럽다. 쉬는 것은
# **부르는 사이의 간격일 뿐**이라 재는 값에 섞이면 안 된다 — 아래 셋이 그것을
# 못 박는다. 진짜로 기다리지 않는다. time.sleep 을 바꿔 끼워 호출만 센다.
def _fake_suite():
    """발화 다섯 · 묶음 하나짜리 정답표. 진짜 정답표를 안 쓴다 — 여기서 재는 것은
    판정이 아니라 부르는 사이의 간격이고, 발화가 늘면 기대 횟수가 흔들린다."""
    return {
        "version": 1,
        "groups": [{"id": name, "label": f"묶음{name}"} for name in load_test_suite.GROUP_IDS],
        "cases": [
            {
                "id": number,
                "group": load_test_suite.GROUP_IDS[0],
                "utterance": f"발화 {number}",
                "enabled": True,
                "expected": {"recipe_ids": ["recipe_002"], "spoken": None},
            }
            for number in range(1, 6)
        ],
    }


def _counted(monkeypatch, **kwargs):
    """가짜 정답표를 가짜 resolve 로 돌리고 (resolve 횟수, 잔 시간들) 을 돌려줌."""
    import time
    from types import SimpleNamespace

    # run_evaluation 의 time 만 바꿔 끼운다. time 모듈 자체를 바꾸면 subprocess(git rev-parse)가 기다리며
    # 부르는 sleep 까지 여기 적혀 쉰 횟수가 흔들린다.
    slept = []
    monkeypatch.setattr(run_evaluation, "time", SimpleNamespace(sleep=slept.append, perf_counter=time.perf_counter))

    asked = []

    def resolve(utterance):
        asked.append(utterance)
        return {"status": "SELECT", "recipe_id": "recipe_002", "candidate_recipe_ids": ["recipe_002"],
                **{name: None for name in check_resolve.SPOKEN_VALUE_NAMES}}

    result = run_evaluation.run(_fake_suite(), resolve=resolve, materialize=False, **kwargs)
    return asked, slept, result


def test_without_a_cooldown_the_runner_never_sleeps(monkeypatch):
    """기본값은 꺼짐. 옵션을 안 적은 평가는 지금까지와 같은 것을 같은 방식으로 재야 한다."""
    asked, slept, result = _counted(monkeypatch)

    assert len(asked) == 5
    assert slept == [], "안 켰는데 쉬었다"
    assert result["summary"]["total"]["HIT"] == 5


def test_a_cooldown_rests_between_bursts_and_not_after_the_last_call(monkeypatch):
    """다섯 번을 두 번마다 쉬면 쉬는 것은 정확히 두 번이다.

    마지막 요청 뒤에는 안 쉰다. 뒤에서 쉬면 아무도 기다릴 이유가 없는 시간이
    회차마다 붙는다 — 144회짜리 평가에서 그것만 2분이다.
    """
    asked, slept, _ = _counted(monkeypatch, cooldown_every=2, cooldown_seconds=5.0)

    assert len(asked) == 5, "쉬는 것이 부르는 횟수를 바꿨다"
    assert slept == [5.0, 5.0], slept

    # 딱 떨어질 때도 뒤에 안 붙는다. 다섯 번을 다섯마다 쉬면 쉴 자리가 없다.
    _, 딱맞음, _ = _counted(monkeypatch, cooldown_every=5, cooldown_seconds=5.0)
    assert 딱맞음 == []


def test_the_cooldown_seconds_reach_sleep_unchanged(monkeypatch):
    """적은 값이 그대로 간다. 여기서 값을 만지면 사람이 적은 것과 실제가 갈린다."""
    _, slept, _ = _counted(monkeypatch, cooldown_every=1, cooldown_seconds=0.25)

    assert slept == [0.25, 0.25, 0.25, 0.25], slept

    # 0 초도 받는다. 「켜 두되 지금은 안 기다린다」를 적을 자리다.
    _, 영초, _ = _counted(monkeypatch, cooldown_every=2, cooldown_seconds=0)
    assert 영초 == [0, 0]


def test_a_negative_cooldown_is_refused_before_anything_is_measured(monkeypatch):
    """음수는 거부한다. 조용히 0 으로 읽으면 켠 줄 알고 시끄러운 채로 두 시간을 돌린다."""
    import pytest


    for kwargs in ({"cooldown_every": -1}, {"cooldown_seconds": -0.5, "cooldown_every": 2}):
        with pytest.raises(ValueError):
            _counted(monkeypatch, **kwargs)

    # 창구도 같이 막는다. 정답표를 읽기 전에 2 로 끝나야 한다.
    for argv in (["run_evaluation", "--cooldown-every", "-1"], ["run_evaluation", "--cooldown-seconds", "-1"]):
        monkeypatch.setattr(run_evaluation.sys, "argv", argv)
        assert run_evaluation.main() == 2, argv


# ── 발화 판정 ────────────────────────────────────────────────────────
#
# 화면 테스트 탭은 run_evaluation 결과의 passed · failure_stage · spoken_fields 를 읽기만 한다.
# 판정 규칙이 여기 하나뿐이라 여기서 못 박는다. 진짜 정답표를 안 쓴다 — 규칙마다
# 한 줄씩 지어낸 발화로 본다.
def _verdict_suite():
    """규칙 하나에 발화 하나. 묶음은 하나."""
    def case(number, recipe_id, spoken):
        expected = {"recipe_ids": [recipe_id]}
        if spoken is not None:
            expected["spoken"] = spoken
        return {"id": number, "group": load_test_suite.GROUP_IDS[0], "utterance": f"발화 {number}",
                "enabled": True, "expected": expected}

    return {
        "version": 1,
        "groups": [{"id": name, "label": f"묶음{name}"} for name in load_test_suite.GROUP_IDS],
        "cases": [
            case(1, "recipe_010", {"argument": "철도"}),
            case(2, "recipe_012", {"admin_level": None}),
            case(3, "recipe_012", {"admin_level": None}),
            case(4, "recipe_010", {"argument": "철도"}),
            case(5, "recipe_061", {"future_field": "값"}),
            case(6, "recipe_001", None),
            case(7, "recipe_001", None),
        ],
    }


# 발화 번호 -> 가짜 /resolve 응답. 7 은 터진다.
_VERDICT_RESPONSES = {
    1: {"recipe_id": "recipe_010", "argument": "철도", "travel_mode": "대중교통", "minutes": None, "admin_level": "시군구"},
    2: {"recipe_id": "recipe_012", "argument": "시군구", "admin_level": None},
    3: {"recipe_id": "recipe_012", "argument": None, "admin_level": "시군구"},
    4: {"recipe_id": "recipe_045", "argument": "틀림"},
    5: {"recipe_id": "recipe_061", "argument": "오송역", "future_field": "값", "another_field": [10, 20]},
    6: {"recipe_id": "recipe_001", "argument": "오송역"},
}


def _verdict_resolve(utterance):
    """_VERDICT_RESPONSES 를 /resolve 응답 모양으로. 없는 번호는 터짐."""
    number = int(utterance.split()[-1])
    if number not in _VERDICT_RESPONSES:
        raise RuntimeError("터짐")
    response = _VERDICT_RESPONSES[number]
    return {"reason": "까닭", "status": "SELECT", "candidate_recipe_ids": [response["recipe_id"]],
            "paths": {}, **response}


def _verdict_rows(materialize=False):
    """_verdict_suite 를 가짜 resolve 로 돌린 결과 줄과 결과 한 벌. ({번호: 줄}, 결과)."""
    result = run_evaluation.run(_verdict_suite(), resolve=_verdict_resolve, materialize=materialize)
    return {row["case_id"]: row for row in result["cases"]}, result


def test_only_the_values_written_in_the_answer_sheet_are_graded():
    """정답표에 argument 만 적었으면 travel_mode · admin_level 이 무엇이어도 안 본다."""
    rows, _ = _verdict_rows()

    assert [field["name"] for field in rows[1]["spoken_fields"]] == ["argument"]
    assert (rows[1]["passed"], rows[1]["failure_stage"]) == (True, None)


def test_a_null_written_in_the_answer_sheet_is_graded_as_null():
    """key 가 있고 값이 null 이면 null 이 정답이다. 값을 지어내면 인자 추출 실패다."""
    rows, _ = _verdict_rows()

    assert rows[2]["spoken_fields"] == [{"name": "admin_level", "expected": None, "actual": None, "correct": True}]
    assert rows[2]["passed"] is True
    assert (rows[3]["passed"], rows[3]["failure_stage"]) == (False, "input")


def test_a_wrong_function_is_a_function_failure_even_when_values_are_also_wrong():
    """기능과 값이 함께 틀리면 기능 선택 실패로 센다. 고르기가 먼저다."""
    rows, _ = _verdict_rows()

    assert rows[4]["spoken_correct"] is False
    assert (rows[4]["passed"], rows[4]["failure_stage"]) == (False, "function")


def test_a_value_name_the_runner_does_not_know_is_graded_and_kept():
    """새 인자가 생겨도 run_evaluation 을 안 고친다. 정답표에 적으면 채점하고, 모델이 내면 결과에 남는다."""
    rows, _ = _verdict_rows()

    assert rows[5]["spoken_fields"] == [{"name": "future_field", "expected": "값", "actual": "값", "correct": True}]
    assert rows[5]["passed"] is True
    assert rows[5]["actual"]["spoken"] == {"argument": "오송역", "future_field": "값", "another_field": [10, 20]}


def test_the_selection_keys_are_not_reported_as_values():
    """reason · status · recipe_id · 후보 · paths 는 고르기 칸이라 인자 목록에 안 든다."""
    rows, _ = _verdict_rows()

    assert set(rows[6]["actual"]["spoken"]) == {"argument"}


def test_an_error_is_its_own_failure_stage_and_the_summary_adds_up():
    """오류는 모델 출력이 없는 실패다. 성공과 실패 단계 셋을 더하면 시행 횟수다."""
    rows, result = _verdict_rows()

    assert (rows[7]["passed"], rows[7]["failure_stage"]) == (False, "error")
    total = result["summary"]["total"]
    assert total["passed"] == 4
    assert total["failure_stages"] == {"function": 1, "input": 1, "scope": 0, "error": 1}


def test_the_utterance_verdict_does_not_read_the_materialize_result(monkeypatch):
    """materialize 가 READY 가 아니어도 발화 판정은 그대로다. 배선은 실행 쪽 판정이다."""
    plain, _ = _verdict_rows()
    monkeypatch.setattr(run_evaluation, "materialized", lambda response, context, now: {"status": "UNWIRED", "workflow": None})
    built, _ = _verdict_rows(materialize=True)

    assert {row["materialize"]["status"] for number, row in built.items() if number != 7} == {"UNWIRED"}
    assert {n: (r["passed"], r["failure_stage"]) for n, r in built.items()} == {
        n: (r["passed"], r["failure_stage"]) for n, r in plain.items()
    }


# ── 한 줄이 끝날 때마다 ──────────────────────────────────────────────
#
# 화면은 progress 로 받은 줄을 그대로 쌓아 실행 중에 보인다. 줄이 판정 전이거나,
# 두 번 오거나, 차례가 바뀌면 실행 중 화면과 끝난 화면이 갈린다.
def _without_timing(result):
    """시각 · 걸린 시간을 뺀 결과. 콜백 유무로 달라지면 안 되는 부분. 걸린 시간 분포(latency)도 뺌."""
    return {
        "summary": {key: value for key, value in result["summary"].items() if key != "latency"},
        "cases": [{key: value for key, value in row.items() if key != "timing"} for row in result["cases"]],
    }


def test_progress_gets_each_graded_row_once_in_suite_order_including_errors():

    seen = []
    plain = run_evaluation.run(_verdict_suite(), resolve=_verdict_resolve, materialize=False)
    watched = run_evaluation.run(
        _verdict_suite(), resolve=_verdict_resolve, materialize=False,
        progress=lambda done, total, row: seen.append((done, total, row)),
    )

    assert [(done, total) for done, total, _ in seen] == [(n, 7) for n in range(1, 8)]
    assert [row["case_id"] for _, _, row in seen] == [case["id"] for case in _verdict_suite()["cases"]]
    assert all(row is final for (_, _, row), final in zip(seen, watched["cases"])), "콜백 줄이 결과 줄과 다르다"
    assert all("passed" in row and "failure_stage" in row for _, _, row in seen), "판정 전 줄이 갔다"
    assert seen[-1][2]["failure_stage"] == "error"
    assert _without_timing(watched) == _without_timing(plain)


def test_an_exception_from_progress_stops_the_run_and_reaches_the_caller():
    """삼키면 화면이 죽었는데 평가만 계속 돈다."""
    import pytest


    asked = []

    def resolve(utterance):
        asked.append(utterance)
        return _verdict_resolve(utterance)

    def progress(done, total, row):
        if done == 2:
            raise RuntimeError("화면이 죽음")

    with pytest.raises(RuntimeError, match="화면이 죽음"):
        run_evaluation.run(_verdict_suite(), resolve=resolve, materialize=False, progress=progress)
    assert len(asked) == 2


# ── 테스트 세트 v2 · 범위 밖 · Test Run 저장 ─────────────────────────
#
# 개수를 박지 않는다. 받아들인 recipe 목록과 하한(MIN_UTTERANCES_PER_RECIPE)에서 센다.
def test_the_loader_refuses_out_of_scope_cases_it_cannot_judge(tmp_path):
    """모르는 갈래 · NO_MATCH 가 아닌 결과(되묻기 · 값 부족 · 지어낸 이름) · 기대 recipe 가 붙은 범위 밖 ·
    판 1 의 범위 밖은 읽지 않는다."""
    import pytest
    import yaml


    groups = [{"id": name, "label": name} for name in (*load_test_suite.GROUP_IDS, load_test_suite.OUT_OF_SCOPE)]
    good_inside = {"id": 1, "group": "spoken", "utterance": "부산역 좌표", "enabled": True,
                   "expected": {"recipe_ids": ["recipe_001"]}}

    def outside(expected):
        return {"id": 2, "group": load_test_suite.OUT_OF_SCOPE, "utterance": "날씨", "enabled": True, "expected": expected}

    def write(version, cases, group_list=groups):
        path = tmp_path / f"suite_{len(list(tmp_path.iterdir()))}.yaml"
        path.write_text(yaml.safe_dump({"version": version, "groups": group_list, "cases": cases}, allow_unicode=True),
                        encoding="utf-8")
        return path

    ok = load_test_suite.load(write(2, [good_inside, outside({"category": "unsupported", "outcomes": ["NO_MATCH"]})]))
    assert [load_test_suite.in_scope(case) for case in ok["cases"]] == [True, False]

    for bad in (
        {"category": "weather", "outcomes": ["NO_MATCH"]},
        {"category": "ambiguous", "outcomes": ["CLARIFY"]},
        {"category": "insufficient", "outcomes": ["CLARIFY", "MISSING_ARGUMENT"]},
        {"category": "unsupported", "outcomes": ["NO_MATCH", "CLARIFY"]},
        {"category": "unsupported", "outcomes": ["MISSING_ARGUMENT"]},
        {"category": "unsupported", "outcomes": ["REFUSED"]},
        {"category": "unsupported", "outcomes": []},
        {"category": "unsupported", "outcomes": ["NO_MATCH"], "recipe_ids": ["recipe_001"]},
    ):
        with pytest.raises(load_test_suite.SuiteError):
            load_test_suite.load(write(2, [good_inside, outside(bad)]))
    with pytest.raises(load_test_suite.SuiteError):
        load_test_suite.load(write(1, [good_inside, outside({"category": "unsupported", "outcomes": ["NO_MATCH"]})]))


def _mixed_suite():
    """범위 안 둘 · 범위 밖 셋. 범위 밖은 셋 다 NO_MATCH 만 정답."""
    groups = [{"id": name, "label": f"묶음{name}"} for name in (*load_test_suite.GROUP_IDS, load_test_suite.OUT_OF_SCOPE)]

    def outside(number, category, outcomes):
        return {"id": number, "group": load_test_suite.OUT_OF_SCOPE, "utterance": f"발화 {number}", "enabled": True,
                "expected": {"category": category, "outcomes": outcomes}}

    return {
        "version": 2,
        "name": "mixed",
        "groups": groups,
        "cases": [
            {"id": 1, "group": "spoken", "utterance": "발화 1", "enabled": True,
             "expected": {"recipe_ids": ["recipe_001"], "spoken": {"argument": "부산역"}}},
            {"id": 2, "group": "spoken", "utterance": "발화 2", "enabled": True,
             "expected": {"recipe_ids": ["recipe_001"], "spoken": {"argument": "강릉역"}}},
            outside(3, "unsupported", ["NO_MATCH"]),
            outside(4, "unsupported", ["NO_MATCH"]),
            outside(5, "unsupported", ["NO_MATCH"]),
        ],
    }


# 발화 번호 -> 가짜 /resolve 응답. 범위 밖 셋은 기능을 고름 · 해당 없음 · 되묻기 — 맞는 것은 해당 없음뿐.
_MIXED = {
    1: {"status": "SELECT", "recipe_id": "recipe_001", "candidate_recipe_ids": ["recipe_001"], "argument": "부산역"},
    2: {"status": "SELECT", "recipe_id": "recipe_001", "candidate_recipe_ids": ["recipe_001"], "argument": "강릉"},
    3: {"status": "SELECT", "recipe_id": "recipe_001", "candidate_recipe_ids": ["recipe_001"], "argument": "청주"},
    4: {"status": "NO_MATCH", "recipe_id": None, "candidate_recipe_ids": [], "argument": None},
    5: {"status": "CLARIFY", "recipe_id": None, "candidate_recipe_ids": ["recipe_019", "recipe_026"], "argument": None},
}


def _mixed_resolve(utterance):
    return {"reason": "r", "travel_mode": None, "minutes": None, "admin_level": None, **_MIXED[int(utterance.split()[-1])]}


def test_out_of_scope_cases_are_judged_by_their_outcome_and_counted_apart_from_in_scope_accuracy():
    """범위 밖이 기능 선택 점수에 섞이면 「못 고른 것」과 「안 고르는 게 맞은 것」이 한 값이 된다."""
    result = run_evaluation.run(_mixed_suite(), resolve=_mixed_resolve, context=run_evaluation.context_payload("both"))
    rows = {row["case_id"]: row for row in result["cases"]}

    assert [rows[n]["outcome"] for n in (3, 4, 5)] == ["READY", "NO_MATCH", "CLARIFY"]
    assert [(rows[n]["passed"], rows[n]["failure_stage"]) for n in (3, 4, 5)] == [(False, "scope"), (True, None), (False, "scope")]
    assert all(rows[n]["grade"] is None and rows[n]["recipe_correct"] is None for n in (3, 4, 5))
    assert (rows[2]["passed"], rows[2]["failure_stage"]) == (False, "input")

    board = result["summary"]["metrics"]
    assert board["selection"] == {"correct": 2, "total": 2}
    assert board["semantic_fields"] == {"correct": 1, "total": 2}
    assert board["joint"] == {"correct": 1, "total": 2}
    assert board["oos"] == {"correct": 1, "total": 3}
    assert board["ready"] == {"correct": 2, "total": 2}
    assert result["summary"]["total"]["oos_categories"] == {"unsupported": {"runs": 3, "passed": 1}}
    assert result["summary"]["recipes"] == {"recipe_001": {"runs": 2, "passed": 1, "hit": 2}}


def _isolate(monkeypatch, tmp_path) -> Path:
    """official · local 두 자리를 tmp 아래 빈 폴더로 바꿈. local 자리를 돌려줌."""
    monkeypatch.setattr(manage_benchmark, "OFFICIAL_DIR", tmp_path / "official")
    monkeypatch.setattr(manage_benchmark, "LOCAL_DIR", tmp_path / "local")
    (tmp_path / "official").mkdir()
    return tmp_path / "local"


def test_a_saved_test_run_loads_back_identically_and_its_metrics_recount_the_same(tmp_path, monkeypatch):
    """저장 -> 목록 -> 불러오기가 한 글자도 안 바뀌어야 불러온 기록을 방금 잰 것과 같은 화면으로 그린다."""
    local = _isolate(monkeypatch, tmp_path)
    result = run_evaluation.run(_mixed_suite(), resolve=_mixed_resolve, context=run_evaluation.context_payload("both"),
                        save_dir=local, dataset={"id": "mixed", "label": "섞인 세트"})
    listed = manage_benchmark.list_benchmarks()

    assert [entry["run_id"] for entry in listed] == [result["meta"]["run_id"]]
    assert listed[0]["complete"] and listed[0]["runs"] == 5 and listed[0]["dataset_id"] == "mixed"
    loaded = manage_benchmark.load_benchmark(listed[0]["kind"], listed[0]["run_id"])
    saved = json.loads(json.dumps(result, ensure_ascii=False))
    saved["meta"].pop("saved_to")
    assert loaded == saved
    assert score.summarize(loaded["cases"], tuple(loaded["meta"]["suite"]["group_labels"])) == loaded["summary"]
    # 끝난 기록은 run.json 하나다. 도는 동안의 파일 · 사람이 읽는 요약은 안 남는다
    assert sorted(p.name for p in (local / result["meta"]["run_id"]).iterdir()) == [manage_benchmark.RUN_FILE]


def test_an_interrupted_test_run_keeps_its_finished_cases_and_recounts_them(tmp_path, monkeypatch):
    """도중에 죽어도 끝난 발화 결과는 남아야 원인을 본다. 합계는 남은 줄로 다시 센다."""
    import pytest

    local = _isolate(monkeypatch, tmp_path)

    def progress(done, total, row):
        if done == 3:
            raise RuntimeError("화면이 죽음")

    with pytest.raises(RuntimeError):
        run_evaluation.run(_mixed_suite(), resolve=_mixed_resolve, context=run_evaluation.context_payload("both"),
                   save_dir=local, progress=progress)
    [entry] = manage_benchmark.list_benchmarks()
    assert not entry["complete"] and entry["kind"] == manage_benchmark.LOCAL
    assert sorted(p.name for p in Path(entry["path"]).iterdir()) == [manage_benchmark.CASES_FILE, manage_benchmark.META_FILE]

    loaded = manage_benchmark.load_benchmark(entry["kind"], entry["run_id"])
    assert [row["case_id"] for row in loaded["cases"]] == [1, 2, 3]
    assert loaded["meta"]["stopped"] == manage_benchmark.INCOMPLETE
    assert loaded["summary"]["total"]["runs"] == 3
    assert loaded["summary"]["metrics"]["oos"] == {"correct": 0, "total": 1}


def test_gpu_information_is_optional_and_never_changes_the_verdicts():
    """nvidia-smi 가 없는 기계에서도 같은 판정으로 끝나야 하고, 온도는 결과에 안 남는다."""
    def strip(result):
        return [{k: v for k, v in row.items() if k != "timing"} for row in result["cases"]]

    plain = run_evaluation.run(_mixed_suite(), resolve=_mixed_resolve, context=run_evaluation.context_payload("both"))
    blind = run_evaluation.run(_mixed_suite(), resolve=_mixed_resolve, context=run_evaluation.context_payload("both"),
                       monitor=monitor_gpu.GpuMonitor(gate=True, sampler=lambda: None, sleep=lambda s: None),
                       environment={"available": False, "gpus": []})

    assert strip(plain) == strip(blind)
    assert plain["meta"]["environment"] is None
    assert blind["meta"]["environment"] == {"available": False, "gpus": []}
    assert "gpu" not in plain["meta"] and "gpu" not in blind["meta"]


def _gpu_samples(temps, throttle=None):
    """온도를 차례로 내는 가짜 sampler. 다 쓰면 마지막 값을 되풀이."""
    queue = list(temps)

    def sampler():
        temp = queue.pop(0) if len(queue) > 1 else queue[0]
        return [{"index": 0, "name": "가짜", "util": 0, "temp": temp, "fan": 30, "throttle": throttle}]

    return sampler


def test_the_quiet_gate_pauses_when_hot_but_leaves_no_temperature_in_the_test_run():
    """3건마다 온도를 보고 66°C 이상이면 58°C 까지 식힌다. 그것은 박자일 뿐이라 결과에 온도가 없다."""
    slept = []
    monitor = monitor_gpu.GpuMonitor(gate=True, sampler=_gpu_samples([40, 67, 62, 57, 50]), sleep=slept.append)
    result = run_evaluation.run(_mixed_suite(), resolve=_mixed_resolve, context=run_evaluation.context_payload("both"), monitor=monitor)
    seen = monitor.summary()

    assert result["meta"]["stopped"] is None and len(result["cases"]) == 5
    assert seen["pauses"] == 1 and seen["max_temp"] == 67 and seen["start_temp"] == 40
    assert monitor_gpu.POLICY["sleep_s"] in slept
    assert "gpu" not in result["meta"]
    dumped = json.dumps(result["meta"], ensure_ascii=False)
    assert not [key for key in ("start_temp", "max_temp", "end_temp", "pauses", "thermal_throttle") if key in dumped]


def test_thermal_throttling_stops_the_run_but_keeps_what_was_measured():
    """열 제한을 보면 식히고 멈춘다. 거기까지의 결과와 까닭은 남는다."""
    monitor = monitor_gpu.GpuMonitor(gate=True, sampler=_gpu_samples([40, 50], throttle=True), sleep=lambda s: None)
    result = run_evaluation.run(_mixed_suite(), resolve=_mixed_resolve, context=run_evaluation.context_payload("both"), monitor=monitor)

    assert result["meta"]["stopped"].startswith("StopRun")
    assert len(result["cases"]) == 3
    assert monitor.summary()["thermal_throttle"] is True


# ── 모델 설정 · 실행 환경 · 옛 실행 기록 ─────────────────────────────
_ENVIRONMENT = {"available": True, "gpus": [
    {"index": 0, "name": "가짜 GPU", "memory_total_mib": 97887},
    {"index": 1, "name": "가짜 GPU", "memory_total_mib": 97887},
]}


def test_the_llm_request_settings_are_read_from_the_real_provider_request_not_written_by_the_evaluator(monkeypatch):
    """Temperature 는 provider 가 실제로 싣는 값이어야 한다. 평가 코드가 숫자를 적으면 provider 가 바뀌어도 모른다."""
    from unittest import mock

    from llm_engine.role_config import RESOLVE, get_role_config
    from llm_engine.llm_selector import get_llm_for

    monkeypatch.setenv("VLLM_URL", "http://192.0.2.1:18000")
    monkeypatch.setenv("OLLAMA_URL", "http://192.0.2.1:11434")
    role = get_role_config(RESOLVE)
    settings = monitor_metadata.request_settings(role)

    sent = {}

    def capture(request, *args, **kwargs):
        sent.update(json.loads(request.data.decode("utf-8")))
        raise RuntimeError("안 보냄")

    with mock.patch("urllib.request.urlopen", capture):
        try:
            get_llm_for(role).generate("발화", {"type": "object"})
        except RuntimeError:
            pass
    flat = {**{k: v for k, v in sent.items() if k != "options"}, **(sent.get("options") or {})}

    assert "temperature" in settings
    assert settings["temperature"] == flat["temperature"]
    assert all(settings[key] == flat[key] for key in settings)
    assert not set(settings) & set(monitor_metadata._REQUEST_PAYLOAD_KEYS)


def test_llm_temperature_and_gpu_hardware_are_saved_and_loaded_with_the_test_run(tmp_path, monkeypatch):

    monkeypatch.setenv("VLLM_URL", "http://192.0.2.1:18000")
    monkeypatch.setenv("OLLAMA_URL", "http://192.0.2.1:11434")
    result = run_evaluation.run(_mixed_suite(), resolve=_mixed_resolve, context=run_evaluation.context_payload("both"),
                        save_dir=tmp_path, environment=_ENVIRONMENT)
    loaded = manage_benchmark.read_run_dir(tmp_path / result["meta"]["run_id"])

    assert "temperature" in loaded["meta"]["conditions"]["request"]
    assert loaded["meta"]["conditions"]["request"] == result["meta"]["conditions"]["request"]
    assert loaded["meta"]["environment"] == _ENVIRONMENT
    assert [gpu["name"] for gpu in loaded["meta"]["environment"]["gpus"]] == ["가짜 GPU", "가짜 GPU"]
    assert all(gpu["memory_total_mib"] == 97887 for gpu in loaded["meta"]["environment"]["gpus"])
    assert loaded["cases"][0]["expected"]["reads"] == ["argument"]


def test_an_old_test_run_without_the_new_fields_still_loads(tmp_path, monkeypatch):
    """4f9540d 로 남긴 실행 기록(옛 범위 밖 갈래 · meta.gpu 온도 · 요청 설정 · 환경 · reads 없음)이 그대로 읽혀야 한다.

    옛 기록을 새 정답표로 다시 채점하지 않는다. 그때의 판정이 그대로 나온다.
    """
    result = run_evaluation.run(_mixed_suite(), resolve=_mixed_resolve, context=run_evaluation.context_payload("both"))
    old = json.loads(json.dumps(result, ensure_ascii=False))
    old["meta"].pop("environment")
    old["meta"]["conditions"].pop("request", None)
    old["meta"]["gpu"] = {"available": True, "start_temp": 37, "max_temp": 70, "end_temp": 70, "pauses": 14,
                          "thermal_throttle": False, "log": []}
    for row in old["cases"]:
        row["expected"].pop("reads", None)
    old["cases"][-1]["expected"].update({"category": "ambiguous", "outcomes": ["CLARIFY"]})
    old["cases"][-1].update({"passed": True, "failure_stage": None, "oos_correct": True})
    folder = _isolate(monkeypatch, tmp_path) / old["meta"]["run_id"]
    folder.mkdir(parents=True)
    (folder / manage_benchmark.RUN_FILE).write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    (folder / manage_benchmark.META_FILE).write_text(json.dumps({"meta": old["meta"], "summary": old["summary"]}, ensure_ascii=False),
                                              encoding="utf-8")

    [entry] = manage_benchmark.list_benchmarks()
    loaded = manage_benchmark.load_benchmark(entry["kind"], entry["run_id"])
    assert loaded == old
    assert loaded["cases"][-1]["passed"] is True, "옛 판정을 새 규칙으로 덮어썼다"


# ── 중지 · 중단된 기록 · 이어 실행 ───────────────────────────────────
#
# 화면의 「중지」는 should_stop 으로, 「이어 실행」은 resume 으로 들어온다. 멈춘 기록이 run.json 으로
# 끝난 척하거나, 이어 재면서 끝난 발화를 다시 부르거나, 지금 조건을 몰래 섞으면 두 번 잰 것이 한 기록이 된다.
# 진짜 정답표(FULL48)의 앞 다섯 발화를 가짜 resolve 로 잰다. 이어 재기는 등록된 정답표만 다시 읽는다.
import threading  # noqa: E402

import pytest  # noqa: E402

FIVE = [1, 2, 3, 4, 5]


def _v1_resolve(asked, hold=None):
    """FULL48 발화에 기대 recipe 와 기대 값을 그대로 돌려주는 가짜 resolve. 부른 발화를 asked 에 적음.

    hold 는 {부른 차례: (entered, release)}. 그 차례면 entered 를 켜고 release 를 기다림
    """
    by_utterance = {case["utterance"]: case for case in load_test_suite.load(load_test_suite.SUITE_PATH)["cases"]}

    def resolve(utterance):
        asked.append(utterance)
        if hold and len(asked) in hold:
            entered, release = hold[len(asked)]
            entered.set()
            assert release.wait(20)
        case = by_utterance[utterance]
        rid = case["expected"]["recipe_ids"][0]
        return {"reason": "가짜", "status": "SELECT", "recipe_id": rid, "candidate_recipe_ids": [rid], "paths": {},
                **(case["expected"].get("spoken") or {})}

    return resolve


def _utterances(ids):
    by_id = {case["id"]: case["utterance"] for case in load_test_suite.load(load_test_suite.SUITE_PATH)["cases"]}
    return [by_id[number] for number in ids]


def _run_v1(local, asked, *, only=FIVE, runs=1, should_stop=None, hold=None, materialize=False, context=None):
    return run_evaluation.run(
        load_test_suite.load(load_test_suite.SUITE_PATH), suite_path=load_test_suite.SUITE_PATH,
        resolve=_v1_resolve(asked, hold), only=only, runs=runs, materialize=materialize, context=context,
        context_label="both" if context else None, save_dir=local, should_stop=should_stop,
        dataset={"id": "test_suite_v1", "label": "FULL48 회귀 테스트"},
    )


def _stopped_after(local, count, **kwargs):
    """count 번 부른 뒤 멈춘 local 기록. (결과, 폴더)."""
    asked = []
    result = _run_v1(local, asked, should_stop=lambda: len(asked) >= count, **kwargs)
    return result, Path(result["meta"]["saved_to"])


def _files(folder):
    return sorted(p.name for p in folder.iterdir())


def _snapshot(folder):
    return {p.name: p.read_bytes() for p in folder.iterdir()}


def _lines(folder):
    return [json.loads(line) for line in (folder / manage_benchmark.CASES_FILE).read_text(encoding="utf-8").splitlines()]


def test_a_stop_while_one_resolve_is_in_flight_saves_that_case_and_never_starts_the_next(tmp_path, monkeypatch):
    """37 개가 끝나고 38 번째를 부르는 중에 중지를 누르면 38 번째는 남고 39 번째는 안 불린다. 여기서는 2 와 3."""
    local = _isolate(monkeypatch, tmp_path)
    asked, stop = [], threading.Event()
    entered, release = threading.Event(), threading.Event()
    done = {}
    worker = threading.Thread(target=lambda: done.update(result=_run_v1(
        local, asked, should_stop=stop.is_set, hold={2: (entered, release)})))
    worker.start()
    assert entered.wait(20)
    stop.set()
    release.set()
    worker.join(20)

    assert asked == _utterances([1, 2]), "중지 뒤에 다음 발화를 불렀다"
    result = done["result"]
    folder = Path(result["meta"]["saved_to"])
    assert _files(folder) == [manage_benchmark.CASES_FILE, manage_benchmark.META_FILE], "멈춘 기록에 run.json 이 생겼다"
    assert [row["case_id"] for row in _lines(folder)] == [1, 2]
    meta = json.loads((folder / manage_benchmark.META_FILE).read_text(encoding="utf-8"))["meta"]
    assert meta["stopped"] == run_evaluation.USER_STOP and meta["stopped_at"] and meta["finished_at"] is None
    assert result["meta"]["stopped"] == run_evaluation.USER_STOP and len(result["cases"]) == 2
    [entry] = manage_benchmark.list_benchmarks()
    assert (entry["complete"], entry["done"], entry["planned"]) == (False, 2, 5)


def test_a_stop_requested_after_the_last_case_is_a_completed_run(tmp_path, monkeypatch):
    local = _isolate(monkeypatch, tmp_path)
    asked = []
    result = _run_v1(local, asked, should_stop=lambda: len(asked) >= 5)
    folder = Path(result["meta"]["saved_to"])

    assert len(asked) == 5 and result["meta"]["stopped"] is None
    assert _files(folder) == [manage_benchmark.RUN_FILE]


@pytest.mark.parametrize("error", ["server", "gpu", "interrupt"])
def test_server_down_gpu_stop_and_interrupt_keep_an_incomplete_record_without_run_json(tmp_path, monkeypatch, error):
    """a60f002 까지는 멈춘 길도 Recorder.finish 를 불러 run.json 을 썼다. 부분 기록이 끝난 기록처럼 보였다."""
    local = _isolate(monkeypatch, tmp_path)
    asked = []
    echo = _v1_resolve(asked)

    def resolve(utterance):
        if len(asked) == 2 and error != "gpu":
            raise {"server": run_evaluation.ServerDown("닿지 않음"), "interrupt": KeyboardInterrupt()}[error]
        return echo(utterance)

    class Hot:
        """두 번째 발화 뒤에 열 제한을 본 GPU 조용 정책."""

        def before_run(self):
            pass

        def after_case(self, done, total):
            if done == 2:
                raise monitor_gpu.StopRun("열 제한")

        def after_run(self, called):
            pass

    result = run_evaluation.run(load_test_suite.load(load_test_suite.SUITE_PATH), suite_path=load_test_suite.SUITE_PATH,
                                resolve=resolve, only=FIVE, materialize=False, save_dir=local,
                                monitor=Hot() if error == "gpu" else None,
                                dataset={"id": "test_suite_v1", "label": "FULL48 회귀 테스트"})
    folder = Path(result["meta"]["saved_to"])

    assert _files(folder) == [manage_benchmark.CASES_FILE, manage_benchmark.META_FILE]
    assert len(_lines(folder)) == 2
    loaded = manage_benchmark.load_benchmark("local", folder.name)
    assert loaded["meta"]["stopped"] == result["meta"]["stopped"] != manage_benchmark.INCOMPLETE
    assert loaded["meta"]["finished_at"] is None


def test_resume_runs_only_the_missing_cases_in_the_same_folder_and_ends_as_one_run_json(tmp_path, monkeypatch):
    local = _isolate(monkeypatch, tmp_path)
    first, folder = _stopped_after(local, 2)
    stored = _lines(folder)

    asked = []
    result = run_evaluation.resume("local", folder.name, resolve=_v1_resolve(asked))

    assert asked == _utterances([3, 4, 5]), "끝난 발화를 다시 불렀다"
    assert result["meta"]["run_id"] == first["meta"]["run_id"] == folder.name
    assert sorted(p.name for p in local.iterdir()) == [folder.name], "새 폴더가 생겼다"
    assert _files(folder) == [manage_benchmark.RUN_FILE]
    saved = json.loads((folder / manage_benchmark.RUN_FILE).read_text(encoding="utf-8"))
    assert [row["case_id"] for row in saved["cases"]] == FIVE
    assert saved["cases"][:2] == stored, "전에 잰 줄이 바뀌었다"
    assert saved["meta"]["stopped"] is None and saved["meta"]["finished_at"]
    assert saved["meta"]["started_at"] == first["meta"]["started_at"]
    assert len(saved["meta"]["resumed_at"]) == 1
    assert saved["summary"] == score.summarize(saved["cases"], tuple(saved["meta"]["suite"]["group_labels"]))
    assert manage_benchmark.list_benchmarks()[0]["complete"]


def test_a_resumed_run_can_be_stopped_again_and_resumed_again(tmp_path, monkeypatch):
    """1 · 2 가 끝난 기록을 이어 재다 3 이 끝나고 4 를 부르는 중에 멈추면 4 는 남고 5 는 안 불린다. 다음 이어 실행은 5 만."""
    local = _isolate(monkeypatch, tmp_path)
    _first, folder = _stopped_after(local, 2)

    asked, stop = [], threading.Event()
    entered, release = threading.Event(), threading.Event()
    worker = threading.Thread(target=lambda: run_evaluation.resume(
        "local", folder.name, resolve=_v1_resolve(asked, {2: (entered, release)}), should_stop=stop.is_set))
    worker.start()
    assert entered.wait(20)
    stop.set()
    release.set()
    worker.join(20)

    assert asked == _utterances([3, 4])
    assert _files(folder) == [manage_benchmark.CASES_FILE, manage_benchmark.META_FILE]
    assert [row["case_id"] for row in _lines(folder)] == [1, 2, 3, 4]
    assert run_evaluation.resume_check("local", folder.name)["resumable"]

    again = []
    result = run_evaluation.resume("local", folder.name, resolve=_v1_resolve(again))
    assert again == _utterances([5])
    assert [row["case_id"] for row in result["cases"]] == FIVE
    assert _files(folder) == [manage_benchmark.RUN_FILE]
    assert len(result["meta"]["resumed_at"]) == 2


def test_resume_finds_missing_work_by_case_and_run_not_by_count(tmp_path, monkeypatch):
    """끝난 줄이 앞에서부터가 아니어도 (case_id, run) 로 빈 것만 잰다. runs 가 여럿이어도 겹쳐 재지 않는다."""
    local = _isolate(monkeypatch, tmp_path)
    _first, folder = _stopped_after(local, 5, runs=2)
    kept = [row for row in _lines(folder) if (row["case_id"], row["run"]) in {(1, 1), (1, 2), (2, 2), (3, 1)}]
    manage_benchmark.repair_rows(folder, kept)

    asked = []
    result = run_evaluation.resume("local", folder.name, resolve=_v1_resolve(asked))

    assert asked == _utterances([2, 3, 4, 4, 5, 5])
    assert [(row["case_id"], row["run"]) for row in result["cases"]] == [(n, r) for n in FIVE for r in (1, 2)]
    assert _files(folder) == [manage_benchmark.RUN_FILE]


def test_resume_replays_the_stored_context_and_materialize_moment(tmp_path, monkeypatch):
    """이어 잰 발화가 지금 시각 · 다른 문맥으로 materialize 되면 한 기록 안의 발화가 다른 조건으로 잰 것이 된다."""
    local = _isolate(monkeypatch, tmp_path)
    seen = []
    monkeypatch.setattr(run_evaluation, "materialized",
                        lambda response, context, now: seen.append((context, now)) or {"status": "READY", "workflow": None})
    context = run_evaluation.context_payload("both")
    _first, folder = _stopped_after(local, 2, materialize=True, context=context)
    stored = json.loads((folder / manage_benchmark.META_FILE).read_text(encoding="utf-8"))["meta"]

    run_evaluation.resume("local", folder.name, resolve=_v1_resolve([]))

    assert len(seen) == 5
    assert {json.dumps(ctx, sort_keys=True) for ctx, _now in seen} == {json.dumps(context, sort_keys=True)}
    assert {now.isoformat() for _ctx, now in seen} == {stored["materialize_now"]}


def test_a_torn_last_line_is_dropped_before_resume_appends(tmp_path, monkeypatch):
    local = _isolate(monkeypatch, tmp_path)
    _first, folder = _stopped_after(local, 2)
    with (folder / manage_benchmark.CASES_FILE).open("a", encoding="utf-8") as handle:
        handle.write('{"case_id": 3, "run"')

    asked = []
    result = run_evaluation.resume("local", folder.name, resolve=_v1_resolve(asked))
    assert asked == _utterances([3, 4, 5])
    assert [row["case_id"] for row in result["cases"]] == FIVE


def _edit_meta(folder, edit):
    path = folder / manage_benchmark.META_FILE
    document = json.loads(path.read_text(encoding="utf-8"))
    edit(document["meta"])
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


CHANGES = {
    "Test Suite": lambda meta: meta["suite"].update(sha256="0" * 64),
    "Model": lambda meta: meta["conditions"].update(model="다른-모델"),
    "Prompt": lambda meta: meta["conditions"]["prompt"].update(sha256="1" * 64),
    "Schema": lambda meta: meta["conditions"]["response_schema"].update(sha256="2" * 64),
    "Menu": lambda meta: meta["conditions"]["menu"].update(sha256="3" * 64),
    "Registry": lambda meta: meta["conditions"]["registry"].update(sha256="4" * 64),
    "Request settings": lambda meta: meta["conditions"]["request"].update(temperature=0.7),
    "Evaluation version": lambda meta: meta.update(result_version=2),
}


@pytest.mark.parametrize("label", list(CHANGES))
def test_a_changed_execution_condition_blocks_resume_and_names_the_changed_field(tmp_path, monkeypatch, label):
    local = _isolate(monkeypatch, tmp_path)
    _first, folder = _stopped_after(local, 2)
    _edit_meta(folder, CHANGES[label])
    before = _snapshot(folder)

    check = run_evaluation.resume_check("local", folder.name)
    assert not check["resumable"] and check["reason"] == run_evaluation.RESUME_CHANGED
    assert [field["label"] for field in check["fields"] if not field["same"]] == [label]
    assert (check["done"], check["planned"]) == (2, 5)

    asked = []
    with pytest.raises(run_evaluation.ResumeRefused):
        run_evaluation.resume("local", folder.name, resolve=_v1_resolve(asked))
    assert asked == [] and _snapshot(folder) == before, "막힌 이어 실행이 파일을 건드렸다"


@pytest.mark.parametrize("drop", ["registry", "request", "materialize_now", "selected_case_ids"])
def test_an_old_record_without_the_resume_conditions_loads_but_cannot_be_resumed(tmp_path, monkeypatch, drop):
    local = _isolate(monkeypatch, tmp_path)
    _first, folder = _stopped_after(local, 2, materialize=True, context=run_evaluation.context_payload("both"))
    _edit_meta(folder, {
        "registry": lambda meta: meta["conditions"].pop("registry"),
        "request": lambda meta: meta["conditions"].pop("request"),
        "materialize_now": lambda meta: meta.pop("materialize_now"),
        "selected_case_ids": lambda meta: meta["suite"].pop("selected_case_ids"),
    }[drop])

    check = run_evaluation.resume_check("local", folder.name)
    assert not check["resumable"] and check["reason"] == run_evaluation.RESUME_UNREPRODUCIBLE
    assert check["gaps"]
    assert [row["case_id"] for row in manage_benchmark.load_benchmark("local", folder.name)["cases"]] == [1, 2]


NOT_CONDITIONS = {
    "git_head": lambda meta: meta.update(git_head="deadbee"),
    "started_at": lambda meta: meta.update(started_at="2020-01-01T00:00:00+09:00"),
    "saved_to": lambda meta: meta.update(saved_to="/어딘가/다른/자리"),
    "environment": lambda meta: meta.update(environment={"available": True, "gpus": [{"name": "다른 GPU"}]}),
    "artifact_root": lambda meta: meta.update(artifact_root="/다른/경로/KRRI_Ontology_Registry"),
    "suite_path": lambda meta: meta["suite"].update(path="/옮긴/자리/test_suite_v1.yaml"),
    "cooldown": lambda meta: meta.update(cooldown={"every": 3, "seconds": 5.0}),
    "role_label": lambda meta: meta.update(role="다른 글자"),
}


@pytest.mark.parametrize("name", list(NOT_CONDITIONS))
def test_values_that_do_not_change_what_is_measured_do_not_block_resume(tmp_path, monkeypatch, name):
    """git HEAD · 시각 · 저장 자리 · GPU 가 달라도 남은 발화는 같은 평가 계약으로 잰다."""
    local = _isolate(monkeypatch, tmp_path)
    _first, folder = _stopped_after(local, 2)
    _edit_meta(folder, NOT_CONDITIONS[name])

    check = run_evaluation.resume_check("local", folder.name)
    assert check["resumable"], check


def test_official_and_finished_records_are_not_resume_targets(tmp_path, monkeypatch):
    local = _isolate(monkeypatch, tmp_path)
    finished = _run_v1(local, [])
    assert run_evaluation.resume_check("local", finished["meta"]["run_id"])["reason"] == run_evaluation.RESUME_FINISHED

    _first, folder = _stopped_after(local, 2)
    official = manage_benchmark.OFFICIAL_DIR / folder.name
    folder.rename(official)
    before = _snapshot(official)
    assert run_evaluation.resume_check("official", folder.name)["reason"] == run_evaluation.RESUME_OFFICIAL
    with pytest.raises(run_evaluation.ResumeRefused):
        run_evaluation.resume("official", folder.name, resolve=_v1_resolve([]))
    assert _snapshot(official) == before


def test_resume_refuses_stored_rows_that_are_not_in_the_plan(tmp_path, monkeypatch):
    local = _isolate(monkeypatch, tmp_path)
    _first, folder = _stopped_after(local, 2)
    rows = _lines(folder)
    manage_benchmark.repair_rows(folder, rows + [rows[0]])
    assert run_evaluation.resume_check("local", folder.name)["reason"] == run_evaluation.RESUME_ROWS
