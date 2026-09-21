"""평가 자산이 어디 있고 저장소가 무엇을 들고 있나.

    dev/evaluation/run_evaluation.py            main
    dev/evaluation/engine/                      안쪽 일 다섯
    dev/evaluation/inputs/test_suites/          정답표 (추적)
    dev/evaluation/outputs/official_benchmark/  골라 남긴 기준 벤치마크 (추적)
    dev/evaluation/outputs/local_benchmark/     보통 실행 (.gitignore)

경로가 조용히 갈리면 화면이 빈 목록을 보이거나, 기준 벤치마크가 커밋에 안 담기거나, 보통 실행이
커밋에 섞이는데, 셋 다 한참 뒤에야 드러난다.
"""

import datetime
import hashlib
import subprocess
from pathlib import Path

import pytest

from dev.evaluation import run_evaluation
from dev.evaluation.engine import load_test_suite, manage_benchmark, monitor_gpu, monitor_metadata, score

REPO_ROOT = Path(__file__).resolve().parents[3]
EVALUATION = REPO_ROOT / "dev" / "evaluation"

# 203 발화 정답표의 기준 벤치마크. 폴더 이름(뒤의 무작위 6자 포함)은 그때의 run_id 그대로다.
CANONICAL = "20260921-090538-test_suite_v2-87532e"

# 옮기기 전 바이트의 sha256. 자리만 옮겼고 내용은 한 글자도 안 바뀌어야 옛 측정과 이어 읽는다.
SUITE_SHA256 = {
    "test_suite_v1.yaml": "1bd40444b9f0daf28a977e4337938bb5af07dab7a7fac9b14787ab27a442670a",
    "test_suite_v2.yaml": "e032664fd667c15873ba58705e0c66d75518588601f2e340effa410aca5e2db7",
}
CANONICAL_SHA256 = {
    "cases.jsonl": "5a5fe48288abf054cfaaa0523b74dcb3b5b650a3e905e59726aa00dd93fc872b",
    "meta.json": "67aaf9a4abed85e6ee580594da25d9b7c1cadc4062da6f261bee83c8477b62e4",
    "run.json": "fc7af87cb02cf8d29f849c1620adfcf9f7773b23ae2f93b8cd25e3bb0380505c",
    "summary.md": "379e0428764e8be3621ed4b1a13d57376c1fdc9e8771f8732af9e12eb4ae068a",
}


def _ignored(path: Path) -> bool:
    """.gitignore 에 걸리나."""
    done = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=REPO_ROOT, capture_output=True)
    return done.returncode == 0


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── 자리 ────────────────────────────────────────────────────────────
def test_the_evaluation_tree_is_one_main_five_engine_modules_inputs_and_outputs():
    assert Path(run_evaluation.__file__).parent == EVALUATION
    engine = [load_test_suite, score, manage_benchmark, monitor_metadata, monitor_gpu]
    assert all(Path(module.__file__).parent == EVALUATION / "engine" for module in engine)
    assert sorted(p.name for p in (EVALUATION / "engine").glob("*.py")) == sorted(
        Path(module.__file__).name for module in engine
    )
    assert load_test_suite.SUITES_DIR == EVALUATION / "inputs" / "test_suites"
    assert manage_benchmark.OFFICIAL_DIR == EVALUATION / "outputs" / "official_benchmark"
    assert manage_benchmark.LOCAL_DIR == EVALUATION / "outputs" / "local_benchmark"
    for gone in ("runner.py", "suite.py", "test_runs.py", "gpu.py", "spoken_audit.py",
                 "test_suites", "test_runs", "reports"):
        assert not (EVALUATION / gone).exists(), gone


def test_both_test_suites_are_found_by_their_version_name_and_their_bytes_did_not_move():
    assert load_test_suite.SUITE_PATH == load_test_suite.SUITES_DIR / "test_suite_v1.yaml"
    assert load_test_suite.SUITE_V2_PATH == load_test_suite.SUITES_DIR / "test_suite_v2.yaml"
    paths = [Path(entry["path"]) for entry in load_test_suite.datasets()]
    assert paths == [load_test_suite.SUITE_PATH, load_test_suite.SUITE_V2_PATH]
    assert sorted(p.name for p in load_test_suite.SUITES_DIR.glob("*.yaml")) == sorted(SUITE_SHA256)
    for path in paths:
        assert _sha256(path) == SUITE_SHA256[path.name], path.name


