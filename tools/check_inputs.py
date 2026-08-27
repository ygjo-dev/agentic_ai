"""배선 줄이 도구의 어느 칸을 쓰는지 inputSchema 와 맞대는 계기판.

tools/check_wiring.py 는 **배선 줄이 있는가**만 센다. 그 줄이 **맞는 칸을 쓰는가**는
아무도 안 봤다. 그래서 이런 일이 있었다 (NOTES.md 「열린 과제」 2026-08-26).

    geo.getRailwayLines 는 stationName 과 railwayName 을 갖는다
    우리 배선은 stationName 하나만 보낸다
      -> "경부선 노선 보여줘" 가 0건
      -> check_wiring 은 통과였다. 줄은 있으니까
      -> 사람이 화면에서 0건을 보고서야 알았다

도구가 늘면 이런 자리가 비례해서 는다. 이 도구가 그것을 센다.

    python tools/check_inputs.py                     probe_out/tools.json 이 있으면 서버 없이
    python tools/check_inputs.py --tools /tmp/tools.json
    python tools/check_inputs.py --refresh           Gateway 에서 다시 받아 파일을 갱신

**표를 복사하지 않는다.** STEP_OF · TOOL_OF 를 demo/api/services/step_service 에서
그대로 import 한다. 읽기만 한다 — 이 파일은 배선도 온톨로지도 안 고친다.

## 스키마는 파일로 갖는다

/api/tools 가 21초 걸린 전례가 있어(NOTES.md 「셋째」) 한 번 받으면
tools/probe_out/tools.json 에 남기고 다음부터는 그것을 읽는다. 그 파일이 있으면
Gateway 없이 돈다. 없을 때만 Gateway 를 부르고 상한은 --timeout (기본 120초)다.
둘 다 안 되면 무엇이 없는지 말하고 멈춘다 — 조용히 빈 표를 내지 않는다.

r5-server 처럼 꺼진 서버의 도구는 /api/tools 에 아예 안 실린다. 배선이 가리키는
도구가 스키마 목록에 없으면 그 줄은 「스키마를 못 받았다」로 적고 넘어간다.

## 세는 법 넷 — 배선 줄마다 · 칸마다

    없는 칸을 보낸다        우리가 보내는 칸이 properties 에 없다.  ★ 반드시 0건이나 오류
    꼭 필요한데 안 보낸다   required 인데 우리 배선에 없다.          ★ 반드시 오류
    있는데 안 쓰는 칸       properties 에 있는데 우리가 안 보낸다.   판단할 자리. 고르지 않는다
    맞다                    나머지

한 줄의 판정은 그 줄의 칸 판정을 모은 것이다. 없는 칸 · 안 보낸 required 가
하나도 없으면 「맞다」이고, 안 쓰는 칸은 몇 개인지만 옆에 적는다.

**어댑터 뒤의 칸으로 맞댄다.** vendor 의 point_radius_to_bbox 는 center / location
과 radiusMeters 를 지우고 minLon · minLat · maxLon · maxLat 를 만든다
(generic_mcp_executor._point_radius_to_bbox_input). 줄에 adapter 가 적혀 있거나,
안 적혀 있어도 도구의 required 에 bbox 넷이 다 있고 input 에 중심 좌표와
반경이 있으면 vendor 가 저절로 건다 (_should_auto_apply_point_radius_to_bbox).
그 둘을 그대로 따라 한다. 어댑터가 걸린 줄은 표에 「어댑터」로 표시된다.

`input_first` 도 따로 센다. 한 줄이 두 자리(첫 단계일 때 · 앞 단계가 있을 때)를
맡으므로 갈래마다 한 행이다. 지금 input_first 를 적은 줄은 없어 행이 안 는다.

## 안 쓰는 칸이 제일 많다 — 추리는 기준 셋

properties 는 도구마다 열 개가 넘고 대부분 limit · includeGeometry 같은 안 보내도
되는 손잡이다. 그냥 늘어놓으면 못 읽으므로 아래 셋 중 하나에 걸리는 칸만 ★ 로
올린다. **걸렸다고 틀린 것은 아니다.** 사람이 볼 자리를 좁힌 것뿐이다.

    R  required 다                  둘째 부류와 같다. 반드시 오류라 늘 올린다
    S  우리가 보내는 칸과 닮았다    camelCase 로 쪼갠 낱말을 하나라도 공유한다.
                                    stationName 대 railwayName 이 Name 을 공유한다.
                                    철도가 이 기준으로 걸린다 — 만든 이유가 이것이다
    O  같은 도구의 다른 줄이 쓴다   한 줄은 보내는데 다른 줄은 안 보내는 칸.
                                    자리마다 받는 것이 달라 그런 것이 보통이지만,
                                    빠뜨린 것과 안 갈려 올린다

왜 이 셋인가. 세 기준 모두 **스키마와 배선만으로** 판정된다 — 서버도 LLM 도
값 판단도 없다. "이 칸이 검색어 같다" 같은 description 읽기는 짐작이라 안 넣었다.
S 가 넓어 보이면 좁히는 것은 사람이 표를 보고 정한다.

## 조용히 죽지 않는다

check_argument 가 나흘간 ValueError 로 죽어 있던 전례가 있다 (NOTES.md 「열린
과제」). tools/ 는 "테스트를 두지 않는다" 가 규칙이라 tests/ 에는 안 넣는다.
대신 **서버 없이 되는 최소 검사를 이 파일 안에 둔다** — `_selfcheck()` 가 손으로
적은 스키마 하나와 배선 한 줄로 네 부류가 각각 한 번씩 나오는지 본 뒤에야 표를
찍는다. 틀리면 첫 줄에서 죽고 표는 안 나온다. pytest 개수는 그대로다.
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from demo.api.services.step_service import (  # noqa: E402
    CENTER_KEYS,
    POINT_RADIUS_TO_BBOX,
    STEP_OF,
    TOOL_OF,
)

GATEWAY_URL = "http://localhost:3000"
TOOLS_PATH_ENV = "/api/tools"
DEFAULT_TIMEOUT = 120
# tools/probe_out/ 은 .gitignore 다. 실측 자산은 전부 거기 둔다.
SCHEMA_PATH = Path(__file__).resolve().parent / "probe_out" / "tools.json"

BBOX_FIELDS = ("minLon", "minLat", "maxLon", "maxLat")
# vendor 의 _point_radius_to_bbox_input 이 지우는 칸. 그 목록 그대로다.
ADAPTER_CONSUMES = set(CENTER_KEYS) | {
    "radius", "radiusMeters", "radius_meters", "radiusKm", "radius_km",
    "distance", "distanceMeters", "distance_meters", "distanceKm", "distance_km",
}
RADIUS_KEYS = ("radiusMeters", "radius_meters", "radius", "radiusKm", "radius_km")

# 판정 넷
UNKNOWN_FIELD = "없는 칸을 보낸다"
MISSING_REQUIRED = "꼭 필요한데 안 보낸다"
UNUSED_FIELD = "있는데 안 쓰는 칸"
OK = "맞다"
NO_SCHEMA = "스키마를 못 받았다"

# 추리는 기준 셋
WHY_REQUIRED = "R"
WHY_SIMILAR = "S"
WHY_OTHER_LINE = "O"


# ── 한글 폭 ──────────────────────────────────────────────────────────
# tools/check_wiring.py 와 같은 방식이다. import 하면 ontology 를 읽으므로
# 서버 없이도 가볍게 돌도록 두 줄만 다시 적었다.


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


# ── 스키마 ──────────────────────────────────────────────────────────


def load_schemas(path: Path) -> dict:
    """도구 이름 -> inputSchema.

    입력  tools.json 경로 (배열이거나 {"tools": [...]})
    출력  {name: {"properties": {...}, "required": [...]}}
    규칙  inputSchema 가 없는 도구는 빈 properties · 빈 required 로 둠
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("tools") or []
    schemas = {}
    for tool in payload:
        if not isinstance(tool, dict) or not tool.get("name"):
            continue
        schema = tool.get("inputSchema") or {}
        schemas[tool["name"]] = {
            "properties": dict(schema.get("properties") or {}),
            "required": list(schema.get("required") or []),
        }
    return schemas


