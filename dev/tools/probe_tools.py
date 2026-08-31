"""Gateway 도구 42개를 한 번씩 눌러 무엇이 실제로 데이터를 주는지 재는 도구.

배선을 적을 곳을 정하려고 먼저 훑는다. STEP_OF 에 열넷을 적었고 스물다섯이
남았는데, 도구가 실제로 데이터를 주는지는 두 개밖에 모른다(road.getCctv 83건 ·
geo.geocode 정상). 빈 껍데기에 배선을 적으면 시연에서 보여줄 것이 안 는다.

    python dev/tools/probe_tools.py
    python dev/tools/probe_tools.py --only road.getCctv,geo.geocode
    python dev/tools/probe_tools.py --tools /경로/tools.json --timeout 120

**손으로 돌리는 점검 도구다.** Gateway 가 떠 있어야 돌고 그 결과는 사람이 본다.
dev/tools/check_resolve.py 와 같은 성격이라 그 파일의 짜임새를 따른다 — 파일 하나에
담고 저장소의 다른 곳을 건드리지 않는다.

**성공 판정을 HTTP 상태로 하지 않는다.** Gateway 전역 핸들러가 모든 오류를
500 + {"error": "Internal Server Error"} 로 덮는다. 본문을 봐야 원인이 보인다.
200 + {"error": ...} 는 실패고 200 + [] 는 0건일 뿐이다.

**user_context 를 반드시 싣는다.** 빠뜨리면 요청마다 새 guest 가 만들어지고
adminBoundary 셋 말고는 전부 거부된다(실측). demo/api/services/execute_service
의 USER_CONTEXT 를 그대로 쓴다 — 두 곳에 적으면 갈린다.

표에는 건수만 찍힌다. 배선을 적을 때는 필드 이름을 봐야 하므로 응답 전문을
dev/tools/probe_out/<도구이름>.json 으로 남긴다. probe_out 은 실측 자산이지만
응답이 커서 저장소에 담을 것이 아니라 .gitignore 에 넣었다.
"""

import argparse
import json
import os
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
from demo.api.services.execute_service import USER_CONTEXT  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

# 도구 목록. 이 저장소 밖이라 --tools 로 바꿀 수 있게 둔다.
DEFAULT_TOOLS_PATH = REPO_ROOT.parent / "KRRI_ASAP" / "tools.json"

# 화면(vendor_to_be_deleted/asap/mcp_client)이 부르는 주소와 같아야 표를 믿을 수 있다.
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:3000").rstrip("/")
EXECUTE_PATH = "/api/tools/execute"

# 도구 하나당 상한. 목록 조회 /api/tools 가 21.1초 걸린 전례가 있어 넉넉히 둔다.
TIMEOUT = 60

OUT_DIR = Path(__file__).resolve().parent / "probe_out"


# ── 인자 규칙 ────────────────────────────────────────────────────────
# required 를 채울 값을 여기 모은다. 함수 안에 흩지 않는다 — 도구가 늘 때
# 고칠 곳이 한 군데여야 한다.

# 오송역. 시연 발화가 전부 이 장소다.
OSONG_LON = 127.3277
OSONG_LAT = 36.6200
OSONG_PLACE = "오송역"

# bbox 를 오송역 좌표에서 넓히는 폭. CCTV 95건이 나온 값이다(실측).
# geocode 가 준 bbox 그대로는 0건이었다.
BBOX_PAD = 0.15

# required 이름 -> 실을 값. 여기 없는 이름은 채울 값이 없다는 뜻이다.
#
#   level · code · statId · pledgeId · url · filename 계열은 일부러 뺐다.
#   그럴듯한 값을 지어내면 표가 "없는 것을 물어서 0건" 인지 "도구가 비었는지"
#   를 못 가른다.
ARGUMENT_RULES = {
    "lon": OSONG_LON,
    "lat": OSONG_LAT,
    "minLon": round(OSONG_LON - BBOX_PAD, 4),
    "minLat": round(OSONG_LAT - BBOX_PAD, 4),
    "maxLon": round(OSONG_LON + BBOX_PAD, 4),
    "maxLat": round(OSONG_LAT + BBOX_PAD, 4),
    "query": OSONG_PLACE,
    "name": OSONG_PLACE,
    "keyword": OSONG_PLACE,
    "sectionName": OSONG_PLACE,
    "stationName": OSONG_PLACE,
}