def test_the_frozen_anchor_keeps_its_48_cases():
    v1 = load_test_suite.load(load_test_suite.SUITE_PATH)
    assert v1["version"] == 1
    assert len(v1["cases"]) == 48
    assert all(load_test_suite.in_scope(case) for case in v1["cases"])
    assert load_test_suite.identity(v1, load_test_suite.SUITE_PATH)["sha256"] == SUITE_SHA256["test_suite_v1.yaml"]


def test_the_broader_suite_is_195_in_scope_plus_8_out_of_scope_no_match():
    v2 = load_test_suite.load(load_test_suite.SUITE_V2_PATH)
    inside = [case for case in v2["cases"] if load_test_suite.in_scope(case)]
    outside = [case for case in v2["cases"] if not load_test_suite.in_scope(case)]

    assert len(v2["cases"]) == 203
    assert len(inside) == 195 and len(outside) == 8

    per_recipe = {}
    for case in inside:
        for rid in case["expected"]["recipe_ids"]:
            per_recipe.setdefault(rid, []).append(case["id"])
    assert len(per_recipe) == 39
    assert {len(ids) for ids in per_recipe.values()} == {5}

    assert {tuple(case["expected"]["outcomes"]) for case in outside} == {("NO_MATCH",)}
    assert load_test_suite.OOS_OUTCOMES == ("NO_MATCH",)


# ── 추적 여부 ────────────────────────────────────────────────────────
def test_official_benchmarks_and_test_suites_are_tracked_and_local_benchmarks_are_ignored():
    """기준 벤치마크는 기계마다 다시 만들 수 없는 기록이라 담는다. 보통 실행은 담지 않는다."""
    assert not _ignored(manage_benchmark.OFFICIAL_DIR / CANONICAL / manage_benchmark.RUN_FILE)
    assert not _ignored(manage_benchmark.OFFICIAL_DIR / "어떤-기록" / manage_benchmark.RUN_FILE)
    assert not _ignored(load_test_suite.SUITE_V2_PATH)
    assert _ignored(manage_benchmark.LOCAL_DIR / "어떤-기록" / manage_benchmark.RUN_FILE)
    assert _ignored(manage_benchmark.LOCAL_DIR / "20260921-102636-test_suite_v1-3a5465")
    assert _ignored(REPO_ROOT / "dev" / "tools" / "sweep_out" / "무엇이든")


def test_the_runner_only_writes_files_and_never_commits_them():
    """평가를 돌릴 때마다 사람 몰래 이력이 늘면 무엇을 언제 담을지 사람이 못 정한다."""
    modules = (run_evaluation, load_test_suite, score, manage_benchmark, monitor_metadata, monitor_gpu)
    for module in modules:
        source = Path(module.__file__).read_text(encoding="utf-8")
        for forbidden in ('"commit"', "'commit'", "git commit", '"add"', "git add"):
            assert forbidden not in source, (module.__name__, forbidden)
    # git 을 부르는 자리는 하나고, 읽기만 한다 (결과에 적을 HEAD).
    called = [
        line.strip()
        for module in modules
        for line in Path(module.__file__).read_text(encoding="utf-8").splitlines()
        if "subprocess.run(" in line and '"git"' in line
    ]
    assert len(called) == 1 and '"git", "rev-parse"' in called[0], called
    assert "subprocess" not in Path(manage_benchmark.__file__).read_text(encoding="utf-8")


# ── 기준 벤치마크 ────────────────────────────────────────────────────
def test_the_canonical_203_benchmark_moved_byte_for_byte_and_still_reads_188_of_203():
    folder = manage_benchmark.OFFICIAL_DIR / CANONICAL
    assert sorted(p.name for p in folder.iterdir()) == sorted(CANONICAL_SHA256)
    for name, digest in CANONICAL_SHA256.items():
        assert _sha256(folder / name) == digest, name

    loaded = manage_benchmark.load_benchmark(CANONICAL)
    total, board = loaded["summary"]["total"], loaded["summary"]["metrics"]
    assert (total["passed"], total["runs"]) == (188, 203)
    assert board["joint"] == {"correct": 181, "total": 195}
    assert board["oos"] == {"correct": 7, "total": 8}
    assert loaded["meta"]["suite"]["case_count"] == len(loaded["cases"]) == 203
    # 줄에 적힌 판정을 다시 세면 저장된 합계와 같다. 채점 규칙이 움직이지 않았다
    recount = score.summarize(loaded["cases"], tuple(loaded["meta"]["suite"]["group_labels"]))
    assert {k: v for k, v in recount.items()} == loaded["summary"]


