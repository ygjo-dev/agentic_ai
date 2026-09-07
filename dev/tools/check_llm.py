"""모델 하나를 정답표와 시연 자로 재는 도구. 저장소가 가진 유일한 LLM 성적계다.

`check_resolve.py` 와 무엇이 다른가.

    check_resolve   POST /resolve 를 부른다. 화면이 지나는 길을 그대로 잰다
    check_llm       resolve_service 를 직접 부른다. FastAPI 를 안 띄워도 되고
                    provider 를 갈아끼워 모델끼리 맞댈 수 있다

**정답표를 다시 적지 않는다.** 발화도 기대값도 판정 자도 전부 `check_resolve` ·
`check_demo` 에서 가져온다. 자가 둘이 되면 두 성적표가 서로를 못 견준다.

2026-09-06 이전에는 이 일을 저장소 밖 실험 환경의 driver 가 했다. 저장소가
바뀌면 함께 고쳐야 하는 코드라 안으로 들여왔고, 밖의 것은 그때의 증거로만 남겼다.
★ 밖에 평가 driver 를 다시 만들지 않는다 — 만들면 두 벌을 손으로 맞추게 된다.

    python dev/tools/check_llm.py                              기본 모델 한 판
    python dev/tools/check_llm.py --model qwen3:32b --runs 3   모델을 골라 세 판
    python dev/tools/check_llm.py --out /tmp/여기               자세한 결과를 파일로
    python dev/tools/check_llm.py --dry-run                    안 재고 지금 무엇에 붙는지만

## --dry-run 이 답하는 것

재기 전에 사람이 늘 확인하던 셋이다 — 어느 모델인가 · 어느 backend 인가 ·
그 서버가 떠 있는가. 그동안은 한 판(수 분)을 시작해 봐야 알았고, 안 떠 있으면
발화마다 타임아웃을 기다린 뒤에야 알았다.

    모델 고르는 차례   --model > LLM_MODEL > models.yaml 의 default
    provider          models.yaml 이 모델마다 적는다 (ollama · vllm)
    host              기계마다 다르므로 환경변수다 (OLLAMA_HOST · VLLM_HOST).
                      안 적혀 있으면 provider 모듈의 코드 기본값이고,
                      --dry-run 이 둘 중 어느 쪽인지 함께 적는다

**서버를 띄우지도 내리지도 않는다.** 닿는지만 보고 말한다.

## 판마다 차례가 같다

정답표를 적힌 차례대로 다 돌고 나서 시연을 돈다. 사이에 다른 요청을
끼우지 않는다 — NOTES 「백다섯째」의 재는 법이다.

## 여러 판을 한 프로세스에서 잇달아 돈다

재현의 단위가 드라이버 프로세스가 아니라 모델 로드다 (NOTES 「아흔한째」).
프로세스를 판마다 새로 띄우면 견줄 수 없는 변수가 하나 는다.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

# 프로젝트 모듈보다 먼저 읽는다. providers 가 import 시점에 OLLAMA_HOST ·
# VLLM_HOST 를 읽어 굳히므로, 뒤에 읽으면 .env 가 안 먹는다.
# (app/api/main.py 가 같은 까닭으로 같은 자리에 둔다)
load_dotenv(REPO_ROOT / ".env")

import paths  # noqa: E402
from dev.tools.check_demo import DEMO, SELECT  # noqa: E402
from dev.tools.check_resolve import (  # noqa: E402
    BASELINE_LAST,
    EXTENSION_LAST,
    HIT,
    MISS,
    NEAR,
    UNATTACHED,
    UTTERANCES,
    _grade,
)
from llm_engine.llm_selector import get_llm  # noqa: E402
from llm_engine.model_config import OLLAMA, VLLM, get_model_config  # noqa: E402
from llm_engine.providers import ollama, vllm  # noqa: E402
from orchestrator import resolve_service  # noqa: E402

# provider -> (host 를 담은 환경변수 이름, 살아 있는지 물어볼 경로).
# 값 자체는 provider 모듈이 이미 읽어 두었으므로 여기서 기본값을 다시 적지 않는다.
PROBE = {
    OLLAMA: ("OLLAMA_HOST", ollama.OLLAMA_HOST, "/api/tags"),
    VLLM: ("VLLM_HOST", vllm.VLLM_HOST, "/v1/models"),
}


def _reachable(url: str, timeout: float = 3) -> str:
    """그 주소가 답하는가.

    출력  사람이 읽을 한 마디. 못 닿는 까닭도 적음
    규칙  상한 3초. 오래 걸리는 점검은 점검이 아님
    제약  예외를 올리지 않는다. 못 닿는다는 사실 자체가 답임
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return f"떠 있다 (HTTP {response.status})"
    except urllib.error.HTTPError as error:
        # 응답이 왔으니 서버는 떠 있다. 그 경로가 없을 뿐이다.
        return f"떠 있다 (HTTP {error.code})"
    except Exception as error:  # noqa: BLE001 — 거부 · 타임아웃 · DNS 가 같은 답이다
        return f"못 닿는다 ({type(error).__name__})"


