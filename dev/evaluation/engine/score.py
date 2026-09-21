"""Resolve 출력을 정답표와 맞대 채점하는 곳. 발화 하나의 판정 · 합계 · 지표 · 요약 글.

**check_resolve 와 같은 자를 쓴다.** 판정(`_grade`) · 이름 있는 값 표기(`_value_mark`) 는
`dev/tools/check_resolve.py` 것을 그대로 부른다. 규칙을 베끼면 두 자가 조용히 어긋난다.

**발화 판정은 고르기와 정답표에 적은 값만 본다.** materialize 결과는 줄에 싣지만 범위 안 판정에 안 들어간다.
범위 밖 발화(정답표 판 2 의 out_of_scope)는 기대 recipe 가 없고, 결과(outcome)가 정답표가 받아들이는
것 중 하나인지로 가른다. outcome 은 resolve status 이고, SELECT 면 그 workflow 의 materialize 판정이다
— 「기능은 섰는데 값이 모자람(MISSING_ARGUMENT)」을 runtime 이 가르는 자리가 거기뿐이다.

여기서 Resolve · materialize · 파일 · GPU 를 부르지 않는다. 받은 값을 채점만 한다.
"""

import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from dev.evaluation.engine import load_test_suite  # noqa: E402
from dev.tools import check_resolve  # noqa: E402

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

# 조건 칸. 있으면 그 참조는 인자 모양에 따라 빠질 수 있다.
CONDITION_KEYS = ("if_endswith", "unless_endswith")


# ================================================================ 기대 recipe 가 읽는 칸
def spoken_refs(execution: dict) -> list[dict]:
    """execution 이 읽는 spoken 참조. [{name, at, use}] execution 안 차례.

    출력  use 는 required · default=<값> · <조건>=<어미> 중 하나
    규칙  {from: spoken.<이름>} 꼴인 dict 만 참조로 셈. 중첩 dict · list 를 끝까지 훑음
          default 가 있으면 안 말해도 실행이 기본값으로 감. 없으면 값이 있어야 부름
          조건(if_endswith · unless_endswith)이 있으면 그 참조는 인자 모양에 따라 빠짐
    """
    from execution import workflow_materializer

    found = []

    def walk(node, at):
        if isinstance(node, dict):
            origin = node.get("from")
            if isinstance(origin, str) and origin.startswith(workflow_materializer.SPOKEN_SOURCE):
                name = origin[len(workflow_materializer.SPOKEN_SOURCE):]
                condition = next((key for key in CONDITION_KEYS if key in node), None)
                if condition:
                    use = f"{condition}={node[condition]}"
                elif "default" in node:
                    use = f"default={json.dumps(node['default'], ensure_ascii=False)}"
                else:
                    use = "required"
                found.append({"name": name, "at": at, "use": use})
            for key, value in node.items():
                walk(value, f"{at}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{at}[{index}]")

    walk(execution.get("workflow") or [], "workflow")
    return found


_READS: dict[str, list[str]] = {}


def recipe_reads(recipe_ids: list[str]) -> list[str]:
    """기대 recipe 들이 모두 읽는 이름 있는 값 이름. 이름 차례.

    규칙  spoken_refs 로 게시된 execution 을 훑음. 여럿이면 교집합
          recipe 파일이 없으면 빈 목록. recipe 마다 한 번만 읽음
    """
    from execution import workflow_materializer

    common = None
    for recipe_id in recipe_ids:
        if recipe_id not in _READS:
            execution = workflow_materializer.load(recipe_id)
            _READS[recipe_id] = sorted({ref["name"] for ref in spoken_refs(execution)} if execution else set())
        names = set(_READS[recipe_id])
        common = names if common is None else common & names
    return sorted(common or ())


# ================================================================ 발화 하나
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


def case_head(case: dict, label: str, run: int) -> dict:
    """결과 줄의 앞머리. 발화 · 묶음 · 기대값. Resolve 를 부르기 전에 정해지는 칸.

    규칙  범위 안이면 expected.reads 에 기대 recipe 의 execution 이 읽는 이름 있는 값 이름을 적음.
          화면이 「사용 안 함」(안 읽음)과 「없음」(읽는데 null)을 가르는 근거임
          범위 밖이면 expected 에 category · outcomes 를 적음
    """
    expected = case["expected"]
    scoped = load_test_suite.in_scope(case)
    row = {
        "case_id": case["id"],
        "group": case["group"],
        "group_label": label,
        "scope": SCOPE_IN if scoped else SCOPE_OUT,
        "recipe_group": expected["recipe_ids"][0] if scoped else None,
        "utterance": case["utterance"],
        "run": run,
        "expected": {"recipe_ids": list(expected.get("recipe_ids") or []), "spoken": expected.get("spoken")},
    }
    if scoped:
        row["expected"]["reads"] = recipe_reads(expected["recipe_ids"])
    else:
        row["expected"].update({"category": expected["category"], "outcomes": list(expected["outcomes"])})
    return row


def grade_error(case: dict, head: dict, exc: Exception, timing: dict) -> dict:
    """Resolve 가 터진 발화 하나의 결과 줄 (Case Result).

    규칙  오류는 「오류: 예외 이름」 으로 check_resolve._grade 에 넘겨 못 붙음이 됨 (범위 밖이면 grade None)
          실패 단계는 STAGE_ERROR
    """
    expected = case["expected"]
    scoped = load_test_suite.in_scope(case)
    wanted_spoken = expected.get("spoken")
    grade = check_resolve._grade(f"오류: {type(exc).__name__}", "-", set(expected.get("recipe_ids") or []))
    error = f"{type(exc).__name__}: {exc}"
    passed, stage = verdict(False, False if wanted_spoken else None, error)
    return {
        **head,
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
        "timing": timing,
        "error": error,
    }


