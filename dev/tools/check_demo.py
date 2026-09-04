"""시연에서 쓸 발화 아홉이 지금 SELECT 로 붙는지 재는 도구.

**정답표(check_resolve.UTTERANCES)와 다른 자다.** 정답표는 recipe 39벌과 1대1 이라
「이 recipe 를 어떤 말로도 못 부른다」를 드러내는 데 쓴다. 시연 발화는 사람이
실제로 할 말이라 한 recipe 를 여러 말로 부른다 — 014 와 019 가 두 번씩 나온다.
두 성질을 한 자에 담으면 정답표의 1대1 이 깨지므로 파일을 갈랐다
(NOTES.md 「열린 과제」 · 「백한째」).

    .venv/bin/python dev/tools/check_demo.py                  아홉을 차례대로
    .venv/bin/python dev/tools/check_demo.py --reverse         거꾸로
    .venv/bin/python dev/tools/check_demo.py --only 4          하나만
    .venv/bin/python dev/tools/check_demo.py --runs 3          발화마다 세 번

**판정은 check_resolve 의 _grade 를 그대로 부른다.** 규칙을 베끼면 두 자가 조용히
어긋난다. 지도 문맥도 그쪽 _context_payload 를 쓴다 — 기본은 both 이고, 정답표를
재는 조건과 같아야 두 표를 나란히 읽을 수 있다.

**시연에서 보는 것은 적중이 아니라 SELECT 다.** 후보가 하나로 좁혀져야 화면이
되묻지 않고 바로 실행한다. 그래서 표에 status 칸이 적중 칸보다 앞에 있다.
"""

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dev.tools.check_resolve import (  # noqa: E402
    HIT,
    ServerDown,
    _call_resolve,
    _clip,
    _grade,
    _pad,
    _short,
    _width,
)

# ── 시연 정답표 아홉 ─────────────────────────────────────────────────
#
# 사람이 정했다. 이 도구에서 고치지 않는다.
#
# 014 와 019 가 두 번씩 나온다. 시연 자는 recipe 를 덮는 자가 아니라 「그날 할
# 말이 통하는가」를 재는 자라 같은 recipe 를 여러 말로 부르는 것이 정상이다.
#
# 4번이 052 인 근거는 실측이다 — ev.searchStations(query="철도기술연구원") 이
# 「한국철도기술연구원」 2건을 낸다 (2026-09-04,
# dev/tools/probe_out/ev.searchStations.railway.json). 충전소 이름 자체라
# 키워드로 찾는 것이 맞다.
DEMO = [
    (1, "오송역 좌표 보여줘", {"recipe_001"}),
    (2, "오송역 CCTV 보여줘", {"recipe_036"}),
    (3, "의왕시 인구 알려줘", {"recipe_012"}),
    (4, "철도기술연구원 근처 충전소 자세히 알려줘", {"recipe_052"}),
    (5, "문서에서 철도안전법 관련 내용 알려줘", {"recipe_014"}),
    (6, "현재 화면 CCTV 보여줘", {"recipe_026"}),
    (7, "여기 CCTV 보여줘", {"recipe_019"}),
    (8, "저장된 문서에서 철도안전법 관련 내용 찾아서 보여줘", {"recipe_014"}),
    (9, "선택한 위치 CCTV 보여줘", {"recipe_019"}),
]

# 화면이 되묻지 않고 바로 실행하는 status.
SELECT = "SELECT"

UTTERANCE_WIDTH = 40
FOUND_WIDTH = 22
STATUS_WIDTH = 8


def _row(number: int, utterance: str, found, status: str, grade: str) -> str:
    """발화 한 줄. 나온 후보와 status 와 판정."""
    return "  ".join(
        [
            f"{number:>2}",
            _pad(_clip(utterance, UTTERANCE_WIDTH), UTTERANCE_WIDTH),
            _pad(_short(found) if not isinstance(found, str) else found, FOUND_WIDTH),
            _pad(status, STATUS_WIDTH),
            grade,
        ]
    )


def _header() -> str:
    return "  ".join(
        [
            "번호",
            _pad("발화", UTTERANCE_WIDTH),
            _pad("나온 후보", FOUND_WIDTH),
            _pad("status", STATUS_WIDTH),
            "판정",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="시연 발화 아홉이 지금 SELECT 로 붙는지 잰다.")
    parser.add_argument("--runs", type=int, default=1, help="발화마다 몇 번 (기본 1)")
    parser.add_argument("--reverse", action="store_true", help="거꾸로 부른다")
    parser.add_argument("--only", default="", help="번호만 골라서. 예: 4 또는 1,4,7")
    parser.add_argument("--model", default="", help="쓸 모델. 없으면 서버 기본 모델")
    args = parser.parse_args()

    entries = list(DEMO)
    if args.only:
        wanted = {int(part) for part in args.only.split(",") if part.strip()}
        entries = [entry for entry in entries if entry[0] in wanted]
    if args.reverse:
        entries = list(reversed(entries))

    print(_header())
    print("-" * (_width(_header())))

    grades = Counter()
    selects = 0
    runs = 0
    started = time.perf_counter()
    for number, utterance, expected in entries:
        for _ in range(args.runs):
            try:
                found, status, _axes, _tally, _alone, _times = _call_resolve(
                    utterance, args.model or None
                )
            except ServerDown as exc:
                print(f"서버에 못 닿았다: {exc}")
                return 1
            grade = _grade(found, status, expected)
            grades[grade] += 1
            runs += 1
            if status == SELECT:
                selects += 1
            print(_row(number, utterance, found, status, grade))

    print("-" * (_width(_header())))
    others = [f"{name} {count}" for name, count in grades.items() if name != HIT]
    line = f"SELECT {selects}/{runs} · 적중 {grades[HIT]}/{runs}"
    if others:
        line += " · " + " · ".join(others)
    print(line + f" · {time.perf_counter() - started:.1f}초")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
