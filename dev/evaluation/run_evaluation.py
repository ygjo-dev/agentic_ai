"""벤치마크 한 번을 돌리는 main. 정답표를 읽고 Resolve 를 부르고 채점해 결과를 남긴다.

    Test Suite 읽기     engine/load_test_suite
      ↓
    Resolve 부르기      resolve_via_api (POST /resolve) → 고른 recipe 를 materialize
      ↓
    채점                engine/score
      ↓
    실행 조건 · GPU     engine/monitor_metadata · engine/monitor_gpu
      ↓
    결과 남기기         engine/manage_benchmark → outputs/local_benchmark/<run_id>/

    python dev/evaluation/run_evaluation.py                        FULL48 · 1회 · materialize 포함
    python dev/evaluation/run_evaluation.py --suite dev/evaluation/inputs/test_suites/test_suite_v2.yaml --gpu gate
                                                                   테스트 세트 v2 · 사무실 조용 정책(박자만, 기록 안 함)
    python dev/evaluation/run_evaluation.py --runs 3 --only 2,4    고른 발화만 여러 번
    python dev/evaluation/run_evaluation.py --context bbox         materialize 에 실을 지도 문맥
    python dev/evaluation/run_evaluation.py --no-materialize       /resolve 만
    python dev/evaluation/run_evaluation.py --cooldown-every 6     6번마다 5초 쉼 (발열 · 팬 소음)
    python dev/evaluation/run_evaluation.py --no-save              벤치마크 폴더를 안 남김
    python dev/evaluation/run_evaluation.py --out 결과.json        결과 JSON 한 장의 자리

화면(app/ui 테스트 탭)은 run_dataset 으로 같은 run 을 부른다. 판정 · 결과 모양이 창구와 같다.
화면의 「중지」는 should_stop 으로, 「이어 실행」은 resume 으로 들어온다. 멈춘 기록은 run.json 없이
meta.json + cases.jsonl 로 남고, 이어 재면 같은 run_id · 같은 폴더에서 남은 발화만 잰다.

**MCP 도구를 부르지 않는다.** `/resolve` 를 부르고, 고른 recipe 를 workflow_materializer 로 KRRI
native workflow 까지만 만든다. Gateway 실행은 `check_resolve --execute` 의 일이다.

`/resolve` 부르기(주소 · timeout · ServerDown)와 지도 문맥은 여기가 원본이다. 계기판
`dev/tools/check_resolve.py` 가 이것을 import 해 쓴다. 평가는 계기판을 import 하지 않는다.

`--out` 의 결과 JSON 한 장은 `dev/tools/sweep_out/` 에 둔다 (`.gitignore`). 벤치마크 폴더는
`outputs/local_benchmark/` 에 남는다(`.gitignore`). 기준으로 남길 것은 사람이
`outputs/official_benchmark/` 로 옮긴다. 여기서 git 을 부르지 않는다.
"""

import argparse
import datetime
import json
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import endpoints  # noqa: E402
from dev.evaluation.engine import load_test_suite, manage_benchmark, monitor_gpu, monitor_metadata, score  # noqa: E402
from dev.evaluation.engine.monitor_gpu import StopRun  # noqa: E402

OUT_DIR = REPO_ROOT / "dev" / "tools" / "sweep_out"
KST = monitor_metadata.KST

load_dotenv(REPO_ROOT / ".env")

# 역할 manifest 의 timeout 보다 짧으면 느린 판을 잴 때 서버가 답하기 전에 여기서
# 끊겨 결과가 오류로만 찬다. 화면의 서비스 호출(app/ui/api_client.RESOLVE_TIMEOUT 180)과 달리
# 평가는 느린 판도 재므로 값을 넉넉히 따로 둔다.
TIMEOUT = 900