def fetch_schemas(gateway: str, path: Path, timeout: int) -> None:
    """Gateway 에서 /api/tools 를 받아 파일로 남김. 실패하면 예외를 그대로 올림."""
    import requests  # 서버 없이 돌 때는 필요 없어 여기서 import

    response = requests.get(f"{gateway}{TOOLS_PATH_ENV}", timeout=timeout)
    response.raise_for_status()
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(response.json(), ensure_ascii=False, indent=2), encoding="utf-8")


# ── 보내는 칸 ────────────────────────────────────────────────────────


def _has_center(fields: dict) -> bool:
    return any(key in fields for key in CENTER_KEYS)


def _has_radius(fields: dict) -> bool:
    return any(key in fields for key in RADIUS_KEYS)


def sent_fields(wiring: dict, variant: str, schema: dict | None) -> tuple[set, str]:
    """그 줄이 도구에 실제로 보내는 칸 이름.

    입력  STEP_OF 한 줄 · "input" 또는 "input_first" · 그 도구의 스키마(없으면 None)
    출력  (칸 이름 집합, 어댑터 표시). 어댑터가 안 걸리면 표시는 빈 문자열
    규칙  adapter 가 적혀 있고 중심 좌표가 있으면 걸림 (step_service.plan 과 같음)
          안 적혀 있어도 required 에 bbox 넷이 다 있고 중심 좌표 · 반경이 있으면
          vendor 가 저절로 걺 (_should_auto_apply_point_radius_to_bbox)
          걸리면 중심 · 반경 칸이 빠지고 bbox 넷이 들어감
    """
    fields = dict(wiring[variant])
    names = set(fields)
    adapter = ""
    if wiring.get("adapter") == POINT_RADIUS_TO_BBOX and _has_center(fields):
        adapter = POINT_RADIUS_TO_BBOX
    elif (
        schema is not None
        and set(BBOX_FIELDS).issubset(schema["required"])
        and _has_center(fields)
        and _has_radius(fields)
    ):
        adapter = f"{POINT_RADIUS_TO_BBOX}:auto"
    if adapter:
        names = (names - ADAPTER_CONSUMES) | set(BBOX_FIELDS)
    return names, adapter


