"""배선 줄이 도구의 어느 칸을 쓰는지 inputSchema 와 맞대는 계기판.

dev/tools/check_wiring.py 는 **배선 줄이 있는가**만 센다. 그 줄이 **맞는 칸을 쓰는가**는
아무도 안 봤다. 그래서 이런 일이 있었다 (NOTES.md 「열린 과제」 2026-08-26).

    geo.getRailwayLines 는 stationName 과 railwayName 을 갖는다
    우리 배선은 stationName 하나만 보낸다
      -> "경부선 노선 보여줘" 가 0건
      -> check_wiring 은 통과였다. 줄은 있으니까
      -> 사람이 화면에서 0건을 보고서야 알았다

도구가 늘면 이런 자리가 비례해서 는다. 이 도구가 그것을 센다.

    python dev/tools/check_inputs.py                     probe_out/tools.json 이 있으면 서버 없이
    python dev/tools/check_inputs.py --tools /tmp/tools.json
    python dev/tools/check_inputs.py --refresh           Gateway 에서 다시 받아 파일을 갱신

**표를 복사하지 않는다.** STEP_OF · TOOL_OF 를 app/api/services/step_service 에서
그대로 import 한다. 읽기만 한다 — 이 파일은 배선도 온톨로지도 안 고친다.

**TOOL_OF 는 이제 「실행 수단」이다** (「마흔아홉째」). server_id · tool 대신
command 를 적은 줄(show_facility)이 있고, 그 줄은 Gateway 도구가 아니라 지도
명령이라 맞댈 inputSchema 가 없다 — 그 args 의 계약은 저쪽 화면(useChat)이다.
그래서 도구 줄과 갈라 「지도 명령 줄」로 따로 세고 표 끝에 몇 줄인지 적는다.
이 갈래를 모르고 ["tool"] 을 읽다가 KeyError 로 죽어 있었다 (「쉰째」에서 발견,
「쉰아홉째」에서 살림).

**값으로 칸이 갈리는 줄(arg_field)은 갈래마다 한 행이다.** 철도 노선 조회는
발화 값이 "…선" 으로 끝나면 stationName 대신 railwayName 을 쓴다
(step_service._by_argument). 한 줄이 두 벌을 보낼 수 있으므로 input_first 와
같은 방식으로 행을 가른다 — 기본 칸 한 행 · 어미가 걸렸을 때의 칸 한 행("(…선)"
표시). 예전에는 기본 칸만 보여 railwayName 이 영영 「안 쓰는 칸」으로 남았다.

## 스키마는 파일로 갖는다

/api/tools 가 21초 걸린 전례가 있어(NOTES.md 「셋째」) 한 번 받으면
dev/tools/probe_out/tools.json 에 남기고 다음부터는 그것을 읽는다. 그 파일이 있으면
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

## 안 쓰는 칸이 제일 많다 — 추리는 기준 넷

properties 는 도구마다 열 개가 넘고 대부분 limit · includeGeometry 같은 안 보내도
되는 손잡이다. 그냥 늘어놓으면 못 읽으므로 아래 넷 중 하나에 걸리는 칸만 ★ 로
올린다. **걸렸다고 틀린 것은 아니다.** 사람이 볼 자리를 좁힌 것뿐이다.

    R  required 다                  둘째 부류와 같다. 반드시 오류라 늘 올린다
    S  우리가 보내는 칸과 닮았다    camelCase 로 쪼갠 낱말을 하나라도 공유한다.
                                    stationName 대 railwayName 이 Name 을 공유한다.
                                    철도가 이 기준으로 걸린다 — 만든 이유가 이것이다
    O  같은 도구의 다른 줄이 쓴다   한 줄은 보내는데 다른 줄은 안 보내는 칸.
                                    자리마다 받는 것이 달라 그런 것이 보통이지만,
                                    빠뜨린 것과 안 갈려 올린다
    A  발화 줄의 안 쓰는 칸         @arg(발화에서 온 값)를 보내는 줄에서, 크기
                                    손잡이(limit · k · offset)가 아닌 안 쓰는 칸
                                    전부. 「쉰아홉째」에 더했다

왜 A 를 더했나 (2026-08-30 「쉰아홉째」). 사람이 하나씩 부딪혀 찾은 넷 —
all · includeGeometry · pledgeCategory · order — 가 R · S · O 어디에도 안 걸렸다.
넷은 칸의 성질이 제각각이라(boolean 둘 · string 둘, 기본값 있는 것 없는 것,
거르는 칸과 출력 칸) 칸의 성질로는 못 좁힌다. 공통점은 자리다 — 전부 발화가
@arg 한 칸으로 접히는 줄이었다. 발화는 자유 문장이라 그 줄의 다른 모든 칸이
「사람 말이 갈 수 없는 자리」가 된다. $prev · $context 줄은 사람 말이 아니라
앞 단계 · 화면이 채우는 자리라 예전 판정(자리마다 받는 것이 다르다) 그대로 둔다.
limit · k · offset 을 뺀 것은 개수 손잡이는 말을 막지 않아서인데, "100개만
보여줘" 같은 발화가 나오면 이 제외를 다시 본다.

왜 이 넷인가. 네 기준 모두 **스키마와 배선만으로** 판정된다 — 서버도 LLM 도
값 판단도 없다. "이 칸이 검색어 같다" 같은 description 읽기는 짐작이라 안 넣었다.
S · A 가 넓어 보이면 좁히는 것은 사람이 표를 보고 정한다.

## 조용히 죽지 않는다

check_argument 가 나흘간 ValueError 로 죽어 있던 전례가 있다 (NOTES.md 「열린
과제」). tools/ 는 "테스트를 두지 않는다" 가 규칙이라 tests/ 에는 안 넣는다.
대신 **서버 없이 되는 최소 검사를 이 파일 안에 둔다** — `_selfcheck()` 가 손으로
적은 스키마 하나와 배선 한 줄로 네 부류가 각각 한 번씩 나오는지 본 뒤에야 표를
찍는다. 틀리면 첫 줄에서 죽고 표는 안 나온다.

그 검사가 이 파일 자신의 KeyError 를 못 잡았다 (「쉰째」) — 손으로 적은 배선만
보고 **진짜 표는 한 줄도 안 읽었기** 때문이다. 그래서 「TOOL_OF · STEP_OF 의
모든 줄을 한 번씩 읽어 본다」를 더했다 — 빈 스키마로 rows_of 를 끝까지 돌린다.
서버가 없어도 돌고, 표의 모양이 바뀌면(이번처럼 command 줄이 생기면) 여기서
죽는다. pytest 쪽에는 dev/tests/tools/test_check_inputs_selfcheck.py 하나가
_selfcheck 를 부른다 — 이 도구는 어쩌다 한 번 돌지만 배선표는 커밋마다 바뀌고,
커밋마다 도는 것은 pytest 다. check_argument 나흘 · check_inputs 하루가 그렇게
새어 나갔다.
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.api.services.step_service import (  # noqa: E402
    CENTER_KEYS,
    POINT_RADIUS_TO_BBOX,
    SPOKEN_VALUE,
    STEP_OF,
    TOOL_OF,
)

GATEWAY_URL = "http://localhost:3000"
TOOLS_PATH_ENV = "/api/tools"
DEFAULT_TIMEOUT = 120
# dev/tools/probe_out/ 은 .gitignore 다. 실측 자산은 전부 거기 둔다.
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

# 추리는 기준 넷
WHY_REQUIRED = "R"
WHY_SIMILAR = "S"
WHY_OTHER_LINE = "O"
WHY_SPOKEN_LINE = "A"

# A 에서 빼는 개수 손잡이. 값이 커 봐야 더 줄 뿐이라 사람 말을 막지 않는다.
SIZE_KNOBS = {"limit", "k", "offset"}


# ── 한글 폭 ──────────────────────────────────────────────────────────
# dev/tools/check_wiring.py 와 같은 방식이다. import 하면 ontology 를 읽으므로
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


def judge(sent: set, schema: dict | None, sent_by_other_lines: set, spoken: bool = False) -> dict:
    """한 줄의 칸 판정.

    입력  보내는 칸 · 스키마(None 이면 못 받은 것) · 같은 도구의 다른 줄이 보내는 칸
          · 이 줄이 발화 값(@arg)을 보내는지
    출력  {verdict, unknown, missing_required, unused: [{name, why}], ok}
    규칙  unused 의 why 는 R · S · O · A 중 걸린 것. 하나도 없으면 빈 문자열
          A 는 spoken 인 줄에서 SIZE_KNOBS 를 뺀 안 쓰는 칸 전부
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
        if spoken and name not in SIZE_KNOBS:
            why += WHY_SPOKEN_LINE
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


