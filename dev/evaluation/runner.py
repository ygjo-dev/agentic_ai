"""정답표(evaluation suite)로 발화 해석을 재고 결과를 JSON 한 벌로 남기는 공통 runner.

    python dev/evaluation/runner.py                        정답표 전체 · 1회 · materialize 포함
    python dev/evaluation/runner.py --runs 3 --only 2,4    고른 발화만 여러 번
    python dev/evaluation/runner.py --context bbox         materialize 에 실을 지도 문맥
    python dev/evaluation/runner.py --no-materialize       /resolve 만
    python dev/evaluation/runner.py --out 결과.json        결과 파일 자리
    python dev/evaluation/runner.py --cooldown-every 6     6번마다 5초 쉼 (발열 · 팬 소음)
    python dev/evaluation/runner.py --suite dev/evaluation/test_suite_v2.yaml --gpu gate
                                                           테스트 세트 v2 · 사무실 조용 정책
    python dev/evaluation/runner.py --no-save              Test Run 을 test_runs 에 안 남김

화면(app/ui 테스트 탭)은 run_dataset 으로 같은 run 을 부른다. 판정 · 결과 모양이 창구와 같다.

**check_resolve 와 같은 자를 쓴다.** 정답표는 `dev/evaluation/suite.py` 로 읽고, 판정(`_grade`) ·
이름 있는 값 표기(`_spoken_values_of` · `NULL_MARK`) · 지도 문맥(`_context_payload`) · 부르는
주소와 timeout · 역할 줄은 `dev/tools/check_resolve.py` 것을 그대로 부른다. 규칙을 베끼면 두
자가 조용히 어긋난다.

check_resolve 는 사람이 읽을 표를 찍고, 이것은 기계가 읽을 결과 한 벌을 낸다. 화면은 그 결과를
읽기만 한다 — 발화 판정(passed · failure_stage)도 여기서 정해 결과에 싣는다.

**발화 판정은 고르기와 정답표에 적은 값만 본다.** materialize 는 따로 싣지만 범위 안 판정에 안 들어간다.
범위 밖 발화(정답표 판 2 의 out_of_scope)는 기대 recipe 가 없고, 결과(outcome)가 정답표가 받아들이는
것 중 하나인지로 가른다. outcome 은 resolve status 이고, SELECT 면 그 workflow 의 materialize 판정이다
— 「기능은 섰는데 값이 모자람(MISSING_ARGUMENT)」을 runtime 이 가르는 자리가 거기뿐이다.

한 번 잰 결과 한 벌이 Test Run 이고 줄 하나가 Case Result 다 (낱말은 test_runs 머리 주석).
save_dir 를 주면 test_runs.Recorder 가 폴더 하나에 남긴다. monitor 를 주면 GPU 기록이 meta.gpu 에 실린다.

**MCP 도구를 부르지 않는다.** `/resolve` 를 부르고, 고른 recipe 를 workflow_materializer 로 KRRI
native workflow 까지만 만든다. Gateway 실행은 `check_resolve --execute` 의 일이다.

결과는 `dev/tools/sweep_out/` 에 둔다 (`.gitignore`). Test Run 은 그 아래 `test_runs/<run_id>/` 다.
"""

import argparse
import datetime
import hashlib
import json
import math
import statistics
import subprocess
import sys
import time
import zoneinfo
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from dev.evaluation import suite as suite_module  # noqa: E402
from dev.tools import check_resolve  # noqa: E402

# 결과 JSON 의 판. 칸의 뜻을 바꾸면 올린다.
# 3: 줄에 scope · recipe_group · outcome · oos_correct · timing.started_at, summary 에 metrics ·
#    latency · recipes, meta 에 run_id · elapsed_s · gpu · suite.name · suite.group_labels
RESULT_VERSION = 3

OUT_DIR = REPO_ROOT / "dev" / "tools" / "sweep_out"

# check_resolve 의 네 칸 -> 결과에 적는 이름. 칸의 뜻은 check_resolve 머리 주석에 있다.
GRADES = {
    check_resolve.HIT: "HIT",
    check_resolve.NEAR: "NEAR",
    check_resolve.MISS: "MISS",
    check_resolve.UNATTACHED: "UNATTACHED",
}

# 고른 recipe 가 없어 materialize 하지 않은 자리.
NOT_SELECTED = "NOT_SELECTED"

# /resolve 응답에서 고르기에 속한 칸. 나머지 칸이 발화에서 뽑은 값이다.
SELECTION_KEYS = ("reason", "candidate_recipe_ids", "status", "recipe_id", "paths")

# 발화 하나가 실패한 단계. 결과 칸 failure_stage 의 값이다.
# scope 는 범위 밖 발화가 받아들이는 결과로 안 끝난 것이다.
STAGE_FUNCTION = "function"
STAGE_INPUT = "input"
STAGE_SCOPE = "scope"
STAGE_ERROR = "error"
STAGES = (STAGE_FUNCTION, STAGE_INPUT, STAGE_SCOPE, STAGE_ERROR)

