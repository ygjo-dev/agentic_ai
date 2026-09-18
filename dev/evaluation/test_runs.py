"""평가 한 번(Test Run)을 파일로 남기고 다시 읽는 곳.

낱말 (화면 · 보고서 · 코드가 같은 뜻으로 쓴다)

    Test Suite    정답표 한 벌. 바뀌지 않는 발화 · 기대값 정의 (dev/evaluation/*.yaml)
                  FULL48 은 얼린 회귀 기준선, 테스트 세트 v2 는 일반화를 재는 넓은 자
    Test Run      정답표 한 벌을 한 모델 · 설정 · 시각에 한 번 잰 것. runner.run 의 결과 한 벌
    Case Result   Test Run 안의 발화 하나의 결과. 결과의 cases 한 줄

Test Run 하나가 폴더 하나다. DB · 서비스를 두지 않는다.

    <RUNS_DIR>/<run_id>/
      meta.json     시작할 때 머리(meta)를 씀. 끝나면 {meta, summary} 로 갈아씀 — 목록이 이것만 읽음
      cases.jsonl   발화 하나가 끝날 때마다 한 줄씩 덧붙임. 도중에 죽어도 끝난 줄이 남음
      run.json      끝났을 때 결과 한 벌 그대로 (runner.run 의 반환값과 같은 모양)
      summary.md    사람이 읽는 요약

run.json 이 있으면 그것이 Test Run 이다. 없으면(도중에 죽음) meta.json 과 cases.jsonl 로
다시 세운다 — 합계는 runner.summarize 가 다시 센다. 화면은 어느 쪽이든 같은 모양을 받는다.

RUNS_DIR 는 dev/tools/sweep_out/ 아래라 .gitignore 다. 기계마다 다른 측정 산출물이다.
"""

import datetime
import json
import re
import secrets
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "dev" / "tools" / "sweep_out" / "test_runs"

META_FILE = "meta.json"
CASES_FILE = "cases.jsonl"
RUN_FILE = "run.json"
SUMMARY_FILE = "summary.md"

# 도중에 끝난 Test Run 을 다시 세웠을 때 meta.stopped 에 적는 말.
INCOMPLETE = "incomplete: run.json 없음 (도중에 끝남)"


def new_run_id(started: datetime.datetime, suite_name: str) -> str:
    """Test Run id. <시작 시각>-<정답표 이름>-<무작위 6자>. 같은 초에 둘이 떠도 안 겹침."""
    slug = re.sub(r"[^0-9A-Za-z_]+", "_", suite_name or "suite").strip("_") or "suite"
    return f"{started:%Y%m%d-%H%M%S}-{slug}-{secrets.token_hex(3)}"


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1)


class Recorder:
    """Test Run 하나를 폴더에 쓰는 자. runner.run 이 시작 · 발화마다 · 끝에 부름.

    규칙  폴더가 이미 있으면 FileExistsError. 다른 Test Run 을 덮어쓰지 않음
          case 는 줄마다 바로 flush. 도중에 죽어도 끝난 줄이 남음
    제약  결과를 고치거나 다시 채점하지 않는다
    """

    def __init__(self, root: Path, run_id: str):
        self.dir = Path(root) / run_id
        self.dir.mkdir(parents=True, exist_ok=False)

    def start(self, meta: dict) -> None:
        (self.dir / META_FILE).write_text(_dump({"meta": meta, "summary": None}), encoding="utf-8")
        (self.dir / CASES_FILE).write_text("", encoding="utf-8")

    def case(self, row: dict) -> None:
        with (self.dir / CASES_FILE).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()

    def finish(self, result: dict) -> None:
        (self.dir / RUN_FILE).write_text(_dump(result), encoding="utf-8")
        (self.dir / META_FILE).write_text(_dump({"meta": result["meta"], "summary": result["summary"]}), encoding="utf-8")
        (self.dir / SUMMARY_FILE).write_text(summary_text(result), encoding="utf-8")


def _run_dir(run: str | Path, root: Path | None) -> Path:
    path = Path(run)
    if path.is_dir():
        return path
    return Path(root or RUNS_DIR) / str(run)


def load_run(run: str | Path, root: Path | None = None) -> dict:
    """저장한 Test Run 한 벌. runner.run 의 반환값과 같은 모양.

    입력  run id 또는 그 폴더 경로
    규칙  run.json 이 있으면 그대로 읽음
          없으면 meta.json 머리와 cases.jsonl 줄로 다시 세움. 합계는 runner.summarize 가 셈.
          meta.stopped 가 비었으면 INCOMPLETE 를 적음. 끝나지 않은 마지막 줄(잘린 JSON)은 버림
          폴더가 없으면 FileNotFoundError
    제약  줄을 다시 채점하지 않는다
    """
    folder = _run_dir(run, root)
    if (folder / RUN_FILE).is_file():
        return json.loads((folder / RUN_FILE).read_text(encoding="utf-8"))
    if not (folder / META_FILE).is_file():
        raise FileNotFoundError(f"Test Run 이 없다: {folder}")

    from dev.evaluation import runner

    head = json.loads((folder / META_FILE).read_text(encoding="utf-8"))["meta"]
    rows = []
    for line in (folder / CASES_FILE).read_text(encoding="utf-8").splitlines() if (folder / CASES_FILE).is_file() else []:
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            break
    meta = {**head, "finished_at": head.get("finished_at"), "stopped": head.get("stopped") or INCOMPLETE}
    labels = tuple((head.get("suite") or {}).get("group_labels") or ())
    return {"meta": meta, "summary": runner.summarize(rows, labels), "cases": rows}