def _variants_of(wiring: dict, variant: str):
    """이 줄이 이 갈래에서 보낼 수 있는 input 벌. arg_field 가 있으면 둘.

    입력  STEP_OF 한 줄 · "input" 또는 "input_first"
    출력  (어미 표시, input) 쌍을 낳음. 기본 벌은 어미 표시가 빈 문자열
    규칙  arg_field 갈래는 @arg 가 든 칸의 이름만 바뀜 (step_service._by_argument
          와 같은 규칙). @arg 가 없는 벌(input_first 가 문맥에서 올 때)에는 안 생김
    """
    base = wiring[variant]
    yield "", base
    rule = wiring.get("arg_field")
    if rule and SPOKEN_VALUE in base.values():
        suffix, field = rule
        yield suffix, {
            (field if value == SPOKEN_VALUE else key): value
            for key, value in base.items()
        }


def rows_of(schemas: dict) -> tuple[list, list]:
    """STEP_OF 전부를 한 줄씩 판정.

    출력  (rows, command_lines)
          rows  [{tool, node, type, variant, arg_suffix, adapter, sent,
                  schema_fields, spoken, ...judge}]
                도구 이름 · 노드 순. 스키마 목록에 없는 도구는 verdict 가 NO_SCHEMA.
                arg_field 가 있는 줄은 갈래마다 한 행 (arg_suffix 로 갈림)
          command_lines  [{node, type, command}]. TOOL_OF 에 tool 이 없는 줄 —
                지도 명령이라 맞댈 inputSchema 가 없어 판정에서 뺌
    """
    # 같은 도구의 다른 줄이 보내는 칸 (O 기준). 먼저 한 바퀴 모은다.
    per_line: list[tuple] = []
    command_lines: list[dict] = []
    for (node, type_id), wiring in STEP_OF.items():
        entry = TOOL_OF[node]
        if "tool" not in entry:
            command_lines.append({"node": node, "type": type_id, "command": entry["command"]})
            continue
        tool = entry["tool"]
        schema = schemas.get(tool)
        for variant in ("input", "input_first"):
            if variant not in wiring:
                continue
            for arg_suffix, fields in _variants_of(wiring, variant):
                branch = dict(wiring)
                branch[variant] = fields
                sent, adapter = sent_fields(branch, variant, schema)
                spoken = SPOKEN_VALUE in fields.values()
                per_line.append((tool, node, type_id, variant, arg_suffix, adapter, sent, schema, spoken))

    by_tool: dict = {}
    for tool, _, _, _, _, _, sent, _, _ in per_line:
        by_tool.setdefault(tool, []).append(sent)

    rows = []
    for tool, node, type_id, variant, arg_suffix, adapter, sent, schema, spoken in per_line:
        others = set()
        for other in by_tool[tool]:
            if other is not sent:
                others |= other
        row = {
            "tool": tool,
            "node": node,
            "type": type_id,
            "variant": variant,
            "arg_suffix": arg_suffix,
            "adapter": adapter,
            "sent": sorted(sent),
            "schema_fields": sorted(schema["properties"]) if schema else [],
            "spoken": spoken,
        }
        row.update(judge(sent, schema, others, spoken))
        rows.append(row)
    rows.sort(key=lambda r: (r["tool"], r["node"], r["type"], r["variant"], r["arg_suffix"]))
    command_lines.sort(key=lambda c: (c["node"], c["type"]))
    return rows, command_lines