# 인자를 만들지 않는 도구. 이름 -> 왜.
#
# 남의 플랫폼(KRRI_ASAP)의 데이터를 지우거나 고치는 도구다. 훑어보자고 누를
# 것이 아니다. required 를 채울 수 있더라도 만들지 않는다.
REFUSED_TOOLS = {
    "bim.updateModel": "모델을 고침",
    "bim.deleteModel": "모델을 지움",
    "knowledge.deleteDoc": "문서를 지움",
}


# ── 한글 폭 ──────────────────────────────────────────────────────────
# 한글은 폭이 2 라 ljust 로는 표가 어긋난다. 표 라이브러리를 쓰지 않으므로
# 여기서 직접 센다. dev/tools/check_resolve.py 와 같은 방식이다.


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


# ── 인자 ────────────────────────────────────────────────────────────


def build_arguments(tool: dict) -> tuple:
    """도구 하나를 최소 인자로 부를 값.

    입력  {name, inputSchema, ...} 하나
    출력  (인자 dict, 못 채운 이유 목록). 부를 수 있으면 이유 목록이 빔
          required 가 비었으면 ({}, [])
    규칙  ARGUMENT_RULES 에 있는 required 만 채움. 하나라도 못 채우면
          (None, [못 채운 이름들])
          REFUSED_TOOLS 에 있으면 required 를 다 채울 수 있어도 (None, [이유])
    제약  값을 지어내지 않는다. 없는 code 를 넣으면 0건의 원인이 도구인지
          인자인지 표에서 안 갈린다
    """
    refusal = REFUSED_TOOLS.get(tool.get("name"))
    if refusal:
        return None, [refusal]

    schema = tool.get("inputSchema") or {}
    required = schema.get("required") or []

    arguments, missing = {}, []
    for field in required:
        if field in ARGUMENT_RULES:
            arguments[field] = ARGUMENT_RULES[field]
        else:
            missing.append(field)

    if missing:
        return None, missing
    return arguments, []


# ── 건수 ────────────────────────────────────────────────────────────

# 건수를 셀 때 배열인지 보는 key. 앞에서부터 처음 맞는 것을 씀.
LIST_KEYS = ("features", "items", "results")

# 셀 수 없을 때 함께 남길 응답 앞토막의 길이.
PREVIEW_LENGTH = 80


def count_records(payload) -> tuple:
    """응답에서 건수를 뽑음.

    입력  파싱한 응답 본문. dict 일 수도 list 일 수도 있음
    출력  (건수, 미리보기). 셀 수 있으면 (int, "")
          못 세면 ("?", 응답 앞 80자)
    규칙  순서대로 봄. 도구마다 응답 모양이 다름
            count · totalMatches 가 있으면 그 값
            features · items · results 가 배열이면 그 길이
            최상위가 배열이면 그 길이
            객체 하나면 1
    제약  도구가 늘면 여기만 고친다. 세는 규칙을 부르는 쪽에 흩지 않는다
    """
    if isinstance(payload, list):
        return len(payload), ""

    if isinstance(payload, dict):
        for key in ("count", "totalMatches"):
            value = payload.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value, ""
        for key in LIST_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                return len(value), ""
        return 1, ""

    return "?", _preview(payload)


def _preview(payload) -> str:
    """응답 앞토막. 건수를 못 셌을 때 무엇이 왔는지 남기려고 씀."""
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return text[:PREVIEW_LENGTH]


# 응답에서 0건의 이유를 찾을 때 보는 key. Gateway 가 warning 에 사유를 적는다.
WARNING_KEYS = ("warning", "warnings", "message", "note")


def find_warning(payload) -> str:
    """응답에 실린 안내 문장. 0건의 이유가 여기 있음.

    입력  파싱한 응답 본문
    출력  찾은 문장. 없으면 ""
    규칙  최상위만 봄. 리스트면 첫 항목을 이어 붙임
    """
    if not isinstance(payload, dict):
        return ""
    for key in WARNING_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value:
            return " / ".join(str(item) for item in value[:2])
    return ""