def _dry_run(config, model_arg: str | None) -> int:
    """안 재고 지금 무엇에 붙는지만 찍음.

    출력  0 이면 그 backend 에 닿음. 1 이면 못 닿거나 모르는 provider
    규칙  값마다 어디서 왔는지를 함께 적음. 「왜 저 모델이 떴지」가 이 도구에
          물어볼 질문이라 출처가 없으면 답이 안 됨
    제약  서버를 띄우거나 내리지 않는다. 닿는지만 봄
    """
    if model_arg:
        source = "--model"
    elif os.environ.get("LLM_MODEL"):
        source = "환경변수 LLM_MODEL"
    else:
        source = f"{paths.MODELS_PATH.name} 의 default"

    print(f"모델      {config.model}   ({source})")
    print(f"provider  {config.provider}   ({paths.MODELS_PATH.name})")

    probe = PROBE.get(config.provider)
    if probe is None:
        print(f"host      모르는 provider 다. 아는 것은 {OLLAMA} · {VLLM} 뿐이다")
        return 1

    env_name, host, path = probe
    origin = f"{env_name}" if os.environ.get(env_name) else "코드 기본값"
    print(f"host      {host}   ({origin})")
    print(f"timeout {config.timeout}초 · reason {config.reason_max_length}자")
    print()

    verdict = _reachable(f"{host}{path}")
    print(f"{host}{path}  ->  {verdict}")
    return 0 if verdict.startswith("떠 있다") else 1


def _ask(llm, run_no: int, number: int, utterance: str, expected: set,
         reason_max_length: int, kind: str) -> dict:
    """발화 하나. 부르다 죽어도 판이 멈추지 않게 오류도 결과로 적는다.

    규칙  오류는 못 붙음으로 셈. _grade 가 frozenset 이 아닌 것을 그렇게 봄
    """
    started = time.perf_counter()
    error = None
    result = {}
    try:
        result = resolve_service.resolve(
            utterance,
            llm_client=llm,
            reason_max_length=reason_max_length,
        )
    except Exception as exc:  # noqa: BLE001 — 오류도 판정 대상이다
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started

    if error is None:
        found = frozenset(
            rid
            for rid in [result.get("recipe_id"), *(result.get("candidate_recipe_ids") or [])]
            if rid
        )
        status = result.get("status") or "-"
    else:
        found = error
        status = "-"

    return {
        "run": run_no,
        "set": kind,
        "index": number,
        "utterance": utterance,
        "expected": sorted(expected),
        "status": status,
        "recipe_id": result.get("recipe_id"),
        "candidate_recipe_ids": result.get("candidate_recipe_ids"),
        "reason": result.get("reason"),
        "argument": result.get("argument"),
        "found": sorted(found) if isinstance(found, frozenset) else None,
        "grade": _grade(found, status, expected),
        "latency": round(elapsed, 3),
        "error": error,
    }


def _one_round(llm, run_no: int, reason_max_length: int) -> tuple:
    """한 판 = 정답표 36 + 시연 9.

    제약  차례를 판마다 똑같이 지킨다.
          사이에 다른 요청을 끼우지 않는다
    """
    rows = [
        _ask(llm, run_no, number, utterance, expected, reason_max_length, "utterance")
        for number, utterance, expected, _flag in UTTERANCES
    ]
    demo_rows = [
        _ask(llm, run_no, number, utterance, expected, reason_max_length, "demo")
        for number, utterance, expected in DEMO
    ]
    return rows, demo_rows


def _tally(rows: list) -> dict:
    """네 칸과 실패점수. 실패점수는 근접×1 + 빗나감×2 + 못붙음×2."""
    counted = Counter(row["grade"] for row in rows)
    latency = [row["latency"] for row in rows]
    return {
        "n": len(rows),
        "HIT": counted[HIT],
        "NEAR": counted[NEAR],
        "MISS": counted[MISS],
        "UNATTACHED": counted[UNATTACHED],
        "failure_score": counted[NEAR] + counted[MISS] * 2 + counted[UNATTACHED] * 2,
        "mean_latency": round(sum(latency) / max(len(latency), 1), 2),
        "max_latency": round(max(latency), 2) if latency else 0,
    }


def _groups(rows: list) -> dict:
    """세 묶음. 시작 데이터가 다르므로 한 백분율로 합치지 않는다."""
    return {
        f"말한 것 (1~{BASELINE_LAST})":
            [r for r in rows if r["index"] <= BASELINE_LAST],
        f"찍은 지점 ({BASELINE_LAST + 1}~{EXTENSION_LAST})":
            [r for r in rows if BASELINE_LAST < r["index"] <= EXTENSION_LAST],
        f"보이는 범위 ({EXTENSION_LAST + 1}~{len(UTTERANCES)})":
            [r for r in rows if r["index"] > EXTENSION_LAST],
    }


