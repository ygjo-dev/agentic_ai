"""정답표(evaluation suite)로 발화 해석을 재고 결과를 JSON 한 벌로 남기는 공통 runner.

    python dev/evaluation/runner.py                        정답표 전체 · 1회 · materialize 포함
    python dev/evaluation/runner.py --runs 3 --only 2,4    고른 발화만 여러 번
    python dev/evaluation/runner.py --context bbox         materialize 에 실을 지도 문맥
    python dev/evaluation/runner.py --no-materialize       /resolve 만
    python dev/evaluation/runner.py --out 결과.json        결과 파일 자리

**check_resolve 와 같은 자를 쓴다.** 정답표는 `dev/evaluation/suite.py` 로 읽고, 판정(`_grade`) ·
이름 있는 값 표기(`_spoken_values_of` · `NULL_MARK`) · 지도 문맥(`_context_payload`) · 부르는
주소와 timeout · 역할 줄은 `dev/tools/check_resolve.py` 것을 그대로 부른다. 규칙을 베끼면 두
자가 조용히 어긋난다.

check_resolve 는 사람이 읽을 표를 찍고, 이것은 기계가 읽을 결과 한 벌을 낸다. 화면이 나중에
같은 결과 모양을 읽을 자리다 — 화면은 아직 없다.

**MCP 도구를 부르지 않는다.** `/resolve` 를 부르고, 고른 recipe 를 workflow_materializer 로 KRRI
native workflow 까지만 만든다. Gateway 실행은 `check_resolve --execute` 의 일이다.

결과는 `dev/tools/sweep_out/` 에 둔다 (`.gitignore`).
"""