# materialize 에 실을 지도 문맥 세 가지. 고르는 데는 안 쓰인다 — /resolve 는 문맥을 안 받는다.
# both 가 KRRI_ASAP 화면에서 우클릭한 뒤와 같은 조건이라 기본이다. bbox 는 우클릭 전, none 은 문맥 없음.
CONTEXT_NONE, CONTEXT_BBOX, CONTEXT_BOTH = "none", "bbox", "both"
CONTEXTS = (CONTEXT_NONE, CONTEXT_BBOX, CONTEXT_BOTH)

# 지도 범위. 오송역(127.3277, 36.6200)에서 반경 15km 이고
# 온톨로지의 지점 주변 범위 변환(radiusMeters 15000)으로 만든 상자다. 시연이 오송·청주에서 돈다.
VIEW_BBOX = [[127.1598, 36.4853], [127.4956, 36.7547]]

# both 일 때 얹는 찍은 지점. bbox 의 중심과 같은 좌표다.
# label 과 source 는 KRRI_ASAP 의 useChat 이 우클릭 뒤에 얹는 문자열과 같다.
PICKED_POINT = {
    "lon": 127.3277,
    "lat": 36.6200,
    "label": "관심 지점",
    "source": "map-right-click",
}


class ServerDown(RuntimeError):
    """서버에 닿지 못했다. 재시도하지 않고 즉시 멈춘다."""


# ================================================================ Resolve
def base_url() -> str:
    """창구 주소(AGENTIC_API_URL).

    규칙  화면이 부르는 주소와 같아야 결과를 믿을 수 있으므로 같은 환경변수를 봄
          부를 때마다 읽음. import 시점에 굳히면 정답표만 빌려 쓰는 자까지 주소를 요구하게 됨
    """
    return endpoints.agentic_api_url()


def resolve_via_api(utterance: str) -> dict:
    """POST /resolve 한 번의 응답 본문.

    규칙  base_url · TIMEOUT · 매개변수 utterance 하나. 지도 문맥을 안 보냄 (/resolve 가 안 받음)
          서버에 못 닿으면 ServerDown. 재시도하지 않음
    """
    try:
        response = requests.post(f"{base_url()}/resolve", params={"utterance": utterance}, timeout=TIMEOUT)
    except requests.exceptions.ConnectionError as exc:
        raise ServerDown(str(exc)) from exc
    response.raise_for_status()
    return response.json()


def context_payload(label: str) -> dict | None:
    """지도 문맥 한 벌. label 은 CONTEXT_NONE · CONTEXT_BBOX · CONTEXT_BOTH.

    출력  문맥 dict. none 이면 None
    규칙  bbox 만 있는 것이 우클릭 전 모양임. selectedLocation 은 null
          both 는 그 위에 찍은 지점을 얹음
    """
    if label == CONTEXT_NONE:
        return None
    context = {"view": {"bbox": VIEW_BBOX}, "selectedLocation": None}
    if label == CONTEXT_BOTH:
        context = {**context, "selectedLocation": dict(PICKED_POINT)}
    return context


def materialized(response: dict, context: dict | None, now: datetime.datetime) -> dict:
    """고른 recipe 의 KRRI native workflow. MCP 는 안 부름.

    규칙  status 가 SELECT 이고 recipe_id 가 있을 때만 만듦. 아니면 NOT_SELECTED
          게시 오류(PlanError 등)는 결과 한 벌을 끝까지 내려고 error 칸에 적음
    """
    from execution import workflow_materializer

    recipe_id = response.get("recipe_id")
    if response.get("status") != "SELECT" or not recipe_id:
        return {"status": score.NOT_SELECTED, "recipe_id": recipe_id, "workflow": None}
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