def find_error(payload) -> str:
    """응답에 실린 오류 메시지. 있으면 실패임.

    입력  파싱한 응답 본문
    출력  오류 메시지. 없으면 ""
    규칙  HTTP 상태를 보지 않음. Gateway 전역 핸들러가 모든 오류를 500 +
          고정 문구로 덮으므로 본문의 error 만이 근거임
          error 가 dict 면 message · detail 을 먼저 봄
    """
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if not error:
        return ""
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        for key in ("message", "detail", "code"):
            value = error.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return json.dumps(error, ensure_ascii=False, default=str)[:PREVIEW_LENGTH]


# ── 호출 ────────────────────────────────────────────────────────────

# 표에 찍는 상태 넷.
DATA = "데이터"
EMPTY = "빈 결과"
FAILED = "실패"
NO_ARGUMENT = "인자 없음"

STATUS_ORDER = (DATA, EMPTY, FAILED, NO_ARGUMENT)


class GatewayDown(RuntimeError):
    """Gateway 에 닿지 못했다. 재시도하지 않고 즉시 멈춘다."""


def _probe(tool: dict, timeout: int = TIMEOUT) -> dict:
    """도구 하나를 한 번 부름.

    입력  {name, inputSchema, ...} 하나 · 상한 초
    출력  {name, status, count, note, payload}. payload 는 안 불렀으면 None
    규칙  인자를 못 만들면 부르지 않고 NO_ARGUMENT 로 돌려줌
          Gateway 에 못 닿으면 GatewayDown. 재시도하지 않음
          응답이 JSON 이 아니면 실패. 본문 앞토막을 note 에 남김
    """
    name = tool["name"]
    arguments, missing = build_arguments(tool)
    if arguments is None:
        return {
            "name": name,
            "status": NO_ARGUMENT,
            "count": "-",
            "note": ", ".join(missing),
            "payload": None,
        }

    # vendor_to_be_deleted/asap/mcp_client.execute_tool 이 만드는 본문과 같은 모양임.
    # 도구 이름은 tool, 인자는 input 이고 user_context 와 server_id 는 그 옆에
    # 따로 얹음. toolName/arguments 로 보내면 42개가 전부
    # "Tool name is required" 로 실패함(실측).
    #
    # 실행기가 지나는 창구를 흉내 내는 것이 이 도구의 전부임. 본문 모양이
    # 갈리면 여기서 되는 것이 화면에서 안 되고, 그것을 표로는 못 알아봄.
    body = {
        "tool": name,
        "input": arguments,
        "user_context": dict(USER_CONTEXT),
    }
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
        return {
            "name": name,
            "status": FAILED,
            "count": "-",
            "note": f"{timeout}초 안에 답이 없음",
            "payload": None,
        }

    try:
        payload = response.json()
    except ValueError:
        return {
            "name": name,
            "status": FAILED,
            "count": "-",
            "note": f"JSON 이 아님 (HTTP {response.status_code}) : {response.text[:PREVIEW_LENGTH]}",
            "payload": None,
        }

    error = find_error(payload)
    if error:
        return {
            "name": name,
            "status": FAILED,
            "count": "-",
            "note": error,
            "payload": payload,
        }

    count, preview = count_records(payload)
    warning = find_warning(payload)
    if count == 0:
        status, note = EMPTY, warning
    elif count == "?":
        status, note = DATA, warning or preview
    else:
        status, note = DATA, warning

    return {
        "name": name,
        "status": status,
        "count": str(count),
        "note": note,
        "payload": payload,
    }


def _save(name: str, payload) -> None:
    """응답 전문을 dev/tools/probe_out/<도구이름>.json 으로 남김.

    규칙  표에는 건수만 찍힘. 배선을 적을 때는 필드 이름을 봐야 함
          안 부른 도구(payload None)는 남기지 않음
    """
    if payload is None:
        return
    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / f"{name}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


# ── 표 ──────────────────────────────────────────────────────────────

NAME_WIDTH = 42
STATUS_WIDTH = 12
COUNT_WIDTH = 8
NOTE_WIDTH = 60