import argparse
import datetime
import hashlib
import json
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
RESULT_VERSION = 1

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
    규칙  check_resolve._spoken_value_verdict 와 같은 대조. 나온 값을 표 글자
          (_spoken_values_of)로 바꿔 기대값의 표 글자와 맞댐. 기대 None 은 NULL_MARK
          적지 않은 칸은 안 봄
    """
    said = dict(check_resolve._spoken_values_of(response))
    rows = []
    for name, value in expected.items():
        if value is None:
            wanted = check_resolve.NULL_MARK
        elif isinstance(value, list):
            wanted = ",".join(str(item) for item in value)
        else:
            wanted = str(value)
        rows.append({"name": name, "expected": value, "actual": response.get(name), "correct": said.get(name) == wanted})
    return rows


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
    """발화 하나를 한 번 잰 결과.

    규칙  후보 집합은 recipe_id 와 candidate_recipe_ids 를 합친 것. _call_resolve 와 같음
          판정은 check_resolve._grade. 오류는 「오류: 예외 이름」 으로 넘겨 못 붙음이 됨
          ServerDown 은 삼키지 않음. 부르는 쪽이 멈춤
    """
    expected = case["expected"]
    wanted_spoken = expected.get("spoken")
    row = {
        "case_id": case["id"],
        "group": case["group"],
        "group_label": label,
        "utterance": case["utterance"],
        "run": run,
        "expected": {"recipe_ids": list(expected["recipe_ids"]), "spoken": wanted_spoken},
    }

    started = time.perf_counter()
    try:
        response = resolve(case["utterance"])
    except check_resolve.ServerDown:
        raise
    except Exception as exc:  # noqa: BLE001 — 오류도 결과의 하나로 남긴다.
        grade = check_resolve._grade(f"오류: {type(exc).__name__}", "-", set(expected["recipe_ids"]))
        return {
            **row,
            "actual": None,
            "grade": GRADES[grade],
            "recipe_correct": False,
            "spoken_fields": [],
            "spoken_correct": False if wanted_spoken else None,
            "materialize": None,
            "timing": {"resolve_s": round(time.perf_counter() - started, 3), "materialize_s": None},
            "error": f"{type(exc).__name__}: {exc}",
        }
    resolve_s = round(time.perf_counter() - started, 3)

    found = frozenset(rid for rid in [response.get("recipe_id"), *(response.get("candidate_recipe_ids") or [])] if rid)
    status = response.get("status") or "-"
    grade = check_resolve._grade(found, status, set(expected["recipe_ids"]))
    fields = spoken_fields(wanted_spoken or {}, response)

    built, materialize_s = None, None
    if materialize:
        started = time.perf_counter()
        built = materialized(response, context, now)
        materialize_s = round(time.perf_counter() - started, 3)

    return {
        **row,
        "actual": {
            "status": status,
            "recipe_id": response.get("recipe_id"),
            "candidate_recipe_ids": list(response.get("candidate_recipe_ids") or []),
            "found_recipe_ids": sorted(found),
            "spoken": {name: response.get(name) for name in check_resolve.SPOKEN_VALUE_NAMES},
            "reason": response.get("reason"),
        },
        "grade": GRADES[grade],
        "recipe_correct": grade == check_resolve.HIT,
        "spoken_fields": fields,
        "spoken_correct": all(field["correct"] for field in fields) if fields else None,
        "materialize": built,
        "timing": {"resolve_s": resolve_s, "materialize_s": materialize_s},
        "error": None,
    }


def summarize(rows: list[dict], labels: tuple) -> dict:
    """묶음마다 네 칸 · 이름 있는 값 · materialize 판정을 셈.

    규칙  묶음을 한 백분율로 합치지 않음. 합계는 따로 한 칸
          넷을 더하면 시행 횟수여야 함
    """
    def tally(group_rows):
        grades = Counter(row["grade"] for row in group_rows)
        spoken = [row["spoken_correct"] for row in group_rows if row["spoken_correct"] is not None]
        built = Counter((row["materialize"] or {}).get("status") for row in group_rows if row["materialize"])
        return {
            "runs": len(group_rows),
            **{name: grades.get(name, 0) for name in GRADES.values()},
            "spoken_hits": sum(spoken),
            "spoken_runs": len(spoken),
            "materialize": dict(sorted(built.items())),
            "errors": sum(1 for row in group_rows if row["error"]),
        }

    groups = {label: tally([row for row in rows if row["group_label"] == label]) for label in labels}
    return {"groups": {label: value for label, value in groups.items() if value["runs"]}, "total": tally(rows)}


def _git_head() -> str | None:
    try:
        done = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None


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
) -> dict:
    """정답표를 재서 결과 한 벌.

    출력  {meta, summary, cases}. json 으로 바로 쓸 수 있는 값만
    규칙  only 가 있으면 그 번호만, 없으면 enabled 인 발화만. 파일 차례 그대로
          발화마다 runs 회
          서버에 못 닿거나 끊기면 거기서 멈추고 거기까지의 결과와 까닭(meta.stopped)을 냄
          materialize 의 부르는 순간은 now 하나로 고정함. 안 주면 시작 시각
    제약  MCP 도구를 부르지 않는다.
    """
    import paths

    path = Path(suite_path or suite_module.SUITE_PATH)
    labels = suite_module.group_labels(suite)
    label_of = dict(zip(suite_module.GROUP_IDS, labels))
    cases = [case for case in suite["cases"] if (case["id"] in only if only else case["enabled"])]

    started = datetime.datetime.now(KST)
    now = now or started
    rows, stopped = [], None
    try:
        for case in cases:
            for number in range(1, runs + 1):
                rows.append(run_case(case, label_of[case["group"]], number, resolve, context, materialize, now))
    except check_resolve.ServerDown as exc:
        stopped = f"ServerDown: {exc}"
    except KeyboardInterrupt:
        stopped = "interrupted"

    return {
        "meta": {
            "result_version": RESULT_VERSION,
            "suite": {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
                "version": suite.get("version"),
                "case_count": len(suite["cases"]),
                "selected_case_ids": [case["id"] for case in cases],
            },
            "runs": runs,
            "resolver": resolver,
            "role": check_resolve._role_label(),
            "context": {"label": context_label, "payload": context},
            "materialize": materialize,
            "materialize_now": now.isoformat() if materialize else None,
            "artifact_root": str(paths.ARTIFACT_ROOT) if paths.ARTIFACT_ROOT else None,
            "git_head": _git_head(),
            "started_at": started.isoformat(),
            "finished_at": datetime.datetime.now(KST).isoformat(),
            "stopped": stopped,
        },
        "summary": summarize(rows, labels),
        "cases": rows,
    }


def _selfcheck() -> None:
    """서버 · LLM · Gateway · 온톨로지 없이 runner 가 정답표 전체를 끝까지 돌고 check_resolve 와 같이 판정하나. 틀리면 죽는다.

    규칙  진짜 정답표를 씀. 가짜 resolve 셋으로 돌림 — 기대 recipe 와 기대 값을 그대로
          돌려주는 것 · 틀린 recipe 와 틀린 값을 돌려주는 것 · 터지는 것
          이름 있는 값 판정이 check_resolve._spoken_value_verdict 와 발화마다 같은지 맞댐
          materialize 는 끔. 이 검사는 recipe 파일을 안 읽음
          결과가 json 한 벌로 써지는지 봄
    """
    suite = suite_module.load()
    by_id = {case["id"]: case for case in suite["cases"]}

    def echo(utterance):
        case = next(case for case in suite["cases"] if case["utterance"] == utterance)
        rid = case["expected"]["recipe_ids"][0]
        return {"status": "SELECT", "recipe_id": rid, "candidate_recipe_ids": [rid], "argument": "오송역",
                **{name: None for name in check_resolve.SPOKEN_VALUE_NAMES[1:]}, **(case["expected"].get("spoken") or {})}

    def wrong(_utterance):
        return {"status": "SELECT", "recipe_id": "recipe_000", "candidate_recipe_ids": [], "argument": None,
                "travel_mode": "틀림", "minutes": [999], "admin_level": "틀림"}

    def boom(_utterance):
        raise RuntimeError("터짐")

    for resolve, grade, spoken in ((echo, "HIT", True), (wrong, "MISS", False), (boom, "UNATTACHED", False)):
        result = run(suite, resolve=resolve, resolver=resolve.__name__, materialize=False)
        json.dumps(result, ensure_ascii=False)
        rows = result["cases"]
        assert len(rows) == sum(1 for case in suite["cases"] if case["enabled"]), resolve.__name__
        assert {row["grade"] for row in rows} == {grade}, (resolve.__name__, Counter(row["grade"] for row in rows))
        total = result["summary"]["total"]
        assert sum(total[name] for name in GRADES.values()) == total["runs"] == len(rows)
        for row in rows:
            if by_id[row["case_id"]]["expected"].get("spoken"):
                assert row["spoken_correct"] is spoken, (resolve.__name__, row["case_id"])
            if row["actual"] is None:
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
    args = parser.parse_args()

    suite_path = Path(args.suite)
    suite = suite_module.load(suite_path)
    only = [int(part) for part in args.only.replace(" ", "").split(",") if part] or None
    if only:
        missing = sorted(set(only) - {case["id"] for case in suite["cases"]})
        if missing:
            print(f"정답표에 없는 번호 : {missing}")
            return 2

    check_resolve.CONTEXT = args.context
    result = run(
        suite,
        suite_path=suite_path,
        runs=args.runs,
        only=only,
        context=check_resolve._context_payload(),
        context_label=args.context,
        materialize=not args.no_materialize,
    )

    out = Path(args.out) if args.out else OUT_DIR / f"evaluation-{datetime.datetime.now(KST):%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    for label, value in {**result["summary"]["groups"], "합계": result["summary"]["total"]}.items():
        print(
            f"  {label}  적중 {value['HIT']}/{value['runs']} · 근접 {value['NEAR']} · 빗나감 {value['MISS']} · "
            f"못 붙음 {value['UNATTACHED']} · 이름 있는 값 {value['spoken_hits']}/{value['spoken_runs']} · 오류 {value['errors']}"
        )
    if result["meta"]["stopped"]:
        print(f"  멈춤: {result['meta']['stopped']}")
    print(f"  결과 {out}")
    return 1 if (result["meta"]["stopped"] or "").startswith("ServerDown") else 0


if __name__ == "__main__":
    sys.exit(main())