# ── 세기 ────────────────────────────────────────────────────────────


def _tokens(name: str) -> set:
    """camelCase · snake_case 를 낱말로. 'stationName' -> {station, name}"""
    parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name).replace("_", " ").lower().split()
    return set(parts)


def judge(sent: set, schema: dict | None, sent_by_other_lines: set) -> dict:
    """한 줄의 칸 판정.

    입력  보내는 칸 · 스키마(None 이면 못 받은 것) · 같은 도구의 다른 줄이 보내는 칸
    출력  {verdict, unknown, missing_required, unused: [{name, why}], ok}
    규칙  unused 의 why 는 R · S · O 중 걸린 것. 하나도 없으면 빈 문자열
    """
    if schema is None:
        return {"verdict": NO_SCHEMA, "unknown": [], "missing_required": [], "unused": [], "ok": []}
    props = set(schema["properties"])
    required = set(schema["required"])
    unknown = sorted(sent - props)
    missing_required = sorted(required - sent)
    ok = sorted(sent & props)

    sent_tokens = set()
    for name in sent:
        sent_tokens |= _tokens(name)

    unused = []
    for name in sorted(props - sent):
        why = ""
        if name in required:
            why += WHY_REQUIRED
        if _tokens(name) & sent_tokens:
            why += WHY_SIMILAR
        if name in sent_by_other_lines:
            why += WHY_OTHER_LINE
        unused.append({"name": name, "why": why})

    if unknown:
        verdict = UNKNOWN_FIELD
    elif missing_required:
        verdict = MISSING_REQUIRED
    else:
        verdict = OK
    return {
        "verdict": verdict,
        "unknown": unknown,
        "missing_required": missing_required,
        "unused": unused,
        "ok": ok,
    }


def rows_of(schemas: dict) -> list:
    """STEP_OF 전부를 한 줄씩 판정.

    출력  [{tool, node, type, variant, adapter, sent, schema_fields, ...judge}]
          도구 이름 · 노드 순. 스키마 목록에 없는 도구는 verdict 가 NO_SCHEMA
    """
    # 같은 도구의 다른 줄이 보내는 칸 (O 기준). 먼저 한 바퀴 모은다.
    per_line: list[tuple] = []
    for (node, type_id), wiring in STEP_OF.items():
        tool = TOOL_OF[node]["tool"]
        schema = schemas.get(tool)
        for variant in ("input", "input_first"):
            if variant not in wiring:
                continue
            sent, adapter = sent_fields(wiring, variant, schema)
            per_line.append((tool, node, type_id, variant, adapter, sent, schema))

    by_tool: dict = {}
    for tool, _, _, _, _, sent, _ in per_line:
        by_tool.setdefault(tool, []).append(sent)

    rows = []
    for tool, node, type_id, variant, adapter, sent, schema in per_line:
        others = set()
        for other in by_tool[tool]:
            if other is not sent:
                others |= other
        row = {
            "tool": tool,
            "node": node,
            "type": type_id,
            "variant": variant,
            "adapter": adapter,
            "sent": sorted(sent),
            "schema_fields": sorted(schema["properties"]) if schema else [],
        }
        row.update(judge(sent, schema, others))
        rows.append(row)
    rows.sort(key=lambda r: (r["tool"], r["node"], r["type"], r["variant"]))
    return rows


