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

official · local 은 보관 갈래다. run_id 에 들어가지 않는다. official 로 올리는 것은 사람이
폴더를 run_id 그대로 옮겨서 한다. 여기에 올리는 기능을 두지 않는다.

run_id 는 「<시작 시각>-<정답표 이름>」(20260921-132500-test_suite_v2). 두 자리를 통틀어 하나뿐이다.
같은 이름이 어느 자리에든 있으면 -2, -3, … 을 붙인다. 무작위 글자를 붙이지 않는다.

    도는 동안      <run_id>/meta.json     시작할 때 쓴 머리(meta). 도중에 죽으면 복구에 씀
                            cases.jsonl   발화 하나가 끝날 때마다 한 줄씩 덧붙임
    중단됨         <run_id>/meta.json     머리에 멈춘 까닭(stopped) · 멈춘 시각 · 잰 시간을 더해 다시 씀
                            cases.jsonl   끝난 줄 그대로. 이어 실행하면 같은 파일에 덧붙임
    끝나면         <run_id>/run.json      결과 한 벌 그대로 (run_evaluation.run 의 반환값과 같은 모양)
                                          잴 것을 다 잰 때만 씀. run.json 을 다 쓴 뒤에만 meta.json · cases.jsonl 을 지움

run.json 이 있으면 그것이 Test Run 이다(끝남). 남은 meta.json · cases.jsonl 은 안 읽는다.
없으면(중단 · 도중에 죽음) meta.json 과 cases.jsonl 로 다시 세운다 — 합계는 score.summarize 가 줄에 적힌
판정을 다시 센다. 줄을 다시 채점하지 않는다. 끝나지 않은 것에 run.json 을 지어 쓰지 않는다.
끝나지 않은 local 기록은 같은 폴더 · 같은 run_id 로 이어 잴 수 있다(Recorder.reopen). 새 폴더를 안 만든다.

사람이 읽는 보고서(요약 글 · 표 · 그림)는 아직 형식이 정해지지 않아 만들지 않는다.

