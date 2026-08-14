"""시연 발화가 지금 온톨로지에서 통하는지 재는 도구.

같은 발화가 두 번 다르게 나온 적이 있어 한 번 눌러본 것은 근거가 안 된다.
발화마다 여러 번 돌려 무엇이 나왔는지 표로 찍는다. 표를 보고 사람이 발화를
고치고, 다시 돌리고, 확정한다.

    python tools/check_resolve.py                   1~3번 × 5회 (4번은 --only)
    python tools/check_resolve.py --runs 10         굳히기
    python tools/check_resolve.py --only 2,4        고친 발화만 다시

화면이 지나는 것과 같은 경로여야 표를 믿을 수 있으므로 POST /resolve 를 부른다.
서버(uvicorn)가 떠 있어야 한다.

발화는 확정됐지만 **이 파일은 지우지 않는다.** 온톨로지나 menu 가 바뀌면 다시
재야 하고, 그때 되살리는 것보다 두는 편이 싸다. 그래서 파일 하나에 담고
저장소의 다른 곳을 건드리지 않는다.

──────────────────────────────────────────────────────────────────────
알아낸 것 (작업 27~30 · qwen2.5:7b · _init recipe 6)

  형식은 발화와 menu 의 표기가 글자 그대로 겹칠 때만 갈린다.
    "워드"          0/10   menu 는 "Word"
    "Word 문서로"   9/10
    "Word로"        9/10   오답이 {004,005} 로 바뀐다 — 형식이 아니라 길이가 갈린다
    menu 에 "Word(워드)" 로 두 표기를 함께 담는 것은 안 들었다 (0/10)

  숫자 + "번" 이 붙으면 무너진다.
    "3번 승강장에 …"      0/5
    "동대구역 승강장에 …"  5/5
    "지금 승강장에 …"      4/5
    "승강장에 …"          5/5
    역명도 시각도 통한다. "3번" 만 다르다 — recipe 번호로 읽히는 것으로 보인다

  끝점은 동사가 정한다.
    "…봐줘"       9/10   10에 1번 문서까지 끌고 간다
    "…분석해줘"   10/10

  NO_MATCH 는 영역으로 갈린다. 어휘 겹침이 아니다.
    "오늘 지하철 요금 알려줘"          5/5   영역 밖
    "CCTV 화면이 뿌옇지 않은지 봐줘"    0/5   영역 안이라 뭐라도 집는다
    "화면이 뿌옇게 나오는데 확인해줘"   0/5   겹치는 어휘가 없는데도 마찬가지

시연 뒤 과제 : 형식 동의어("워드" · "피피티" · "파워포인트")를 프롬프트
지시문에 명시하는 안. menu 문장(데이터)에 담는 것은 실패했다.

──────────────────────────────────────────────────────────────────────
recipe 6 → 8 (작업 32 · qwen2.5:7b · _init recipe 8 · 1~3 은 10회, 4 는 5회)

  #  기대            나온 것                적중     recipe 6 때
  1  {003}           {001,003,005,006} 10회  0/10     10/10
  2  {004}           {002,004}         10회  0/10     10/10
  3  {005,006}       {003,005}         10회  0/10     10/10
  4  {}              -                       5/5      5/5

  **셋 다 10회가 전부 같은 답이다.** 흔들린 것이 아니라 후보 판정이 통째로
  옮겨갔다. 원인으로 보이는 것 : 새로 생긴 001·002(데이터 → 프레임 추출)가
  003·004·005·006 의 **앞토막**이라 "어디서 끝나는가" 가 후보를 못 가른다.
  1번은 승강장 갈래 넷을 통째로 집었고, 2번은 예상대로 002 를 함께 물었다.
  3번은 문서를 달랬는데 분석까지인 003 이 끼고 PPT(006)가 빠졌다.

  발화를 고치는 것은 다음 작업이다. 여기서는 recipe 를 온톨로지에 맞추는 것이
  목적이었고, 표는 recipe 8개 상태의 첫 측정이라 앞으로의 비교 대상이 된다.
"""

import argparse
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import requests