def _report(run_no, rows, demo_rows, elapsed, model, provider) -> str:
    summary = _tally(rows)
    selects = sum(1 for r in demo_rows if r["status"] == SELECT)
    lines = [
        f"# {model} ({provider}) · {run_no}판",
        "",
        f"prompt {paths.RECIPE_SELECTION_PROMPT_PATH} · "
        f"menu {len(paths.MENU_YAML_PATH.read_text(encoding='utf-8'))}자 · {elapsed:.1f}초",
        "",
        f"적중 {summary['HIT']}/{summary['n']} · 근접 {summary['NEAR']} · "
        f"빗나감 {summary['MISS']} · 못 붙음 {summary['UNATTACHED']} · "
        f"실패점수 {summary['failure_score']}",
        f"시연 SELECT {selects}/{len(demo_rows)} · "
        f"적중 {sum(1 for r in demo_rows if r['grade'] == HIT)}/{len(demo_rows)}",
        f"latency 평균 {summary['mean_latency']}초 · 최대 {summary['max_latency']}초",
        "",
        "## 묶음",
        "",
    ]
    for name, group in _groups(rows).items():
        g = _tally(group)
        lines.append(
            f"- {name} : 적중 {g['HIT']}/{g['n']} · 근접 {g['NEAR']} · "
            f"빗나감 {g['MISS']} · 못 붙음 {g['UNATTACHED']} · 실패 {g['failure_score']}")
    lines += ["", "## 적중이 아닌 것", ""]
    for row in rows + demo_rows:
        if row["grade"] != HIT or (row["set"] == "demo" and row["status"] != SELECT):
            lines.append(f"- [{row['set']} {row['index']}] {row['utterance']}")
            lines.append(f"  - 기대 {row['expected']} · 나온 것 {row['found']} · "
                         f"{row['grade']} · status {row['status']}")
            lines.append(f"  - reason: {row['reason']}")
            if row["error"]:
                lines.append(f"  - error: {row['error']}")
    return "\n".join(lines) + "\n"


def _repro(all_runs: list) -> list:
    """여러 판을 발화별로 맞댐. 같았는가와 어느 칸이 달랐는가만 셈."""
    lines = ["", "재현성 (판을 발화별로 맞댐)"]
    fields = ("status", "recipe_id", "candidate_recipe_ids", "reason", "argument")
    for kind, total in (("utterance", len(UTTERANCES)), ("demo", len(DEMO))):
        per_run = [[r for r in run if r["set"] == kind] for run in all_runs]
        same_candidate = same_whole = 0
        for i in range(total):
            trio = [run[i] for run in per_run]
            if len({json.dumps(t["candidate_recipe_ids"], ensure_ascii=False) for t in trio}) == 1:
                same_candidate += 1
            if len({json.dumps({f: t[f] for f in fields}, sort_keys=True, ensure_ascii=False)
                    for t in trio}) == 1:
                same_whole += 1
        lines.append(f"  {kind:<10} 후보 동일 {same_candidate}/{total} · "
                     f"전체 동일 {same_whole}/{total}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description="모델 하나를 정답표 36 과 시연 9 로 잰다.")
    parser.add_argument("--model", default=None, help="쓸 모델. 없으면 기본 모델")
    parser.add_argument("--runs", type=int, default=1, help="몇 판 (기본 1)")
    parser.add_argument("--out", default="", help="자세한 결과를 남길 디렉터리")
    parser.add_argument("--dry-run", action="store_true",
                        help="안 재고 지금 무엇에 붙는지와 그 서버가 떠 있는지만")
    args = parser.parse_args()

    config = get_model_config(args.model)
    if args.dry_run:
        return _dry_run(config, args.model)

    llm = get_llm(args.model)
    out = Path(args.out) if args.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)

    print(f"{config.model} · {config.provider} · timeout {config.timeout}초 · "
          f"reason {config.reason_max_length}자")

    all_runs, verdicts = [], []
    for run_no in range(1, args.runs + 1):
        started = time.perf_counter()
        rows, demo_rows = _one_round(llm, run_no, config.reason_max_length)
        elapsed = time.perf_counter() - started
        all_runs.append(rows + demo_rows)

        summary = _tally(rows)
        selects = sum(1 for r in demo_rows if r["status"] == SELECT)
        verdicts.append({"run": run_no, "model": config.model,
                         "provider": config.provider, **summary,
                         "demo_select": selects, "elapsed": round(elapsed, 1)})
        print(f"  {run_no}판  적중 {summary['HIT']}/{summary['n']} · "
              f"근접 {summary['NEAR']} · 빗나감 {summary['MISS']} · "
              f"못 붙음 {summary['UNATTACHED']} · 실패 {summary['failure_score']} · "
              f"시연 {selects}/{len(demo_rows)} · {elapsed:.0f}초", flush=True)

        if out:
            with (out / f"run{run_no}.jsonl").open("w", encoding="utf-8") as handle:
                for row in rows + demo_rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            (out / f"run{run_no}.md").write_text(
                _report(run_no, rows, demo_rows, elapsed, config.model, config.provider),
                encoding="utf-8")

    if args.runs > 1:
        for line in _repro(all_runs):
            print(line)
    if out:
        (out / "verdicts.json").write_text(
            json.dumps(verdicts, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n자세한 결과 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