**여기서 git 을 부르지 않는다.** 채점 · Resolve · GPU 도 안 본다. 파일만 다룬다.
"""

import datetime
import json
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUTS_DIR = REPO_ROOT / "dev" / "evaluation" / "outputs"
OFFICIAL_DIR = OUTPUTS_DIR / "official_benchmark"
LOCAL_DIR = OUTPUTS_DIR / "local_benchmark"

# 목록 한 줄의 kind 칸 값. 보관 갈래다.
OFFICIAL = "official"
LOCAL = "local"
KINDS = (OFFICIAL, LOCAL)

META_FILE = "meta.json"
CASES_FILE = "cases.jsonl"
RUN_FILE = "run.json"

# 도중에 끝난 Test Run 을 다시 세웠을 때 meta.stopped 에 적는 말.
INCOMPLETE = "incomplete: run.json 없음 (도중에 끝남)"


class DuplicateRunId(ValueError):
    """같은 run_id 가 official 과 local 두 자리에 다 있다. 보관 상태가 틀린 것이다."""


def new_run_id(started: datetime.datetime, suite_name: str, attempt: int = 1) -> str:
    """Test Run id. <시작 시각>-<정답표 이름>, 두 번째부터 -<차례>.

    규칙  attempt 1 이면 「20260921-103000-test_suite_v2」, 2 면 「…-test_suite_v2-2」
          정답표 이름에서 영숫자 · _ 밖의 글자는 _ 로 바꿈
    제약  무작위 글자를 붙이지 않는다
    """
    slug = re.sub(r"[^0-9A-Za-z_]+", "_", suite_name or "suite").strip("_") or "suite"
    base = f"{started:%Y%m%d-%H%M%S}-{slug}"
    return base if attempt == 1 else f"{base}-{attempt}"


def roots() -> dict[str, Path]:
    """벤치마크가 사는 두 자리. {kind: 폴더}. 부를 때 모듈 값을 읽음."""
    return {OFFICIAL: OFFICIAL_DIR, LOCAL: LOCAL_DIR}


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1)


def _write_atomic(path: Path, text: str) -> None:
    """파일 하나를 다 쓰거나 안 씀. 옆에 임시 파일을 쓰고 fsync 한 뒤 os.replace."""
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class Recorder:
    """Test Run 하나를 폴더에 쓰는 자. run_evaluation.run 이 시작 · 발화마다 · 끝에 부름.

    규칙  run_id 는 official · local 두 자리와 root 를 통틀어 아직 없는 이름. 있으면 -2, -3, …
          폴더를 exist_ok=False 로 만들어 자리를 잡음. 동시에 둘이 떠도 mkdir 이 하나만 이김
          case 는 줄마다 바로 flush. 도중에 죽어도 끝난 줄이 남음
          interrupt 는 meta.json 만 다시 씀(멈춘 까닭 등). cases.jsonl 은 그대로 둠
          finish 는 run.json 을 다 쓴 뒤에만 meta.json · cases.jsonl 을 지움
          reopen 은 끝나지 않은 폴더를 그대로 잡음. 이름 · 폴더를 새로 안 만듦
    제약  다른 Test Run 을 덮어쓰지 않는다. 결과를 고치거나 다시 채점하지 않는다
    """

    @classmethod
    def reopen(cls, folder: Path) -> "Recorder":
        """끝나지 않은 Test Run 폴더를 이어 쓰는 자. run.json 이 있거나 meta.json 이 없으면 ValueError."""
        folder = Path(folder)
        if (folder / RUN_FILE).is_file() or not (folder / META_FILE).is_file():
            raise ValueError(f"이어 쓸 수 있는 끝나지 않은 Test Run 이 아니다: {folder}")
        recorder = cls.__new__(cls)
        recorder.run_id, recorder.dir = folder.name, folder
        return recorder

    def __init__(self, root: Path, started: datetime.datetime, suite_name: str):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        namespace = {Path(folder) for folder in roots().values()} | {root}
        attempt = 1
        while True:
            self.run_id = new_run_id(started, suite_name, attempt)
            self.dir = root / self.run_id
            attempt += 1
            if any((folder / self.run_id).exists() for folder in namespace):
                continue
            try:
                self.dir.mkdir(exist_ok=False)
                return
            except FileExistsError:
                continue

    def start(self, meta: dict) -> None:
        _write_atomic(self.dir / META_FILE, _dump({"meta": meta}))
        (self.dir / CASES_FILE).write_text("", encoding="utf-8")

    def case(self, row: dict) -> None:
        with (self.dir / CASES_FILE).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()

    def interrupt(self, meta: dict) -> None:
        """끝나지 않고 멈춘 머리를 meta.json 에 다시 씀. cases.jsonl 은 안 건드림."""
        _write_atomic(self.dir / META_FILE, _dump({"meta": meta}))

    def finish(self, result: dict) -> None:
        _write_atomic(self.dir / RUN_FILE, _dump(result))
        for name in (META_FILE, CASES_FILE):
            (self.dir / name).unlink(missing_ok=True)


def run_dir(kind: str, run_id: str) -> Path:
    """kind · run_id 가 가리키는 폴더. 모르는 kind 면 ValueError."""
    if kind not in KINDS:
        raise ValueError(f"모르는 보관 갈래: {kind!r} (official · local 중 하나)")
    return roots()[kind] / str(run_id)


def duplicate_run_ids() -> set[str]:
    """official 과 local 두 자리에 다 있는 run_id. 정상이면 빈 집합."""
    found = {}
    for kind, folder in roots().items():
        found[kind] = {path.name for path in folder.iterdir() if path.is_dir()} if folder.is_dir() else set()
    return found[OFFICIAL] & found[LOCAL]


def _read_rows(folder: Path) -> tuple[list[dict], bool]:
    """cases.jsonl 의 끝난 줄들과, 끝이 잘렸나(마지막 줄이 깨졌거나 줄바꿈 없이 끝남).

    규칙  깨진 줄을 만나면 거기서 멈춤. 그 뒤는 안 읽음. 파일이 없으면 ([], False)
    """
    path = folder / CASES_FILE
    if not path.is_file():
        return [], False
    text = path.read_text(encoding="utf-8")
    rows, torn = [], bool(text) and not text.endswith("\n")
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            torn = True
            break
    return rows, torn


def read_incomplete(folder: Path) -> dict:
    """끝나지 않은 Test Run 한 벌을 이어 재려고 읽음. {"meta", "rows", "torn"}.

    규칙  meta 는 meta.json 머리 그대로(INCOMPLETE 를 채우지 않음). rows 는 cases.jsonl 의 끝난 줄
          torn 은 끝이 잘렸나. 잘렸으면 이어 쓰기 전에 repair_rows 로 끝난 줄만 남김
          run.json 이 있거나 meta.json 이 없으면 ValueError
    제약  줄을 다시 채점하지 않는다
    """
    folder = Path(folder)
    if (folder / RUN_FILE).is_file():
        raise ValueError(f"끝난 Test Run 이다: {folder}")
    if not (folder / META_FILE).is_file():
        raise ValueError(f"meta.json 이 없다: {folder}")
    meta = json.loads((folder / META_FILE).read_text(encoding="utf-8"))["meta"]
    rows, torn = _read_rows(folder)
    return {"meta": meta, "rows": rows, "torn": torn}


def repair_rows(folder: Path, rows: list[dict]) -> None:
    """cases.jsonl 을 끝난 줄만으로 다시 씀. 잘린 끝 뒤에 새 줄을 덧붙이면 그 줄까지 못 읽게 되므로."""
    _write_atomic(Path(folder) / CASES_FILE, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def read_run_dir(folder: Path) -> dict:
    """폴더 하나의 Test Run. run_evaluation.run 의 반환값과 같은 모양.

    규칙  run.json 이 있으면 그대로 읽음. 남은 meta.json · cases.jsonl 은 안 읽음
          없으면 meta.json 머리와 cases.jsonl 줄로 다시 세움. 합계는 score.summarize 가 셈.
          meta.stopped 가 비었으면 INCOMPLETE 를 적음. 끝나지 않은 마지막 줄(잘린 JSON)은 버림
          둘 다 없으면 FileNotFoundError
    제약  줄을 다시 채점하지 않는다. 끝나지 않은 것에 run.json 을 쓰지 않는다
    """
    folder = Path(folder)
    if (folder / RUN_FILE).is_file():
        return json.loads((folder / RUN_FILE).read_text(encoding="utf-8"))
    if not (folder / META_FILE).is_file():
        raise FileNotFoundError(f"Test Run 이 없다: {folder}")

    from dev.evaluation.engine import score

    head = json.loads((folder / META_FILE).read_text(encoding="utf-8"))["meta"]
    rows, _torn = _read_rows(folder)
    meta = {**head, "finished_at": head.get("finished_at"), "stopped": head.get("stopped") or INCOMPLETE}
    labels = tuple((head.get("suite") or {}).get("group_labels") or ())
    return {"meta": meta, "summary": score.summarize(rows, labels), "cases": rows}


def load_benchmark(kind: str, run_id: str) -> dict:
    """저장한 Test Run 한 벌. 어느 자리(kind)의 것인지를 부르는 쪽이 밝힘.

    입력  kind 는 official · local. run_id 는 폴더 이름
    규칙  그 자리의 폴더만 읽음 (read_run_dir). 다른 자리로 돌아가 찾지 않음
          같은 run_id 가 두 자리에 다 있으면 DuplicateRunId. 하나를 골라 주지 않음
          폴더가 없으면 FileNotFoundError
    """
    if str(run_id) in duplicate_run_ids():
        raise DuplicateRunId(f"run_id 가 official 과 local 에 다 있다: {run_id}")
    return read_run_dir(run_dir(kind, run_id))


# 목록 한 줄은 run.json(수 MB)을 통째로 읽어 만든다. 화면이 다시 그릴 때마다 읽지 않게
# 파일 (경로, 크기, 고친 시각) 이 같으면 지난번에 만든 줄을 그대로 씀.
_ENTRY_CACHE: dict[tuple, dict] = {}


def planned_runs(meta: dict) -> int | None:
    """Test Run 이 잴 수 전체. 고른 발화 수 × runs. meta 에 칸이 없으면 None."""
    selected = (meta.get("suite") or {}).get("selected_case_ids")
    runs = meta.get("runs")
    if not isinstance(selected, list) or not isinstance(runs, int):
        return None
    return len(selected) * runs


def _entry(path: Path, kind: str) -> dict | None:
    """폴더 하나의 목록 줄. 읽을 수 없으면 None."""
    complete = (path / RUN_FILE).is_file()
    source = path / (RUN_FILE if complete else META_FILE)
    if not source.is_file():
        return None
    stat = source.stat()
    key = (str(source), stat.st_size, stat.st_mtime_ns)
    if not complete and (path / CASES_FILE).is_file():
        rows_stat = (path / CASES_FILE).stat()
        key += (rows_stat.st_size, rows_stat.st_mtime_ns)
    if key not in _ENTRY_CACHE:
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(document, dict) or not isinstance(document.get("meta"), dict):
            return None
        meta = document["meta"]
        suite = meta.get("suite") or {}
        total = ((document.get("summary") or {}).get("total") or {}) if complete else {}
        _ENTRY_CACHE[key] = {
            "started_at": meta.get("started_at"),
            "dataset_id": suite.get("dataset_id"),
            "suite_label": suite.get("label") or suite.get("name"),
            "suite_name": suite.get("name"),
            "runs": total.get("runs"),
            "passed": total.get("passed"),
            "stopped": meta.get("stopped"),
            "done": total.get("runs") if complete else len(_read_rows(path)[0]),
            "planned": planned_runs(meta),
        }
    return {"run_id": path.name, "kind": kind, "path": str(path), "complete": complete, **_ENTRY_CACHE[key]}


def list_benchmarks() -> list[dict]:
    """저장한 Test Run 목록. official · local 을 한 줄로 합쳐 최근 것이 앞.

    출력  [{run_id, kind, path, complete, duplicate, started_at, dataset_id, suite_label, suite_name, runs, passed, stopped,
            done, planned}]
          run_id 는 폴더 이름 그대로. kind 는 official · local
          complete 는 run.json 이 있나. 끝난 것은 run.json 만으로 목록에 오름
          끝나지 않은 것(meta.json 만)도 complete 거짓으로 오름. runs · passed 는 None
          done 은 끝난 줄 수(끝나지 않은 것은 cases.jsonl 의 줄 수), planned 는 잴 수 전체(planned_runs)
          duplicate 는 같은 run_id 가 다른 자리에도 있나. 목록에서 빼지 않고 표시만 함
    규칙  두 자리를 섞어 started_at 으로 정렬. kind 로 먼저 가르지 않음
          읽을 수 없는 폴더(run.json · meta.json 이 없거나 깨짐)는 건너뜀. 파일을 옮기거나 베끼지 않음
    """
    entries = []
    for kind, folder in roots().items():
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if path.is_dir():
                entry = _entry(path, kind)
                if entry is not None:
                    entries.append(entry)
    counted: dict[str, int] = {}
    for entry in entries:
        counted[entry["run_id"]] = counted.get(entry["run_id"], 0) + 1
    for entry in entries:
        entry["duplicate"] = counted[entry["run_id"]] > 1
    return sorted(entries, key=lambda entry: entry["started_at"] or "", reverse=True)


def storage_problems() -> list[str]:
    """보관 자리가 틀린 상태를 사람이 읽을 문장으로. 정상이면 빈 목록.

    규칙  official 자리가 없으면 한 줄 (Git 이 추적하는 폴더라 없으면 저장소가 틀린 것임)
          같은 run_id 가 두 자리에 다 있으면 그 이름마다 한 줄
          local 자리가 없는 것은 문제가 아님 (첫 실행이 만듦)
    """
    problems = []
    if not OFFICIAL_DIR.is_dir():
        problems.append(f"공식 기록 폴더가 없습니다: {OFFICIAL_DIR}")
    problems += [f"같은 실행 기록 id 가 공식 · 로컬에 다 있습니다: {run_id}" for run_id in sorted(duplicate_run_ids())]
    return problems