# ================================================================ 발화 하나
def run_case(case: dict, label: str, run: int, resolve, context: dict | None, materialize: bool, now) -> dict:
    """발화 하나를 한 번 잰 결과 (Case Result). Resolve → materialize → score.

    규칙  timing.started_at 은 부르기 직전 시각. resolve_s 는 resolve 호출 하나만 감쌈
          resolve 가 터지면 score.grade_error. 아니면 materialize 한 뒤 score.grade_case
          ServerDown 은 삼키지 않음. 부르는 쪽이 멈춤
    """
    head = score.case_head(case, label, run)
    started_at = datetime.datetime.now(KST).isoformat(timespec="milliseconds")
    started = time.perf_counter()
    try:
        response = resolve(case["utterance"])
    except ServerDown:
        raise
    except Exception as exc:  # noqa: BLE001 — 오류도 결과의 하나로 남긴다.
        timing = {"started_at": started_at, "resolve_s": round(time.perf_counter() - started, 3), "materialize_s": None}
        return score.grade_error(case, head, exc, timing)
    resolve_s = round(time.perf_counter() - started, 3)

    built, materialize_s = None, None
    if materialize:
        started = time.perf_counter()
        built = materialized(response, context, now)
        materialize_s = round(time.perf_counter() - started, 3)
    timing = {"started_at": started_at, "resolve_s": resolve_s, "materialize_s": materialize_s}
    return score.grade_case(case, head, response, built, timing)


# ================================================================ 정답표 한 벌
# 사람이 「중지」를 눌러 멈춘 까닭. meta.stopped 에 적힌다.
USER_STOP = "user_stop: 사용자가 중지함"


def _measure(plan: list, rows: list, *, planned: int, label_of: dict, resolve, context, materialize: bool, now,
             cooldown_every: int, cooldown_seconds: float, recorder, progress, monitor, should_stop) -> tuple[str | None, int]:
    """plan 의 (발화, 차례) 를 차례로 재서 rows 에 덧붙임. (멈춘 까닭 또는 None, 이번에 부른 수).

    규칙  줄마다 차례대로: recorder.case · progress(끝난 수, 전체 수, 그 줄) · monitor.after_case(끝난 수, 전체 수).
          끝난 수는 rows 전체(이어 재면 전에 잰 줄 포함)
          should_stop 은 Resolve 를 부르기 바로 앞에서 봄(쉼 뒤). 참이면 USER_STOP 으로 멈춤.
          이미 부른 Resolve 는 끝까지 기다려 그 줄을 남긴 뒤에 멈춤
          마지막 줄 뒤에는 안 봄. 다 잰 뒤에 눌린 중지는 끝난 것으로 둠
          서버에 못 닿거나(ServerDown) StopRun · KeyboardInterrupt 면 거기서 멈추고 까닭을 돌려줌
    제약  두 줄을 동시에 재지 않는다. 다음 발화를 미리 부르지 않는다
    """
    stopped, called = None, 0
    try:
        if monitor:
            monitor.before_run()
        for case, number in plan:
            # 다음 요청 앞에서 쉰다. 뒤에서 쉬면 마지막 요청 뒤에도 쉬게 되고,
            # 그만큼은 아무도 기다릴 이유가 없는 시간이다.
            if cooldown_every and called and called % cooldown_every == 0:
                time.sleep(cooldown_seconds)
            if should_stop and should_stop():
                stopped = USER_STOP
                break
            rows.append(run_case(case, label_of[case["group"]], number, resolve, context, materialize, now))
            called += 1
            if recorder:
                recorder.case(rows[-1])
            if progress:
                progress(len(rows), planned, rows[-1])
            if monitor:
                monitor.after_case(len(rows), planned)
    except ServerDown as exc:
        stopped = f"ServerDown: {exc}"
    except StopRun as exc:
        stopped = f"StopRun: {exc}"
    except KeyboardInterrupt:
        stopped = "interrupted"

    if monitor:
        try:
            monitor.after_run(called)
        except KeyboardInterrupt:
            pass
    return stopped, called


