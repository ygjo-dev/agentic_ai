"""시연 발화가 지금 온톨로지에서 통하는지 재는 도구.

**아래 GT 는 잠정이다.** MCP 도구 39개로 recipe 가 48개가 됐고, 거기에 축 조회
(ontology/shortlist.py)가 붙었다. 무엇이 정답인지는 표를 보고 사람이 정한다.

같은 발화가 두 번 다르게 나온 적이 있어 한 번 눌러본 것은 근거가 안 된다.
발화마다 여러 번 돌려 무엇이 나왔는지 표로 찍는다. 표를 보고 사람이 발화를
고치고, 다시 돌리고, 확정한다.

    python tools/check_resolve.py                   1~6번 × 5회
    python tools/check_resolve.py --runs 10         굳히기
    python tools/check_resolve.py --only 2          고친 발화만 다시
    python tools/check_resolve.py --model qwen3:4b  모델만 바꿔 (서버 재시작 없이)

화면이 지나는 것과 같은 경로여야 표를 믿을 수 있으므로 POST /resolve 를 부른다.
서버(uvicorn)가 떠 있어야 한다.

발화가 확정된 뒤에도 **이 파일은 지우지 않는다.** 온톨로지나 menu 가 바뀌면 다시
재야 하고, 그때 되살리는 것보다 두는 편이 싸다. 그래서 파일 하나에 담고
저장소의 다른 곳을 건드리지 않는다.

실측 기록과 "다시 시도하지 말 것" 은 NOTES.md 에 있다. 발화를 고치기 전에
읽는다 — 이미 재본 것을 또 재게 된다.

**여기와 NOTES.md 에 적힌 알아낸 것은 예전 온톨로지(철도 CCTV 14노드)와 예전
모델(qwen2.5:7b) 기준이다.** 지금 기본 모델은 `models.yaml` 의 qwen3:8b 다.

표를 두 장 찍는다. 적중 표와 축 표다. 후보가 안 맞을 때 LLM 이 recipe 를 잘못
고른 것인지 축을 잘못 쓴 것인지는 축 표에서 갈린다.
"""

import argparse
import os
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv

# (번호, 발화, 기대 recipe 집합, 기본 실행 여부)
#
# **기대값은 잠정이다.** 축 조회(ontology/shortlist.py)를 넣고 처음 재는
# 발화들이라 무엇이 정답인지 표를 보고 사람이 정한다.
#
#   001  말한 장소 → 장소 좌표 변환
#   025  말한 장소 → 장소 좌표 변환 → CCTV 조회
#   035  말한 장소 → 장소 좌표 변환 → 전기차 충전소 검색
#   046  말한 장소 → 장소 좌표 변환 → 지점 행정구역 판별 → 연령별 인구 구성 조회
#   007~010  말한 키워드 → 선거 네 데이터셋의 검색. 발화만으로는 안 갈린다
#
# 1 과 2 는 같은 recipe 를 다르게 물은 것이다. 001 은 22개 recipe 의 앞토막이라
# 끝점이 실제로 갈리는지가 관건이고, 그것을 가르는 것이 want 축이다.
UTTERANCES = [
    (1, "오송역 위치 보여줘",        {"recipe_001"}, True),
    (2, "오송역 좌표 알려줘",        {"recipe_001"}, True),
    (3, "오송역 CCTV 보여줘",        {"recipe_025"}, True),
    (4, "청주시 인구 구성 알려줘",   {"recipe_046"}, True),
    (5, "오송역 근처 충전소 찾아줘", {"recipe_035"}, True),
    (6, "국회의원 선거구 찾아줘",
     {"recipe_007", "recipe_008", "recipe_009", "recipe_010"}, True),
]

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

# 화면이 부르는 주소와 같아야 표를 믿을 수 있다. 그래서 같은 환경변수를 본다.
BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
TIMEOUT = 180  # demo/ui/api_client.RESOLVE_TIMEOUT 과 같다. LLM 이 끼는 호출이다.

RECIPES_DIR = REPO_ROOT / "workflows" / "static" / "recipes"
INIT_RECIPES_DIR = REPO_ROOT / "workflows" / "static" / "_init" / "recipes"

UTTERANCE_WIDTH = 38  # 표에서 발화 칸의 폭. 넘치면 자른다 — 번호로 알아본다.


# ── 한글 폭 ──────────────────────────────────────────────────────────
# 한글은 폭이 2 라 ljust 로는 표가 어긋난다. 표 라이브러리를 쓰지 않으므로
# 여기서 직접 센다.


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def _clip(text: str, width: int) -> str:
    """폭 width 안에 들어가게 자름. 잘렸으면 끝에 … 를 붙임."""
    if _width(text) <= width:
        return text
    kept, used = "", 0
    for ch in text:
        ch_width = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if used + ch_width > width - 1:
            break
        kept, used = kept + ch, used + ch_width
    return kept + "…"