# ── 최소 검사 ──────────────────────────────────────────────────────


def _selfcheck() -> None:
    """서버 없이 네 부류가 각각 한 번씩 나오는지. 틀리면 여기서 죽는다.

    규칙  손으로 적은 스키마 · 배선으로 판정 규칙을 봄
          진짜 TOOL_OF · STEP_OF 도 빈 스키마로 끝까지 한 바퀴 읽음.
          표의 모양이 바뀌어 이 파일이 못 읽게 되면 여기서 죽음
    이력  「마흔아홉째」가 TOOL_OF 에 tool 없는 줄을 더했을 때 손으로 적은
          배선만 보던 이 검사는 통과했고 rows_of 는 KeyError 로 죽어 있었음
          (「쉰째」 발견 · 「쉰아홉째」 수리). 전 줄 읽기가 그 구멍임
    """
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
    # A: 발화 줄에서는 크기 손잡이 말고 다 걸린다. 발화 줄이 아니면 안 걸린다.
    spoken_schema = {"properties": {"query": {}, "all": {}, "limit": {}}, "required": []}
    unused = {u["name"]: u["why"] for u in judge({"query"}, spoken_schema, set(), spoken=True)["unused"]}
    assert unused == {"all": "A", "limit": ""}, unused
    unused = {u["name"]: u["why"] for u in judge({"query"}, spoken_schema, set(), spoken=False)["unused"]}
    assert unused == {"all": "", "limit": ""}, unused
    # 어댑터: 명시 · 자동 · 안 걸림
    wiring = {"input": {"center": "$prev.location", "radiusMeters": 1}, "adapter": POINT_RADIUS_TO_BBOX}
    assert sent_fields(wiring, "input", None) == (set(BBOX_FIELDS), POINT_RADIUS_TO_BBOX)
    bbox_schema = {"properties": {}, "required": list(BBOX_FIELDS)}
    auto = {"input": {"location": "$prev.location", "radiusMeters": 1}}
    assert sent_fields(auto, "input", bbox_schema)[1].endswith(":auto")
    assert sent_fields(auto, "input", schema) == ({"location", "radiusMeters"}, "")
    assert _tokens("stationName") & _tokens("railwayName") == {"name"}
    # arg_field: @arg 가 든 칸만 이름이 바뀐 갈래가 하나 더 나온다
    ruled = {"input": {"s": SPOKEN_VALUE, "k": 1}, "arg_field": ("선", "r")}
    assert list(_variants_of(ruled, "input")) == [
        ("", {"s": SPOKEN_VALUE, "k": 1}),
        ("선", {"r": SPOKEN_VALUE, "k": 1}),
    ]
    assert list(_variants_of({"input": {"bbox": "$prev.bbox"}}, "input")) == [("", {"bbox": "$prev.bbox"})]

    # 진짜 표 전 줄 읽기. 스키마가 비어도 rows_of 는 끝까지 돌아야 한다.
    rows, command_lines = rows_of({})
    assert rows, "배선 줄을 하나도 못 읽었다"
    assert all(row["verdict"] == NO_SCHEMA for row in rows), "빈 스키마인데 딴 판정이 나왔다"
    covered = {(r["node"], r["type"]) for r in rows} | {(c["node"], c["type"]) for c in command_lines}
    assert covered == set(STEP_OF), covered ^ set(STEP_OF)
    for line in command_lines:
        assert "tool" not in TOOL_OF[line["node"]], line