# 결과 줄의 scope 칸.
SCOPE_IN = "in_scope"
SCOPE_OUT = "out_of_scope"


class StopRun(Exception):
    """평가를 여기서 멈춘다. 까닭이 meta.stopped 에 남고 거기까지의 결과는 그대로 나감.

    monitor(GPU 열 제한 등)나 progress 가 던짐. 다른 예외는 삼키지 않음
    """

KST = zoneinfo.ZoneInfo("Asia/Seoul")


def resolve_via_api(utterance: str) -> dict:
    """POST /resolve 한 번의 응답 본문.

    규칙  check_resolve._call_resolve 와 같은 주소 · 같은 timeout · 같은 매개변수
          서버에 못 닿으면 ServerDown. 재시도하지 않음
    """
    try:
        response = check_resolve.requests.post(
            f"{check_resolve._base_url()}/resolve",
            params={"utterance": utterance},
            timeout=check_resolve.TIMEOUT,
        )
    except check_resolve.requests.exceptions.ConnectionError as exc:
        raise check_resolve.ServerDown(str(exc)) from exc
    response.raise_for_status()
    return response.json()


def spoken_fields(expected: dict, response: dict) -> list[dict]:
    """정답표에 적은 이름 있는 값마다 맞았나.

    출력  [{name, expected, actual, correct}] 정답표에 적은 차례
    규칙  check_resolve._spoken_value_verdict 와 같은 대조. 양쪽을 표 글자
          (check_resolve._value_mark)로 바꿔 맞댐. 기대 None 은 NULL_MARK 라 null 이 정답임
          정답표에 적은 이름만 봄. 적지 않은 이름은 응답에 무엇이 와도 안 봄
          이름을 고정 목록으로 거르지 않음. 새 이름도 같은 규칙으로 맞댐
    """
    return [
        {
            "name": name,
            "expected": value,
            "actual": response.get(name),
            "correct": check_resolve._value_mark(response.get(name)) == check_resolve._value_mark(value),
        }
        for name, value in expected.items()
    ]


def verdict(recipe_correct: bool, spoken_correct: bool | None, error: str | None) -> tuple[bool, str | None]:
    """발화 하나의 최종 판정.

    출력  (성공 여부, 실패 단계). 성공이면 단계는 None
    규칙  실행 오류면 STAGE_ERROR. 모델 출력이 없음
          기능 선택이 적중(HIT)이 아니면 STAGE_FUNCTION. 값이 함께 틀려도 이쪽임
          기능은 맞고 정답표에 적은 값 중 하나라도 틀리면 STAGE_INPUT
          정답표에 적은 값이 없으면(spoken_correct None) 기능 선택만으로 가름
    제약  materialize 결과를 보지 않는다.
          발화 판정은 고르기와 뽑기를 재는 것임. 배선 · READY 여부는 실행 쪽 판정임
    """
    if error:
        return False, STAGE_ERROR
    if not recipe_correct:
        return False, STAGE_FUNCTION
    if spoken_correct is False:
        return False, STAGE_INPUT
    return True, None


def outcome_of(status: str, built: dict | None) -> str:
    """발화 하나가 어디서 끝났나. 범위 밖 판정이 읽는 값.

    규칙  SELECT 가 아니면 status 그대로 (CLARIFY · NO_MATCH)
          SELECT 이고 materialize 했으면 그 판정 (READY · MISSING_ARGUMENT · …)
          materialize 를 안 했으면 SELECT
    """
    if status != "SELECT":
        return status
    if built and built.get("status") not in (None, NOT_SELECTED):
        return built["status"]
    return status


def materialized(response: dict, context: dict | None, now: datetime.datetime) -> dict:
    """고른 recipe 의 KRRI native workflow. MCP 는 안 부름.

    규칙  status 가 SELECT 이고 recipe_id 가 있을 때만 만듦. 아니면 NOT_SELECTED
          게시 오류(PlanError 등)는 결과 한 벌을 끝까지 내려고 error 칸에 적음
    """
    from execution import workflow_materializer

    recipe_id = response.get("recipe_id")
    if response.get("status") != "SELECT" or not recipe_id:
        return {"status": NOT_SELECTED, "recipe_id": recipe_id, "workflow": None}
    try:
        result = workflow_materializer.materialize(recipe_id, response, context, now)
    except Exception as exc:  # noqa: BLE001 — 게시 오류도 결과의 하나로 남긴다.
        return {"status": "ERROR", "recipe_id": recipe_id, "workflow": None, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "status": result["status"],
        "recipe_id": recipe_id,
        "missing": result["missing"],
        "workflow": result["workflow"],
        "nodes": result["nodes"],
        "commands": result["commands"],
    }