def _close(head: dict, rows: list, labels: tuple, *, stopped: str | None, complete: bool, elapsed_s: float,
           ended: datetime.datetime, environment, recorder) -> dict:
    """잰 줄로 결과 한 벌을 세우고 남김. 다 쟀으면 run.json, 아니면 meta.json 만 다시 씀.

    규칙  다 잰 것(complete)만 finished_at 을 적고 recorder.finish 로 run.json 을 씀
          못 다 잰 것은 finished_at None · stopped(까닭) · stopped_at 을 적어 recorder.interrupt. cases.jsonl 은 그대로
          합계는 score.summarize 가 줄에 적힌 판정을 셈
    제약  못 다 잰 것에 run.json 을 쓰지 않는다
    """
    tail = {"finished_at": ended.isoformat(), "elapsed_s": round(elapsed_s, 1), "stopped": None, "environment": environment}
    if not complete:
        tail = {"finished_at": None, "elapsed_s": round(elapsed_s, 1), "stopped": stopped or manage_benchmark.INCOMPLETE,
                "stopped_at": ended.isoformat(), "environment": environment}
    result = {"meta": {**head, **tail}, "summary": score.summarize(rows, labels), "cases": rows}
    if recorder:
        if complete:
            recorder.finish(result)
        else:
            recorder.interrupt(result["meta"])
        result["meta"]["saved_to"] = str(recorder.dir)
    return result


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
    environment: dict | None = None,
    should_stop=None,
) -> dict:
    """정답표를 재서 결과 한 벌 (Test Run).

    출력  {meta, summary, cases}. json 으로 바로 쓸 수 있는 값만
          meta 머리는 monitor_metadata.benchmark_meta. 끝에 finished_at · elapsed_s · stopped · environment 를 더함.
          다 못 잰 것은 finished_at 이 None 이고 stopped_at 이 더 붙음
    규칙  only 가 있으면 그 번호만, 없으면 enabled 인 발화만. 파일 차례 그대로
          발화마다 runs 회
          서버에 못 닿거나 끊기거나 StopRun 이거나 should_stop() 이 참이면 거기서 멈추고
          거기까지의 결과와 까닭(meta.stopped)을 냄. should_stop 은 Resolve 를 부르기 바로 앞에서만 봄 (_measure)
          materialize 의 부르는 순간은 now 하나로 고정함. 안 주면 시작 시각
          cooldown_every 가 0 보다 크면 그만큼 부른 뒤 cooldown_seconds 초 쉼.
          센 수는 발화 × runs 전체를 통틀어서임. 0 이면 안 쉼(기본)
          발화 하나가 끝날 때마다 차례대로: save_dir 이면 그 줄을 cases.jsonl 에 덧붙임 ·
          progress(잰 수, 전체 수, 그 결과 줄) · monitor.after_case(잰 수, 전체 수).
          결과 줄은 판정까지 끝난 cases 의 한 줄 그대로(오류 줄 포함). 줄마다 정확히 한 번, 정답표 차례로
          progress 가 던진 예외는 삼키지 않음. 평가가 거기서 멈추고 예외가 부르는 쪽으로 감
          (KeyboardInterrupt · StopRun 만 meta.stopped 로 남김). 그래도 끝난 줄은 cases.jsonl 에 남음
          monitor 가 있으면 시작 전 before_run, 끝나고 after_run. 결과에 아무것도 안 실음 (박자만)
          environment 는 실행 하드웨어 한 벌(monitor_gpu.environment). 그대로 meta.environment 에 실림
          save_dir 이면 manage_benchmark.Recorder 가 <save_dir>/<run_id>/ 에 남김.
          도는 동안 meta.json + cases.jsonl, 다 재면 run.json 하나만 남음.
          멈추면 run.json 을 안 쓰고 meta.json 에 까닭을 적음. 이어 재기는 resume
          dataset 은 {id, label}. 있으면 meta.suite 에 dataset_id · label 로 실림
    제약  MCP 도구를 부르지 않는다.
          쉬는 것을 재는 값에 섞지 않는다.
          다음 요청 앞에서만 쉬므로 마지막 요청 뒤에는 안 쉼. resolve_s 는
          resolve 호출 하나만 감싸 재므로 쉬어도 시간이 안 늘어나고 판정도 안 바뀜
          run 자체는 GPU 를 보지 않는다. nvidia-smi 는 넘겨받은 monitor · environment 의 일임.
          재는 자(판정 · 결과 줄)에 기계 상태를 섞으면 같은 정답표가 기계마다 다른 것을 재게 됨
    """
    if cooldown_every < 0 or cooldown_seconds < 0:
        raise ValueError(
            f"쉬는 설정은 0 이상이다: cooldown_every={cooldown_every} · cooldown_seconds={cooldown_seconds}"
        )

    # 1. Test Suite
    path = Path(suite_path or load_test_suite.SUITE_PATH)
    labels = load_test_suite.group_labels(suite)
    label_of = load_test_suite.label_of(suite)
    cases = [case for case in suite["cases"] if (case["id"] in only if only else case["enabled"])]

    # 2. 저장 자리와 실행 조건
    started = datetime.datetime.now(KST)
    now = now or started
    suite_name = load_test_suite.identity(suite, path)["name"]
    recorder = manage_benchmark.Recorder(save_dir, started, suite_name) if save_dir else None
    head = monitor_metadata.benchmark_meta(
        run_id=recorder.run_id if recorder else manage_benchmark.new_run_id(started, suite_name),
        suite=suite, suite_path=path, cases=cases, dataset=dataset, runs=runs, resolver=resolver,
        cooldown_every=cooldown_every, cooldown_seconds=cooldown_seconds,
        context=context, context_label=context_label, materialize=materialize, now=now, started=started,
    )
    if recorder:
        recorder.start(head)

    # 3. 발화마다 Resolve → 채점
    plan = [(case, number) for case in cases for number in range(1, runs + 1)]
    rows: list[dict] = []
    stopped, _called = _measure(
        plan, rows, planned=len(plan), label_of=label_of, resolve=resolve, context=context, materialize=materialize,
        now=now, cooldown_every=cooldown_every, cooldown_seconds=cooldown_seconds, recorder=recorder,
        progress=progress, monitor=monitor, should_stop=should_stop,
    )

    # 4. 합계 · 저장
    finished = datetime.datetime.now(KST)
    return _close(head, rows, labels, stopped=stopped, complete=stopped is None,
                  elapsed_s=(finished - started).total_seconds(), ended=finished, environment=environment,
                  recorder=recorder)


