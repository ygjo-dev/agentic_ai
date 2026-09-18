"""정답표(evaluation suite)로 발화 해석을 재고 결과를 JSON 한 벌로 남기는 공통 runner.

    python dev/evaluation/runner.py                        정답표 전체 · 1회 · materialize 포함
    python dev/evaluation/runner.py --runs 3 --only 2,4    고른 발화만 여러 번
    python dev/evaluation/runner.py --context bbox         materialize 에 실을 지도 문맥
    python dev/evaluation/runner.py --no-materialize       /resolve 만
    python dev/evaluation/runner.py --out 결과.json        결과 파일 자리
    python dev/evaluation/runner.py --cooldown-every 6     6번마다 5초 쉼 (발열 · 팬 소음)

화면(app/ui 테스트 탭)은 run_dataset 으로 같은 run 을 부른다. 판정 · 결과 모양이 창구와 같다.

**check_resolve 와 같은 자를 쓴다.** 정답표는 `dev/evaluation/suite.py` 로 읽고, 판정(`_grade`) ·
이름 있는 값 표기(`_spoken_values_of` · `NULL_MARK`) · 지도 문맥(`_context_payload`) · 부르는
주소와 timeout · 역할 줄은 `dev/tools/check_resolve.py` 것을 그대로 부른다. 규칙을 베끼면 두
자가 조용히 어긋난다.

check_resolve 는 사람이 읽을 표를 찍고, 이것은 기계가 읽을 결과 한 벌을 낸다. 화면은 그 결과를
읽기만 한다 — 발화 판정(passed · failure_stage)도 여기서 정해 결과에 싣는다.

**발화 판정은 고르기와 정답표에 적은 값만 본다.** materialize 는 따로 싣지만 판정에 안 들어간다.

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
RESULT_VERSION = 2

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
STAGE_FUNCTION = "function"
STAGE_INPUT = "input"
STAGE_ERROR = "error"
STAGES = (STAGE_FUNCTION, STAGE_INPUT, STAGE_ERROR)

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
          actual.spoken 은 응답에서 SELECTION_KEYS 를 뺀 칸 전부. 이름을 고정 목록으로 거르지 않음
          발화 판정(passed · failure_stage)은 verdict. materialize 를 안 봄
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
        error = f"{type(exc).__name__}: {exc}"
        passed, stage = verdict(False, False if wanted_spoken else None, error)
        return {
            **row,
            "actual": None,
            "grade": GRADES[grade],
            "recipe_correct": False,
            "spoken_fields": [],
            "spoken_correct": False if wanted_spoken else None,
            "passed": passed,
            "failure_stage": stage,
            "materialize": None,
            "timing": {"resolve_s": round(time.perf_counter() - started, 3), "materialize_s": None},
            "error": error,
        }
    resolve_s = round(time.perf_counter() - started, 3)

    found = frozenset(rid for rid in [response.get("recipe_id"), *(response.get("candidate_recipe_ids") or [])] if rid)
    status = response.get("status") or "-"
    grade = check_resolve._grade(found, status, set(expected["recipe_ids"]))
    fields = spoken_fields(wanted_spoken or {}, response)
    spoken_correct = all(field["correct"] for field in fields) if fields else None
    passed, stage = verdict(grade == check_resolve.HIT, spoken_correct, None)

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
            "spoken": {name: value for name, value in response.items() if name not in SELECTION_KEYS},
            "reason": response.get("reason"),
        },
        "grade": GRADES[grade],
        "recipe_correct": grade == check_resolve.HIT,
        "spoken_fields": fields,
        "spoken_correct": spoken_correct,
        "passed": passed,
        "failure_stage": stage,
        "materialize": built,
        "timing": {"resolve_s": resolve_s, "materialize_s": materialize_s},
        "error": None,
    }


def summarize(rows: list[dict], labels: tuple) -> dict:
    """묶음마다 네 칸 · 이름 있는 값 · 발화 판정 · materialize 판정을 셈.

    규칙  묶음을 한 백분율로 합치지 않음. 합계는 따로 한 칸
          넷을 더하면 시행 횟수여야 함
          passed 와 failure_stages 셋을 더해도 시행 횟수임
    """
    def tally(group_rows):
        grades = Counter(row["grade"] for row in group_rows)
        spoken = [row["spoken_correct"] for row in group_rows if row["spoken_correct"] is not None]
        built = Counter((row["materialize"] or {}).get("status") for row in group_rows if row["materialize"])
        stages = Counter(row["failure_stage"] for row in group_rows if not row["passed"])
        return {
            "runs": len(group_rows),
            **{name: grades.get(name, 0) for name in GRADES.values()},
            "spoken_hits": sum(spoken),
            "spoken_runs": len(spoken),
            "passed": sum(1 for row in group_rows if row["passed"]),
            "failure_stages": {stage: stages.get(stage, 0) for stage in STAGES},
            "materialize": dict(sorted(built.items())),
            "errors": sum(1 for row in group_rows if row["error"]),
        }

    groups = {label: tally([row for row in rows if row["group_label"] == label]) for label in labels}
    return {"groups": {label: value for label, value in groups.items() if value["runs"]}, "total": tally(rows)}


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

    출력  {model, provider, role_version, prompt, response_schema, menu}. 파일 셋은 _file_record 꼴
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
) -> dict:
    """정답표를 재서 결과 한 벌.

    출력  {meta, summary, cases}. json 으로 바로 쓸 수 있는 값만
          meta 에 실행 조건(conditions) · 기능 설명(functions) 이 실림
    규칙  only 가 있으면 그 번호만, 없으면 enabled 인 발화만. 파일 차례 그대로
          발화마다 runs 회
          서버에 못 닿거나 끊기면 거기서 멈추고 거기까지의 결과와 까닭(meta.stopped)을 냄
          materialize 의 부르는 순간은 now 하나로 고정함. 안 주면 시작 시각
          cooldown_every 가 0 보다 크면 그만큼 부른 뒤 cooldown_seconds 초 쉼.
          센 수는 발화 × runs 전체를 통틀어서임. 0 이면 안 쉼(기본)
          progress 가 있으면 한 번 잴 때마다 progress(잰 수, 전체 수, 그 결과 줄) 를 부름
    제약  MCP 도구를 부르지 않는다.
          쉬는 것을 재는 값에 섞지 않는다.
          다음 요청 **앞에서만** 쉬므로 마지막 요청 뒤에는 안 쉼. resolve_s 는
          resolve 호출 하나만 감싸 재므로 쉬어도 시간이 안 늘어나고 판정도 안 바뀜
          쉬려고 GPU 를 보지 않는다.
          nvidia-smi · 온도 조회 · 병렬 실행 · vLLM 재기동을 넣지 않음. 부르는
          횟수만 세어 time.sleep 한다 — 재는 자에 기계 상태를 섞으면 같은 정답표가
          기계마다 다른 것을 재게 됨
    """
    import paths

    if cooldown_every < 0 or cooldown_seconds < 0:
        raise ValueError(
            f"쉬는 설정은 0 이상이다: cooldown_every={cooldown_every} · cooldown_seconds={cooldown_seconds}"
        )

    path = Path(suite_path or suite_module.SUITE_PATH)
    labels = suite_module.group_labels(suite)
    label_of = dict(zip(suite_module.GROUP_IDS, labels))
    cases = [case for case in suite["cases"] if (case["id"] in only if only else case["enabled"])]

    started = datetime.datetime.now(KST)
    now = now or started
    measured_on = conditions()
    rows, stopped = [], None
    called, planned = 0, len(cases) * runs
    try:
        for case in cases:
            for number in range(1, runs + 1):
                # 다음 요청 앞에서 쉰다. 뒤에서 쉬면 마지막 요청 뒤에도 쉬게 되고,
                # 그만큼은 아무도 기다릴 이유가 없는 시간이다.
                if cooldown_every and called and called % cooldown_every == 0:
                    time.sleep(cooldown_seconds)
                rows.append(run_case(case, label_of[case["group"]], number, resolve, context, materialize, now))
                called += 1
                if progress:
                    progress(called, planned, rows[-1])
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
            "conditions": measured_on,
            "functions": functions(),
            "cooldown": {"every": cooldown_every, "seconds": cooldown_seconds},
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


def datasets() -> list[dict]:
    """고를 수 있는 정답표 목록. suite.datasets 그대로."""
    return suite_module.datasets()


def run_dataset(dataset_id: str, **options) -> dict:
    """이름으로 고른 정답표를 재서 결과 한 벌. 화면 테스트 탭이 부르는 자리.

    입력  dataset_id 는 datasets() 의 id. options 는 run 의 키워드 인자 그대로
    출력  run 의 결과. meta.suite 에 dataset id · 이름이 더 붙음
    규칙  정답표를 suite.load 로 읽고 run 을 부름. 창구(main)와 같은 판정 · 같은 결과 모양
          모르는 id 면 KeyError
    제약  판정 규칙을 여기 따로 두지 않는다
    """
    chosen = next((entry for entry in datasets() if entry["id"] == dataset_id), None)
    if chosen is None:
        raise KeyError(f"모르는 정답표: {dataset_id!r}")
    path = Path(chosen["path"])
    result = run(suite_module.load(path), suite_path=path, **options)
    result["meta"]["suite"].update({"dataset_id": chosen["id"], "label": chosen["label"]})
    return result


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

    cases = (
        (echo, "HIT", True, None),
        (wrong, "MISS", False, STAGE_FUNCTION),
        (boom, "UNATTACHED", False, STAGE_ERROR),
    )
    for resolve, grade, spoken, stage in cases:
        result = run(suite, resolve=resolve, resolver=resolve.__name__, materialize=False)
        json.dumps(result, ensure_ascii=False)
        rows = result["cases"]
        assert len(rows) == sum(1 for case in suite["cases"] if case["enabled"]), resolve.__name__
        assert {row["grade"] for row in rows} == {grade}, (resolve.__name__, Counter(row["grade"] for row in rows))
        assert {(row["passed"], row["failure_stage"]) for row in rows} == {(stage is None, stage)}, resolve.__name__
        total = result["summary"]["total"]
        assert sum(total[name] for name in GRADES.values()) == total["runs"] == len(rows)
        assert total["passed"] + sum(total["failure_stages"].values()) == total["runs"]
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
    parser.add_argument("--cooldown-every", type=int, default=0, help="몇 번 부르고 쉴까. 0 이면 안 쉼 (기본 0)")
    parser.add_argument("--cooldown-seconds", type=float, default=5.0, help="쉬는 시간 초 (기본 5)")
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

    check_resolve.CONTEXT = args.context
    result = run(
        suite,
        suite_path=suite_path,
        runs=args.runs,
        only=only,
        context=check_resolve._context_payload(),
        context_label=args.context,
        materialize=not args.no_materialize,
        cooldown_every=args.cooldown_every,
        cooldown_seconds=args.cooldown_seconds,
    )

    out = Path(args.out) if args.out else OUT_DIR / f"evaluation-{datetime.datetime.now(KST):%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    for label, value in {**result["summary"]["groups"], "합계": result["summary"]["total"]}.items():
        stages = value["failure_stages"]
        print(
            f"  {label}  적중 {value['HIT']}/{value['runs']} · 근접 {value['NEAR']} · 빗나감 {value['MISS']} · "
            f"못 붙음 {value['UNATTACHED']} · 이름 있는 값 {value['spoken_hits']}/{value['spoken_runs']} · 오류 {value['errors']}"
        )
        print(
            f"  {label}  발화 성공 {value['passed']}/{value['runs']} · 실패 기능 선택 {stages[STAGE_FUNCTION]} · "
            f"인자 추출 {stages[STAGE_INPUT]} · 실행 오류 {stages[STAGE_ERROR]}"
        )
    if result["meta"]["stopped"]:
        print(f"  멈춤: {result['meta']['stopped']}")
    print(f"  결과 {out}")
    return 1 if (result["meta"]["stopped"] or "").startswith("ServerDown") else 0


if __name__ == "__main__":
    sys.exit(main())