# ── 최소 검사 ──────────────────────────────────────────────────────


def _selfcheck() -> None:
    """서버 없이 네 부류가 각각 한 번씩 나오는지. 틀리면 여기서 죽는다."""
    schema = {"properties": {"a": {}, "b": {}, "c": {}, "cName": {}}, "required": ["a", "b"]}
    result = judge({"a", "x", "aName"}, schema, {"c"})
    assert result["unknown"] == ["aName", "x"], result
    assert result["missing_required"] == ["b"], result
    assert result["verdict"] == UNKNOWN_FIELD, result
    unused = {u["name"]: u["why"] for u in result["unused"]}
    assert unused == {"b": "R", "c": "O", "cName": "S"}, unused
    assert result["ok"] == ["a"], result
    assert judge({"a", "b"}, schema, set())["verdict"] == OK
    assert judge({"a"}, schema, set())["verdict"] == MISSING_REQUIRED
    assert judge({"a"}, None, set())["verdict"] == NO_SCHEMA
    # 어댑터: 명시 · 자동 · 안 걸림
    wiring = {"input": {"center": "$prev.location", "radiusMeters": 1}, "adapter": POINT_RADIUS_TO_BBOX}
    assert sent_fields(wiring, "input", None) == (set(BBOX_FIELDS), POINT_RADIUS_TO_BBOX)
    bbox_schema = {"properties": {}, "required": list(BBOX_FIELDS)}
    auto = {"input": {"location": "$prev.location", "radiusMeters": 1}}
    assert sent_fields(auto, "input", bbox_schema)[1].endswith(":auto")
    assert sent_fields(auto, "input", schema) == ({"location", "radiusMeters"}, "")
    assert _tokens("stationName") & _tokens("railwayName") == {"name"}


# ── 표 ──────────────────────────────────────────────────────────────

TOOL_W, LINE_W, SENT_W = 42, 58, 44


def _line_label(row: dict) -> str:
    label = f"{row['node']} × {row['type']}"
    if row["variant"] == "input_first":
        label += " (첫)"
    return label


def _print_table(rows: list) -> None:
    print("## 표 — 도구 · 배선 줄 · 보내는 칸 · 판정")
    print()
    print("  " + _pad("도구", TOOL_W) + _pad("배선 줄 (노드 × 받는 타입)", LINE_W) + _pad("보내는 칸", SENT_W) + "판정")
    for row in rows:
        sent = ", ".join(row["sent"]) + (" ·어댑터" if row["adapter"] else "")
        verdict = row["verdict"]
        if verdict == UNKNOWN_FIELD:
            verdict += "  ★ " + ", ".join(row["unknown"])
            if row["missing_required"]:
                verdict += " · required 빠짐 " + ", ".join(row["missing_required"])
        elif verdict == MISSING_REQUIRED:
            verdict += "  ★ " + ", ".join(row["missing_required"])
        elif verdict == OK:
            verdict += f"  · 안 쓰는 칸 {len(row['unused'])}"
        print("  " + _pad(row["tool"], TOOL_W) + _pad(_line_label(row), LINE_W) + _pad(sent, SENT_W) + verdict)
    print()


