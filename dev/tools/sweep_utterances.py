"""발화 후보를 대량으로 던져 **나온 것만** 기록하는 도구.

정답을 정하지 않는다. 적중·근접 같은 판정을 매기지 않는다. `check_resolve` 의
정답표(UTTERANCES)를 읽지 않는다. 이 파일은 관측 기록기다 — 무엇이 맞는지는
표를 보고 사람이 정한다.

    python dev/tools/sweep_utterances.py                     서버 기본 모델 · 10회
    python dev/tools/sweep_utterances.py --model qwen3:8b    모델만 바꿔 (서버 안 내림)
    python dev/tools/sweep_utterances.py --runs 3            빨리 훑어보기
    python dev/tools/sweep_utterances.py --only 3,7          발화 번호만 골라

`check_resolve._call_resolve` 를 그대로 쓴다. 화면이 지나는 것과 같은 경로여야
표를 믿을 수 있고, 두 도구의 표를 나란히 놓을 수 있다.

하나가 실패해도 전체가 멈추면 안 된다. 발화 하나에서 오류가 나면 그 회차를
「오류」로 적고 다음으로 간다. 서버에 못 닿으면 잠깐 쉬었다 다시 부르고, 그래도
안 되면 그 회차만 버린다.

산출물은 `dev/tools/sweep_out/` 에 둔다 (`.gitignore` 에 있다).

    sweep-<모델>-<날짜>.txt    사람이 읽을 표
    sweep-<모델>-<날짜>.json   내일 다시 셀 수 있는 같은 내용
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# _call_resolve 만 가져온다. 정답표(UTTERANCES)는 쓰지 않는다.
from tools.check_resolve import BASE_URL, ServerDown, _call_resolve  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "sweep_out"


# ── 발화 후보 예순 ──────────────────────────────────────────────────
# (번호, 자리, 발화). 「자리」는 무엇을 겨냥했는지 적어 둔 것이지 정답이 아니다.
#
# 겨냥한 자리는 여섯이다. 각 자리마다 말투를 서넛씩 바꿨다.
#   가  경계 도형이 안 갈리는 자리
#   나  선거 — 지점으로 찾는 자리
#   다  선거 — 이름으로 검색하는 자리
#   라  인구 — 셋이 안 갈리는 자리
#   마  철도
#   바  이미 되는 것의 말투 변주 (흔들리는지 본다)
#
# 「죽음」인 자리(지방선거 공약 셋 · 웹 둘)는 겨냥하지 않았다. 다만 위 발화가
# 그리로 흘러가면 그것도 관측이므로 표에 그대로 적힌다.
UTTERANCES = [
    (1,  "가 경계", "오송역 행정구역 알려줘"),
    (2,  "가 경계", "오송역이 어느 동인지 알려줘"),
    (3,  "가 경계", "오송역이 어느 행정동에 속하는지 알려줘"),
    (4,  "가 경계", "오송역 행정경계 보여줘"),
    (5,  "가 경계", "오송역 경계 도형 내려받아줘"),
    (6,  "가 경계", "오송역 행정구역 경계 지도에 그려줘"),
    (7,  "가 경계", "청주시 행정경계 보여줘"),
    (8,  "가 경계", "청주시 경계 도형 줘"),
    (9,  "가 경계", "경부선이 지나는 행정구역 알려줘"),
    (10, "가 경계", "경부선 통과 행정구역 목록 뽑아줘"),

    (11, "나 선거·지점", "오송역 국회의원 선거구 알려줘"),
    (12, "나 선거·지점", "오송역이 어느 선거구인지 알려줘"),
    (13, "나 선거·지점", "오송역은 무슨 선거구에 들어가?"),
    (14, "나 선거·지점", "오송역 국회의원 누구야"),
    (15, "나 선거·지점", "오송역 지역구 국회의원 알려줘"),
    (16, "나 선거·지점", "오송역 선거구 당선인 알려줘"),
    (17, "나 선거·지점", "오송역 선거구 공약 알려줘"),
    (18, "나 선거·지점", "오송역 국회의원 공약 보여줘"),
    (19, "나 선거·지점", "오송역 국회의원 교통 공약 알려줘"),
    (20, "나 선거·지점", "오송역 선거구 철도 공약 알려줘"),

    (21, "다 선거·검색", "청주 국회의원 선거구 검색해줘"),
    (22, "다 선거·검색", "청주 선거구 찾아줘"),
    (23, "다 선거·검색", "청주 선거구 당선인 검색해줘"),
    (24, "다 선거·검색", "청주 지역 당선인 알려줘"),
    (25, "다 선거·검색", "청주 국회의원 공약 검색해줘"),
    (26, "다 선거·검색", "청주 선거구 공약 검색해줘"),
    (27, "다 선거·검색", "철도 공약 있는 선거구 찾아줘"),
    (28, "다 선거·검색", "교통 공약 많은 선거구 검색해줘"),
    (29, "다 선거·검색", "더불어민주당 당선인 선거구 검색해줘"),
    (30, "다 선거·검색", "충북 선거구 목록 보여줘"),

    (31, "라 인구", "오송역 인구 알려줘"),
    (32, "라 인구", "오송역 일대 인구 얼마야"),
    (33, "라 인구", "청주시 인구 알려줘"),
    (34, "라 인구", "청주시 인구 몇 명이야"),
    (35, "라 인구", "청주시 인구 순위 알려줘"),
    (36, "라 인구", "인구 많은 시군구 순위 보여줘"),
    (37, "라 인구", "오송역 연령대별 인구 알려줘"),
    (38, "라 인구", "오송역 주변 연령별 인구 구성 보여줘"),
    (39, "라 인구", "오송역 인구 변화 알려줘"),
    (40, "라 인구", "오송역 인구 추이 보여줘"),
    (41, "라 인구", "청주시 인구 통계 검색해줘"),

    (42, "마 철도", "경부선 노선 보여줘"),
    (43, "마 철도", "경부선 노선도 알려줘"),
    (44, "마 철도", "경부선 구간 형상 보여줘"),
    (45, "마 철도", "경부선 선형 데이터 줘"),
    (46, "마 철도", "오송역 지나는 노선 알려줘"),
    (47, "마 철도", "오송역 정차 노선 뭐 있어"),
    (48, "마 철도", "경부선 주변 CCTV 보여줘"),
    (49, "마 철도", "경부선 구간 CCTV 알려줘"),

    (50, "바 변주", "철도 안전 문서 찾아줘"),
    (51, "바 변주", "철도 안전 문서 줘"),
    (52, "바 변주", "철도안전법 내용 찾아줘"),
    (53, "바 변주", "철도 안전 관련 자료 검색해줘"),
    (54, "바 변주", "전기차 충전소 검색해줘"),
    (55, "바 변주", "전기차 충전소 데이터 줘"),
    (56, "바 변주", "충전소 어디 있어"),
    (57, "바 변주", "오송역 CCTV 보여줘"),
    (58, "바 변주", "오송역 주변 CCTV 알려줘"),
    (59, "바 변주", "오송역 근처 충전소 자세히 알려줘"),
    (60, "바 변주", "오송역 근처 충전소 찾아줘"),
]


# ── 한글 폭 ─────────────────────────────────────────────────────────
# check_resolve 와 같은 이유로 직접 센다. 한글은 폭이 2 라 ljust 로는 어긋난다.


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _clip(text: str, width: int) -> str:
    if _width(text) <= width:
        return text
    out = ""
    for ch in text:
        if _width(out + ch) > width - 1:
            return out + "…"
        out += ch
    return out


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def _cell(text: str, width: int) -> str:
    return _pad(_clip(text, width), width)


def _short(recipe_ids) -> str:
    """{"recipe_004", "recipe_005"} → "{004, 005}". 빈 것은 "{}"."""
    if recipe_ids is None:
        return "-"
    trimmed = sorted(
        rid[len("recipe_"):] if rid.startswith("recipe_") else rid
        for rid in recipe_ids
    )
    return "{" + ", ".join(trimmed) + "}"


# ── 한 발화 재기 ────────────────────────────────────────────────────


def _one_run(utterance: str, model: str | None) -> dict:
    """/resolve 한 번. 무엇이 나왔는지 그대로 담는다.

    오류가 나도 예외를 밖으로 내보내지 않는다 — 사람이 자는 동안 도는 도구라
    발화 하나가 전체를 멈추면 안 된다. 서버에 못 닿으면 한 번 쉬었다 다시 부른다.
    """
    for attempt in range(2):
        try:
            started = time.monotonic()
            final, status, argument, tally, alone = _call_resolve(utterance, model)
            llm_count, _status = tally
            return {
                "ok": True,
                "status": status,
                "llm_candidates": sorted(alone) if alone else [],
                "final": sorted(final),
                "argument": argument,
                "llm_count": llm_count,
                "seconds": round(time.monotonic() - started, 2),
            }
        except ServerDown as exc:
            if attempt == 0:
                time.sleep(10)
                continue
            return {"ok": False, "status": "오류", "error": f"ServerDown: {exc}"}
        except Exception as exc:  # 표를 오류로 채울지언정 멈추지 않는다
            return {"ok": False, "status": "오류", "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": False, "status": "오류", "error": "알 수 없음"}


def _summarise(runs: list) -> dict:
    """회차들을 한 발화의 요약으로 접는다. **판정을 매기지 않는다.**"""
    good = [r for r in runs if r.get("ok")]
    errors = [r for r in runs if not r.get("ok")]

    def key(run: dict) -> tuple:
        return (
            run["status"],
            _short(run["final"]),
            _short(run["llm_candidates"]),
            run["argument"],
        )

    shapes = Counter(key(r) for r in good)
    statuses = Counter(r["status"] for r in runs)

    top = shapes.most_common(1)[0] if shapes else None
    return {
        "runs": len(runs),
        "ok": len(good),
        "errors": len(errors),
        "status_counts": dict(statuses),
        "status_stable": len(statuses) == 1,
        "shape_count": len(shapes),
        "shapes": [{"shape": list(k), "count": v} for k, v in shapes.most_common()],
        "top": {"shape": list(top[0]), "count": top[1]} if top else None,
        "error_messages": sorted({r.get("error", "") for r in errors}),
    }


# ── 표 ──────────────────────────────────────────────────────────────

NO_W, PLACE_W, UTT_W = 4, 12, 28
STATUS_W, SET_W, ARG_W = 10, 26, 14


def _header() -> list:
    row = (
        _cell("번호", NO_W) + "  " + _cell("자리", PLACE_W) + "  " + _cell("발화", UTT_W) + "  "
        + _cell("회", 5) + "  " + _cell("status", STATUS_W) + "  "
        + _cell("LLM 후보", SET_W) + "  " + _cell("최종 후보", SET_W) + "  "
        + _cell("인자", ARG_W)
    )
    return [row, "─" * _width(row)]


def _shape_row(no, place, utt, count, total, shape) -> str:
    status, final, llm, argument = shape
    return (
        _cell(str(no), NO_W) + "  " + _cell(place, PLACE_W) + "  " + _cell(utt, UTT_W) + "  "
        + _cell(f"{count}/{total}", 5) + "  " + _cell(status, STATUS_W) + "  "
        + _cell(llm, SET_W) + "  " + _cell(final, SET_W) + "  "
        + _cell(argument, ARG_W)
    )


def _render(model_label: str, runs: int, records: list, started_at: str, elapsed) -> str:
    lines = [
        "발화 쓸기 — 나온 것만 적는다",
        "",
        f"모델      {model_label}",
        f"서버      {BASE_URL}",
        f"회차      발화마다 {runs}회",
        f"발화      {len(records)}개",
        f"시작      {started_at}",
        f"걸린 시간 {elapsed}",
        "",
        "**판정을 매기지 않았다.** 무엇이 맞는지는 사람이 정한다. 정답표는 읽지 않았다.",
        "발화마다 가장 많이 나온 모양을 맨 위에 적고, 갈린 경우 갈린 것을 전부 적는다.",
        "",
    ]

    lines += ["", "── 표 1. 발화마다 나온 모양 ──", ""] + _header()
    for rec in records:
        summary = rec["summary"]
        no, place, utt = rec["no"], rec["place"], rec["utterance"]
        if not summary["shapes"]:
            lines.append(_shape_row(no, place, utt, summary["errors"], summary["runs"],
                                    ("오류", "-", "-", "-", "-", "-", "-", "-")))
        for i, shape in enumerate(summary["shapes"]):
            lines.append(_shape_row(
                no if i == 0 else "", place if i == 0 else "", utt if i == 0 else "",
                shape["count"], summary["runs"], tuple(shape["shape"]),
            ))
        if summary["errors"] and summary["shapes"]:
            lines.append(_shape_row("", "", "", summary["errors"], summary["runs"],
                                    ("오류", "-", "-", "-", "-", "-", "-", "-")))
        lines.append("")

    lines += ["", "── 표 2. 흔들리는가 ──", ""]
    row = (_cell("번호", NO_W) + "  " + _cell("발화", UTT_W + 6) + "  "
           + _cell("status 10회", 14) + "  " + _cell("모양 수", 8) + "  " + "나온 것")
    lines += [row, "─" * 110]
    for rec in records:
        s = rec["summary"]
        counts = ", ".join(f"{k} {v}" for k, v in sorted(s["status_counts"].items(), key=lambda x: -x[1]))
        stable = "한결같다" if s["status_stable"] else "★ 갈린다"
        note = ""
        top = s["top"]
        if top:
            status, final = top["shape"][0], top["shape"][1]
            if status == "SELECT":
                note = f"SELECT {final}"
            elif status == "CLARIFY":
                n = len([x for x in final.strip("{}").split(",") if x.strip()])
                note = f"CLARIFY {n}개 {final}"
            else:
                note = f"{status} {final}"
        lines.append(
            _cell(str(rec["no"]), NO_W) + "  " + _cell(rec["utterance"], UTT_W + 6) + "  "
            + _cell(stable, 14) + "  " + _cell(str(s["shape_count"]), 8) + "  "
            + f"{counts}   |   {note}"
        )

    lines += ["", "", "── 표 3. 갈래별 목록 ──", ""]
    single, clarify, wobbly, axis_only, failed = [], [], [], [], []
    for rec in records:
        s = rec["summary"]
        top = s["top"]
        line = f"  {rec['no']:>3}  {rec['utterance']}"
        if s["errors"] == s["runs"]:
            failed.append(line + f"   ({'; '.join(s['error_messages'])[:80]})")
            continue

        # 「갈린다」를 둘로 가른다. status·최종 후보가 갈리는 것과, 그 둘은 같은데
        # LLM 후보나 인자만 갈리는 것은 사람이 볼 때 전혀 다른 일이다.
        verdicts = {(sh["shape"][0], sh["shape"][1]) for sh in s["shapes"]}
        if len(verdicts) > 1:
            shapes = " / ".join(f"{sh['shape'][0]} {sh['shape'][1]} ×{sh['count']}"
                                for sh in s["shapes"])
            wobbly.append(line + f"   {shapes}")
        elif s["shape_count"] > 1:
            names = ("status", "최종", "LLM 후보", "인자")
            differing = [
                names[i] for i in range(len(names))
                if len({sh["shape"][i] for sh in s["shapes"]}) > 1
            ]
            variants = " / ".join(
                "·".join(sh["shape"][i] for i in range(len(names)) if names[i] in differing)
                + f" ×{sh['count']}" for sh in s["shapes"]
            )
            axis_only.append(line + f"   [{', '.join(differing)}] {variants}")

        if top and s["status_counts"].get("SELECT", 0) == s["runs"]:
            single.append(line + f"   → {top['shape'][1]}")
        elif top and top["shape"][0] == "CLARIFY":
            n = len([x for x in top["shape"][1].strip("{}").split(",") if x.strip()])
            clarify.append(line + f"   → {n}개로 되묻는다 {top['shape'][1]}"
                                  f" ({top['count']}/{s['runs']})")
    lines += [f"★ 하나로 가는 발화 (SELECT {runs}/{runs})   {len(single)}개"] + (single or ["  (없음)"])
    lines += ["", f"★ 되묻는 발화 (CLARIFY 가 가장 많이 나옴)   {len(clarify)}개"] + (clarify or ["  (없음)"])
    lines += ["", f"★ 회차마다 갈리는 발화 — status 나 최종 후보가 갈린다   {len(wobbly)}개"] + (wobbly or ["  (없음)"])
    lines += ["", f"판정은 같은데 LLM 후보·인자만 갈리는 발화   {len(axis_only)}개"] + (axis_only or ["  (없음)"])
    lines += ["", f"오류만 난 발화   {len(failed)}개"] + (failed or ["  (없음)"])
    lines.append("")
    return "\n".join(lines)


# ── 실행 ────────────────────────────────────────────────────────────


def _sweep(model: str | None, runs: int, only: set, stamp: str) -> int:
    model_label = model or "서버 기본"
    slug = (model or "server-default").replace(":", "-").replace("/", "-")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    txt_path = OUT_DIR / f"sweep-{slug}-{stamp}.txt"
    json_path = OUT_DIR / f"sweep-{slug}-{stamp}.json"

    targets = [u for u in UTTERANCES if not only or u[0] in only]
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    began = time.monotonic()
    records = []

    print(f"\n=== {model_label} · 발화 {len(targets)} × {runs}회 ===", flush=True)
    for no, place, utt in targets:
        rows = [_one_run(utt, model) for _ in range(runs)]
        rec = {
            "no": no, "place": place, "utterance": utt,
            "runs": rows, "summary": _summarise(rows),
        }
        records.append(rec)
        s = rec["summary"]
        top = s["top"]
        mark = "" if s["status_stable"] else "  ★갈림"
        head = f"{top['shape'][0]} {top['shape'][1]} {top['count']}/{runs}" if top else "오류"
        print(f"  {no:>3} {utt:<30} {head}{mark}", flush=True)

        # 중간에 끊겨도 여기까지가 남는다.
        elapsed = f"{(time.monotonic() - began) / 60:.1f}분"
        json_path.write_text(json.dumps({
            "model": model_label, "runs": runs, "started_at": started_at,
            "elapsed": elapsed, "base_url": BASE_URL, "records": records,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        txt_path.write_text(_render(model_label, runs, records, started_at, elapsed),
                            encoding="utf-8")

    print(f"  → {txt_path}\n  → {json_path}", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="발화 후보를 쓸어 나온 것만 기록한다.")
    parser.add_argument("--runs", type=int, default=10, help="발화마다 몇 번 (기본 10)")
    parser.add_argument("--model", default="", help="쓸 모델. 비우면 서버 기본 모델")
    parser.add_argument("--only", default="", help="돌릴 발화 번호. 예: 3,7")
    parser.add_argument("--stamp", default="", help="파일 이름에 쓸 날짜. 비우면 오늘")
    parser.add_argument("--render", default="", help="이미 받아 둔 json 으로 표만 다시 그린다")
    args = parser.parse_args()

    if args.render:
        data = json.loads(Path(args.render).read_text(encoding="utf-8"))
        txt = Path(args.render).with_suffix(".txt")
        txt.write_text(_render(data["model"], data["runs"], data["records"],
                               data["started_at"], data["elapsed"]), encoding="utf-8")
        print(f"  → {txt}")
        return 0

    only = {int(x) for x in args.only.split(",") if x.strip()}
    stamp = args.stamp or datetime.now().strftime("%Y-%m-%d")
    return _sweep(args.model or None, args.runs, only, stamp)


if __name__ == "__main__":
    raise SystemExit(main())