# ================================================================ 이어 실행
# 이어 실행을 막는 까닭. 화면이 그대로 보인다.
RESUME_CHANGED = "실행 조건이 변경되어 이어 실행할 수 없습니다."
RESUME_UNREPRODUCIBLE = "저장된 실행 조건만으로 동일 실행을 재현할 수 없습니다."
RESUME_OFFICIAL = "공식 기록은 이어 실행하지 않습니다."
RESUME_FINISHED = "완료 파일(run.json)로 저장된 기록이라 이어 실행할 수 없습니다."
RESUME_ROWS = "저장된 발화 결과가 실행 계획과 맞지 않습니다."

# meta.json 머리에서 멈출 때마다 새로 적는 칸. 이어 잴 때 머리에서 뗀다.
_SEGMENT_KEYS = ("finished_at", "elapsed_s", "stopped", "stopped_at", "environment", "saved_to")


class ResumeRefused(ValueError):
    """이 기록은 이어 잴 수 없다. 까닭이 문장으로 붙음. 파일은 안 건드림."""


def _unit(row: dict) -> tuple:
    """결과 줄 하나의 실행 신원. (case_id, run)."""
    return row["case_id"], row.get("run", 1)


def resume_check(kind: str, run_id: str, *, resolver: str = "api /resolve") -> dict:
    """저장된 기록을 같은 run_id 로 이어 잴 수 있나.

    출력  {resumable, reason, fields, gaps, done, planned}
          fields 는 monitor_metadata.compare_resume 의 줄들 (조건마다 저장된 값 · 지금 값 · 같나).
          resolver 가 다르면 Resolver 줄이 끝에 붙음. gaps 는 저장된 머리에 없는 칸 이름
    규칙  local 의 끝나지 않은 기록(meta.json + cases.jsonl)만 이어 잼. official 은 RESUME_OFFICIAL, run.json 은 RESUME_FINISHED
          저장된 머리에 이어 잴 칸이 없으면 RESUME_UNREPRODUCIBLE. 짐작하지 않음
          조건이 하나라도 다르면 RESUME_CHANGED
          끝난 줄이 계획(selected_case_ids × runs)에 없거나 같은 (case_id, run) 이 둘이면 RESUME_ROWS
    제약  파일을 쓰거나 고치지 않는다. Resolve 를 부르지 않는다
    """
    def refused(reason, **extra):
        return {"resumable": False, "reason": reason, "fields": [], "gaps": [], "done": None, "planned": None, **extra}

    if kind != manage_benchmark.LOCAL:
        return refused(RESUME_OFFICIAL)
    folder = manage_benchmark.run_dir(kind, run_id)
    if (folder / manage_benchmark.RUN_FILE).is_file():
        return refused(RESUME_FINISHED)
    try:
        stored = manage_benchmark.read_incomplete(folder)
    except (OSError, ValueError, KeyError) as exc:
        return refused(f"{RESUME_UNREPRODUCIBLE} ({type(exc).__name__}: {exc})")
    meta, rows = stored["meta"], stored["rows"]
    counts = {"done": len(rows), "planned": manage_benchmark.planned_runs(meta)}

    gaps = monitor_metadata.resume_gaps(meta)
    fields = monitor_metadata.compare_resume(
        monitor_metadata.resume_identity(meta), monitor_metadata.current_resume_identity(meta)
    )
    if meta.get("resolver") not in (None, resolver):
        fields.append({"label": "Resolver", "stored": meta.get("resolver"), "current": resolver, "same": False})
    if gaps:
        return {**refused(RESUME_UNREPRODUCIBLE), "fields": fields, "gaps": gaps, **counts}
    if not all(field["same"] for field in fields):
        return {**refused(RESUME_CHANGED), "fields": fields, **counts}

    plan = {(case_id, number) for case_id in meta["suite"]["selected_case_ids"] for number in range(1, meta["runs"] + 1)}
    units = [_unit(row) for row in rows]
    if len(set(units)) != len(units) or not set(units) <= plan:
        return {**refused(RESUME_ROWS), "fields": fields, **counts}
    return {"resumable": True, "reason": None, "fields": fields, "gaps": [], **counts}