def _print_watch(rows: list) -> None:
    print("## ★ 눈여겨볼 자리 — 안 쓰는 칸 중 R · S · O 에 걸린 것")
    print()
    print("  R required · S 우리 칸과 낱말을 공유 · O 같은 도구의 다른 줄이 쓴다")
    print()
    print("  " + _pad("도구", TOOL_W) + _pad("배선 줄", LINE_W) + _pad("우리 칸", 30) + "안 쓰는 칸 (왜)")
    count = 0
    for row in rows:
        flagged = [u for u in row["unused"] if u["why"]]
        if not flagged:
            continue
        count += len(flagged)
        print(
            "  "
            + _pad(row["tool"], TOOL_W)
            + _pad(_line_label(row), LINE_W)
            + _pad(", ".join(row["sent"]), 30)
            + " · ".join(f"{u['name']}({u['why']})" for u in flagged)
        )
    print()
    by_why = Counter()
    similar = []
    for row in rows:
        for u in row["unused"]:
            for why in u["why"]:
                by_why[why] += 1
            if WHY_SIMILAR in u["why"]:
                similar.append(f"{row['tool']}.{u['name']}")
    print(f"  걸린 칸 {count} · R {by_why[WHY_REQUIRED]} · S {by_why[WHY_SIMILAR]} · O {by_why[WHY_OTHER_LINE]}")
    # O 는 자리마다 받는 것이 달라 생기는 것이 보통이다. 철도 같은 것은 S 에서 나온다.
    print(f"  S 만 따로 : {', '.join(similar) or '없음'}")
    print()


def _print_total(rows: list) -> None:
    lines = [r for r in rows if r["verdict"] != NO_SCHEMA]
    no_schema = [r for r in rows if r["verdict"] == NO_SCHEMA]
    unknown = sum(len(r["unknown"]) for r in lines)
    missing = sum(len(r["missing_required"]) for r in lines)
    unused = sum(len(r["unused"]) for r in lines)
    flagged = sum(1 for r in lines for u in r["unused"] if u["why"])
    verdicts = Counter(r["verdict"] for r in rows)
    firsts = sum(1 for r in rows if r["variant"] == "input_first")
    print("## 합계")
    print()
    print(f"  배선 줄 {len(rows)} (input {len(rows) - firsts} · input_first {firsts}) · 도구 {len({r['tool'] for r in rows})}")
    print(f"  줄 판정   맞다 {verdicts[OK]} · 없는 칸 {verdicts[UNKNOWN_FIELD]} · 안 보낸 required {verdicts[MISSING_REQUIRED]} · 스키마 못 받음 {verdicts[NO_SCHEMA]}")
    print(f"  칸 합계   없는 칸 {unknown} · 안 보낸 required {missing} · 안 쓰는 칸 {unused} (그중 ★ {flagged})")
    if no_schema:
        print()
        print("  스키마를 못 받은 도구:")
        for tool in sorted({r["tool"] for r in no_schema}):
            print(f"    {tool}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tools", default=str(SCHEMA_PATH), help=f"tools.json (기본 {SCHEMA_PATH})")
    parser.add_argument("--gateway", default=GATEWAY_URL)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Gateway 상한 초")
    parser.add_argument("--refresh", action="store_true", help="파일이 있어도 Gateway 에서 다시 받는다")
    parser.add_argument("--json", help="행을 json 으로도 남길 경로")
    args = parser.parse_args()

    _selfcheck()

    path = Path(args.tools)
    if args.refresh or not path.exists():
        try:
            fetch_schemas(args.gateway, path, args.timeout)
            print(f"스키마: {args.gateway}{TOOLS_PATH_ENV} -> {path}")
        except Exception as error:  # noqa: BLE001 — 무엇이 막혔는지 사람에게 말하고 멈춘다
            if path.exists():
                print(f"Gateway 실패({error}). 파일 {path} 로 대신 돈다")
            else:
                print(f"스키마가 없다. Gateway 도 실패({error}) · 파일도 없음({path})")
                print("  curl -s http://localhost:3000/api/tools -o tools/probe_out/tools.json")
                return 2
    else:
        print(f"스키마: {path} (서버 안 씀. 다시 받으려면 --refresh)")
    schemas = load_schemas(path)
    print(f"도구 {len(schemas)}개 · 배선 줄 {len(STEP_OF)}")
    print()

    rows = rows_of(schemas)
    _print_table(rows)

    print("## 스키마의 칸 — 배선이 가리키는 도구만 (required 는 *)")
    print()
    for tool in sorted({r["tool"] for r in rows}):
        schema = schemas.get(tool)
        if schema is None:
            print("  " + _pad(tool, TOOL_W) + NO_SCHEMA)
            continue
        req = set(schema["required"])
        print("  " + _pad(tool, TOOL_W) + ", ".join(f"{n}*" if n in req else n for n in sorted(schema["properties"])))
    print()

    _print_watch(rows)
    _print_total(rows)

    if args.json:
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"행 json: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
