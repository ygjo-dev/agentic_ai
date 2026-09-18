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