# (번호, 발화, 기대 recipe 집합, 기본 실행 여부)
#
# recipe id 로 적어도 되는 이유 : _init 의 001~008 은 고정이다. 노드를 등록해도
# 새 recipe 는 009 부터 붙으므로 이 여덟의 뜻은 안 변한다.
#
#   001  승강장 CCTV → 프레임 추출
#   002  궤도 검측차 CCTV → 프레임 추출
#   003  승강장 CCTV → 프레임 추출 → 혼잡도 분석
#   004  궤도 검측차 CCTV → 프레임 추출 → 균열 검출
#   005  ... 혼잡도 분석 → Word 생성
#   006  ... 혼잡도 분석 → PPT 생성
#   007  ... 균열 검출 → Word 생성
#   008  ... 균열 검출 → PPT 생성
#
# **번호가 6개 시절에서 밀렸다.** _init 을 손으로 고른 것에서 온톨로지가 만들
# 수 있는 경로 전부로 다시 만들면서 001·002(데이터 → 프레임 추출)가 생겼다.
# 아래 기대값은 같은 경로를 가리키도록 갈아끼운 것이다.
#
# 넷 다 확정본이다. demo/ui/components/sample_picker.py 의 SAMPLES 와 같다.
# probe(원래 발화에서 한 가지만 바꾼 것)는 다 지웠다 — 거기서 알아낸 것은
# 파일 맨 위 docstring 에 남겼다.
UTTERANCES = [
    (1, "승강장에 사람이 얼마나 몰렸는지 분석해줘",       {"recipe_003"},               True),
    (2, "검측차 영상에서 레일 갈라진 데 있는지 확인해줘",  {"recipe_004"},               True),
    (3, "승강장 혼잡도 결과를 문서로 정리해줘",           {"recipe_005", "recipe_006"}, True),
    (4, "오늘 지하철 요금 알려줘",                       set(),                        False),
]

BASE_URL = "http://localhost:8000"
TIMEOUT = 180  # demo/ui/api_client.RESOLVE_TIMEOUT 과 같다. LLM 이 끼는 호출이다.

REPO_ROOT = Path(__file__).resolve().parent.parent
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
    """폭 width 안에 들어가게 자른다. 잘렸으면 끝에 … 를 붙인다."""
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


def _call_resolve(utterance: str) -> frozenset:
    """POST /resolve 한 번. recipe_id 와 candidate_recipe_ids 를 합친 후보 집합."""
    try:
        response = requests.post(
            f"{BASE_URL}/resolve", params={"utterance": utterance}, timeout=TIMEOUT
        )
    except requests.exceptions.ConnectionError as exc:
        raise ServerDown(str(exc)) from exc

    response.raise_for_status()
    result = response.json()
    found = [result.get("recipe_id"), *(result.get("candidate_recipe_ids") or [])]
    return frozenset(rid for rid in found if rid)


# ── 측정 ────────────────────────────────────────────────────────────


def _measure(entries, runs: int, outcomes: dict) -> None:
    """발화마다 runs 회 돌려 outcomes[번호] 에 나온 집합들의 Counter 를 쌓는다.

    돌려주지 않고 받은 dict 에 채우는 이유 : 중간에 끊겨도(Ctrl-C · 서버 중단)
    거기까지의 결과가 부르는 쪽에 남아 있어야 표를 찍을 수 있다.

    실행 하나가 끝날 때마다 점 하나를 찍는다 — 20회면 몇 분 걸려서
    아무것도 안 나오면 멈춘 줄 안다.
    """
    for number, utterance, _expected, _default in entries:
        counter = Counter()
        outcomes[number] = counter
        sys.stdout.write(f"  {number} ")
        sys.stdout.flush()
        for _ in range(runs):
            try:
                counter[_call_resolve(utterance)] += 1
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

    print(f"발화 {len(entries)}개 × {args.runs}회 · {_recipe_state()}")
    print()

    outcomes, note, status = {}, "", 0
    try:
        _measure(entries, args.runs, outcomes)
    except ServerDown:
        # 재시도하지 않는다. 여기까지 잰 것이 있으면 표는 찍는다.
        note, status = "uvicorn 을 먼저 실행하세요", 1
    except KeyboardInterrupt:
        # 오래 걸리는 도구라 중간에 끊는 일이 생긴다. 거기까지의 표를 찍는다.
        note = "(중단됨 — 여기까지의 결과)"

    if any(outcomes.values()):
        _print_table(entries, outcomes, args.runs)
    if note:
        print()
        print(note)

    return status


if __name__ == "__main__":
    sys.exit(main())
