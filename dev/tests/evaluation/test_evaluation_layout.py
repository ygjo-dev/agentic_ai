"""평가 자산이 어디 있고 저장소가 무엇을 들고 있나.

정답표 · 실행 기록 · 보고서가 `dev/evaluation` 한 지붕 아래 있고, 실행 기록과 보고서가
`.gitignore` 밖(추적 대상)에 있는지를 본다. 경로가 조용히 갈리면 화면이 빈 목록을 보이거나
평가 결과가 커밋에 안 담기는데, 둘 다 한참 뒤에야 드러난다.

**판정 · 기대값을 여기서 세지 않는다.** 발화 수 · 묶음 구성은 파일이 말하고
`dev/tests/tools/test_dashboard_selfchecks.py` 가 본다. 여기는 자리와 추적 여부다.
"""

import subprocess
from pathlib import Path

from dev.evaluation import runner, suite as suite_module, test_runs

REPO_ROOT = Path(__file__).resolve().parents[3]
EVALUATION = REPO_ROOT / "dev" / "evaluation"


def _tracked(path: Path) -> bool:
    """git 이 이 자리를 담을 수 있나. .gitignore 에 걸리면 거짓."""
    done = subprocess.run(
        ["git", "check-ignore", "-q", str(path)], cwd=REPO_ROOT, capture_output=True
    )
    return done.returncode != 0


def test_the_evaluation_assets_live_under_one_roof():
    assert suite_module.SUITES_DIR == EVALUATION / "test_suites"
    assert test_runs.RUNS_DIR == EVALUATION / "test_runs"
    assert (EVALUATION / "reports").is_dir()
    for module in (suite_module, runner, test_runs):
        assert Path(module.__file__).parent == EVALUATION


def test_both_test_suites_are_found_by_their_version_name():
    assert suite_module.SUITE_PATH == EVALUATION / "test_suites" / "test_suite_v1.yaml"
    assert suite_module.SUITE_V2_PATH == EVALUATION / "test_suites" / "test_suite_v2.yaml"
    paths = [Path(entry["path"]) for entry in suite_module.datasets()]
    assert paths == [suite_module.SUITE_PATH, suite_module.SUITE_V2_PATH]
    assert all(path.is_file() for path in paths)
    assert sorted(p.name for p in (EVALUATION / "test_suites").glob("*.yaml")) == [
        "test_suite_v1.yaml", "test_suite_v2.yaml",
    ]


def test_the_frozen_anchor_keeps_its_cases_after_the_move():
    """이름과 자리만 갈았다. 발화 · 기대값이 하나라도 움직이면 옛 측정과 이어 읽을 수 없다."""
    v1 = suite_module.load(suite_module.SUITE_PATH)
    assert v1["version"] == 1
    assert len(v1["cases"]) == 48
    assert all(suite_module.in_scope(case) for case in v1["cases"])
    assert suite_module.identity(v1, suite_module.SUITE_PATH)["sha256"] == (
        "1bd40444b9f0daf28a977e4337938bb5af07dab7a7fac9b14787ab27a442670a"
    )


def test_the_broader_suite_is_five_per_recipe_plus_out_of_scope_no_match():
    v2 = suite_module.load(suite_module.SUITE_V2_PATH)
    inside = [case for case in v2["cases"] if suite_module.in_scope(case)]
    outside = [case for case in v2["cases"] if not suite_module.in_scope(case)]

    assert len(v2["cases"]) == 203
    assert len(inside) == 195 and len(outside) == 8

    per_recipe = {}
    for case in inside:
        for rid in case["expected"]["recipe_ids"]:
            per_recipe.setdefault(rid, []).append(case["id"])
    assert len(per_recipe) == 39
    assert {len(ids) for ids in per_recipe.values()} == {5}

    assert {tuple(case["expected"]["outcomes"]) for case in outside} == {("NO_MATCH",)}
    assert suite_module.OOS_OUTCOMES == ("NO_MATCH",)


def test_test_runs_and_reports_are_version_controlled():
    """기계마다 다시 만들 수 없는 기록이다. .gitignore 아래 두면 커밋에 안 담긴다."""
    assert _tracked(test_runs.RUNS_DIR)
    assert _tracked(EVALUATION / "reports")
    assert _tracked(test_runs.RUNS_DIR / "어떤-실행-기록" / test_runs.RUN_FILE)
    assert not _tracked(REPO_ROOT / "dev" / "tools" / "sweep_out" / "무엇이든")


def test_the_runner_only_writes_files_and_never_commits_them():
    """평가를 돌릴 때마다 사람 몰래 이력이 늘면 무엇을 언제 담을지 사람이 못 정한다."""
    for module in (runner, test_runs):
        source = Path(module.__file__).read_text(encoding="utf-8")
        for forbidden in ('"commit"', "'commit'", "git commit", '"add"', "git add"):
            assert forbidden not in source, (module.__name__, forbidden)
    # runner 가 git 을 부르는 자리는 하나고, 읽기만 한다 (결과에 적을 HEAD).
    source = Path(runner.__file__).read_text(encoding="utf-8")
    called = [line.strip() for line in source.splitlines() if "subprocess.run(" in line]
    assert len(called) == 1 and '"git", "rev-parse"' in called[0], called
    assert "subprocess" not in Path(test_runs.__file__).read_text(encoding="utf-8")


def test_a_saved_run_round_trips_through_the_new_path(tmp_path, monkeypatch):
    monkeypatch.setattr(test_runs, "RUNS_DIR", tmp_path)

    def resolve(_utterance):
        return {"reason": "없음", "status": "NO_MATCH", "recipe_id": None, "candidate_recipe_ids": [],
                "argument": None, "travel_mode": None, "minutes": None, "admin_level": None}

    v1 = suite_module.load(suite_module.SUITE_PATH)
    only = [v1["cases"][0]["id"]]
    saved = runner.run(v1, suite_path=suite_module.SUITE_PATH, resolve=resolve, only=only,
                       materialize=False, save_dir=tmp_path,
                       dataset={"id": "test_suite_v1", "label": "FULL48 회귀 테스트"})

    listed = test_runs.list_runs()
    assert [entry["run_id"] for entry in listed] == [saved["meta"]["run_id"]]
    assert listed[0]["dataset_id"] == "test_suite_v1"
    assert test_runs.load_run(saved["meta"]["run_id"])["summary"] == saved["summary"]
    assert saved["meta"]["run_id"].split("-")[2] == "test_suite_v1"


def test_the_historical_v2_run_keeps_its_own_counts():
    """219 발화 · 옛 범위 밖 정의로 잰 기록이다. 새 203 정의로 다시 세지 않는다."""
    kept = [entry for entry in test_runs.list_runs() if entry["dataset_id"] == "test_suite_v2"]
    assert kept, "옮겨 둔 v2 기록이 없다"
    oldest = min(kept, key=lambda entry: entry["started_at"] or "")
    assert oldest["runs"] == 219, "옛 기록을 새 정의로 다시 셌다"
    loaded = test_runs.load_run(oldest["run_id"])
    assert loaded["meta"]["suite"]["case_count"] == len(loaded["cases"])
    assert loaded["summary"]["total"]["runs"] == len(loaded["cases"])