def list_runs(root: Path | None = None) -> list[dict]:
    """저장한 Test Run 목록. 최근 것이 앞.

    출력  [{run_id, path, complete, started_at, dataset_id, suite_label, suite_name, runs, passed, stopped}]
          complete 는 run.json 이 있나. runs · passed 는 끝난 것만 (도중이면 None)
    규칙  meta.json 만 읽음. 읽을 수 없는 폴더는 건너뜀
    """
    folder = Path(root or RUNS_DIR)
    if not folder.is_dir():
        return []
    entries = []
    for path in folder.iterdir():
        meta_path = path / META_FILE
        if not meta_path.is_file():
            continue
        try:
            document = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        meta = document.get("meta") or {}
        summary = document.get("summary") or {}
        suite = meta.get("suite") or {}
        total = summary.get("total") or {}
        entries.append({
            "run_id": meta.get("run_id") or path.name,
            "path": str(path),
            "complete": (path / RUN_FILE).is_file(),
            "started_at": meta.get("started_at"),
            "dataset_id": suite.get("dataset_id"),
            "suite_label": suite.get("label") or suite.get("name"),
            "suite_name": suite.get("name"),
            "runs": total.get("runs"),
            "passed": total.get("passed"),
            "stopped": meta.get("stopped"),
        })
    return sorted(entries, key=lambda entry: entry["started_at"] or "", reverse=True)


def _ratio(pair: dict | None) -> str:
    if not pair or not pair.get("total"):
        return "-"
    return f"{pair['correct']}/{pair['total']} ({pair['correct'] / pair['total']:.1%})"


def summary_text(result: dict) -> str:
    """사람이 읽는 Test Run 요약 (markdown)."""
    meta, summary = result["meta"], result["summary"]
    metrics = summary.get("metrics") or {}
    latency = summary.get("latency") or {}
    gpu = meta.get("gpu") or {}
    conditions = meta.get("conditions") or {}
    suite = meta.get("suite") or {}
    lines = [
        f"# Test Run {meta.get('run_id')}",
        "",
        f"- Test Suite: {suite.get('label') or suite.get('name')} (v{suite.get('version')}, sha256 {str(suite.get('sha256'))[:12]}, {suite.get('case_count')} cases)",
        f"- model: {conditions.get('model')} · {conditions.get('provider')} · role v{conditions.get('role_version')}",
        f"- started {meta.get('started_at')} · finished {meta.get('finished_at')} · elapsed {meta.get('elapsed_s')} s",
        f"- stopped: {meta.get('stopped')}",
        "",
        "| metric | result |",
        "|---|---|",
        f"| Selection | {_ratio(metrics.get('selection'))} |",
        f"| Semantic fields | {_ratio(metrics.get('semantic_fields'))} |",
        f"| Semantic cases | {_ratio(metrics.get('semantic_cases'))} |",
        f"| Joint | {_ratio(metrics.get('joint'))} |",
        f"| OOS | {_ratio(metrics.get('oos'))} |",
        f"| READY | {_ratio(metrics.get('ready'))} |",
        f"| Errors | {summary['total'].get('errors')} |",
        "",
        f"latency (s): min {latency.get('min')} · median {latency.get('median')} · p95 {latency.get('p95')} · max {latency.get('max')}",
        f"GPU: available {gpu.get('available')} · start {gpu.get('start_temp')} · max {gpu.get('max_temp')} · end {gpu.get('end_temp')} "
        f"· pauses {gpu.get('pauses')} · throttle {gpu.get('thermal_throttle')}",
        "",
        "## failed cases",
        "",
    ]
    failed = [row for row in result["cases"] if not row["passed"]]
    if not failed:
        lines.append("none")
    for row in failed:
        actual = row.get("actual") or {}
        bad = [f"{f['name']} {f['expected']!r}->{f['actual']!r}" for f in row.get("spoken_fields") or [] if not f["correct"]]
        expected = row["expected"].get("recipe_ids") or row["expected"].get("outcomes")
        lines.append(
            f"- #{row['case_id']} [{row['failure_stage']}] {row['utterance']} · expected {expected} · "
            f"actual {actual.get('status')} {actual.get('recipe_id')} {actual.get('candidate_recipe_ids')} "
            f"outcome {row.get('outcome')} {'; '.join(bad)}{' · ' + row['error'] if row.get('error') else ''}"
        )
    return "\n".join(lines) + "\n"