# ── 호출 ────────────────────────────────────────────────────────────


class ServerDown(RuntimeError):
    """서버에 닿지 못했다. 재시도하지 않고 즉시 멈춘다."""


def _short(recipe_ids) -> str:
    """{"recipe_004", "recipe_005"} → "{004, 005}"."""
    trimmed = sorted(rid[len("recipe_"):] if rid.startswith("recipe_") else rid for rid in recipe_ids)
    return "{" + ", ".join(trimmed) + "}"


def _axes(result: dict) -> tuple:
    """응답의 축 셋. 표에 한 줄로 찍을 형태.

    출력  (given, want, about). 안 쓴 축은 "-"
    규칙  Counter 의 key 라 튜플로 둠. 리스트는 해시가 안 됨
    """
    return tuple(result.get(axis) or "-" for axis in ("given", "want", "about"))


def _call_resolve(utterance: str, model: str | None = None) -> tuple:
    """POST /resolve 한 번.

    입력  발화 · 모델 이름(없으면 서버 기본 모델)
    출력  (후보 집합, 축 셋). 후보는 recipe_id 와 candidate_recipe_ids 를 합친 것
    규칙  서버에 못 닿으면 ServerDown. 재시도하지 않고 즉시 멈춤
          모델은 요청마다 실어 보냄. 모델을 바꾸는 데 서버를 다시 띄우지 않음
    """
    params = {"utterance": utterance}
    if model:
        params["model"] = model

    try:
        response = requests.post(
            f"{BASE_URL}/resolve", params=params, timeout=TIMEOUT
        )
    except requests.exceptions.ConnectionError as exc:
        raise ServerDown(str(exc)) from exc

    response.raise_for_status()
    result = response.json()
    found = [result.get("recipe_id"), *(result.get("candidate_recipe_ids") or [])]
    return frozenset(rid for rid in found if rid), _axes(result)


# ── 측정 ────────────────────────────────────────────────────────────


def _measure(
    entries, runs: int, outcomes: dict, axes: dict, model: str | None = None
) -> None:
    """발화마다 runs 회 돌려 결과를 쌓음.

    입력  발화 목록 · 반복 횟수 · 채워 넣을 dict 둘 · 모델 이름
    규칙  outcomes[번호] 에 나온 후보 집합들의 Counter 를 쌓음
          axes[번호] 에 나온 (given, want, about) 조합의 Counter 를 쌓음
          실행 하나가 끝날 때마다 점 하나를 찍음. 20회면 몇 분 걸려서
          아무것도 안 나오면 멈춘 줄 앎
          오류도 결과의 하나로 Counter 에 남김. 그때 축은 안 쌓음. 응답이 없음
    제약  결과를 돌려주지 않는다.
          받은 dict 에 채움. 중간에 끊겨도(Ctrl-C · 서버 중단) 거기까지의
          결과가 부르는 쪽에 남아 있어야 표를 찍을 수 있음
    """
    for number, utterance, _expected, _default in entries:
        counter = Counter()
        axis_counter = Counter()
        outcomes[number] = counter
        axes[number] = axis_counter
        sys.stdout.write(f"  {number} ")
        sys.stdout.flush()
        for _ in range(runs):
            try:
                found, axis = _call_resolve(utterance, model)
                counter[found] += 1
                axis_counter[axis] += 1
                sys.stdout.write(".")
            except ServerDown:
                sys.stdout.write("\n")
                raise
            except Exception as exc:  # noqa: BLE001 — 오류도 결과의 하나로 표에 남긴다.
                counter[f"오류: {type(exc).__name__}"] += 1
                sys.stdout.write("!")
            sys.stdout.flush()
        sys.stdout.write("\n")
        sys.stdout.flush()


# ── 표 ──────────────────────────────────────────────────────────────


def _print_table(entries, outcomes: dict, runs: int) -> None:
    hit_column = 2 + 3 + UTTERANCE_WIDTH + 4  # 표의 "적중" 칸이 시작하는 자리.
    hit_width = len(f"{runs}/{runs}") + 4

    print()
    print(
        "  "
        + _pad("#", 3)
        + _pad("발화", UTTERANCE_WIDTH + 4)
        + _pad("적중", hit_width)
        + "틀렸을 때 나온 것"
    )

    total_hits = total_runs = 0
    imperfect = []

    for number, utterance, expected, _default in entries:
        counter = outcomes.get(number)
        done = sum(counter.values()) if counter else 0
        if done == 0:  # 끊겨서 아직 한 번도 안 돈 발화. 0/0 을 적으면 오해한다.
            continue
        hits = sum(
            count for result, count in counter.items()
            if isinstance(result, frozenset) and set(result) == expected
        )
        total_hits, total_runs = total_hits + hits, total_runs + done
        if hits < done:
            imperfect.append(number)

        misses = sorted(
            (
                (result, count) for result, count in counter.items()
                if not (isinstance(result, frozenset) and set(result) == expected)
            ),
            key=lambda item: (-item[1], _short(item[0]) if isinstance(item[0], frozenset) else item[0]),
        )

        head = (
            "  "
            + _pad(str(number), 3)
            + _pad(_clip(utterance, UTTERANCE_WIDTH), UTTERANCE_WIDTH + 4)
            + _pad(f"{hits}/{done}", hit_width)
        )
        if not misses:
            print(head.rstrip())
            continue

        for index, (result, count) in enumerate(misses):
            shown = _short(result) if isinstance(result, frozenset) else result
            prefix = head if index == 0 else " " * hit_column
            print(prefix + _pad(shown, 20) + f"{count}회")

    percent = round(100 * total_hits / total_runs) if total_runs else 0
    print(" " * hit_column + "─" * hit_width)
    print(" " * hit_column + _pad(f"{total_hits}/{total_runs}", hit_width) + f"{percent}%")

    if imperfect:
        print()
        print("  ⚠ 완전 적중이 아닌 발화 : " + " · ".join(str(n) for n in imperfect))