def test_the_old_219_case_raw_run_is_no_longer_kept_anywhere():
    """219 발화 · 옛 범위 밖 정의로 잰 기록은 지웠다. 그 숫자는 NOTES.md 에만 남는다."""
    old = "20260918-161110-test_suite_v2-e2cf28"
    assert all(entry["run_id"] != old for entry in manage_benchmark.list_benchmarks())
    assert not any((folder / old).exists() for folder in manage_benchmark.roots().values())


# ── official · local 목록과 저장 ──────────────────────────────────────
def _no_match(_utterance):
    return {"reason": "없음", "status": "NO_MATCH", "recipe_id": None, "candidate_recipe_ids": [],
            "argument": None, "travel_mode": None, "minutes": None, "admin_level": None}


def _save_one(root: Path) -> dict:
    v1 = load_test_suite.load(load_test_suite.SUITE_PATH)
    return run_evaluation.run(v1, suite_path=load_test_suite.SUITE_PATH, resolve=_no_match,
                              only=[v1["cases"][0]["id"]], materialize=False, save_dir=root,
                              dataset={"id": "test_suite_v1", "label": "FULL48 회귀 테스트"})


def test_a_local_benchmark_saves_and_is_listed_next_to_the_official_ones(tmp_path, monkeypatch):
    monkeypatch.setattr(manage_benchmark, "LOCAL_DIR", tmp_path)
    saved = _save_one(tmp_path)

    listed = manage_benchmark.list_benchmarks()
    kinds = {entry["run_id"]: entry["kind"] for entry in listed}
    assert kinds[saved["meta"]["run_id"]] == manage_benchmark.LOCAL
    assert kinds[CANONICAL] == manage_benchmark.OFFICIAL
    assert manage_benchmark.load_benchmark(saved["meta"]["run_id"])["summary"] == saved["summary"]
    assert manage_benchmark.load_benchmark(CANONICAL)["meta"]["run_id"] == CANONICAL
    # 보여주려고 파일을 옮기거나 베끼지 않는다
    assert sorted(p.name for p in tmp_path.iterdir()) == [saved["meta"]["run_id"]]


def test_run_dataset_saves_to_local_benchmark_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(manage_benchmark, "LOCAL_DIR", tmp_path)
    before = sorted(p.name for p in manage_benchmark.OFFICIAL_DIR.iterdir())
    result = run_evaluation.run_dataset("test_suite_v1", resolve=_no_match, only=[1], materialize=False,
                                        environment={"available": False, "gpus": []})

    assert Path(result["meta"]["saved_to"]).parent == tmp_path
    assert sorted(p.name for p in manage_benchmark.OFFICIAL_DIR.iterdir()) == before


def test_a_new_run_id_is_time_and_suite_without_random_hex():
    started = datetime.datetime(2026, 9, 21, 10, 30, 0)
    assert manage_benchmark.new_run_id(started, "test_suite_v2") == "20260921-103000-test_suite_v2"
    assert manage_benchmark.new_run_id(started, "test_suite_v2", 2) == "20260921-103000-test_suite_v2-2"
    assert manage_benchmark.new_run_id(started, "이상한 이름!") == "20260921-103000-suite"


def test_a_second_run_in_the_same_second_gets_a_numeric_suffix_and_never_overwrites(tmp_path):
    started = datetime.datetime(2026, 9, 21, 10, 30, 0)
    first = manage_benchmark.Recorder(tmp_path, started, "test_suite_v2")
    first.start({"run_id": first.run_id})
    (first.dir / "표시").write_text("첫째", encoding="utf-8")
    second = manage_benchmark.Recorder(tmp_path, started, "test_suite_v2")
    third = manage_benchmark.Recorder(tmp_path, started, "test_suite_v2")

    assert [first.run_id, second.run_id, third.run_id] == [
        "20260921-103000-test_suite_v2", "20260921-103000-test_suite_v2-2", "20260921-103000-test_suite_v2-3",
    ]
    assert (first.dir / "표시").read_text(encoding="utf-8") == "첫째"


def test_a_saved_run_folder_is_named_by_its_run_id(tmp_path):
    saved = _save_one(tmp_path)
    run_id = saved["meta"]["run_id"]
    assert Path(saved["meta"]["saved_to"]) == tmp_path / run_id
    assert run_id.endswith("-test_suite_v1")
    assert len(run_id.split("-")) == 3


@pytest.mark.parametrize("name", ["test_suite_v1", "test_suite_v2"])
def test_every_registered_suite_loads(name):
    suite = load_test_suite.load(load_test_suite.dataset(name)["path"])
    assert suite["cases"]