def _print_table(results: list) -> None:
    """도구 이름 · 상태 · 건수 · 비고. 맨 아래에 상태 넷의 개수."""
    print()
    print(
        "  "
        + _pad("도구", NAME_WIDTH)
        + _pad("상태", STATUS_WIDTH)
        + _pad("건수", COUNT_WIDTH)
        + "비고"
    )

    for result in results:
        print(
            "  "
            + _pad(_clip(result["name"], NAME_WIDTH - 2), NAME_WIDTH)
            + _pad(result["status"], STATUS_WIDTH)
            + _pad(result["count"], COUNT_WIDTH)
            + _clip(result["note"], NOTE_WIDTH)
        )

    tally = Counter(result["status"] for result in results)
    print("  " + "─" * (NAME_WIDTH + STATUS_WIDTH + COUNT_WIDTH + 20))
    print(
        "  "
        + _pad(f"도구 {len(results)}개", NAME_WIDTH)
        + " · ".join(f"{status} {tally.get(status, 0)}" for status in STATUS_ORDER)
    )


# ── 목록 ────────────────────────────────────────────────────────────


def load_tools(path: Path) -> list:
    """도구 목록을 읽음.

    입력  tools.json 경로
    출력  [{name, description, inputSchema, ...}, ...]
    규칙  최상위가 배열이면 그대로. {"tools": [...]} 면 그 안을 씀
    제약  없으면 FileNotFoundError 를 그대로 올린다. 부르는 쪽이 무엇이
          없는지 사람에게 말하고 멈춘다
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("tools") or []
    return [tool for tool in payload if isinstance(tool, dict) and tool.get("name")]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gateway 도구를 한 번씩 눌러 무엇이 데이터를 주는지 잰다."
    )
    parser.add_argument(
        "--tools", default=str(DEFAULT_TOOLS_PATH),
        help=f"도구 목록 json (기본 {DEFAULT_TOOLS_PATH})",
    )
    parser.add_argument("--only", default="", help="누를 도구 이름. 예: road.getCctv,geo.geocode")
    parser.add_argument("--timeout", type=int, default=TIMEOUT, help=f"도구당 상한 초 (기본 {TIMEOUT})")
    parser.add_argument("--dry-run", action="store_true", help="부르지 않고 만들어질 인자만 찍음")
    args = parser.parse_args()

    tools_path = Path(args.tools)
    if not tools_path.is_file():
        print(f"도구 목록이 없습니다 : {tools_path}")
        print("KRRI_ASAP 저장소의 tools.json 경로를 --tools 로 알려주세요.")
        return 2

    tools = load_tools(tools_path)
    if args.only:
        wanted = [part for part in args.only.replace(" ", "").split(",") if part]
        tools = [tool for tool in tools if tool["name"] in wanted]
        missing = sorted(set(wanted) - {tool["name"] for tool in tools})
        if missing:
            print(f"목록에 없는 도구 : {missing}")
            return 2

    if args.dry_run:
        return _print_dry_run(tools)

    print(f"도구 {len(tools)}개 · {GATEWAY_URL}{EXECUTE_PATH} · 도구당 {args.timeout}초")

    results, note, status = [], "", 0
    try:
        for tool in tools:
            result = _probe(tool, args.timeout)
            _save(result["name"], result.pop("payload"))
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
        _print_table(results)
        print()
        print(f"응답 전문 : {OUT_DIR}")
    if note:
        print()
        print(note)

    return status


def _print_dry_run(tools: list) -> int:
    """부르지 않고 만들어질 인자만 찍음. 인자 규칙을 고친 뒤 보는 용도."""
    print(f"도구 {len(tools)}개 · 부르지 않음")
    print()
    unfillable = []
    for tool in tools:
        arguments, missing = build_arguments(tool)
        if arguments is None:
            unfillable.append(tool["name"])
            shown = f"{NO_ARGUMENT} ({', '.join(missing)})"
        else:
            shown = json.dumps(arguments, ensure_ascii=False)
        print("  " + _pad(_clip(tool["name"], NAME_WIDTH - 2), NAME_WIDTH) + shown)
    print()
    print(f"  {NO_ARGUMENT} {len(unfillable)}개 : {', '.join(unfillable)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
