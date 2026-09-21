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
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from dev.evaluation import run_evaluation
from dev.evaluation.engine import load_test_suite, manage_benchmark, monitor_gpu, monitor_metadata, score

REPO_ROOT = Path(__file__).resolve().parents[3]
EVALUATION = REPO_ROOT / "dev" / "evaluation"
sys.path.insert(0, str(REPO_ROOT / "dev" / "tools"))

# 203 발화 정답표의 기준 벤치마크. 폴더 이름이 run_id 다.
CANONICAL = "20260921-090538-test_suite_v2"
# 이 기계에서 돌린 FULL48 보통 실행. .gitignore 라 clone 에는 없다
LOCAL_FULL48 = "20260921-102636-test_suite_v1"
# 이름을 정하기 전 무작위 6자가 붙어 있던 두 이름. 다시 생기면 안 된다
RETIRED_RUN_IDS = ("20260921-090538-test_suite_v2-87532e", "20260921-102636-test_suite_v1-3a5465")

# 옮기기 전 바이트의 sha256. 자리만 옮겼고 내용은 한 글자도 안 바뀌어야 옛 측정과 이어 읽는다.
SUITE_SHA256 = {
    "test_suite_v1.yaml": "1bd40444b9f0daf28a977e4337938bb5af07dab7a7fac9b14787ab27a442670a",
    "test_suite_v2.yaml": "e032664fd667c15873ba58705e0c66d75518588601f2e340effa410aca5e2db7",
}
# 끝난 기준 벤치마크는 run.json 하나다. meta.run_id 한 줄만 폴더 이름에 맞췄고 나머지 바이트는 그대로다
CANONICAL_SHA256 = {
    "run.json": "66ec7aba228dbdd0aa785fdbd2f4318bff8f10e3815e17b604a10cc8e400e3bb",
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
    assert _ignored(manage_benchmark.LOCAL_DIR / LOCAL_FULL48 / manage_benchmark.RUN_FILE)
    assert not _ignored(manage_benchmark.LOCAL_DIR / ".gitkeep")
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
def test_the_canonical_203_benchmark_is_one_run_json_and_still_reads_188_of_203():
    folder = manage_benchmark.OFFICIAL_DIR / CANONICAL
    assert sorted(p.name for p in folder.iterdir()) == sorted(CANONICAL_SHA256)
    for name, digest in CANONICAL_SHA256.items():
        assert _sha256(folder / name) == digest, name

    loaded = manage_benchmark.load_benchmark(manage_benchmark.OFFICIAL, CANONICAL)
    assert loaded["meta"]["run_id"] == CANONICAL
    total, board = loaded["summary"]["total"], loaded["summary"]["metrics"]
    assert (total["passed"], total["runs"]) == (188, 203)
    assert board["selection"] == {"correct": 184, "total": 195}
    assert board["semantic_fields"] == {"correct": 187, "total": 190}
    assert board["semantic_cases"] == {"correct": 147, "total": 150}
    assert board["joint"] == {"correct": 181, "total": 195}
    assert board["oos"] == {"correct": 7, "total": 8}
    assert total["errors"] == 0
    assert loaded["meta"]["suite"]["case_count"] == len(loaded["cases"]) == 203
    # 줄에 적힌 판정을 다시 세면 저장된 합계와 같다. 채점 규칙이 움직이지 않았다
    recount = score.summarize(loaded["cases"], tuple(loaded["meta"]["suite"]["group_labels"]))
    assert {k: v for k, v in recount.items()} == loaded["summary"]


def test_the_old_219_case_raw_run_is_no_longer_kept_anywhere():
    """219 발화 · 옛 범위 밖 정의로 잰 기록은 지웠다. 그 숫자는 NOTES.md 에만 남는다."""
    old = "20260918-161110-test_suite_v2-e2cf28"
    assert all(entry["run_id"] != old for entry in manage_benchmark.list_benchmarks())
    assert not any((folder / old).exists() for folder in manage_benchmark.roots().values())
    leftovers = [p for p in REPO_ROOT.rglob("*e2cf28*") if ".git" not in p.relative_to(REPO_ROOT).parts]
    assert leftovers == []


def test_the_two_kept_runs_are_named_by_time_and_suite_only():
    """무작위 6자가 붙은 옛 이름은 없어지고, 폴더 이름과 run.json 안의 run_id 가 같다."""
    assert (manage_benchmark.OFFICIAL_DIR / CANONICAL).is_dir()
    for folder in manage_benchmark.roots().values():
        for old in RETIRED_RUN_IDS:
            assert not (folder / old).exists(), old
    local = manage_benchmark.LOCAL_DIR / LOCAL_FULL48
    if not local.exists():
        pytest.skip("이 기계에서 돌린 FULL48 보통 실행이 없다 (.gitignore 라 clone 에는 없음)")
    assert sorted(p.name for p in local.iterdir()) == [manage_benchmark.RUN_FILE]
    loaded = manage_benchmark.load_benchmark(manage_benchmark.LOCAL, LOCAL_FULL48)
    assert loaded["meta"]["run_id"] == LOCAL_FULL48
    assert (loaded["summary"]["total"]["passed"], loaded["summary"]["total"]["runs"]) == (48, 48)


def test_no_human_report_files_are_kept_or_written():
    """보고서 형식은 아직 정하지 않았다. summary.md 같은 사람용 파일을 남기지 않는다."""
    for folder in manage_benchmark.roots().values():
        assert not list(folder.rglob("summary.md")), folder
    assert not hasattr(manage_benchmark, "SUMMARY_FILE")
    assert not hasattr(score, "summary_text")
    assert not (EVALUATION / "reports").exists()


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
    assert manage_benchmark.load_benchmark(manage_benchmark.LOCAL, saved["meta"]["run_id"])["summary"] == saved["summary"]
    assert manage_benchmark.load_benchmark(manage_benchmark.OFFICIAL, CANONICAL)["meta"]["run_id"] == CANONICAL
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


def test_a_second_run_in_the_same_second_gets_a_numeric_suffix_and_never_overwrites(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
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
    assert re.fullmatch(r"\d{8}-\d{6}-test_suite_v1", run_id), run_id


def test_no_random_suffix_generator_is_left_in_the_evaluation_code():
    for path in EVALUATION.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in ("token_hex", "uuid", "random"):
            assert forbidden not in source, (path.name, forbidden)


def _isolate(monkeypatch, tmp_path) -> tuple[Path, Path]:
    """official · local 두 자리를 tmp 아래 빈 폴더로 바꿈. (official, local)."""
    official, local = tmp_path / "official", tmp_path / "local"
    official.mkdir()
    local.mkdir()
    monkeypatch.setattr(manage_benchmark, "OFFICIAL_DIR", official)
    monkeypatch.setattr(manage_benchmark, "LOCAL_DIR", local)
    return official, local


def _fake_run(folder: Path, run_id: str, started: str, *, complete: bool = True, passed: int = 1, runs: int = 2) -> None:
    """다 끝난(run.json) 또는 도중에 죽은(meta.json + cases.jsonl) 기록 폴더 하나."""
    folder.mkdir(parents=True)
    meta = {"run_id": run_id, "started_at": started, "suite": {"name": "test_suite_v2", "dataset_id": "test_suite_v2"}}
    if complete:
        summary = {"total": {"runs": runs, "passed": passed}}
        (folder / manage_benchmark.RUN_FILE).write_text(json.dumps({"meta": meta, "summary": summary, "cases": []}), encoding="utf-8")
    else:
        (folder / manage_benchmark.META_FILE).write_text(json.dumps({"meta": meta}), encoding="utf-8")
        (folder / manage_benchmark.CASES_FILE).write_text("", encoding="utf-8")


# ── run_id 이름 · 두 자리를 통틀어 하나 ──────────────────────────────
def test_the_collision_check_looks_at_both_official_and_local(tmp_path, monkeypatch):
    """공식으로 옮긴 기록과 같은 이름을 로컬에 새로 만들면 나중에 옮길 때 부딪힌다."""
    official, local = _isolate(monkeypatch, tmp_path)
    started = datetime.datetime(2026, 9, 21, 13, 25, 0)
    (official / "20260921-132500-test_suite_v2").mkdir()
    (local / "20260921-132500-test_suite_v2-2").mkdir()

    recorder = manage_benchmark.Recorder(local, started, "test_suite_v2")

    assert recorder.run_id == "20260921-132500-test_suite_v2-3"
    assert recorder.dir == local / recorder.run_id
    assert not (official / recorder.run_id).exists()


# ── 도는 동안 · 끝난 뒤의 파일 ──────────────────────────────────────
def test_a_running_benchmark_keeps_meta_and_cases_and_a_finished_one_keeps_only_run_json(tmp_path, monkeypatch):
    _, local = _isolate(monkeypatch, tmp_path)
    seen = []

    def watch(done, total, row):
        folder = next(local.iterdir())
        seen.append(sorted(p.name for p in folder.iterdir()))

    v1 = load_test_suite.load(load_test_suite.SUITE_PATH)
    result = run_evaluation.run(v1, suite_path=load_test_suite.SUITE_PATH, resolve=_no_match, only=[1, 2],
                                materialize=False, save_dir=local, progress=watch)

    assert seen == [[manage_benchmark.CASES_FILE, manage_benchmark.META_FILE]] * 2
    folder = local / result["meta"]["run_id"]
    assert sorted(p.name for p in folder.iterdir()) == [manage_benchmark.RUN_FILE]
    assert "summary" in json.loads((folder / manage_benchmark.RUN_FILE).read_text(encoding="utf-8"))


def test_run_json_wins_over_leftover_running_files(tmp_path, monkeypatch):
    """run.json 을 쓴 뒤 임시 파일을 지우기 전에 죽어도, 끝난 기록으로 읽고 남은 줄에 흔들리지 않는다."""
    _, local = _isolate(monkeypatch, tmp_path)
    folder = local / "20260921-140000-test_suite_v2"
    _fake_run(folder, folder.name, "2026-09-21T14:00:00+09:00", passed=2, runs=2)
    (folder / manage_benchmark.META_FILE).write_text(json.dumps({"meta": {"run_id": "딴것"}}), encoding="utf-8")
    (folder / manage_benchmark.CASES_FILE).write_text('{"case_id": 999}\n', encoding="utf-8")

    [entry] = manage_benchmark.list_benchmarks()
    loaded = manage_benchmark.load_benchmark(manage_benchmark.LOCAL, folder.name)

    assert entry["complete"] and (entry["passed"], entry["runs"]) == (2, 2)
    assert loaded["meta"]["run_id"] == folder.name and loaded["cases"] == []


# ── 불러올 기록 목록 · 불러오기 ─────────────────────────────────────
def test_official_and_local_are_one_list_sorted_newest_first_with_their_kind(tmp_path, monkeypatch):
    official, local = _isolate(monkeypatch, tmp_path)
    _fake_run(official / "20260921-090538-test_suite_v2", "20260921-090538-test_suite_v2", "2026-09-21T09:05:38+09:00")
    _fake_run(local / "20260921-102636-test_suite_v1", "20260921-102636-test_suite_v1", "2026-09-21T10:26:36+09:00")
    _fake_run(official / "20260921-120000-test_suite_v2", "20260921-120000-test_suite_v2", "2026-09-21T12:00:00+09:00")
    _fake_run(local / "20260921-141000-test_suite_v2", "20260921-141000-test_suite_v2", "2026-09-21T14:10:00+09:00",
              complete=False)
    (local / "깨진-폴더").mkdir()
    (local / "깨진-폴더" / manage_benchmark.RUN_FILE).write_text("{", encoding="utf-8")

    listed = manage_benchmark.list_benchmarks()

    assert [(e["run_id"], e["kind"]) for e in listed] == [
        ("20260921-141000-test_suite_v2", "local"),
        ("20260921-120000-test_suite_v2", "official"),
        ("20260921-102636-test_suite_v1", "local"),
        ("20260921-090538-test_suite_v2", "official"),
    ]
    assert [e["complete"] for e in listed] == [False, True, True, True]
    assert listed[0]["runs"] is None and not any(e["duplicate"] for e in listed)
    assert manage_benchmark.load_benchmark("official", "20260921-120000-test_suite_v2")["meta"]["run_id"] == "20260921-120000-test_suite_v2"
    assert manage_benchmark.load_benchmark("local", "20260921-141000-test_suite_v2")["meta"]["stopped"] == manage_benchmark.INCOMPLETE
    with pytest.raises(FileNotFoundError):
        manage_benchmark.load_benchmark("local", "20260921-120000-test_suite_v2")
    with pytest.raises(ValueError):
        manage_benchmark.load_benchmark("공식", "20260921-120000-test_suite_v2")


def test_the_same_run_id_in_both_places_is_reported_not_silently_resolved(tmp_path, monkeypatch):
    official, local = _isolate(monkeypatch, tmp_path)
    twin = "20260921-132500-test_suite_v2"
    _fake_run(official / twin, twin, "2026-09-21T13:25:00+09:00", passed=1)
    _fake_run(local / twin, twin, "2026-09-21T13:25:00+09:00", passed=2)

    listed = manage_benchmark.list_benchmarks()

    assert sorted(e["kind"] for e in listed) == ["local", "official"]
    assert all(e["duplicate"] for e in listed)
    assert manage_benchmark.duplicate_run_ids() == {twin}
    assert any(twin in problem for problem in manage_benchmark.storage_problems())
    for kind in manage_benchmark.KINDS:
        with pytest.raises(manage_benchmark.DuplicateRunId):
            manage_benchmark.load_benchmark(kind, twin)


def test_a_missing_official_folder_is_reported_instead_of_an_empty_list(tmp_path, monkeypatch):
    """목록을 읽는 자리가 사라지면 빈 목록만 보여서는 원인을 모른다. 2026-09-21 불러올 기록이 빈 까닭이 이것이었다."""
    monkeypatch.setattr(manage_benchmark, "OFFICIAL_DIR", tmp_path / "없는-자리")
    monkeypatch.setattr(manage_benchmark, "LOCAL_DIR", tmp_path / "local")
    assert manage_benchmark.list_benchmarks() == []
    assert any("공식 기록 폴더가 없습니다" in problem for problem in manage_benchmark.storage_problems())


def test_the_repository_storage_is_valid_and_lists_the_canonical_run():
    """실제 저장소 자리로 목록을 만들면 기준 벤치마크가 공식으로 나오고 보관 문제가 없다."""
    assert manage_benchmark.storage_problems() == []
    entries = {(e["kind"], e["run_id"]): e for e in manage_benchmark.list_benchmarks()}
    canonical = entries[(manage_benchmark.OFFICIAL, CANONICAL)]
    assert canonical["complete"] and (canonical["passed"], canonical["runs"]) == (188, 203)
    assert canonical["dataset_id"] == "test_suite_v2"


# ── 평가가 계기판을 부르지 않는다 ────────────────────────────────────
def test_the_evaluation_code_never_imports_check_resolve():
    """판정 규칙의 원본은 평가 쪽이다. 평가가 계기판의 밑줄 함수를 빌려 쓰면 방향이 거꾸로다."""
    for path in EVALUATION.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        imports = [line for line in source.splitlines() if re.match(r"\s*(from|import)\s", line)]
        assert not [line for line in imports if "check_resolve" in line], path.name


def test_check_resolve_uses_the_evaluation_rules_instead_of_its_own_copy():
    import check_resolve

    assert check_resolve._grade is score.grade
    assert check_resolve._value_mark is score.value_mark
    assert (check_resolve.HIT, check_resolve.NEAR, check_resolve.MISS, check_resolve.UNATTACHED) == (
        score.HIT, score.NEAR, score.MISS, score.UNATTACHED)
    assert check_resolve.NULL_MARK == score.NULL_MARK
    assert check_resolve.ServerDown is run_evaluation.ServerDown
    assert check_resolve.TIMEOUT == run_evaluation.TIMEOUT
    assert check_resolve._role_label is monitor_metadata.role_label
    for label in run_evaluation.CONTEXTS:
        check_resolve.CONTEXT, was = label, check_resolve.CONTEXT
        try:
            assert check_resolve._context_payload() == run_evaluation.context_payload(label)
        finally:
            check_resolve.CONTEXT = was
    source = Path(check_resolve.__file__).read_text(encoding="utf-8")
    for copied in ("def _grade(", "def _value_mark(", "class ServerDown", "def _role_label(", "VIEW_BBOX = "):
        assert copied not in source, copied


@pytest.mark.parametrize("name", ["test_suite_v1", "test_suite_v2"])
def test_every_registered_suite_loads(name):
    suite = load_test_suite.load(load_test_suite.dataset(name)["path"])
    assert suite["cases"]