def run_case(case: dict, label: str, run: int, resolve, context: dict | None, materialize: bool, now) -> dict:
    """발화 하나를 한 번 잰 결과 (Case Result).

    규칙  후보 집합은 recipe_id 와 candidate_recipe_ids 를 합친 것. _call_resolve 와 같음
          범위 안: 판정은 check_resolve._grade. 발화 판정(passed · failure_stage)은 verdict.
          materialize 를 안 봄
          범위 밖: grade · recipe_correct 는 None. outcome 이 expected.outcomes 에 있으면 성공,
          아니면 STAGE_SCOPE
          오류는 「오류: 예외 이름」 으로 넘겨 못 붙음이 됨 (범위 밖이면 grade None)
          actual.spoken 은 응답에서 SELECTION_KEYS 를 뺀 칸 전부. 이름을 고정 목록으로 거르지 않음
          timing.started_at 은 부르기 직전 시각. resolve_s 는 resolve 호출 하나만 감쌈
          ServerDown 은 삼키지 않음. 부르는 쪽이 멈춤
    """
    expected = case["expected"]
    scoped = suite_module.in_scope(case)
    wanted_spoken = expected.get("spoken")
    row = {
        "case_id": case["id"],
        "group": case["group"],
        "group_label": label,
        "scope": SCOPE_IN if scoped else SCOPE_OUT,
        "recipe_group": expected["recipe_ids"][0] if scoped else None,
        "utterance": case["utterance"],
        "run": run,
        "expected": {"recipe_ids": list(expected.get("recipe_ids") or []), "spoken": wanted_spoken},
    }
    if not scoped:
        row["expected"].update({"category": expected["category"], "outcomes": list(expected["outcomes"])})

    started_at = datetime.datetime.now(KST).isoformat(timespec="milliseconds")
    started = time.perf_counter()
    try:
        response = resolve(case["utterance"])
    except check_resolve.ServerDown:
        raise
    except Exception as exc:  # noqa: BLE001 — 오류도 결과의 하나로 남긴다.
        grade = check_resolve._grade(f"오류: {type(exc).__name__}", "-", set(expected.get("recipe_ids") or []))
        error = f"{type(exc).__name__}: {exc}"
        passed, stage = verdict(False, False if wanted_spoken else None, error)
        return {
            **row,
            "actual": None,
            "grade": GRADES[grade] if scoped else None,
            "recipe_correct": False if scoped else None,
            "spoken_fields": [],
            "spoken_correct": False if wanted_spoken else None,
            "outcome": None,
            "oos_correct": None if scoped else False,
            "passed": passed,
            "failure_stage": stage,
            "materialize": None,
            "timing": {"started_at": started_at, "resolve_s": round(time.perf_counter() - started, 3), "materialize_s": None},
            "error": error,
        }
    resolve_s = round(time.perf_counter() - started, 3)

    found = frozenset(rid for rid in [response.get("recipe_id"), *(response.get("candidate_recipe_ids") or [])] if rid)
    status = response.get("status") or "-"

    built, materialize_s = None, None
    if materialize:
        started = time.perf_counter()
        built = materialized(response, context, now)
        materialize_s = round(time.perf_counter() - started, 3)
    outcome = outcome_of(status, built)

    if scoped:
        grade = GRADES[check_resolve._grade(found, status, set(expected["recipe_ids"]))]
        fields = spoken_fields(wanted_spoken or {}, response)
        spoken_correct = all(field["correct"] for field in fields) if fields else None
        recipe_correct = grade == GRADES[check_resolve.HIT]
        passed, stage = verdict(recipe_correct, spoken_correct, None)
        oos_correct = None
    else:
        grade, fields, spoken_correct, recipe_correct = None, [], None, None
        oos_correct = outcome in expected["outcomes"]
        passed, stage = (True, None) if oos_correct else (False, STAGE_SCOPE)

    return {
        **row,
        "actual": {
            "status": status,
            "recipe_id": response.get("recipe_id"),
            "candidate_recipe_ids": list(response.get("candidate_recipe_ids") or []),
            "found_recipe_ids": sorted(found),
            "spoken": {name: value for name, value in response.items() if name not in SELECTION_KEYS},
            "reason": response.get("reason"),
        },
        "grade": grade,
        "recipe_correct": recipe_correct,
        "spoken_fields": fields,
        "spoken_correct": spoken_correct,
        "outcome": outcome,
        "oos_correct": oos_correct,
        "passed": passed,
        "failure_stage": stage,
        "materialize": built,
        "timing": {"started_at": started_at, "resolve_s": resolve_s, "materialize_s": materialize_s},
        "error": None,
    }


