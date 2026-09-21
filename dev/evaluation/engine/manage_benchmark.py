"""벤치마크 결과를 파일로 남기고 다시 읽는 곳. 저장 · 목록 · 불러오기 · 도중에 끝난 것 복구.

낱말 (화면 · 코드가 같은 뜻으로 쓴다)

    Test Suite    정답표 한 벌. 바뀌지 않는 발화 · 기대값 정의 (dev/evaluation/inputs/test_suites/*.yaml)
                  FULL48 은 얼린 회귀 기준선, 테스트 세트 v2 는 일반화를 재는 넓은 자
    Test Run      정답표 한 벌을 한 모델 · 설정 · 시각에 한 번 잰 것. run_evaluation.run 의 결과 한 벌
    Case Result   Test Run 안의 발화 하나의 결과. 결과의 cases 한 줄

Test Run 하나가 폴더 하나다. DB · 서비스를 두지 않는다. 폴더는 두 자리 중 하나에 있다.

    outputs/official_benchmark/<run_id>/   골라서 남긴 기준 벤치마크. Git 이 추적한다
    outputs/local_benchmark/<run_id>/      화면 · 개발 중에 돌린 보통 실행. .gitignore
                                          새로 도는 벤치마크는 여기로 간다

official 로 올리는 것은 사람이 폴더를 옮겨서 한다. 여기에 올리는 기능을 두지 않는다.

    <run_id>/
      meta.json     시작할 때 머리(meta)를 씀. 끝나면 {meta, summary} 로 갈아씀 — 목록이 이것만 읽음
      cases.jsonl   발화 하나가 끝날 때마다 한 줄씩 덧붙임. 도중에 죽어도 끝난 줄이 남음
      run.json      끝났을 때 결과 한 벌 그대로 (run_evaluation.run 의 반환값과 같은 모양)
      summary.md    사람이 읽는 요약 (score.summary_text 가 만든 글을 받아 씀)

run.json 이 있으면 그것이 Test Run 이다. 없으면(도중에 죽음) meta.json 과 cases.jsonl 로
다시 세운다 — 합계는 score.summarize 가 줄에 적힌 판정을 다시 센다. 줄을 다시 채점하지 않는다.

**여기서 git 을 부르지 않는다.** 채점 · Resolve · GPU 도 안 본다. 파일만 다룬다.
"""

import datetime
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUTS_DIR = REPO_ROOT / "dev" / "evaluation" / "outputs"
OFFICIAL_DIR = OUTPUTS_DIR / "official_benchmark"
LOCAL_DIR = OUTPUTS_DIR / "local_benchmark"

# 목록 한 줄의 kind 칸 값.
OFFICIAL = "official"
LOCAL = "local"

META_FILE = "meta.json"
CASES_FILE = "cases.jsonl"
RUN_FILE = "run.json"
SUMMARY_FILE = "summary.md"

# 도중에 끝난 Test Run 을 다시 세웠을 때 meta.stopped 에 적는 말.
INCOMPLETE = "incomplete: run.json 없음 (도중에 끝남)"


def new_run_id(started: datetime.datetime, suite_name: str, attempt: int = 1) -> str:
    """Test Run id. <시작 시각>-<정답표 이름>, 두 번째부터 -<차례>.

    규칙  attempt 1 이면 「20260921-103000-test_suite_v2」, 2 면 「…-test_suite_v2-2」
          정답표 이름에서 영숫자 · _ 밖의 글자는 _ 로 바꿈
    """
    slug = re.sub(r"[^0-9A-Za-z_]+", "_", suite_name or "suite").strip("_") or "suite"
    base = f"{started:%Y%m%d-%H%M%S}-{slug}"
    return base if attempt == 1 else f"{base}-{attempt}"


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1)