# ── 표 ──────────────────────────────────────────────────────────────

TOOL_W, LINE_W, SENT_W = 42, 58, 44


def _line_label(row: dict) -> str:
    label = f"{row['node']} × {row['type']}"
    if row["variant"] == "input_first":
        label += " (첫)"
    if row["arg_suffix"]:
        label += f" (…{row['arg_suffix']})"
    return label


def _print_table(rows: list, command_lines: list) -> None:
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
    # 도구가 아닌 줄. 맞댈 inputSchema 가 없어 위 표에서 뺐고, 몇 줄인지만 적는다.
    print(f"  지도 명령 줄 {len(command_lines)} (도구를 안 불러 판정에서 뺌)")
    for line in command_lines:
        print(f"    {line['node']} × {line['type']}  ->  {line['command']}")
    print()


def _print_watch(rows: list) -> None:
    print("## ★ 눈여겨볼 자리 — 안 쓰는 칸 중 R · S · O · A 에 걸린 것")
    print()
    print("  R required · S 우리 칸과 낱말을 공유 · O 같은 도구의 다른 줄이 쓴다")
    print("  A 발화(@arg) 줄의 안 쓰는 칸 (limit · k · offset 제외)")
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
    print(
        f"  걸린 칸 {count} · R {by_why[WHY_REQUIRED]} · S {by_why[WHY_SIMILAR]}"
        f" · O {by_why[WHY_OTHER_LINE]} · A {by_why[WHY_SPOKEN_LINE]}"
    )
    # O 는 자리마다 받는 것이 달라 생기는 것이 보통이다. 철도 같은 것은 S 에서 나온다.
    print(f"  S 만 따로 : {', '.join(similar) or '없음'}")
    print()


def _print_total(rows: list, command_lines: list) -> None:
    lines = [r for r in rows if r["verdict"] != NO_SCHEMA]
    no_schema = [r for r in rows if r["verdict"] == NO_SCHEMA]
    unknown = sum(len(r["unknown"]) for r in lines)
    missing = sum(len(r["missing_required"]) for r in lines)
    unused = sum(len(r["unused"]) for r in lines)
    flagged = sum(1 for r in lines for u in r["unused"] if u["why"])
    verdicts = Counter(r["verdict"] for r in rows)
    firsts = sum(1 for r in rows if r["variant"] == "input_first")
    branches = sum(1 for r in rows if r["arg_suffix"])
    print("## 합계")
    print()
    print(
        f"  판정한 행 {len(rows)} (input {len(rows) - firsts - branches} · input_first {firsts}"
        f" · 값 갈래 {branches}) · 지도 명령 줄 {len(command_lines)} · 도구 {len({r['tool'] for r in rows})}"
    )
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
                print("  curl -s http://localhost:3000/api/tools -o dev/tools/probe_out/tools.json")
                return 2
    else:
        print(f"스키마: {path} (서버 안 씀. 다시 받으려면 --refresh)")
    schemas = load_schemas(path)
    print(f"도구 {len(schemas)}개 · 배선 줄 {len(STEP_OF)}")
    print()

    rows, command_lines = rows_of(schemas)
    _print_table(rows, command_lines)

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
    _print_total(rows, command_lines)

    if args.json:
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"행 json: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