def latency(rows: list[dict]) -> dict | None:
    """resolve 한 번에 걸린 시간(초)의 분포. 잰 줄이 없으면 None.

    출력  {count, min, median, p95, max, total}. p95 는 nearest-rank
    """
    values = sorted(row["timing"]["resolve_s"] for row in rows if (row.get("timing") or {}).get("resolve_s") is not None)
    if not values:
        return None
    rank = max(1, math.ceil(0.95 * len(values)))
    return {
        "count": len(values),
        "min": values[0],
        "median": round(statistics.median(values), 3),
        "p95": values[rank - 1],
        "max": values[-1],
        "total": round(sum(values), 3),
    }


def _pair(correct: int, total: int) -> dict:
    return {"correct": correct, "total": total}


def metrics(tally: dict) -> dict:
    """tally 한 벌에서 읽는 여섯 지표. {이름: {correct, total}}.

    규칙  selection        범위 안 적중(HIT) / 범위 안 시행
          semantic_fields  채점한 이름 있는 값 칸 중 맞은 칸 / 채점한 칸
          semantic_cases   값을 채점한 발화 중 전부 맞은 발화 / 값을 채점한 발화
          joint            범위 안 발화 성공(기능 + 값) / 범위 안 시행
          oos              범위 밖 성공 / 범위 밖 시행
          ready            범위 안에서 materialize 가 READY 인 것 / materialize 한 것
    제약  묶음을 가로질러 하나의 백분율로 합치지 않는다. 이것은 넘겨받은 tally 한 벌의 값임
    """
    return {
        "selection": _pair(tally[GRADES[check_resolve.HIT]], tally["in_scope_runs"]),
        "semantic_fields": _pair(tally["field_hits"], tally["field_runs"]),
        "semantic_cases": _pair(tally["spoken_hits"], tally["spoken_runs"]),
        "joint": _pair(tally["in_scope_passed"], tally["in_scope_runs"]),
        "oos": _pair(tally["oos_passed"], tally["oos_runs"]),
        "ready": _pair(tally["in_scope_ready"], tally["in_scope_materialized"]),
    }


def summarize(rows: list[dict], labels: tuple) -> dict:
    """묶음마다 네 칸 · 이름 있는 값 · 발화 판정 · 범위 밖 · materialize 판정을 셈.

    출력  {groups: {묶음 이름: tally}, total: tally, metrics, latency, recipes}
          recipes 는 {기대 recipe: {runs, passed, hit}}. 범위 안만
    규칙  묶음을 한 백분율로 합치지 않음. 합계는 따로 한 칸
          네 칸(HIT · NEAR · MISS · UNATTACHED)을 더하면 범위 안 시행 횟수여야 함
          passed 와 failure_stages 넷을 더하면 시행 횟수임
          범위 밖 줄은 네 칸 · 값 칸에 안 들어가고 oos_* 에만 들어감
    """
    def tally(group_rows):
        inside = [row for row in group_rows if row.get("scope", SCOPE_IN) == SCOPE_IN]
        outside = [row for row in group_rows if row.get("scope") == SCOPE_OUT]
        grades = Counter(row["grade"] for row in inside)
        spoken = [row["spoken_correct"] for row in inside if row["spoken_correct"] is not None]
        fields = [field["correct"] for row in inside for field in row.get("spoken_fields") or []]
        built = Counter((row["materialize"] or {}).get("status") for row in group_rows if row["materialize"])
        inside_built = [(row["materialize"] or {}).get("status") for row in inside if row["materialize"]]
        stages = Counter(row["failure_stage"] for row in group_rows if not row["passed"])
        categories = {}
        for row in outside:
            entry = categories.setdefault(row["expected"]["category"], {"runs": 0, "passed": 0})
            entry["runs"] += 1
            entry["passed"] += bool(row["passed"])
        return {
            "runs": len(group_rows),
            "in_scope_runs": len(inside),
            **{name: grades.get(name, 0) for name in GRADES.values()},
            "spoken_hits": sum(spoken),
            "spoken_runs": len(spoken),
            "field_hits": sum(fields),
            "field_runs": len(fields),
            "passed": sum(1 for row in group_rows if row["passed"]),
            "in_scope_passed": sum(1 for row in inside if row["passed"]),
            "oos_runs": len(outside),
            "oos_passed": sum(1 for row in outside if row["passed"]),
            "oos_categories": dict(sorted(categories.items())),
            "failure_stages": {stage: stages.get(stage, 0) for stage in STAGES},
            "materialize": dict(sorted(built.items())),
            "in_scope_ready": sum(1 for status in inside_built if status == workflow_ready()),
            "in_scope_materialized": len(inside_built),
            "errors": sum(1 for row in group_rows if row["error"]),
        }

    recipes = {}
    for row in rows:
        if row.get("scope", SCOPE_IN) != SCOPE_IN:
            continue
        entry = recipes.setdefault(row.get("recipe_group") or row["expected"]["recipe_ids"][0], {"runs": 0, "passed": 0, "hit": 0})
        entry["runs"] += 1
        entry["passed"] += bool(row["passed"])
        entry["hit"] += row["grade"] == GRADES[check_resolve.HIT]

    groups = {label: tally([row for row in rows if row["group_label"] == label]) for label in labels}
    total = tally(rows)
    return {
        "groups": {label: value for label, value in groups.items() if value["runs"]},
        "total": total,
        "metrics": metrics(total),
        "latency": latency(rows),
        "recipes": dict(sorted(recipes.items())),
    }


