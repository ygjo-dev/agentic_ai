"""Gateway 도구 42개의 응답이 어떤 칸으로 오는지 적는 사전.

인수인계 문서의 「미결 — 도구를 온톨로지에 넣을 것인가」가 걸림돌로 적은 것이
"output 모양을 모른다(tools.json 에 inputSchema 만 있다)" 였다. 그 걸림돌을
없애는 것이 이 도구다. 개편에서 배선을 간선별로 다시 적을 때 무엇에서 무엇으로
값을 옮길지는 이 표를 보고 정한다.

    python dev/tools/probe_shapes.py --tools /경로/tools.json
    python dev/tools/probe_shapes.py --only geo.geocode,road.getCctv

dev/tools/probe_tools.py 와 무엇이 다른가.

    probe_tools    무엇이 데이터를 주는가.  건수를 센다
    probe_shapes   무엇을 어떤 칸으로 주는가.  배선을 적을 재료를 만든다

**값이 아니라 모양을 적는다.** geojson · coordinates · features 의 값은 표에
안 적고 길이만 적는다. 어제 vworld 응답이 405KB 였다.

ARGUMENT_RULES · REFUSED_TOOLS · 한글 폭 함수는 probe_tools 에서 import 해서
쓴다. 복사하면 도구가 늘 때 두 곳이 조용히 어긋난다.

**남의 데이터를 고치는 도구는 probe_tools 와 똑같이 안 부른다.** REFUSED_TOOLS
를 그대로 재사용한다 (bim.updateModel · bim.deleteModel · knowledge.deleteDoc).

도구 목록은 저장소 밖이라 --tools 로 받는다. Gateway 에서 직접 받아도 된다.

    curl -s http://localhost:3000/api/tools -o /tmp/tools.json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.api.services.execute_service import USER_CONTEXT  # noqa: E402
from tools.probe_tools import (  # noqa: E402
    ARGUMENT_RULES,
    DEFAULT_TOOLS_PATH,
    EXECUTE_PATH,
    GATEWAY_URL,
    NO_ARGUMENT,
    OUT_DIR,
    PREVIEW_LENGTH,
    TIMEOUT,
    GatewayDown,
    _clip,
    _pad,
    build_arguments,
    find_error,
    find_warning,
    load_tools,
)

# ── 인자 덮어쓰기 ────────────────────────────────────────────────────
# ARGUMENT_RULES 는 모든 query 에 "오송역" 을 넣는다. 그것 때문에 행정구역 ·
# 인구 도구가 전부 0건이었다. 0건이면 칸 이름을 볼 것이 없어 사전이 비므로
# 도구별로 덮어쓴다.
#
# **어젯밤 실측으로 확인된 값만 적는다. 지어내지 않는다.** 근거를 옆에 붙인다.
ARGUMENT_OVERRIDES = {
    "adminBoundary.searchBoundaries": {"query": "청주시"},
    # 오송역은 0건, 청주시는 4건 (2026-08-23 실측)
    "vworld.getAdministrativeBoundaries": {"query": "청주시"},
    # 오송역은 0건, 청주시는 4건 (2026-08-23 실측)
    "population.searchStatistics": {"query": "청주시"},
    # 31건 (2026-08-23 실측). required 가 없어 ARGUMENT_RULES 로는 안 실린다
    "geo.getRailwayLines": {"stationName": "오송역"},
    # NOTES.md 2026-08-22 (셋째) 실측. query="청주" 로 254 -> 4건
    "election.searchDistricts": {"query": "청주"},
    "election.searchAssemblyDistricts": {"query": "청주"},
    "election.searchAssemblyPledgeDistricts": {"query": "철도"},
}

# ── 상태 ────────────────────────────────────────────────────────────
# 표에 찍는 결과 다섯. NO_ARGUMENT 는 probe_tools 와 같은 문자열을 쓴다.

DATA = "데이터"
EMPTY = "0건"
ERROR = "오류"
NO_PERMISSION = "권한 없음"

STATUS_ORDER = (DATA, EMPTY, ERROR, NO_ARGUMENT, NO_PERMISSION)

# 배열도 count 도 없이 못 찾았다고만 답할 때의 status 값. election 의
# getLocalPledgeSummary · findLocalPledgeSummaryByPoint 둘이 이렇게 답한다
# (2026-08-23 실측). 셀 배열이 없다고 데이터로 세면 표가 거짓말을 한다.
NOT_FOUND_STATUS = "not_found"

# Gateway 가 권한 없는 도구를 거부할 때의 문구. web-search 서버가 우리
# user_context 에 안 열려 있어 이렇게 답한다(2026-08-22 실측). 데이터가 없는
# 것과 못 부르는 것은 다르므로 갈라 센다.
PERMISSION_MARK = "not applied for this user"


# ── 무엇을 볼 것인가 ─────────────────────────────────────────────────

# 건수를 셀 때 배열인지 보는 key. 앞에서부터 처음 맞는 것을 쓴다.
LIST_KEYS = ("features", "items", "results")

# 좌표가 실리는 칸 이름. 소문자로 맞춰 이것으로 시작하면 좌표로 본다 —
# road.getCctv 가 centerLon · centerLat 로 주므로 정확히 같은 이름만 보면
# 놓친다. 간선별 배선의 출발점이라 놓치면 안 된다.
COORDINATE_PREFIXES = ("location", "center", "lon", "lat")

# 지도 범위가 실리는 칸 이름. [[a,b],[c,d]] 인지 [a,b,c,d] 인지가 배선에 직접
# 걸린다 — 어댑터를 어디에 걸지가 갈린다.
BBOX_KEY = "bbox"

# 다음 도구의 입력이 될 만한 식별자 칸. 소문자로 맞춰 정확히 같은 것만 본다.
CODE_KEYS = ("code", "level", "id", "statid", "sig_cd", "datasetid")

# 식별자 값을 표에 그대로 적을 길이 상한. 넘으면 모양만 적는다.
CODE_SAMPLE_LENGTH = 24

# 표에 적을 최상위 칸의 최대 개수. 넘으면 …
TOP_KEY_LIMIT = 12

# _shape 이 파고드는 깊이 상한. geojson 안까지 들어가면 405KB 를 훑는다.
SHAPE_DEPTH = 2


def _numbers(value) -> bool:
    """숫자만 든 빈 적 없는 배열인지. 좌표와 지도 범위를 가릴 때 씀."""
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
    )


def _letters(length: int, used: int) -> tuple:
    """숫자 자리를 a b c d 로. 값 대신 자리 수를 보이려는 것.

    출력  ("[a,b]", 다음에 쓸 글자 번호)
    규칙  여덟 개를 넘으면 처음으로 돌아감. bbox 는 넷이라 겹칠 일이 없음
    """
    letters = "abcdefgh"
    shown = ",".join(letters[(used + index) % len(letters)] for index in range(length))
    return "[" + shown + "]", used + length


def _shape(value, depth: int = 0) -> str:
    """값 하나의 모양. 값 자체는 적지 않음.

    입력  응답에서 꺼낸 값 · 지금 깊이
    출력  "[a,b]" · "[[a,b],[c,d]]" · "수" · "문자" · "[]" 같은 한 토막
    규칙  숫자만 든 배열은 길이만큼 a b c d 를 늘어놓음
          배열 안에 배열이 있으면 한 겹 더 들어감. SHAPE_DEPTH 까지만
          dict 는 칸 수만. 깊이를 넘으면 "…"
    제약  값을 적지 않는다. 좌표와 지도 범위는 그대로 적으면 표가 숫자로
          차고, geojson 은 405KB 다
    """
    if depth > SHAPE_DEPTH:
        return "…"
    if isinstance(value, bool) or value is None:
        return "값"
    if isinstance(value, (int, float)):
        return "수"
    if isinstance(value, str):
        # 빈 문자열은 칸이 있는데 안 채워 온 것이다. "문자" 로 적으면 배선을
        # 적는 사람이 값이 있는 줄 안다 — ev.searchStations 의 location 이 그렇다.
        return "문자" if value else '""'
    if isinstance(value, list):
        if not value:
            return "[]"
        if _numbers(value):
            return _letters(len(value), 0)[0]
        # [[a,b],[c,d]] 인지 [a,b,c,d] 인지가 배선에 직접 걸린다. 안쪽까지 펴서
        # 적는다 — 겹수만 적으면 그 둘이 표에서 같아 보인다.
        if len(value) <= 4 and all(_numbers(item) for item in value):
            parts, used = [], 0
            for item in value:
                shown, used = _letters(len(item), used)
                parts.append(shown)
            return "[" + ",".join(parts) + "]"
        inner = _shape(value[0], depth + 1)
        return f"[{inner}×{len(value)}]" if len(value) > 1 else f"[{inner}]"
    if isinstance(value, dict):
        return "{" + str(len(value)) + "칸}"
    return "값"


def sources(payload) -> list:
    """칸을 훑을 자리 전부. 최상위와 배열 첫 항목들.

    입력  파싱한 응답 본문
    출력  [(붙일 이름표, dict), ...]. 없는 자리는 빠짐
    규칙  최상위가 dict 면 이름표 없이 봄. 최상위가 배열이면 "[0]."
          features · items · results 의 첫 항목을 각각 그 이름으로 봄
          GeoJSON Feature 는 properties 를 합쳐서 봄. 선거구 코드가 거기 있음
          items 를 features 보다 먼저 봄. 같은 값이면 items 쪽이 정리된
          이름이라 배선을 적을 때 그쪽을 씀
    제약  둘째 항목부터는 보지 않는다. 사전은 모양을 적는 것이지 데이터를
          훑는 것이 아니다
    """
    found = []
    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict):
            found.append(("[0].", payload[0]))
        return found
    if not isinstance(payload, dict):
        return found

    found.append(("", payload))
    for key in ("items", "features", "results"):
        value = payload.get(key)
        if not (isinstance(value, list) and value and isinstance(value[0], dict)):
            continue
        item = value[0]
        properties = item.get("properties")
        if isinstance(properties, dict):
            item = {**item, **properties}
        found.append((f"{key}[0].", item))
    return found


def top_keys(payload) -> list:
    """최상위 칸 이름. 이름만 적고 값은 안 적음.

    출력  [칸 이름, ...]. 최상위가 배열이면 첫 항목의 칸 이름
    규칙  TOP_KEY_LIMIT 개까지. 넘으면 마지막에 "…"
    """
    if isinstance(payload, list):
        keys = list(payload[0]) if payload and isinstance(payload[0], dict) else []
    elif isinstance(payload, dict):
        keys = list(payload)
    else:
        return []
    if len(keys) > TOP_KEY_LIMIT:
        return keys[:TOP_KEY_LIMIT] + ["…"]
    return keys


def coordinate_fields(payload) -> list:
    """좌표를 내놓는 칸과 그 모양.

    출력  ["location=[a,b]", "[0].centerLon=수", ...]. 없으면 빈 목록
    규칙  sources 가 주는 자리를 다 봄. 이름을 소문자로 맞춰
          COORDINATE_PREFIXES 로 시작하면 좌표로 봄
          같은 이름과 모양이 두 자리에서 나오면 앞의 것만 적음
    제약  좌표 값을 적지 않는다. 모양만 적는다
    """
    return _collect(
        payload,
        lambda key: str(key).lower().startswith(COORDINATE_PREFIXES),
        lambda value: _shape(value),
    )


def bbox_fields(payload) -> list:
    """지도 범위 칸과 그 모양.

    출력  ["bbox=[[a,b],[c,d]]", "items[0].bbox=[a,b,c,d]"]. 없으면 빈 목록
    규칙  sources 가 주는 자리를 다 봄
          값이 None 이면 "없음". 칸은 있는데 안 채워 보내는 것과 칸 자체가
          없는 것은 다름
    """
    return _collect(
        payload,
        lambda key: str(key).lower() == BBOX_KEY,
        lambda value: "없음" if value is None else _shape(value),
    )


def code_fields(payload) -> list:
    """다음 도구의 입력이 될 만한 식별자 칸과 예시 하나.

    출력  ["items[0].code=4311101", ...]. 없으면 빈 목록
    규칙  sources 가 주는 자리를 다 봄. 소문자로 맞춰 CODE_KEYS 와 정확히
          같은 이름만
          짧은 문자열과 수는 값을 그대로 적음 — 체계가 맞는지는 값을 봐야
          갈림. 길거나 중첩된 값은 모양만
    """
    return _collect(
        payload,
        lambda key: str(key).lower() in CODE_KEYS,
        _code_value,
    )


def _code_value(value) -> str:
    """식별자 칸에 적을 것. 짧으면 값 그대로, 길면 모양만."""
    if isinstance(value, str) and len(value) <= CODE_SAMPLE_LENGTH:
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return _shape(value)


def _collect(payload, wanted, shown) -> list:
    """자리를 다 훑어 조건에 맞는 칸을 "이름표이름=모양" 으로 모음.

    입력  응답 본문 · 칸 이름 판정 함수 · 값을 무엇으로 적을지 정하는 함수
    출력  ["items[0].bbox=[a,b,c,d]", ...]. 순서는 sources 순서
    규칙  같은 이름과 같은 모양이 두 자리에서 나오면 앞의 것만 적음.
          items 와 features 가 같은 것을 두 번 말하는 일이 잦음
    """
    found, seen = [], set()
    for prefix, source in sources(payload):
        for key, value in source.items():
            if not wanted(key):
                continue
            mark = (str(key).lower(), shown(value))
            if mark in seen:
                continue
            seen.add(mark)
            found.append(f"{prefix}{key}={mark[1]}")
    return found


def record_count(payload):
    """응답의 건수.

    출력  int. 못 세면 "?"
    규칙  probe_tools.count_records 와 같은 순서지만 객체 하나를 1 로 세지
          않음. 사전은 "몇 건" 이 아니라 "배열이 있느냐" 를 물음
            count · totalMatches 가 있으면 그 값
            features · items · results 가 배열이면 그 길이
            최상위가 배열이면 그 길이
            그 밖에는 "?"
    """
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("count", "totalMatches"):
            value = payload.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        for key in LIST_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
    return "?"


# ── 인자 ────────────────────────────────────────────────────────────


def shaped_arguments(tool: dict) -> tuple:
    """도구 하나를 부를 인자. 덮어쓰기를 얹은 것.

    입력  {name, inputSchema, ...} 하나
    출력  (인자 dict, 못 채운 이유 목록). 부를 수 있으면 이유 목록이 빔
    규칙  probe_tools.build_arguments 로 required 를 채운 뒤
          ARGUMENT_OVERRIDES 를 얹음. 덮어쓰기는 required 가 아닌 칸도 넣음 —
          query 가 optional 인 도구가 많고 안 넣으면 전국이 나와 0건과
          구별이 안 됨
          REFUSED_TOOLS · 못 채운 required 는 build_arguments 가 그대로 막음
    제약  값을 지어내지 않는다. 덮어쓰기는 실측으로 확인된 값만 적는다
    """
    arguments, missing = build_arguments(tool)
    if arguments is None:
        return None, missing
    return {**arguments, **ARGUMENT_OVERRIDES.get(tool["name"], {})}, []


def label_of(arguments: dict) -> str:
    """응답 파일 이름에 붙일 라벨. 무슨 인자로 눌렀는지.

    출력  인자에 실린 첫 문자열. 좌표만 실었으면 "좌표". 인자가 없으면 "기본"
    규칙  파일 이름에 쓰므로 경로 구분자와 공백을 뺌
    """
    for value in arguments.values():
        if isinstance(value, str) and value.strip():
            return value.strip().replace("/", "_").replace("\\", "_").replace(" ", "_")
    return "좌표" if arguments else "기본"


# ── 호출 ────────────────────────────────────────────────────────────


def probe(tool: dict, timeout: int = TIMEOUT) -> dict:
    """도구 하나를 한 번 누르고 모양을 적음.

    입력  {name, inputSchema, ...} 하나 · 상한 초
    출력  {name, label, status, count, top, coordinates, bboxes, codes,
           notice, payload}
    규칙  인자를 못 만들면 부르지 않고 NO_ARGUMENT
          본문에 error 가 있으면 오류. 그 문구에 PERMISSION_MARK 가 있으면
          권한 없음. HTTP 상태를 보지 않음 — Gateway 가 모든 오류를 500 +
          고정 문구로 덮음
          건수가 0 이면 0건. 그때 warning · message 가 있는지를 notice 에 적음
          최상위 status 가 NOT_FOUND_STATUS 면 셀 배열이 없어도 0건
          Gateway 에 못 닿으면 GatewayDown. 재시도하지 않음
    제약  응답 값을 표에 적지 않는다. 전문은 파일로만 남긴다
    """
    name = tool["name"]
    arguments, missing = shaped_arguments(tool)
    if arguments is None:
        return _row(name, "-", NO_ARGUMENT, "-", notice=", ".join(missing))

    label = label_of(arguments)

    # vendor_to_be_deleted/asap/mcp_client.execute_tool 이 만드는 본문과 같은 모양이다.
    # user_context 를 빼면 요청마다 새 guest 가 만들어져 adminBoundary 셋
    # 말고는 전부 거부된다(실측).
    body = {"tool": name, "input": arguments, "user_context": dict(USER_CONTEXT)}
    server_id = tool.get("serverId")
    if server_id:
        body["server_id"] = server_id

    try:
        response = requests.post(
            f"{GATEWAY_URL}{EXECUTE_PATH}", json=body, timeout=timeout
        )
    except requests.exceptions.ConnectionError as exc:
        raise GatewayDown(str(exc)) from exc
    except requests.exceptions.Timeout:
        return _row(name, label, ERROR, "-", notice=f"{timeout}초 안에 답이 없음")

    try:
        payload = response.json()
    except ValueError:
        return _row(
            name, label, ERROR, "-",
            notice=f"JSON 이 아님 (HTTP {response.status_code})",
        )

    error = find_error(payload)
    if error:
        status = NO_PERMISSION if PERMISSION_MARK in error else ERROR
        return _row(name, label, status, "-", notice=error[:PREVIEW_LENGTH], payload=payload)

    count = record_count(payload)
    if isinstance(payload, dict) and payload.get("status") == NOT_FOUND_STATUS:
        count = 0
    status = EMPTY if count == 0 else DATA
    notice = find_warning(payload)
    if status == EMPTY:
        notice = notice or "문구 없음"

    return _row(
        name, label, status, str(count),
        top=top_keys(payload),
        coordinates=coordinate_fields(payload),
        bboxes=bbox_fields(payload),
        codes=code_fields(payload),
        notice=notice,
        payload=payload,
    )


def _row(name, label, status, count, top=None, coordinates=None, bboxes=None,
         codes=None, notice="", payload=None) -> dict:
    """표 한 줄. 칸이 빠지는 자리가 없게 여기서 한 번에 만든다."""
    return {
        "name": name,
        "label": label,
        "status": status,
        "count": count,
        "top": top or [],
        "coordinates": coordinates or [],
        "bboxes": bboxes or [],
        "codes": codes or [],
        "notice": notice,
        "payload": payload,
    }


def save(name: str, label: str, payload) -> None:
    """응답 전문을 dev/tools/probe_out/<도구>.<라벨>.json 으로 남김.

    규칙  표에는 칸 이름만 찍힘. 배선을 적을 때 값을 봐야 하면 이 파일을 봄
          안 부른 도구(payload None)는 남기지 않음
          같은 도구를 다른 인자로 누르면 다른 파일이 됨. 라벨이 그것을 가름
    """
    if payload is None:
        return
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f"{name}.{label}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


# ── 표 ──────────────────────────────────────────────────────────────

NAME_WIDTH = 44
STATUS_WIDTH = 11
COUNT_WIDTH = 7
COORDINATE_WIDTH = 30
BBOX_WIDTH = 22
CODE_WIDTH = 34
TOP_WIDTH = 46
NOTICE_WIDTH = 40


def _joined(values: list) -> str:
    return " ".join(values) if values else "-"


def print_table(results: list) -> None:
    """도구 한 줄씩. 값이 아니라 칸 이름과 모양."""
    print()
    print(
        "  "
        + _pad("도구", NAME_WIDTH)
        + _pad("결과", STATUS_WIDTH)
        + _pad("건수", COUNT_WIDTH)
        + _pad("좌표 칸", COORDINATE_WIDTH)
        + _pad("bbox 칸", BBOX_WIDTH)
        + _pad("코드 칸", CODE_WIDTH)
        + _pad("최상위 칸", TOP_WIDTH)
        + "0건 문구 · 비고"
    )

    for result in results:
        print(
            "  "
            + _pad(_clip(result["name"], NAME_WIDTH - 2), NAME_WIDTH)
            + _pad(result["status"], STATUS_WIDTH)
            + _pad(str(result["count"]), COUNT_WIDTH)
            + _pad(_clip(_joined(result["coordinates"]), COORDINATE_WIDTH - 2), COORDINATE_WIDTH)
            + _pad(_clip(_joined(result["bboxes"]), BBOX_WIDTH - 2), BBOX_WIDTH)
            + _pad(_clip(_joined(result["codes"]), CODE_WIDTH - 2), CODE_WIDTH)
            + _pad(_clip(" ".join(result["top"]) or "-", TOP_WIDTH - 2), TOP_WIDTH)
            + _clip(result["notice"] or "-", NOTICE_WIDTH)
        )

    tally = Counter(result["status"] for result in results)
    print("  " + "─" * 100)
    print(
        "  "
        + _pad(f"도구 {len(results)}개", NAME_WIDTH)
        + " · ".join(f"{status} {tally.get(status, 0)}" for status in STATUS_ORDER)
    )


def receiving_fields(tool: dict) -> list:
    """이 도구가 식별자를 받는 칸. inputSchema 에서 읽음.

    입력  {name, inputSchema, ...} 하나
    출력  ["code(선택)", "level(필수)", ...]. 없으면 빈 목록
    규칙  properties 의 이름을 소문자로 맞춰 CODE_KEYS 와 같은 것만
          required 에 있으면 필수, 아니면 선택
    제약  응답이 아니라 선언을 읽는다. 눌러보지 않아도 알 수 있는 것이다
    """
    schema = tool.get("inputSchema") or {}
    required = set(schema.get("required") or [])
    return [
        f"{key}({'필수' if key in required else '선택'})"
        for key in (schema.get("properties") or {})
        if str(key).lower() in CODE_KEYS
    ]


def print_materials(results: list, tools: list) -> None:
    """배선 재료. 개편에서 간선별 배선을 적을 때 보는 갈래 다섯.

    규칙  무엇을 어떻게 이을지는 적지 않음. 재료만 갈라 놓음
    """
    groups = [
        ("좌표를 내놓는 도구", [r for r in results if r["coordinates"]], "coordinates"),
        ("bbox 를 내놓는 도구", [r for r in results if r["bboxes"]], "bboxes"),
        ("코드를 내놓는 도구", [r for r in results if r["codes"]], "codes"),
    ]
    for title, rows, key in groups:
        print()
        print(f"  {title} ({len(rows)}개)")
        for row in rows:
            print("  " + _pad(_clip(row["name"], NAME_WIDTH - 2), NAME_WIDTH) + _joined(row[key]))

    receiving = [(tool["name"], receiving_fields(tool)) for tool in tools]
    receiving = [(name, fields) for name, fields in receiving if fields]
    print()
    print(f"  코드를 받는 도구 ({len(receiving)}개)")
    for name, fields in receiving:
        print("  " + _pad(_clip(name, NAME_WIDTH - 2), NAME_WIDTH) + " ".join(fields))

    silent = [r for r in results if r["status"] == EMPTY and r["notice"] == "문구 없음"]
    print()
    print(f"  0건인데 문구가 없는 도구 ({len(silent)}개)")
    for row in silent:
        print("  " + _clip(row["name"], NAME_WIDTH - 2))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gateway 도구의 응답이 어떤 칸으로 오는지 적는다."
    )
    parser.add_argument(
        "--tools", default=str(DEFAULT_TOOLS_PATH),
        help=f"도구 목록 json (기본 {DEFAULT_TOOLS_PATH})",
    )
    parser.add_argument("--only", default="", help="누를 도구 이름. 예: geo.geocode,road.getCctv")
    parser.add_argument("--timeout", type=int, default=TIMEOUT, help=f"도구당 상한 초 (기본 {TIMEOUT})")
    args = parser.parse_args()

    tools_path = Path(args.tools)
    if not tools_path.is_file():
        print(f"도구 목록이 없습니다 : {tools_path}")
        print(f"curl -s {GATEWAY_URL}/api/tools -o /tmp/tools.json 으로 받아 --tools 로 알려주세요.")
        return 2

    tools = load_tools(tools_path)
    if args.only:
        wanted = [part for part in args.only.replace(" ", "").split(",") if part]
        tools = [tool for tool in tools if tool["name"] in wanted]
        missing = sorted(set(wanted) - {tool["name"] for tool in tools})
        if missing:
            print(f"목록에 없는 도구 : {missing}")
            return 2

    print(f"도구 {len(tools)}개 · {GATEWAY_URL}{EXECUTE_PATH} · 도구당 {args.timeout}초")

    results, note, status = [], "", 0
    try:
        for tool in tools:
            result = probe(tool, args.timeout)
            save(result["name"], result["label"], result.pop("payload"))
            results.append(result)
            # 42번이라 오래 걸린다. 아무것도 안 나오면 멈춘 줄 안다.
            sys.stdout.write(".")
            sys.stdout.flush()
    except GatewayDown:
        note, status = "Gateway 가 떠 있는지 보세요 (docker compose ps)", 1
    except KeyboardInterrupt:
        note = "(중단됨 — 여기까지의 결과)"

    print()
    if results:
        print_table(results)
        print_materials(results, tools)
        print()
        print(f"응답 전문 : {OUT_DIR}")
    if note:
        print()
        print(note)

    return status


if __name__ == "__main__":
    sys.exit(main())
