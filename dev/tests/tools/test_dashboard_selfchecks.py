"""대상 : dev/tools/ — 계기판의 자체 검사가 커밋마다 돈다

**재는 도구가 조용히 죽은 것이 세 번이다.** check_argument 나흘
(「스물다섯째」) · check_inputs 하루(「쉰째」→「쉰아홉째」에서 살림) ·
check_resolve (「예순셋째」). 앞의 둘은 배선표가 바뀔 때 도구가 못 따라간
것이고, 셋째는 발화가 늘어(화면 다섯) 묶음이 셋이 됐는데 묶음 이름을 고르는
자리가 두 갈래에 머문 것이다. 셋 다 「판정은 다 해 놓고 표를 찍는 마지막에
죽는다」가 같다.

배선표도 발화 목록도 커밋마다 바뀌는데 계기판은 어쩌다 한 번, 그것도 서버를
띄워야 돈다. 커밋마다 도는 것은 pytest 라 그 자리에 `_selfcheck` 호출을 둔다.

서버 · Gateway · tools.json · 온톨로지를 안 부른다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import check_resolve  # noqa: E402


def test_the_resolve_dashboard_prints_to_the_end_however_the_groups_are_split():
    """스텁이 아니라 진짜 UTTERANCES 를 씀. 묶음 경계가 바뀌면 여기서 빨간불."""
    check_resolve._selfcheck()


def test_the_group_label_chooser_does_not_miss_the_screen_utterances():
    """「예순셋째」의 음성 대조군. 두 갈래로 되돌리면 자체 검사가 죽어야 한다.

    이것이 없으면 `_selfcheck` 가 통과해도 그것이 「이 버그를 잡아서」인지
    「아무것도 안 봐서」인지 못 가른다.
    """
    was = check_resolve._group_label
    try:
        check_resolve._group_label = (
            lambda n: check_resolve.BASELINE_LABEL
            if n <= check_resolve.BASELINE_LAST
            else check_resolve.EXTENSION_LABEL
        )
        try:
            check_resolve._selfcheck()
        except (AssertionError, KeyError):
            pass
        else:
            raise AssertionError("두 갈래로 되돌렸는데 자체 검사가 안 죽었다")
    finally:
        check_resolve._group_label = was


def test_the_evaluation_runner_runs_the_whole_suite_to_the_end_and_grades_like_check_resolve():
    """runner 는 check_resolve 의 판정을 그대로 부른다. 정답표 전체를 가짜 resolve 로 돌려 판정이 어긋나면 여기서 빨간불.

    정답표가 YAML 로 바뀌어도 계기판과 runner 가 같은 파일 · 같은 판정을 쓰는지를 커밋마다 본다.
    """
    from dev.evaluation import runner

    runner._selfcheck()


def test_the_answer_table_grades_only_spoken_fields_the_expected_recipe_actually_reads():
    """정답표가 채점하는 이름 있는 값은 기대 recipe 의 Recipe.execution 이 읽는 칸이어야 한다.

    안 읽는 칸은 맞혀도 틀려도 실행이 안 바뀌어 점수가 실행의 뜻과 어긋난다.
    recipe 의 배선이 바뀌어 칸이 빠지면 정답표도 함께 고쳐야 하므로 커밋마다 본다.
    """
    from dev.evaluation import spoken_audit

    spoken_audit._selfcheck()


# ── 오래 도는 회귀평가의 쉼표 ────────────────────────────────────────
#
# 48 × 3 을 쉬지 않고 돌리면 GPU 넷이 계속 물려 있어 팬이 시끄럽다. 쉬는 것은
# **부르는 사이의 간격일 뿐**이라 재는 값에 섞이면 안 된다 — 아래 셋이 그것을
# 못 박는다. 진짜로 기다리지 않는다. time.sleep 을 바꿔 끼워 호출만 센다.
def _fake_suite():
    """발화 다섯 · 묶음 하나짜리 정답표. 진짜 정답표를 안 쓴다 — 여기서 재는 것은
    판정이 아니라 부르는 사이의 간격이고, 발화가 늘면 기대 횟수가 흔들린다."""
    from dev.evaluation import suite as suite_module

    return {
        "version": 1,
        "groups": [{"id": name, "label": f"묶음{name}"} for name in suite_module.GROUP_IDS],
        "cases": [
            {
                "id": number,
                "group": suite_module.GROUP_IDS[0],
                "utterance": f"발화 {number}",
                "enabled": True,
                "expected": {"recipe_ids": ["recipe_002"], "spoken": None},
            }
            for number in range(1, 6)
        ],
    }


def _counted(monkeypatch, **kwargs):
    """가짜 정답표를 가짜 resolve 로 돌리고 (resolve 횟수, 잔 시간들) 을 돌려줌."""
    from dev.evaluation import runner

    slept = []
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: slept.append(seconds))

    asked = []

    def resolve(utterance):
        asked.append(utterance)
        return {"status": "SELECT", "recipe_id": "recipe_002", "candidate_recipe_ids": ["recipe_002"],
                **{name: None for name in check_resolve.SPOKEN_VALUE_NAMES}}

    result = runner.run(_fake_suite(), resolve=resolve, materialize=False, **kwargs)
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

    from dev.evaluation import runner

    for kwargs in ({"cooldown_every": -1}, {"cooldown_seconds": -0.5, "cooldown_every": 2}):
        with pytest.raises(ValueError):
            _counted(monkeypatch, **kwargs)

    # 창구도 같이 막는다. 정답표를 읽기 전에 2 로 끝나야 한다.
    for argv in (["runner", "--cooldown-every", "-1"], ["runner", "--cooldown-seconds", "-1"]):
        monkeypatch.setattr(runner.sys, "argv", argv)
        assert runner.main() == 2, argv


# ── 발화 판정 ────────────────────────────────────────────────────────
#
# 화면 테스트 탭은 runner 결과의 passed · failure_stage · spoken_fields 를 읽기만 한다.
# 판정 규칙이 여기 하나뿐이라 여기서 못 박는다. 진짜 정답표를 안 쓴다 — 규칙마다
# 한 줄씩 지어낸 발화로 본다.
def _verdict_suite():
    """규칙 하나에 발화 하나. 묶음은 하나."""
    from dev.evaluation import suite as suite_module

    def case(number, recipe_id, spoken):
        expected = {"recipe_ids": [recipe_id]}
        if spoken is not None:
            expected["spoken"] = spoken
        return {"id": number, "group": suite_module.GROUP_IDS[0], "utterance": f"발화 {number}",
                "enabled": True, "expected": expected}

    return {
        "version": 1,
        "groups": [{"id": name, "label": f"묶음{name}"} for name in suite_module.GROUP_IDS],
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
    from dev.evaluation import runner

    result = runner.run(_verdict_suite(), resolve=_verdict_resolve, materialize=materialize)
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
    """새 인자가 생겨도 runner 를 안 고친다. 정답표에 적으면 채점하고, 모델이 내면 결과에 남는다."""
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
    from dev.evaluation import runner

    plain, _ = _verdict_rows()
    monkeypatch.setattr(runner, "materialized", lambda response, context, now: {"status": "UNWIRED", "workflow": None})
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
    from dev.evaluation import runner

    seen = []
    plain = runner.run(_verdict_suite(), resolve=_verdict_resolve, materialize=False)
    watched = runner.run(
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

    from dev.evaluation import runner

    asked = []

    def resolve(utterance):
        asked.append(utterance)
        return _verdict_resolve(utterance)

    def progress(done, total, row):
        if done == 2:
            raise RuntimeError("화면이 죽음")

    with pytest.raises(RuntimeError, match="화면이 죽음"):
        runner.run(_verdict_suite(), resolve=resolve, materialize=False, progress=progress)
    assert len(asked) == 2


# ── 테스트 세트 v2 · 범위 밖 · Test Run 저장 ─────────────────────────
#
# 개수를 박지 않는다. 받아들인 recipe 목록과 하한(MIN_UTTERANCES_PER_RECIPE)에서 센다.
def test_test_suite_v2_gives_every_accepted_recipe_enough_distinct_utterances_and_out_of_scope_means_no_match():
    """v2 는 recipe 마다 다섯 이상이어야 일반화를 잰다고 말할 수 있고, 범위 밖은 NO_MATCH 만 정답이다.

    되묻기(CLARIFY)가 정답인 발화 · 값 부족(MISSING_ARGUMENT)이 정답인 발화가 섞이면
    「기능이 없다」와 「더 물어야 한다」가 한 점수가 된다.
    """
    from collections import Counter

    import paths
    from dev.evaluation import spoken_audit
    from dev.evaluation import suite as suite_module

    v2 = suite_module.load(suite_module.SUITE_V2_PATH)
    accepted = {path.stem for path in paths.RECIPES_DIR.glob("recipe_*.yaml")}
    inside = [case for case in v2["cases"] if suite_module.in_scope(case)]
    per_recipe = Counter(case["expected"]["recipe_ids"][0] for case in inside)

    assert set(per_recipe) == accepted
    assert min(per_recipe.values()) >= spoken_audit.MIN_UTTERANCES_PER_RECIPE
    assert len(inside) >= len(accepted) * spoken_audit.MIN_UTTERANCES_PER_RECIPE
    assert len({case["id"] for case in v2["cases"]}) == len(v2["cases"])
    assert len({case["utterance"] for case in v2["cases"]}) == len(v2["cases"])
    outside = [case for case in v2["cases"] if not suite_module.in_scope(case)]
    assert outside, "범위 밖 발화가 없다"
    assert all(case["expected"]["outcomes"] == ["NO_MATCH"] for case in outside)
    assert not any("CLARIFY" in (case["expected"].get("outcomes") or []) for case in v2["cases"])
    assert not any("MISSING_ARGUMENT" in (case["expected"].get("outcomes") or []) for case in v2["cases"])
    assert len(v2["cases"]) == len(inside) + len(outside)
    assert spoken_audit.integrity(v2, anchor=suite_module.load()) == []


def test_full48_stays_the_frozen_version_1_anchor_next_to_v2():
    """v2 를 붙여도 FULL48 은 판 1 · 범위 안만 · 같은 묶음으로 읽혀야 한다. 옛 기록과 이어 읽는 자다."""
    from dev.evaluation import spoken_audit
    from dev.evaluation import suite as suite_module

    full = suite_module.load()
    assert full["version"] == 1
    assert suite_module.datasets()[0]["path"] == suite_module.SUITE_PATH
    assert all(suite_module.in_scope(case) for case in full["cases"])
    assert tuple(group["id"] for group in full["groups"]) == suite_module.GROUP_IDS
    assert len(suite_module.utterances(full)) == len(full["cases"])
    assert spoken_audit.integrity(full) == []


def test_the_loader_refuses_out_of_scope_cases_it_cannot_judge(tmp_path):
    """모르는 갈래 · NO_MATCH 가 아닌 결과(되묻기 · 값 부족 · 지어낸 이름) · 기대 recipe 가 붙은 범위 밖 ·
    판 1 의 범위 밖은 읽지 않는다."""
    import pytest
    import yaml

    from dev.evaluation import suite as suite_module

    groups = [{"id": name, "label": name} for name in (*suite_module.GROUP_IDS, suite_module.OUT_OF_SCOPE)]
    good_inside = {"id": 1, "group": "spoken", "utterance": "부산역 좌표", "enabled": True,
                   "expected": {"recipe_ids": ["recipe_001"]}}

    def outside(expected):
        return {"id": 2, "group": suite_module.OUT_OF_SCOPE, "utterance": "날씨", "enabled": True, "expected": expected}

    def write(version, cases, group_list=groups):
        path = tmp_path / f"suite_{len(list(tmp_path.iterdir()))}.yaml"
        path.write_text(yaml.safe_dump({"version": version, "groups": group_list, "cases": cases}, allow_unicode=True),
                        encoding="utf-8")
        return path

    ok = suite_module.load(write(2, [good_inside, outside({"category": "unsupported", "outcomes": ["NO_MATCH"]})]))
    assert [suite_module.in_scope(case) for case in ok["cases"]] == [True, False]

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
        with pytest.raises(suite_module.SuiteError):
            suite_module.load(write(2, [good_inside, outside(bad)]))
    with pytest.raises(suite_module.SuiteError):
        suite_module.load(write(1, [good_inside, outside({"category": "unsupported", "outcomes": ["NO_MATCH"]})]))


def _mixed_suite():
    """범위 안 둘 · 범위 밖 셋. 범위 밖은 셋 다 NO_MATCH 만 정답."""
    from dev.evaluation import suite as suite_module

    groups = [{"id": name, "label": f"묶음{name}"} for name in (*suite_module.GROUP_IDS, suite_module.OUT_OF_SCOPE)]

    def outside(number, category, outcomes):
        return {"id": number, "group": suite_module.OUT_OF_SCOPE, "utterance": f"발화 {number}", "enabled": True,
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
    from dev.evaluation import runner

    result = runner.run(_mixed_suite(), resolve=_mixed_resolve, context=runner.context_payload("both"))
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


def test_a_saved_test_run_loads_back_identically_and_its_metrics_recount_the_same(tmp_path):
    """저장 -> 목록 -> 불러오기가 한 글자도 안 바뀌어야 불러온 기록을 방금 잰 것과 같은 화면으로 그린다."""
    import json

    from dev.evaluation import runner, test_runs

    result = runner.run(_mixed_suite(), resolve=_mixed_resolve, context=runner.context_payload("both"),
                        save_dir=tmp_path, dataset={"id": "mixed", "label": "섞인 세트"})
    listed = test_runs.list_runs(tmp_path)

    assert [entry["run_id"] for entry in listed] == [result["meta"]["run_id"]]
    assert listed[0]["complete"] and listed[0]["runs"] == 5 and listed[0]["dataset_id"] == "mixed"
    loaded = test_runs.load_run(listed[0]["run_id"], tmp_path)
    saved = json.loads(json.dumps(result, ensure_ascii=False))
    saved["meta"].pop("saved_to")
    assert loaded == saved
    assert runner.summarize(loaded["cases"], tuple(loaded["meta"]["suite"]["group_labels"])) == loaded["summary"]
    assert (tmp_path / result["meta"]["run_id"] / test_runs.SUMMARY_FILE).read_text(encoding="utf-8").startswith("# Test Run")


def test_an_interrupted_test_run_keeps_its_finished_cases_and_recounts_them(tmp_path):
    """도중에 죽어도 끝난 발화 결과는 남아야 원인을 본다. 합계는 남은 줄로 다시 센다."""
    import pytest

    from dev.evaluation import runner, test_runs

    def progress(done, total, row):
        if done == 3:
            raise RuntimeError("화면이 죽음")

    with pytest.raises(RuntimeError):
        runner.run(_mixed_suite(), resolve=_mixed_resolve, context=runner.context_payload("both"),
                   save_dir=tmp_path, progress=progress)
    [entry] = test_runs.list_runs(tmp_path)
    assert not entry["complete"]

    loaded = test_runs.load_run(entry["path"])
    assert [row["case_id"] for row in loaded["cases"]] == [1, 2, 3]
    assert loaded["meta"]["stopped"] == test_runs.INCOMPLETE
    assert loaded["summary"]["total"]["runs"] == 3
    assert loaded["summary"]["metrics"]["oos"] == {"correct": 0, "total": 1}


def test_gpu_information_is_optional_and_never_changes_the_verdicts():
    """nvidia-smi 가 없는 기계에서도 같은 판정으로 끝나야 하고, 온도는 결과에 안 남는다."""
    from dev.evaluation import gpu, runner

    def strip(result):
        return [{k: v for k, v in row.items() if k != "timing"} for row in result["cases"]]

    plain = runner.run(_mixed_suite(), resolve=_mixed_resolve, context=runner.context_payload("both"))
    blind = runner.run(_mixed_suite(), resolve=_mixed_resolve, context=runner.context_payload("both"),
                       monitor=gpu.GpuMonitor(gate=True, sampler=lambda: None, sleep=lambda s: None),
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
    from dev.evaluation import gpu, runner

    slept = []
    monitor = gpu.GpuMonitor(gate=True, sampler=_gpu_samples([40, 67, 62, 57, 50]), sleep=slept.append)
    result = runner.run(_mixed_suite(), resolve=_mixed_resolve, context=runner.context_payload("both"), monitor=monitor)
    seen = monitor.summary()

    assert result["meta"]["stopped"] is None and len(result["cases"]) == 5
    assert seen["pauses"] == 1 and seen["max_temp"] == 67 and seen["start_temp"] == 40
    assert gpu.POLICY["sleep_s"] in slept
    assert "gpu" not in result["meta"]
    dumped = json.dumps(result["meta"], ensure_ascii=False)
    assert not [key for key in ("start_temp", "max_temp", "end_temp", "pauses", "thermal_throttle") if key in dumped]


def test_thermal_throttling_stops_the_run_but_keeps_what_was_measured():
    """열 제한을 보면 식히고 멈춘다. 거기까지의 결과와 까닭은 남는다."""
    from dev.evaluation import gpu, runner

    monitor = gpu.GpuMonitor(gate=True, sampler=_gpu_samples([40, 50], throttle=True), sleep=lambda s: None)
    result = runner.run(_mixed_suite(), resolve=_mixed_resolve, context=runner.context_payload("both"), monitor=monitor)

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

    from dev.evaluation import runner
    from llm_engine.role_config import RESOLVE, get_role_config
    from llm_engine.llm_selector import get_llm_for

    monkeypatch.setenv("VLLM_URL", "http://192.0.2.1:18000")
    monkeypatch.setenv("OLLAMA_URL", "http://192.0.2.1:11434")
    role = get_role_config(RESOLVE)
    settings = runner.request_settings(role)

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
    assert not set(settings) & set(runner._REQUEST_PAYLOAD_KEYS)


def test_llm_temperature_and_gpu_hardware_are_saved_and_loaded_with_the_test_run(tmp_path, monkeypatch):
    from dev.evaluation import runner, test_runs

    monkeypatch.setenv("VLLM_URL", "http://192.0.2.1:18000")
    monkeypatch.setenv("OLLAMA_URL", "http://192.0.2.1:11434")
    result = runner.run(_mixed_suite(), resolve=_mixed_resolve, context=runner.context_payload("both"),
                        save_dir=tmp_path, environment=_ENVIRONMENT)
    loaded = test_runs.load_run(result["meta"]["run_id"], tmp_path)

    assert "temperature" in loaded["meta"]["conditions"]["request"]
    assert loaded["meta"]["conditions"]["request"] == result["meta"]["conditions"]["request"]
    assert loaded["meta"]["environment"] == _ENVIRONMENT
    assert [gpu["name"] for gpu in loaded["meta"]["environment"]["gpus"]] == ["가짜 GPU", "가짜 GPU"]
    assert all(gpu["memory_total_mib"] == 97887 for gpu in loaded["meta"]["environment"]["gpus"])
    assert loaded["cases"][0]["expected"]["reads"] == ["argument"]


def test_an_old_test_run_without_the_new_fields_still_loads(tmp_path):
    """4f9540d 로 남긴 실행 기록(옛 범위 밖 갈래 · meta.gpu 온도 · 요청 설정 · 환경 · reads 없음)이 그대로 읽혀야 한다.

    옛 기록을 새 정답표로 다시 채점하지 않는다. 그때의 판정이 그대로 나온다.
    """
    from dev.evaluation import runner, test_runs

    result = runner.run(_mixed_suite(), resolve=_mixed_resolve, context=runner.context_payload("both"))
    old = json.loads(json.dumps(result, ensure_ascii=False))
    old["meta"].pop("environment")
    old["meta"]["conditions"].pop("request", None)
    old["meta"]["gpu"] = {"available": True, "start_temp": 37, "max_temp": 70, "end_temp": 70, "pauses": 14,
                          "thermal_throttle": False, "log": []}
    for row in old["cases"]:
        row["expected"].pop("reads", None)
    old["cases"][-1]["expected"].update({"category": "ambiguous", "outcomes": ["CLARIFY"]})
    old["cases"][-1].update({"passed": True, "failure_stage": None, "oos_correct": True})
    folder = tmp_path / old["meta"]["run_id"]
    folder.mkdir()
    (folder / test_runs.RUN_FILE).write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    (folder / test_runs.META_FILE).write_text(json.dumps({"meta": old["meta"], "summary": old["summary"]}, ensure_ascii=False),
                                              encoding="utf-8")

    [entry] = test_runs.list_runs(tmp_path)
    loaded = test_runs.load_run(entry["run_id"], tmp_path)
    assert loaded == old
    assert loaded["cases"][-1]["passed"] is True, "옛 판정을 새 규칙으로 덮어썼다"