def resume(
    kind: str,
    run_id: str,
    *,
    resolve=resolve_via_api,
    resolver: str = "api /resolve",
    progress=None,
    monitor=None,
    environment: dict | None = None,
    should_stop=None,
) -> dict:
    """끝나지 않은 local 기록을 같은 run_id · 같은 폴더에서 이어 잰 결과 한 벌 (Test Run).

    출력  run 과 같은 모양. cases 는 전에 잰 줄과 새로 잰 줄을 계획 차례로 한 번씩
    규칙  resume_check 가 막으면 ResumeRefused. 그때 파일을 안 건드림
          잴 것은 계획(selected_case_ids × runs) 중 끝난 줄에 없는 (case_id, run) 뿐. 끝난 발화를 다시 안 부름
          정답표 · 문맥 · materialize · 부르는 순간(materialize_now) · 쉼 설정은 저장된 머리 그대로 씀
          끝이 잘린 cases.jsonl 은 끝난 줄만 남기고 이어 씀
          시작할 때 meta.json 에서 지난번 멈춘 까닭을 떼고 resumed_at 에 이번 시각을 더함.
          다시 멈추면 run 과 같이 meta.json 에 까닭을 적고, 다 재면 같은 폴더에 run.json 을 쓰고 meta.json · cases.jsonl 을 지움
          elapsed_s 는 잰 동안의 시간을 더한 것 (멈춰 있던 시간은 안 셈). environment 는 저장된 것이 있으면 그것
    제약  새 run_id · 새 폴더를 만들지 않는다. 전에 잰 줄을 다시 채점하거나 고치지 않는다.
          지금 조건을 저장된 조건 대신 쓰지 않는다
    """
    verdict = resume_check(kind, run_id, resolver=resolver)
    if not verdict["resumable"]:
        raise ResumeRefused(verdict["reason"])
    folder = manage_benchmark.run_dir(kind, run_id)
    stored = manage_benchmark.read_incomplete(folder)
    meta, rows = stored["meta"], list(stored["rows"])

    suite_path = Path(load_test_suite.dataset(meta["suite"]["dataset_id"])["path"])
    suite = load_test_suite.load(suite_path)
    by_id = {case["id"]: case for case in suite["cases"]}
    cases = [by_id[case_id] for case_id in meta["suite"]["selected_case_ids"]]
    runs = meta["runs"]
    order = {(case["id"], number): index for index, (case, number) in
             enumerate((case, number) for case in cases for number in range(1, runs + 1))}
    done = {_unit(row) for row in rows}
    plan = [(case, number) for case in cases for number in range(1, runs + 1) if (case["id"], number) not in done]

    if stored["torn"]:
        manage_benchmark.repair_rows(folder, rows)
    recorder = manage_benchmark.Recorder.reopen(folder)
    started = datetime.datetime.now(KST)
    head = {key: value for key, value in meta.items() if key not in _SEGMENT_KEYS}
    head["resumed_at"] = [*(meta.get("resumed_at") or []), started.isoformat()]
    before = meta.get("elapsed_s") or 0.0
    environment = meta.get("environment") or environment
    recorder.interrupt({**head, "elapsed_s": before, "environment": environment})

    materialize = meta["materialize"]
    now = datetime.datetime.fromisoformat(meta["materialize_now"]) if materialize else started
    cooldown = meta.get("cooldown") or {}
    stopped, _called = _measure(
        plan, rows, planned=len(order), label_of=load_test_suite.label_of(suite), resolve=resolve,
        context=meta["context"]["payload"], materialize=materialize, now=now,
        cooldown_every=cooldown.get("every") or 0, cooldown_seconds=cooldown.get("seconds") or 0.0,
        recorder=recorder, progress=progress, monitor=monitor, should_stop=should_stop,
    )

    finished = datetime.datetime.now(KST)
    rows.sort(key=lambda row: order[_unit(row)])
    return _close(head, rows, tuple(meta["suite"].get("group_labels") or ()), stopped=stopped,
                  complete=stopped is None and len(rows) == len(order),
                  elapsed_s=before + (finished - started).total_seconds(), ended=finished, environment=environment,
                  recorder=recorder)