class Recorder:
    """Test Run 하나를 폴더에 쓰는 자. run_evaluation.run 이 시작 · 발화마다 · 끝에 부름.

    규칙  폴더를 exist_ok=False 로 만들어 자리를 잡음. 이미 있으면 차례(-2, -3, …)를 붙여 다시 잡음.
          다른 Test Run 을 덮어쓰지 않음. 동시에 둘이 떠도 mkdir 이 하나만 이김
          case 는 줄마다 바로 flush. 도중에 죽어도 끝난 줄이 남음
    제약  결과를 고치거나 다시 채점하지 않는다
    """

    def __init__(self, root: Path, started: datetime.datetime, suite_name: str):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        attempt = 1
        while True:
            self.run_id = new_run_id(started, suite_name, attempt)
            self.dir = root / self.run_id
            try:
                self.dir.mkdir(exist_ok=False)
                return
            except FileExistsError:
                attempt += 1

    def start(self, meta: dict) -> None:
        (self.dir / META_FILE).write_text(_dump({"meta": meta, "summary": None}), encoding="utf-8")
        (self.dir / CASES_FILE).write_text("", encoding="utf-8")

    def case(self, row: dict) -> None:
        with (self.dir / CASES_FILE).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()

    def finish(self, result: dict, summary_md: str) -> None:
        (self.dir / RUN_FILE).write_text(_dump(result), encoding="utf-8")
        (self.dir / META_FILE).write_text(_dump({"meta": result["meta"], "summary": result["summary"]}), encoding="utf-8")
        (self.dir / SUMMARY_FILE).write_text(summary_md, encoding="utf-8")


def roots() -> dict[str, Path]:
    """벤치마크가 사는 두 자리. {kind: 폴더}. official 이 먼저."""
    return {OFFICIAL: OFFICIAL_DIR, LOCAL: LOCAL_DIR}


def _run_dir(run: str | Path, root: Path | None) -> Path:
    """run id 나 폴더 경로 -> 폴더. root 가 없으면 official · local 차례로 찾음."""
    path = Path(run)
    if path.is_dir():
        return path
    if root is not None:
        return Path(root) / str(run)
    for folder in roots().values():
        if (folder / str(run)).is_dir():
            return folder / str(run)
    return LOCAL_DIR / str(run)


def load_benchmark(run: str | Path, root: Path | None = None) -> dict:
    """저장한 Test Run 한 벌. run_evaluation.run 의 반환값과 같은 모양.

    입력  run id 또는 그 폴더 경로. root 가 없으면 official · local 두 자리에서 찾음
    규칙  run.json 이 있으면 그대로 읽음
          없으면 meta.json 머리와 cases.jsonl 줄로 다시 세움. 합계는 score.summarize 가 셈.
          meta.stopped 가 비었으면 INCOMPLETE 를 적음. 끝나지 않은 마지막 줄(잘린 JSON)은 버림
          폴더가 없으면 FileNotFoundError
    제약  줄을 다시 채점하지 않는다
    """
    folder = _run_dir(run, root)
    if (folder / RUN_FILE).is_file():
        return json.loads((folder / RUN_FILE).read_text(encoding="utf-8"))
    if not (folder / META_FILE).is_file():
        raise FileNotFoundError(f"Test Run 이 없다: {folder}")

    from dev.evaluation.engine import score

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
    return {"meta": meta, "summary": score.summarize(rows, labels), "cases": rows}


def _list_one(folder: Path, kind: str) -> list[dict]:
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
            "kind": kind,
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
    return entries


def list_benchmarks(root: Path | None = None) -> list[dict]:
    """저장한 Test Run 목록. 최근 것이 앞.

    입력  root 가 있으면 그 폴더 하나만(kind 는 local). 없으면 official · local 두 자리
    출력  [{run_id, kind, path, complete, started_at, dataset_id, suite_label, suite_name, runs, passed, stopped}]
          kind 는 official · local. complete 는 run.json 이 있나. runs · passed 는 끝난 것만 (도중이면 None)
    규칙  meta.json 만 읽음. 읽을 수 없는 폴더는 건너뜀. 파일을 옮기거나 베끼지 않음
    """
    if root is not None:
        entries = _list_one(Path(root), LOCAL)
    else:
        entries = [entry for kind, folder in roots().items() for entry in _list_one(folder, kind)]
    return sorted(entries, key=lambda entry: entry["started_at"] or "", reverse=True)