def workflow_ready() -> str:
    """materialize 가 부를 수 있다고 한 판정 이름. workflow_materializer.READY."""
    from execution import workflow_materializer

    return workflow_materializer.READY


def _file_record(path: Path) -> dict:
    """실행 조건에 적을 파일 하나. {path, sha256}.

    규칙  저장소 안이면 저장소 뿌리에서의 상대 경로, 밖이면 절대 경로
          파일이 없으면 sha256 은 None
    """
    path = Path(path)
    try:
        shown = str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        shown = str(path)
    return {"path": shown, "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}


def conditions() -> dict:
    """이번 평가를 잰 조건. 모델 · prompt · 응답 schema · menu 파일과 그 sha256.

    출력  {model, provider, role_version, inference, prompt, response_schema, menu}. 파일 셋은 _file_record 꼴
          역할 설정을 못 읽으면 {error} 하나
    규칙  이 저장소의 역할 manifest 와 게시 menu 를 읽음. 창구가 같은 사본에서 떠 있을 때
          창구가 쓰는 판과 같음. /resolve 응답에는 판이 안 실림 (_role_label 과 같음)
          prompt · schema 경로는 역할 이름과 판 번호가 정함. role_config 의 규칙 그대로
    제약  못 읽었다고 평가를 멈추지 않는다. 재는 것은 창구임
    """
    import paths
    from llm_engine.role_config import RESOLVE, get_role_config

    try:
        role = get_role_config(RESOLVE)
    except ValueError as error:
        return {"error": f"역할 {RESOLVE} 못 읽음 ({error})"}
    role_dir = paths.ROLES_DIR / RESOLVE
    return {
        "model": role.model,
        "provider": role.provider,
        "role_version": role.version,
        "inference": dict(role.inference),
        "prompt": _file_record(role_dir / "prompts" / f"v{role.prompt_version}.yaml"),
        "response_schema": _file_record(role_dir / "response_schemas" / f"v{role.response_schema_version}.yaml"),
        "menu": _file_record(paths.MENU_YAML_PATH),
    }


def functions() -> dict[str, str]:
    """기능 설명. {recipe id: menu 의 function 문장}.

    규칙  게시 menu(paths.MENU_YAML_PATH) 원문 그대로. 결과를 읽는 쪽이 기능 번호 옆에 보일 글자
          menu 를 못 읽으면 빈 dict. 평가를 멈추지 않음
    제약  문장을 다듬거나 줄이지 않는다
    """
    import paths
    import yaml

    try:
        menu = yaml.safe_load(paths.MENU_YAML_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return {
        recipe_id: entry.get("function") or ""
        for recipe_id, entry in (menu.get("recipes") or {}).items()
        if isinstance(entry, dict)
    }


def _git_head() -> str | None:
    try:
        done = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None


def context_payload(label: str) -> dict | None:
    """check_resolve 의 지도 문맥 한 벌. label 은 CONTEXT_NONE · CONTEXT_BBOX · CONTEXT_BOTH.

    규칙  check_resolve._context_payload 를 그 label 로 부름. 전역 CONTEXT 는 되돌려 둠
    """
    previous = check_resolve.CONTEXT
    check_resolve.CONTEXT = label
    try:
        return check_resolve._context_payload()
    finally:
        check_resolve.CONTEXT = previous


def run(
    suite: dict,
    *,
    suite_path: Path | None = None,
    resolve=resolve_via_api,
    resolver: str = "api /resolve",
    runs: int = 1,
    only: list[int] | None = None,
    context: dict | None = None,
    context_label: str | None = None,
    materialize: bool = True,
    now: datetime.datetime | None = None,
    cooldown_every: int = 0,
    cooldown_seconds: float = 5.0,
    progress=None,
    monitor=None,
    save_dir: Path | None = None,
    dataset: dict | None = None,
) -> dict:
    """정답표를 재서 결과 한 벌 (Test Run).

    출력  {meta, summary, cases}. json 으로 바로 쓸 수 있는 값만
          meta 에 run_id · 정답표 신원 · 실행 조건(conditions) · 기능 설명(functions) ·
          시작 · 끝 · elapsed_s · gpu 가 실림
    규칙  only 가 있으면 그 번호만, 없으면 enabled 인 발화만. 파일 차례 그대로
          발화마다 runs 회
          서버에 못 닿거나 끊기거나 StopRun 이면 거기서 멈추고 거기까지의 결과와 까닭(meta.stopped)을 냄
          materialize 의 부르는 순간은 now 하나로 고정함. 안 주면 시작 시각
          cooldown_every 가 0 보다 크면 그만큼 부른 뒤 cooldown_seconds 초 쉼.
          센 수는 발화 × runs 전체를 통틀어서임. 0 이면 안 쉼(기본)
          발화 하나가 끝날 때마다 차례대로: save_dir 이면 그 줄을 cases.jsonl 에 덧붙임 ·
          progress(잰 수, 전체 수, 그 결과 줄) · monitor.after_case(잰 수, 전체 수).
          결과 줄은 판정까지 끝난 cases 의 한 줄 그대로(오류 줄 포함). 줄마다 정확히 한 번, 정답표 차례로
          progress 가 던진 예외는 삼키지 않음. 평가가 거기서 멈추고 예외가 부르는 쪽으로 감
          (KeyboardInterrupt · StopRun 만 meta.stopped 로 남김). 그래도 끝난 줄은 cases.jsonl 에 남음
          monitor 가 있으면 시작 전 before_run, 끝나고 after_run, 그 기록(summary)이 meta.gpu
          save_dir 이면 test_runs.Recorder 가 <save_dir>/<run_id>/ 에 남김. 끝나면 run.json
          dataset 은 {id, label}. 있으면 meta.suite 에 dataset_id · label 로 실림
    제약  MCP 도구를 부르지 않는다.
          쉬는 것을 재는 값에 섞지 않는다.
          다음 요청 **앞에서만** 쉬므로 마지막 요청 뒤에는 안 쉼. resolve_s 는
          resolve 호출 하나만 감싸 재므로 쉬어도 시간이 안 늘어나고 판정도 안 바뀜
          run 자체는 GPU 를 보지 않는다.
          nvidia-smi · 온도 조회는 넘겨받은 monitor(dev/evaluation/gpu.py)의 일이고, 그 기록은
          meta.gpu 에만 실림 — 재는 자(판정 · 결과 줄)에 기계 상태를 섞으면 같은 정답표가
          기계마다 다른 것을 재게 됨
    """
    import paths

    from dev.evaluation import test_runs

    if cooldown_every < 0 or cooldown_seconds < 0:
        raise ValueError(
            f"쉬는 설정은 0 이상이다: cooldown_every={cooldown_every} · cooldown_seconds={cooldown_seconds}"
        )

    path = Path(suite_path or suite_module.SUITE_PATH)
    labels = suite_module.group_labels(suite)
    label_of = suite_module.label_of(suite)
    cases = [case for case in suite["cases"] if (case["id"] in only if only else case["enabled"])]

    started = datetime.datetime.now(KST)
    now = now or started
    identity = suite_module.identity(suite, path)
    run_id = test_runs.new_run_id(started, identity["name"])
    head = {
        "result_version": RESULT_VERSION,
        "run_id": run_id,
        "suite": {
            "path": str(path),
            **identity,
            "group_labels": list(labels),
            "selected_case_ids": [case["id"] for case in cases],
            **({"dataset_id": dataset["id"], "label": dataset["label"]} if dataset else {}),
        },
        "runs": runs,
        "resolver": resolver,
        "role": check_resolve._role_label(),
        "conditions": conditions(),
        "functions": functions(),
        "cooldown": {"every": cooldown_every, "seconds": cooldown_seconds},
        "context": {"label": context_label, "payload": context},
        "materialize": materialize,
        "materialize_now": now.isoformat() if materialize else None,
        "artifact_root": str(paths.ARTIFACT_ROOT) if paths.ARTIFACT_ROOT else None,
        "git_head": _git_head(),
        "started_at": started.isoformat(),
    }
    recorder = test_runs.Recorder(save_dir, run_id) if save_dir else None
    if recorder:
        recorder.start(head)

    rows, stopped = [], None
    called, planned = 0, len(cases) * runs
    try:
        if monitor:
            monitor.before_run()
        for case in cases:
            for number in range(1, runs + 1):
                # 다음 요청 앞에서 쉰다. 뒤에서 쉬면 마지막 요청 뒤에도 쉬게 되고,
                # 그만큼은 아무도 기다릴 이유가 없는 시간이다.
                if cooldown_every and called and called % cooldown_every == 0:
                    time.sleep(cooldown_seconds)
                rows.append(run_case(case, label_of[case["group"]], number, resolve, context, materialize, now))
                called += 1
                if recorder:
                    recorder.case(rows[-1])
                if progress:
                    progress(called, planned, rows[-1])
                if monitor:
                    monitor.after_case(called, planned)
    except check_resolve.ServerDown as exc:
        stopped = f"ServerDown: {exc}"
    except StopRun as exc:
        stopped = f"StopRun: {exc}"
    except KeyboardInterrupt:
        stopped = "interrupted"

    finished = datetime.datetime.now(KST)
    if monitor:
        try:
            monitor.after_run(called)
        except KeyboardInterrupt:
            pass

    result = {
        "meta": {
            **head,
            "finished_at": finished.isoformat(),
            "elapsed_s": round((finished - started).total_seconds(), 1),
            "stopped": stopped,
            "gpu": monitor.summary() if monitor else None,
        },
        "summary": summarize(rows, labels),
        "cases": rows,
    }
    if recorder:
        recorder.finish(result)
        result["meta"]["saved_to"] = str(recorder.dir)
    return result


def datasets() -> list[dict]:
    """고를 수 있는 정답표 목록. suite.datasets 그대로."""
    return suite_module.datasets()


def run_dataset(dataset_id: str, *, save: bool = True, runs_dir: Path | None = None, **options) -> dict:
    """이름으로 고른 정답표를 재서 결과 한 벌 (Test Run). 화면 테스트 탭이 부르는 자리.

    입력  dataset_id 는 datasets() 의 id. options 는 run 의 키워드 인자 그대로
          save 면 Test Run 을 runs_dir(없으면 test_runs.RUNS_DIR)에 남김
    출력  run 의 결과. meta.suite 에 dataset id · 이름이 붙음
    규칙  정답표를 suite.load 로 읽고 run 을 부름. 창구(main)와 같은 판정 · 같은 결과 모양
          모르는 id 면 KeyError
    제약  판정 규칙을 여기 따로 두지 않는다
    """
    from dev.evaluation import test_runs

    chosen = next((entry for entry in datasets() if entry["id"] == dataset_id), None)
    if chosen is None:
        raise KeyError(f"모르는 정답표: {dataset_id!r}")
    path = Path(chosen["path"])
    save_dir = (runs_dir or test_runs.RUNS_DIR) if save else None
    return run(
        suite_module.load(path), suite_path=path, save_dir=save_dir,
        dataset={"id": chosen["id"], "label": chosen["label"]}, **options,
    )


def _selfcheck() -> None:
    """서버 · LLM · Gateway · 온톨로지 없이 runner 가 정답표마다 끝까지 돌고 check_resolve 와 같이 판정하나. 틀리면 죽는다.

    규칙  suite.DATASETS 의 진짜 정답표를 다 씀. 가짜 resolve 셋으로 돌림 — 기대 recipe 와 기대 값
          (범위 밖이면 받아들이는 status)을 그대로 돌려주는 것 · 틀린 recipe 와 틀린 값을 돌려주는 것 · 터지는 것
          이름 있는 값 판정이 check_resolve._spoken_value_verdict 와 발화마다 같은지 맞댐 (FULL48)
          지표 넷이 줄에서 다시 센 값과 같은지 봄
          materialize 는 끔. 이 검사는 recipe 파일을 안 읽음
          결과가 json 한 벌로 써지는지 봄
    """
    for entry in suite_module.datasets():
        suite = suite_module.load(entry["path"])
        _selfcheck_suite(suite, entry["path"] == suite_module.SUITE_PATH)


def _selfcheck_suite(suite: dict, anchor: bool) -> None:
    by_id = {case["id"]: case for case in suite["cases"]}
    by_utterance = {case["utterance"]: case for case in suite["cases"]}

    def echo(utterance):
        case = by_utterance[utterance]
        if not suite_module.in_scope(case):
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
        (wrong, "MISS", False, STAGE_FUNCTION, STAGE_SCOPE),
        (boom, "UNATTACHED", False, STAGE_ERROR, STAGE_ERROR),
    )
    for resolve, grade, spoken, stage, outside_stage in cases:
        result = run(suite, resolve=resolve, resolver=resolve.__name__, materialize=False)
        json.dumps(result, ensure_ascii=False)
        rows = result["cases"]
        inside = [row for row in rows if row["scope"] == SCOPE_IN]
        outside = [row for row in rows if row["scope"] == SCOPE_OUT]
        assert len(rows) == sum(1 for case in suite["cases"] if case["enabled"]), resolve.__name__
        assert {row["grade"] for row in inside} == {grade}, (resolve.__name__, Counter(row["grade"] for row in inside))
        assert {row["grade"] for row in outside} <= {None}, resolve.__name__
        assert {(row["passed"], row["failure_stage"]) for row in inside} == {(stage is None, stage)}, resolve.__name__
        assert {(row["passed"], row["failure_stage"]) for row in outside} <= {(outside_stage is None, outside_stage)}, resolve.__name__
        total = result["summary"]["total"]
        assert sum(total[name] for name in GRADES.values()) == total["in_scope_runs"] == len(inside)
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


def main() -> int:
    parser = argparse.ArgumentParser(description="정답표로 발화 해석을 재고 JSON 결과 한 벌을 남긴다.")
    parser.add_argument("--suite", default=str(suite_module.SUITE_PATH), help="정답표 YAML (기본 dev/evaluation/resolve_regression.yaml)")
    parser.add_argument("--runs", type=int, default=1, help="발화마다 몇 번 (기본 1)")
    parser.add_argument("--only", default="", help="돌릴 발화 번호. 예: 2,4")
    parser.add_argument(
        "--context",
        choices=(check_resolve.CONTEXT_NONE, check_resolve.CONTEXT_BBOX, check_resolve.CONTEXT_BOTH),
        default=check_resolve.CONTEXT_BOTH,
        help="materialize 에 실을 지도 문맥. 기본 both",
    )
    parser.add_argument("--no-materialize", action="store_true", help="/resolve 만 잰다")
    parser.add_argument("--out", default="", help="결과 JSON 경로 (기본 dev/tools/sweep_out/evaluation-<시각>.json)")
    parser.add_argument("--cooldown-every", type=int, default=0, help="몇 번 부르고 쉴까. 0 이면 안 쉼 (기본 0)")
    parser.add_argument("--cooldown-seconds", type=float, default=5.0, help="쉬는 시간 초 (기본 5)")
    parser.add_argument(
        "--gpu", choices=("off", "record", "gate"), default="record",
        help="GPU 기록. record 는 기록만, gate 는 사무실 조용 정책(dev/evaluation/gpu.POLICY)으로 쉬고 멈춤 (기본 record)",
    )
    parser.add_argument("--no-save", action="store_true", help="Test Run 을 dev/tools/sweep_out/test_runs 에 안 남김")
    args = parser.parse_args()

    # --only 와 같은 자리에서 막는다. 정답표를 읽기 전에 죽어야 오래 도는 회귀평가가
    # 한참 뒤에 설정 오타로 멈추는 일이 없다.
    if args.cooldown_every < 0 or args.cooldown_seconds < 0:
        print(f"쉬는 설정은 0 이상이다 : --cooldown-every {args.cooldown_every} · --cooldown-seconds {args.cooldown_seconds}")
        return 2

    suite_path = Path(args.suite)
    suite = suite_module.load(suite_path)
    only = [int(part) for part in args.only.replace(" ", "").split(",") if part] or None
    if only:
        missing = sorted(set(only) - {case["id"] for case in suite["cases"]})
        if missing:
            print(f"정답표에 없는 번호 : {missing}")
            return 2

    from dev.evaluation import gpu, test_runs

    dataset = next(
        ({"id": entry["id"], "label": entry["label"]} for entry in datasets() if Path(entry["path"]).resolve() == suite_path.resolve()),
        None,
    )
    result = run(
        suite,
        suite_path=suite_path,
        runs=args.runs,
        only=only,
        context=context_payload(args.context),
        context_label=args.context,
        materialize=not args.no_materialize,
        cooldown_every=args.cooldown_every,
        cooldown_seconds=args.cooldown_seconds,
        monitor=None if args.gpu == "off" else gpu.GpuMonitor(gate=args.gpu == "gate"),
        save_dir=None if args.no_save else test_runs.RUNS_DIR,
        dataset=dataset,
    )

    out = Path(args.out) if args.out else OUT_DIR / f"evaluation-{datetime.datetime.now(KST):%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    for label, value in {**result["summary"]["groups"], "합계": result["summary"]["total"]}.items():
        stages = value["failure_stages"]
        print(
            f"  {label}  적중 {value['HIT']}/{value['in_scope_runs']} · 근접 {value['NEAR']} · 빗나감 {value['MISS']} · "
            f"못 붙음 {value['UNATTACHED']} · 이름 있는 값 {value['spoken_hits']}/{value['spoken_runs']} · 오류 {value['errors']}"
        )
        print(
            f"  {label}  발화 성공 {value['passed']}/{value['runs']} · 실패 기능 선택 {stages[STAGE_FUNCTION]} · "
            f"인자 추출 {stages[STAGE_INPUT]} · 범위 밖 {stages[STAGE_SCOPE]} · 실행 오류 {stages[STAGE_ERROR]}"
        )
    board = result["summary"]["metrics"]
    print("  지표  " + " · ".join(f"{name} {pair['correct']}/{pair['total']}" for name, pair in board.items()))
    if result["meta"]["stopped"]:
        print(f"  멈춤: {result['meta']['stopped']}")
    print(f"  결과 {out}")
    if result["meta"].get("saved_to"):
        print(f"  Test Run {result['meta']['saved_to']}")
    return 1 if (result["meta"]["stopped"] or "").startswith("ServerDown") else 0


if __name__ == "__main__":
    sys.exit(main())