def run_dataset(dataset_id: str, *, save: bool = True, runs_dir: Path | None = None, **options) -> dict:
    """이름으로 고른 정답표를 재서 결과 한 벌 (Test Run). 화면 테스트 탭이 부르는 자리.

    입력  dataset_id 는 load_test_suite.datasets() 의 id. options 는 run 의 키워드 인자 그대로
          save 면 Test Run 을 runs_dir(없으면 manage_benchmark.LOCAL_DIR)에 남김
          environment 를 안 주면 monitor_gpu.environment() 로 이 기계의 GPU 를 적음
    출력  run 의 결과. meta.suite 에 dataset id · 이름이 붙음
    규칙  모르는 id 면 KeyError
    제약  판정 규칙을 여기 따로 두지 않는다
    """
    chosen = load_test_suite.dataset(dataset_id)
    path = Path(chosen["path"])
    save_dir = (runs_dir or manage_benchmark.LOCAL_DIR) if save else None
    options.setdefault("environment", monitor_gpu.environment())
    return run(
        load_test_suite.load(path), suite_path=path, save_dir=save_dir,
        dataset={"id": chosen["id"], "label": chosen["label"]}, **options,
    )


# ================================================================ 명령줄
def main() -> int:
    parser = argparse.ArgumentParser(description="정답표로 발화 해석을 재고 벤치마크 결과를 남긴다.")
    parser.add_argument("--suite", default=str(load_test_suite.SUITE_PATH), help="정답표 YAML (기본 inputs/test_suites/test_suite_v1.yaml)")
    parser.add_argument("--runs", type=int, default=1, help="발화마다 몇 번 (기본 1)")
    parser.add_argument("--only", default="", help="돌릴 발화 번호. 예: 2,4")
    parser.add_argument(
        "--context",
        choices=CONTEXTS,
        default=CONTEXT_BOTH,
        help="materialize 에 실을 지도 문맥. 기본 both",
    )
    parser.add_argument("--no-materialize", action="store_true", help="/resolve 만 잰다")
    parser.add_argument("--out", default="", help="결과 JSON 경로 (기본 dev/tools/sweep_out/evaluation-<시각>.json)")
    parser.add_argument("--cooldown-every", type=int, default=0, help="몇 번 부르고 쉴까. 0 이면 안 쉼 (기본 0)")
    parser.add_argument("--cooldown-seconds", type=float, default=5.0, help="쉬는 시간 초 (기본 5)")
    parser.add_argument(
        "--gpu", choices=("off", "record", "gate"), default="record",
        help="record 는 실행 하드웨어(GPU 이름 · VRAM)만 적음, gate 는 거기에 사무실 조용 정책"
             "(engine/monitor_gpu.POLICY)으로 쉬고 멈춤, off 는 둘 다 안 함 (기본 record)",
    )
    parser.add_argument("--no-save", action="store_true", help="벤치마크 폴더를 outputs/local_benchmark 에 안 남김")
    args = parser.parse_args()

    # --only 와 같은 자리에서 막는다. 정답표를 읽기 전에 죽어야 오래 도는 회귀평가가
    # 한참 뒤에 설정 오타로 멈추는 일이 없다.
    if args.cooldown_every < 0 or args.cooldown_seconds < 0:
        print(f"쉬는 설정은 0 이상이다 : --cooldown-every {args.cooldown_every} · --cooldown-seconds {args.cooldown_seconds}")
        return 2

    suite_path = Path(args.suite)
    suite = load_test_suite.load(suite_path)
    only = [int(part) for part in args.only.replace(" ", "").split(",") if part] or None
    if only:
        missing = sorted(set(only) - {case["id"] for case in suite["cases"]})
        if missing:
            print(f"정답표에 없는 번호 : {missing}")
            return 2

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
        monitor=monitor_gpu.GpuMonitor(gate=True) if args.gpu == "gate" else None,
        save_dir=None if args.no_save else manage_benchmark.LOCAL_DIR,
        dataset=load_test_suite.dataset_of_path(suite_path),
        environment=None if args.gpu == "off" else monitor_gpu.environment(),
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
            f"  {label}  발화 성공 {value['passed']}/{value['runs']} · 실패 기능 선택 {stages[score.STAGE_FUNCTION]} · "
            f"인자 추출 {stages[score.STAGE_INPUT]} · 범위 밖 {stages[score.STAGE_SCOPE]} · 실행 오류 {stages[score.STAGE_ERROR]}"
        )
    board = result["summary"]["metrics"]
    print("  지표  " + " · ".join(f"{name} {pair['correct']}/{pair['total']}" for name, pair in board.items()))
    if result["meta"]["stopped"]:
        print(f"  멈춤: {result['meta']['stopped']}")
    print(f"  결과 {out}")
    if result["meta"].get("saved_to"):
        print(f"  벤치마크 {result['meta']['saved_to']}")
    return 1 if (result["meta"]["stopped"] or "").startswith("ServerDown") else 0


if __name__ == "__main__":
    sys.exit(main())