AXIS_WIDTH = 46  # 축 표에서 (given, want, about) 칸의 폭.


def _print_axes(entries, axes: dict) -> None:
    """발화마다 어떤 축이 나왔는지.

    입력  발화 목록 · {번호: 축 조합 Counter}
    규칙  많이 나온 것부터. 조합이 하나면 한 줄, 갈리면 여러 줄
          적중 표가 안 맞을 때 무엇이 틀렸는지 여기서 갈림.
          축이 흔들렸는지, 축은 같은데 LLM 이 recipe 를 다르게 골랐는지
    """
    print()
    print(
        "  "
        + _pad("#", 3)
        + _pad("발화", UTTERANCE_WIDTH + 4)
        + _pad("given · want · about", AXIS_WIDTH)
        + "횟수"
    )

    for number, utterance, _expected, _default in entries:
        counter = axes.get(number)
        if not counter:
            continue

        head = (
            "  "
            + _pad(str(number), 3)
            + _pad(_clip(utterance, UTTERANCE_WIDTH), UTTERANCE_WIDTH + 4)
        )
        rows = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        for index, (axis, count) in enumerate(rows):
            prefix = head if index == 0 else " " * _width(head)
            shown = _clip(" · ".join(axis), AXIS_WIDTH - 2)
            print(prefix + _pad(shown, AXIS_WIDTH) + f"{count}회")


def _recipe_state() -> str:
    """표 머리에 적을 지금 recipe 상태. _init 그대로인지, 노드가 등록됐는지."""
    current = sorted(p.stem for p in RECIPES_DIR.glob("recipe_*.yaml"))
    initial = sorted(p.stem for p in INIT_RECIPES_DIR.glob("recipe_*.yaml"))
    label = "_init" if current == initial else "등록됨"
    return f"{label} (recipe {len(current)})"


def main() -> int:
    parser = argparse.ArgumentParser(description="후보 발화가 지금 온톨로지에서 통하는지 잰다.")
    parser.add_argument("--runs", type=int, default=5, help="발화마다 몇 번 돌릴지 (기본 5)")
    parser.add_argument("--only", default="", help="돌릴 발화 번호. 예: 2,4")
    parser.add_argument("--model", default="", help="쓸 모델. 예: qwen2.5:7b (기본: 서버 기본 모델)")
    args = parser.parse_args()

    if args.only:
        wanted = [int(part) for part in args.only.replace(" ", "").split(",") if part]
        entries = [entry for entry in UTTERANCES if entry[0] in wanted]
        missing = sorted(set(wanted) - {entry[0] for entry in entries})
        if missing:
            print(f"목록에 없는 번호 : {missing}")
            return 2
    else:
        entries = [entry for entry in UTTERANCES if entry[3]]

    # 모델을 적는다. NOTES.md 의 측정 기록은 조건 없는 숫자를 받지 않는다.
    print(
        f"발화 {len(entries)}개 × {args.runs}회 · {_recipe_state()}"
        f" · 모델 {args.model or '서버 기본'}"
    )
    print()

    outcomes, axes, note, status = {}, {}, "", 0
    try:
        _measure(entries, args.runs, outcomes, axes, args.model)
    except ServerDown:
        # 재시도하지 않는다. 여기까지 잰 것이 있으면 표는 찍는다.
        note, status = "uvicorn 을 먼저 실행하세요", 1
    except KeyboardInterrupt:
        # 오래 걸리는 도구라 중간에 끊는 일이 생긴다. 거기까지의 표를 찍는다.
        note = "(중단됨 — 여기까지의 결과)"

    if any(outcomes.values()):
        _print_table(entries, outcomes, args.runs)
    if any(axes.values()):
        _print_axes(entries, axes)
    if note:
        print()
        print(note)

    return status


if __name__ == "__main__":
    sys.exit(main())