def grade_case(case: dict, head: dict, response: dict, built: dict | None, timing: dict) -> dict:
    """Resolve 응답 하나를 채점한 결과 줄 (Case Result).

    입력  head 는 case_head. built 는 materialize 결과(안 했으면 None)
    규칙  후보 집합은 recipe_id 와 candidate_recipe_ids 를 합친 것. check_resolve._call_resolve 와 같음
          범위 안: 판정은 check_resolve._grade. 발화 판정(passed · failure_stage)은 verdict.
          materialize 를 안 봄
          범위 밖: grade · recipe_correct 는 None. outcome 이 expected.outcomes 에 있으면 성공,
          아니면 STAGE_SCOPE
          actual.spoken 은 응답에서 SELECTION_KEYS 를 뺀 칸 전부. 이름을 고정 목록으로 거르지 않음
    """
    expected = case["expected"]
    found = frozenset(rid for rid in [response.get("recipe_id"), *(response.get("candidate_recipe_ids") or [])] if rid)
    status = response.get("status") or "-"
    outcome = outcome_of(status, built)

    if load_test_suite.in_scope(case):
        grade = GRADES[check_resolve._grade(found, status, set(expected["recipe_ids"]))]
        fields = spoken_fields(expected.get("spoken") or {}, response)
        spoken_correct = all(field["correct"] for field in fields) if fields else None
        recipe_correct = grade == GRADES[check_resolve.HIT]
        passed, stage = verdict(recipe_correct, spoken_correct, None)
        oos_correct = None
    else:
        grade, fields, spoken_correct, recipe_correct = None, [], None, None
        oos_correct = outcome in expected["outcomes"]
        passed, stage = (True, None) if oos_correct else (False, STAGE_SCOPE)

    return {
        **head,
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
        "timing": timing,
        "error": None,
    }


# ================================================================ 합계 · 지표
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


def workflow_ready() -> str:
    """materialize 가 부를 수 있다고 한 판정 이름. workflow_materializer.READY."""
    from execution import workflow_materializer

    return workflow_materializer.READY


def summarize(rows: list[dict], labels: tuple) -> dict:
    """묶음마다 네 칸 · 이름 있는 값 · 발화 판정 · 범위 밖 · materialize 판정을 셈.

    출력  {groups: {묶음 이름: tally}, total: tally, metrics, latency, recipes}
          recipes 는 {기대 recipe: {runs, passed, hit}}. 범위 안만
    규칙  묶음을 한 백분율로 합치지 않음. 합계는 따로 한 칸
          네 칸(HIT · NEAR · MISS · UNATTACHED)을 더하면 범위 안 시행 횟수여야 함
          passed 와 failure_stages 넷을 더하면 시행 횟수임
          범위 밖 줄은 네 칸 · 값 칸에 안 들어가고 oos_* 에만 들어감
    제약  줄을 다시 채점하지 않는다. 줄에 적힌 판정을 셀 뿐임
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


# ================================================================ 요약 글
def _ratio(pair: dict | None) -> str:
    if not pair or not pair.get("total"):
        return "-"
    return f"{pair['correct']}/{pair['total']} ({pair['correct'] / pair['total']:.1%})"


def summary_text(result: dict) -> str:
    """사람이 읽는 벤치마크 요약 (markdown). 저장할 때 summary.md 가 됨."""
    meta, summary = result["meta"], result["summary"]
    metrics_ = summary.get("metrics") or {}
    latency_ = summary.get("latency") or {}
    conditions = meta.get("conditions") or {}
    request = conditions.get("request") or {}
    gpus = (meta.get("environment") or {}).get("gpus") or []
    suite = meta.get("suite") or {}
    lines = [
        f"# Test Run {meta.get('run_id')}",
        "",
        f"- Test Suite: {suite.get('label') or suite.get('name')} (v{suite.get('version')}, sha256 {str(suite.get('sha256'))[:12]}, {suite.get('case_count')} cases)",
        f"- model: {conditions.get('model')} · {conditions.get('provider')} · role v{conditions.get('role_version')} "
        f"· request {json.dumps(request, ensure_ascii=False)}",
        "- environment: " + (", ".join(f"GPU{g.get('index')} {g.get('name')} {g.get('memory_total_mib')} MiB" for g in gpus) or "not recorded"),
        f"- started {meta.get('started_at')} · finished {meta.get('finished_at')} · elapsed {meta.get('elapsed_s')} s",
        f"- stopped: {meta.get('stopped')}",
        "",
        "| metric | result |",
        "|---|---|",
        f"| Selection | {_ratio(metrics_.get('selection'))} |",
        f"| Semantic fields | {_ratio(metrics_.get('semantic_fields'))} |",
        f"| Semantic cases | {_ratio(metrics_.get('semantic_cases'))} |",
        f"| Joint | {_ratio(metrics_.get('joint'))} |",
        f"| OOS | {_ratio(metrics_.get('oos'))} |",
        f"| Errors | {summary['total'].get('errors')} |",
        "",
        f"latency (s): min {latency_.get('min')} · median {latency_.get('median')} · p95 {latency_.get('p95')} · max {latency_.get('max')}",
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
