"""recipe 의 노드 사슬을 vendor 실행기가 받는 steps 배열로 바꾼다. **우리 코드다.**

**온톨로지는 무엇을 어떤 순서로 하는지만 말한다.** 그 노드가 어느 도구인지,
input 을 어떻게 채우는지는 온톨로지에 없다 — wiring.yaml 이 갖는다.
온톨로지에 도구 이름을 적으면 노드가 특정 MCP 서버에 묶여, 같은 일을 하는
도구로 갈아끼울 때 도메인을 고쳐야 한다.

    TOOL_OF   노드            -> 실행 수단 · 답 첫 줄
    STEP_OF   (노드, 받는 타입) -> input

**두 표는 wiring.yaml 이 갖고 아래 _load_wiring 이 그것을 판다.** 노드를
등록하면 recipe 는 저절로 느는데 배선은 사람이 코드에 적어야 했다. 값이 같은지
대보려고 남겨 뒀던 코드 표 두 벌은 대보고 나서 지웠다(1-b). 줄마다의 실측 근거
주석도 그때 wiring.yaml 로 갔다.
**그래도 온톨로지에는 안 넣는다** — 까닭은 바로 아래 문단 그대로다.

**실행 수단이 둘이다.** 마흔은 Gateway 의 MCP 도구를 부르고(server_id · tool),
하나는 부를 도구가 없어 지도 명령만 낸다(command). 「모든 경로가 도구로 끝난다」
는 전제가 깨지는 자리가 여기 한 곳이고, 온톨로지는 그것을 모른다 — 거기 적힌
것은 「장소 이름을 받아 시설물 화면을 내놓는다」 뿐이다. 도구 이름을 온톨로지에
안 적기로 한 규칙이 그래서 값을 한다.

**같은 노드가 두 자리에 온다.** 전기차 충전소 검색은 말한 키워드 뒤에도 오고
장소 좌표 변환 뒤에도 온다. 그때 받는 것이 query 와 center 로 달라서 노드당
한 줄로는 적을 수 없다. 그래서 STEP_OF 의 키가 (노드, 받는 타입)이고, 그
타입은 온톨로지의 hasInput 선언과 1:1 이다. 어느 줄을 쓸지는 plan 이 앞
단계가 내놓는 타입을 보고 고른다 — 타입 판정은 ontology_service 를 거친다.

**배선은 여기서 끝난다.** 앞 단계 결과를 다음 input 에 어떻게 넣을지는
vendor_to_be_deleted/asap/generic_mcp_executor 의 _resolve_reference 가 안다 — 도구별이 아니라
필드 이름별이라 도구가 늘어도 재사용된다. 우리는 $prev.location 처럼 "앞
단계의 무엇" 이라고만 적는다.

발화에서 온 값이 들어가는 자리가 @arg 다. 무엇을 뽑을지는 발화 해석 LLM 이
argument 로 함께 내놓고, 그것이 없을 때만 place_in 이 장소 하나를 뽑는다.
"""

import re

import yaml

import paths
from demo.api.services import ontology_service

SERVER_ID = "asap-mcp-core"

# web.search · web.fetch 만 다른 MCP 서버에 있다. 나머지 마흔은 SERVER_ID 다.
# 여기를 틀리면 Gateway 가 도구를 못 찾는다 — tools.json 의 serverId 가 근거다.
WEB_SERVER_ID = "web-search"

# 좌표 하나를 지도 범위로 넓힐 때의 반경. road.getCctv 와 ev.searchStations 가
# 같은 값을 쓴다. vendor 의 point_radius_to_bbox 어댑터가
# 중심 좌표와 이 값으로 bbox 를 만든다 — 대상 도구의 required 에 bbox 넷이
# 있으면 저절로 걸리고, 아니면 단계에 adapter 를 적어야 걸린다.
#
# 어제 geocode bbox 에 ±0.15도를 더해 95건이 나왔고 그것이 대략 15km 다.
# 이 값으로는 오송역 83건이 나왔다(실측). 어댑터가 위도를 보정하기 때문에
# 세로가 ±0.1347도로 좁아진다 — ±0.15도로 네 변을 똑같이 넓히던 것과 다르다.
RADIUS_METERS = 15000

# 발화에서 온 값을 가리키는 표시. 하나뿐이다.
#
# 예전 이름은 @place 였다. 키워드를 받는 도구(search_documents ·
# search_election_districts)도 같은 자리에 발화에서 온 값을 넣으므로 표시가
# "장소" 를 뜻하면 안 된다. 그 값이 장소인지 키워드인지 식별자인지는 발화 해석
# 응답의 given 이 말한다 — 여기는 그것을 구분하지 않는다.
SPOKEN_VALUE = "@arg"

# 발화에서 온 값이 노선 이름인지 가르는 어미.
#
# 규칙  "…선" 으로 끝나면 노선 이름. 아니면 지금 그대로 역 이름
# 한계  "1호선" 처럼 두 칸 다 답이 있는 값도 노선 쪽으로 간다.
#       "…선" 도 "…역" 도 아닌 값("청주")은 역 이름 자리에 그대로 남는다.
#       실측 표와 언제 이 자를 걷어내는지는 NOTES.md 「쉰째」에 있다
RAILWAY_LINE_SUFFIX = "선"

# 지도 명령 하나가 곧 실행인 자리의 op 이름.
#
# 저쪽 화면이 이 op 을 이름으로 알아본다 — KRRI_ASAP/ASAP-web 의
# useChat.isDigitalTwinFacilityCommand 가 `cmd.op === 'digitalTwin.showFacility'`
# 로 가르고 args.facilityName 을 문자열일 때만 읽는다. 저쪽 orchestrator 의
# market_plugin_engine._show_facility 도 같은 op 과 같은 칸으로 만든다.
# 두 파일 다 읽기만 했다.
SHOW_FACILITY_COMMAND = "digitalTwin.showFacility"

# 앞 단계를 가리키는 표시. 실제 step id 로 바꿔서 vendor 에 넘긴다.
PREVIOUS_STEP = "$prev"

# 앞 단계의 지도 범위를 받는 두 모양. 여러 줄이 똑같이 쓰므로 상수로 둔다 —
# 줄마다 베껴 적으면 한 곳만 고쳤을 때 조용히 어긋난다.
#
# vendor 의 _resolve_reference 가 minLon · minLat · maxLon · maxLat 를
# 앞 단계 bbox 의 [0][0] · [0][1] · [1][0] · [1][1] 로 푼다. geocode 도
# rail.getSectionGeometry 도 bbox 를 [[minLon, minLat], [maxLon, maxLat]] 로
# 내놓으므로 같은 표시가 둘 다에 걸린다.
#
# 받는 쪽 모양은 도구마다 다르다. road.getCctv 는 네 칸을 따로 받고
# (required 넷), 나머지는 bbox 한 칸에 평평한 네 수를 받는다
# ("[minLon, minLat, maxLon, maxLat] 조회 범위", tools.json).
BBOX_FROM_PREVIOUS = [
    f"{PREVIOUS_STEP}.minLon",
    f"{PREVIOUS_STEP}.minLat",
    f"{PREVIOUS_STEP}.maxLon",
    f"{PREVIOUS_STEP}.maxLat",
]

# 앞 단계의 지점 좌표를 받는 모양. find…ByPoint 다섯이 똑같이 쓴다.
POINT_FROM_PREVIOUS = {"lon": f"{PREVIOUS_STEP}.lon", "lat": f"{PREVIOUS_STEP}.lat"}

# 저쪽 화면이 발화와 함께 보내는 지도 문맥을 가리키는 표시.
#
# **@arg 도 $prev 도 아닌 셋째 자리다.** @arg 는 사람이 입으로 말한 값이고
# $prev 는 앞 단계가 내놓은 값인데, 이것은 사람이 아무 값도 말하지 않았는데
# 화면이 함께 보내온 값이다.
#
# **_filled 이 이 표시를 안 바꾼다. 바꿀 것이 없다.** vendor 의
# _build_resolution_scope 가 state["context"] 를 그대로 scope["context"] 에
# 얹고 _resolve_reference 가 "$context.…" 를 그 자리에서 푼다. 우리가 여기서
# 값을 채우면 같은 일을 두 곳이 하게 되고, 문맥이 빈 요청에서 어느 쪽이
# 비운 것인지 알 수 없어진다.
CONTEXT_VALUE = "$context"

# 문맥의 찍은 지점. 저쪽 ChatRequest.context.selectedLocation 이다
# ({lon, lat, label, source}. source 는 "map-right-click").
#
# 통째로 넘긴다. vendor 의 _parse_lon_lat 이 dict 에서 lon · lat 을 꺼내므로
# 칸 이름을 우리가 다시 적을 필요가 없다.
SELECTED_LOCATION = f"{CONTEXT_VALUE}.selectedLocation"

# 문맥의 찍은 지점을 lon · lat 두 칸으로. find…ByPoint 다섯이 그 모양으로 받는다.
POINT_FROM_CONTEXT = {
    "lon": f"{SELECTED_LOCATION}.lon",
    "lat": f"{SELECTED_LOCATION}.lat",
}

# 문맥의 보이는 범위. 저쪽 ChatRequest.context.view.bbox 이고
# [[minLon, minLat], [maxLon, maxLat]] 두 겹이다 (2026-08-28 확인 —
# KRRI_ASAP/ASAP-web 의 CameraManager.getMapContext 와 MapLibre2DMap.getMapContext
# 가 둘 다 [[west, south], [east, north]] 로 만든다).
#
# **$prev 의 bbox 와 모양이 같다.** 그래서 BBOX_FROM_PREVIOUS 와 같은 네 이름을
# 쓴다 — vendor 의 _resolve_reference 가 minLon 을 bbox[0][0] 로 푸는 규칙이
# 앞 단계 결과든 문맥이든 한 벌이다.
VIEW_FROM_CONTEXT = f"{CONTEXT_VALUE}.view"
BBOX_FROM_CONTEXT = [
    f"{VIEW_FROM_CONTEXT}.minLon",
    f"{VIEW_FROM_CONTEXT}.minLat",
    f"{VIEW_FROM_CONTEXT}.maxLon",
    f"{VIEW_FROM_CONTEXT}.maxLat",
]

# 문맥의 어느 칸이 어느 시작 데이터 노드인가. **온톨로지 밖이다** —
# 저쪽 화면의 계약이라 온톨로지가 알 일이 아니고, TOOL_OF · STEP_OF 와 같은
# 자리에 둔다. key 는 온톨로지의 데이터 노드 id 이고 축 선택지와 같은 값이다
# (execute_service.NO_ARGUMENT_ANSWER 가 같은 방식이다).
CONTEXT_STARTS = {
    "picked_point": ("selectedLocation",),
    "visible_extent": ("view", "bbox"),
}

# 앞 단계의 행정구역을 층위와 코드로 받는 모양. population 두 도구가 똑같이 쓴다.
#
# adminBoundary.findBoundaryByPoint 가 여덟 지점에서 늘 items 3건을
# sido -> sigungu -> emd 순서로 내놓고(2026-08-24 실측, 응답 전문은
# dev/tools/probe_out/), items.N.layerId 의 낱말이 population 두 도구의 level
# enum 과 글자까지 같다 (ASAP-mcp/main.py:402).
#
# **items.1 은 시군구다. 지금은 시군구 한 자리로 박는다.** 발화가 시도를
# 말했는지 읍면동을 말했는지는 이 자리에서 알 수 없다 — 발화 해석이 층위를
# 함께 내놓지 않는다. NOTES.md 「열린 과제」에 남겼다.
ADMIN_LEVEL_FROM_PREVIOUS = {
    "level": f"{PREVIOUS_STEP}.items.1.layerId",
    "code": f"{PREVIOUS_STEP}.items.1.code",
}

# 중심 좌표와 반경을 bbox 넷으로 바꾸는 vendor 어댑터의 이름.
#
# road.getCctv 는 bbox 넷이 전부 required 라 vendor 가 저절로 건다.
# ev.searchStations 는 넷 다 optional 이라 안 걸린다 —
# 그래서 그 단계에만 이 이름을 적는다.
POINT_RADIUS_TO_BBOX = "point_radius_to_bbox"

# point_radius_to_bbox 가 중심 좌표를 찾는 칸 이름. vendor 의
# _extract_center_point 가 보는 것과 같은 순서 · 같은 이름이다.
#
# 이 중 하나도 안 남으면 어댑터가 ValueError 를 올린다("point_radius_to_bbox에는
# center/location 좌표가 필요합니다"). 그래서 plan 이 어댑터를 걸기 전에 본다.
CENTER_KEYS = ("center", "point", "coordinate", "coordinates", "location")

# _filled 이 "이 칸은 채울 수 없으니 안 보낸다" 를 알리는 표시.
#
# None 을 쓰지 않는다. None 은 도구가 받는 값일 수 있어 "빼라" 와 "null 을
# 보내라" 가 안 갈린다.
DROP = object()


# ── 배선표를 파일에서 읽는다 ──────────────────────────────────────

# YAML 이 "<이름>" 이라고만 적고 값은 여기 두는 것들.
#
# **왜 값을 안 옮겼나.** 옮기면 원천이 둘이 된다 — RADIUS_METERS 는 배선표
# 말고 demo/ui/config.py 도 쓰고, POINT_RADIUS_TO_BBOX 는 vendor 어댑터의
# 이름이라 저쪽이 주인이고, RAILWAY_LINE_SUFFIX 는 값 판단의 자라 그 뜻과
# 한계가 코드(상수 옆 주석)에 있어야 한다.
#
# DROP 은 여기 없다. 표에 오는 값이 아니라 _filled 이 "이 칸은 못 채운다" 를
# 알리려고 만드는 표시라 YAML 이 적을 자리가 없다.
_SYMBOLS = {
    "RADIUS_METERS": RADIUS_METERS,
    "POINT_RADIUS_TO_BBOX": POINT_RADIUS_TO_BBOX,
    "RAILWAY_LINE_SUFFIX": RAILWAY_LINE_SUFFIX,
}

_SYMBOL_PATTERN = re.compile(r"^<([A-Z][A-Z0-9_]*)>$")

# YAML 의 한 절 이름. 여기 없는 절이 오면 터진다 — 오타 난 절은 조용히 빈 표가
# 되고, 그것이 「계기판이 조용히 죽는다」의 모양이다.
_SECTIONS = ("anchors", "tool_of", "step_of")

# 배선 한 줄이 가질 수 있는 칸. input_frist 같은 오타가 조용히 넘어가면 화면
# 문맥에서 시작하는 자리가 소리 없이 사라진다.
_WIRING_FIELDS = ("input", "input_first", "adapter", "arg_field")

# **밖에서 넷이 이 두 이름을 import 한다** — dev/tools/check_wiring.py ·
# dev/tools/check_inputs.py · vendor_to_be_deleted/asap/workflow_answer.py · 시험들.
# 그래서 다시 읽을 때 객체를 갈아 끼우지 않고 **같은 dict 를 비우고 다시
# 채운다.** 먼저 import 해 간 쪽이 옛 객체를 쥐면 조용히 어긋난다.
TOOL_OF: dict = {}
STEP_OF: dict = {}

_wiring_mtime = None


def _resolved(value):
    """YAML 조각의 "<이름>" 을 코드의 값으로. 중첩된 것까지.

    입력  yaml.safe_load 가 낸 조각
    출력  같은 모양에 표시만 바뀐 것
    규칙  어절 전체가 "<이름>" 일 때만 바꿈. 문자열 안에 섞어 쓰지 않음 —
          값의 타입이 바뀜(RADIUS_METERS 는 수다)
    제약  모르는 이름을 조용히 넘기지 않는다.
          그대로 두면 "<RADIUS_METERS>" 라는 문자열이 도구에 그대로 실려
          나가고, 0건이 오지 오류가 오지 않는다
    """
    if isinstance(value, dict):
        return {key: _resolved(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolved(item) for item in value]
    if isinstance(value, str):
        match = _SYMBOL_PATTERN.fullmatch(value)
        if match:
            name = match.group(1)
            if name not in _SYMBOLS:
                raise ValueError(f"{paths.WIRING_PATH.name}: 모르는 이름 <{name}>")
            return _SYMBOLS[name]
    return value


def _wiring_row(node_id: str, type_id: str, row) -> dict:
    """YAML 의 배선 한 줄을 표에 넣을 모양으로.

    입력  노드 id · 받는 타입 id · 그 줄
    출력  STEP_OF 의 값 하나
    규칙  arg_field 는 (어미, 칸 이름) 짝임. YAML 목록으로 오므로 튜플로 바꿈 —
          _by_argument 가 짝으로 풀고, 옛 표와 값까지 같아야 함
    제약  모르는 칸 이름에서 터진다
    """
    if not isinstance(row, dict):
        raise ValueError(f"{paths.WIRING_PATH.name}: {node_id} × {type_id} 이 dict 가 아니다")

    unknown = [key for key in row if key not in _WIRING_FIELDS]
    if unknown:
        raise ValueError(f"{paths.WIRING_PATH.name}: {node_id} × {type_id} 에 모르는 칸 {unknown}")
    if "input" not in row:
        raise ValueError(f"{paths.WIRING_PATH.name}: {node_id} × {type_id} 에 input 이 없다")

    wiring = _resolved(row)
    if "arg_field" in wiring:
        wiring["arg_field"] = tuple(wiring["arg_field"])
    return wiring


def _load_wiring() -> None:
    """wiring.yaml 을 파서 TOOL_OF · STEP_OF 를 채움.

    규칙  step_of 는 두 겹임(노드 -> 받는 타입 -> 줄). 그 둘을 짝 키로 묶음.
          YAML 은 짝을 키로 쓸 수 없어 파일에서만 두 겹임
          파일 차례를 그대로 지킴. 계기판이 STEP_OF 를 순서대로 찍음
    제약  두 표를 다 만든 뒤에 갈아 넣는다.
          중간에 터지면 반만 바뀐 표가 남고, 그것은 빈 표보다 나쁘다
          객체를 새로 만들지 않는다. 먼저 import 해 간 쪽이 옛 dict 를 쥔다
    """
    document = yaml.safe_load(paths.WIRING_PATH.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{paths.WIRING_PATH.name}: 최상위가 dict 가 아니다")

    unknown = [key for key in document if key not in _SECTIONS]
    if unknown:
        raise ValueError(f"{paths.WIRING_PATH.name}: 모르는 절 {unknown}")
    for section in ("tool_of", "step_of"):
        if not isinstance(document.get(section), dict):
            raise ValueError(f"{paths.WIRING_PATH.name}: {section} 절이 없다")

    tool_of = _resolved(document["tool_of"])

    step_of = {}
    for node_id, by_type in document["step_of"].items():
        if not isinstance(by_type, dict):
            raise ValueError(f"{paths.WIRING_PATH.name}: {node_id} 아래가 dict 가 아니다")
        for type_id, row in by_type.items():
            step_of[(node_id, type_id)] = _wiring_row(node_id, type_id, row)

    TOOL_OF.clear()
    TOOL_OF.update(tool_of)
    STEP_OF.clear()
    STEP_OF.update(step_of)


def reload_wiring() -> None:
    """파일이 바뀌었으면 다시 판다.

    규칙  mtime 이 그대로면 아무것도 안 함. 요청마다 파일을 통째로 파지 않음
          등록 화면이 wiring.yaml 을 쓰면 서버를 안 내리고 반영되어야 함
    제약  판정이 끝난 뒤에 mtime 을 적는다.
          터진 파일에 mtime 만 먼저 적으면 다음 요청이 「안 바뀌었다」고 보고
          조용히 옛 표로 돈다
          경로 하나를 만드는 도중에는 안 부른다. plan 이 도는 사이에 표가
          갈리면 앞 단계와 뒷 단계가 다른 배선을 쓴다
    """
    global _wiring_mtime

    mtime = paths.WIRING_PATH.stat().st_mtime_ns
    if mtime == _wiring_mtime:
        return

    _load_wiring()
    _wiring_mtime = mtime


# import 하는 때에 한 번 판다. 계기판 넷은 TOOL_OF · STEP_OF 를 import 해서
# 곧장 읽을 뿐 아무 함수도 안 부른다 — 여기서 안 채우면 빈 표를 본다.
reload_wiring()


# 장소로 볼 어절의 끝 글자.
PLACE_SUFFIXES = "역시군구읍면동리"

# 한글 어절 하나가 통째로 장소인지 본다.
#
# **LLM 을 쓰지 않는다. 대비책이다.** 인자는 이제 발화 해석 LLM 이 argument 로
# 함께 내놓고, 이 정규식은 그것이 null 로 올 때만 돈다.
#
# 못 잡는 것 : "충북대 근처" · "청주 시내" 처럼 끝 글자가 다른 곳,
#              "오송역의" 처럼 조사가 붙은 어절, "서울에서 대전까지" 의 둘 중 하나.
# 잘못 잡는 것 : "알려주시" 같은 어절도 형태가 같다. 실제 발화에서는 드물다.
# 지우지 않는 이유 : LLM 이 흔들리거나 argument 를 빠뜨렸을 때 장소 발화만은
#                    여전히 돌아야 한다. 뽑는 값도 이름도 예전 그대로다.
PLACE_PATTERN = re.compile(f"[가-힣]{{2,}}[{PLACE_SUFFIXES}]")


def place_in(text: str) -> str | None:
    """발화에서 장소 하나.

    입력  사용자 발화
    출력  첫 번째로 걸린 어절. 없으면 None
    규칙  어절 전체가 걸려야 함. "보여줘" 처럼 일부만 맞는 것은 안 봄
          여러 개면 첫 번째. 발화가 "서울에서 대전까지" 인 recipe 는 아직 없음
    이력  예전에는 인자를 뽑는 유일한 자리였음. 발화 해석 LLM 이 argument 를
          함께 내주게 되어 지금은 대비책임. 그 값이 null 일 때만 부름
    """
    for word in str(text or "").split():
        if PLACE_PATTERN.fullmatch(word):
            return word
    return None


def context_starts(context: dict | None) -> list[str]:
    """지금 문맥이 값을 줄 수 있는 시작 데이터 노드.

    입력  저쪽 화면이 보낸 context. 없거나 dict 가 아니면 빈 것으로 봄
    출력  노드 id 목록. CONTEXT_STARTS 에 적힌 차례
    규칙  칸이 있고 비어 있지 않아야 셈. selectedLocation 이 null 로 오는
          것이 저쪽의 평상시 모양임 (우클릭을 안 했을 때)
          bbox 는 두 겹 목록이라 빈 목록도 없는 것으로 셈
    제약  값이 좌표로 쓸 만한지 여기서 보지 않는다.
          범위를 재는 것은 vendor 의 _parse_lon_lat 이고, 여기가 또 재면
          두 곳이 다른 기준을 갖게 됨
    """
    found = []
    for node_id, path in CONTEXT_STARTS.items():
        value = context if isinstance(context, dict) else None
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if value not in (None, "", [], {}):
            found.append(node_id)
    return found


def wiring_at(node_id: str, source_id: str) -> dict | None:
    """그 자리에서 쓸 배선 한 줄.

    입력  부를 노드 id · 그 앞에 선 노드 id. 앞이 실행 노드일 수도 있고
          경로의 첫 칸인 데이터 노드일 수도 있음
    출력  STEP_OF 의 한 줄. 맞는 줄이 없으면 None
    규칙  앞 노드가 건네는 타입을 순서대로 보고 먼저 걸리는 줄을 씀.
          그 순서가 온톨로지에 적힌 hasOutput 순서임
          둘 이상 맞으면 앞 노드가 먼저 내놓는 것을 씀. 장소 좌표 변환은
          지점 좌표를 먼저 내놓으므로 CCTV 조회가 좌표 줄을 씀
          데이터 노드가 앞이면 그것이 is-a 로 가리키는 타입을 봄.
          말한 식별자는 선거구 코드 하나를 가리킴
    제약  온톨로지를 직접 읽지 않는다. 타입 판정은 ontology_service 가 함
    """
    for type_id in ontology_service.handed_types(source_id):
        wiring = STEP_OF.get((node_id, type_id))
        if wiring is not None:
            return wiring
    return None


def input_of(wiring: dict, first: bool) -> dict:
    """그 줄이 이 자리에서 쓸 input.

    입력  STEP_OF 한 줄 · 이것이 첫 step 인지
    출력  input 한 벌. 아직 @arg 와 $prev 가 그대로 들어 있음
    규칙  첫 step 이고 input_first 가 적혀 있으면 그것을 씀. 같은 타입을
          앞 단계에서 받을 수도 화면 문맥에서 받을 수도 있는 자리를 위한 것임
          지도 범위 · 지점 좌표를 받는 열다섯 줄이 그것을 적었음. 첫 자리에
          서는 앞 노드는 보이는 범위 · 찍은 지점 둘뿐이라 그 벌이 곧
          "문맥에서 온 값" 임
    이력  한동안 이것을 적은 줄이 하나도 없었음. 마지막이 충전소 상세 조회였고
          `말한 식별자 is-a 충전소 번호` 를 떼면서 사라졌음(2026-08-26).
          2026-08-28 에 화면 문맥이 들어오면서 다시 쓰임
    """
    if first and "input_first" in wiring:
        return wiring["input_first"]
    return wiring["input"]


def unwired(recipe_id: str) -> list[str]:
    """아직 배선이 안 붙은 노드.

    입력  recipe id
    출력  맞는 배선 줄이 없는 실행 노드 id 목록. 경로 순서. 전부 있으면 빈 목록
    규칙  실행 노드만 셈. 데이터 노드는 부를 것이 없어 세지 않음
          노드가 STEP_OF 에 있어도 이 자리에서 받는 타입에 줄이 없으면 셈.
          배선은 이제 (노드, 받는 타입)마다 있고 자리마다 갈림
          부르는 쪽(execute_service.run)이 비어 있지 않으면 도구를 하나도
          안 부름. 배선을 안 적은 자리와 그 이유는 wiring.yaml 의 step_of
          아래 주석에 있음
          부르기 전에 wiring.yaml 이 바뀌었으면 다시 읽음
    """
    reload_wiring()

    executable = set(ontology_service.executable_in(recipe_id))

    missing, source_id = [], None
    for entry in ontology_service.path_of(recipe_id):
        node_id = entry["node_id"]
        if (
            source_id is not None
            and node_id in executable
            and wiring_at(node_id, source_id) is None
        ):
            missing.append(node_id)
        source_id = node_id
    return missing


def plan(recipe_id: str, argument: str) -> dict:
    """recipe 한 벌을 vendor 가 받는 실행 계획으로.

    입력  recipe id · 발화에서 뽑은 인자. 장소일 수도 키워드일 수도 식별자일
          수도 있음. 어느 것인지는 여기서 안 가름
    출력  steps  vendor 의 intent["steps"] 에 그대로 들어갈 배열
          nodes  steps 와 같은 길이. steps[i] 를 만든 노드 id
          commands  도구를 안 부르고 곧장 내는 지도 명령
          command_nodes  commands 와 같은 길이. commands[i] 를 만든 노드 id
          headline  답의 첫 줄. 경로의 마지막 실행 노드가 정함
    규칙  step id 는 s1 · s2 … 로 붙음. $prev 를 앞 step 의 id 로 바꿈
          배선 줄에 command 가 적힌 노드는 step 이 아니라 지도 명령이 됨.
          그 노드는 부를 도구가 없음
          지도 명령을 낸 노드는 previous_id 를 안 바꿈. vendor 에 넘어간
          step 이 없어 $prev 로 가리킬 것이 없음
          어느 배선 줄을 쓸지는 앞 노드가 건네는 타입이 정함. wiring_at 이 그것임
          맞는 줄이 없는 노드는 step 을 만들지 않음. 데이터 노드
          (spoken_place)도 값을 준비할 뿐 부를 것이 없어 빠짐
          adapter 가 적힌 줄만 step 에 inputAdapter 칸이 생김. 없는 것은
          vendor 가 도구 스키마를 보고 스스로 정함
          arg_field 가 적힌 줄은 발화에서 온 값을 보고 칸 이름이 갈림.
          _by_argument 가 그것임
          앞 단계가 없어 중심 좌표 칸이 빠졌으면 inputAdapter 도 안 실음.
          걸 것이 없는데 걸면 vendor 어댑터가 ValueError 를 올림
          실행 노드가 빠져 반쪽으로 도는 것은 부르기 전에 unwired 가 막음
          맨 앞에서 한 번만 wiring.yaml 을 다시 읽음. 경로를 만드는 도중에
          표가 갈리면 앞 단계와 뒷 단계가 다른 배선을 씀
    제약  첫 step 의 input 에 $prev 를 쓸 수는 있으나 그 칸은 빠진 채로 나간다.
          required 인 칸이면 도구가 거부하고 그것은 배선이 틀린 것이다
    이력  예전에는 배선이 노드당 한 줄이었고 첫 step 이 $prev 를 가리키면
          _filled 이 그 칸을 빼고 불렀음. recipe 012 · 013 이 그것에 걸려
          발화에서 온 값을 버리고 전국을 검색했음. 이제 그 자리는 키워드 줄이
          걸림. _filled 의 이력 절 참고
    """
    reload_wiring()

    steps: list[dict] = []
    nodes: list[str] = []
    commands: list[dict] = []
    command_nodes: list[str] = []
    headline = ""
    previous_id = None
    source_id = None

    for entry in ontology_service.path_of(recipe_id):
        node_id = entry["node_id"]
        wiring = wiring_at(node_id, source_id) if source_id is not None else None
        source_id = node_id
        if wiring is None:
            continue

        tool = TOOL_OF[node_id]
        filled = _filled(
            _by_argument(wiring, input_of(wiring, first=previous_id is None), argument),
            argument,
            previous_id,
        )
        headline = _headline(tool["headline"], argument)

        if "command" in tool:
            commands.append({"op": tool["command"], "args": filled})
            command_nodes.append(node_id)
            continue

        step_id = f"s{len(steps) + 1}"
        step = {
            "id": step_id,
            "server_id": tool["server_id"],
            "tool": tool["tool"],
            "input": filled,
        }
        if wiring.get("adapter") and _has_center(step["input"]):
            step["inputAdapter"] = wiring["adapter"]
        steps.append(step)
        nodes.append(node_id)
        previous_id = step_id

    return {
        "steps": steps,
        "nodes": nodes,
        "commands": commands,
        "command_nodes": command_nodes,
        "headline": headline,
    }


def _by_argument(wiring: dict, tool_input: dict, argument: str) -> dict:
    """발화에서 온 값을 보고 @arg 가 든 칸의 이름을 고름.

    입력  STEP_OF 한 줄 · 그 줄이 이 자리에서 쓸 input · 발화에서 뽑은 인자
    출력  칸 이름만 갈린 input. arg_field 가 없는 줄은 받은 것 그대로
    규칙  arg_field 는 (어미, 그 어미일 때 쓸 칸 이름) 한 쌍임
          값이 그 어미로 끝날 때만 바꿈. 아니면 적힌 칸 이름 그대로임
          바꾸는 것은 @arg 가 든 칸 하나뿐임. 다른 칸은 안 건드림
          인자가 비면 어떤 어미로도 안 끝나므로 안 바뀜
    제약  값을 고치지 않는다. 칸 이름만 고른다.
          어느 칸이 맞는지는 도구가 아는 것이고 여기는 짐작한다 —
          짐작이 틀리면 0건이 나오지 도구가 오류를 내지 않는다
          자를 넓히지 않는다. "…선" 하나이고 그 한계는 상수 옆에 적혀 있다
    이력  철도 노선 조회가 노선 이름을 stationName 으로 보내 0건이었음
          (2026-08-26 화면 실측). 온톨로지가 「말한 장소」 하나로 역 이름과
          노선 이름을 함께 담아 줄이 안 갈렸음. 타입을 새로 만드는 길과
          견주어 이쪽을 골랐음 — NOTES.md 「쉰째」
    """
    rule = wiring.get("arg_field")
    if rule is None:
        return tool_input

    suffix, field = rule
    if not str(argument or "").endswith(suffix):
        return tool_input

    return {
        (field if value == SPOKEN_VALUE else key): value
        for key, value in tool_input.items()
    }


def _headline(template: str, argument: str) -> str:
    """답의 첫 줄. 인자가 이미 문장 안에 있으면 앞에 안 붙임.

    입력  TOOL_OF 의 headline 틀 · 발화에서 뽑은 인자
    출력  채운 문장
    규칙  틀은 전부 "{arg} …" 꼴이라 인자가 문장 앞에 붙음. 뒤 문장이 인자로
          시작하면 같은 말이 두 번 나감
          겹침은 앞머리 일치로 봄. 인자가 붙는 자리가 앞이라 앞에서만
          더듬거림
          겹치면 인자를 빼고 뒤 문장만. 인자가 비어도 마찬가지임
    제약  TOOL_OF 48줄을 고치지 않는다.
          겹치는 것은 한 줄이 아니라 「인자 + 도구 이름」이 만나는 자리다.
          줄마다 고치면 발화가 바뀔 때 또 겹친다
    이력  "전기차 충전소 데이터 검색해줘" 가 "전기차 충전소 전기차 충전소를
          조회했습니다." 로 나갔음. 틀이 "{arg} 전기차 충전소를 조회했습니다."
          이고 인자도 "전기차 충전소" 였음 (2026-08-25 화면 실측).
          포함(substring)으로 보면 "역" 같은 짧은 인자가 "국회의원 지역구"
          안에 걸려 멀쩡한 인자까지 빠짐. 앞머리로 좁혔음
    """
    rest = template.format(arg="").strip()
    if not argument or rest.startswith(argument):
        return rest
    return template.format(arg=argument)


def _has_center(tool_input: dict) -> bool:
    """point_radius_to_bbox 가 걸 중심 좌표가 input 에 남았는지.

    입력  _filled 을 지난 step 의 input
    출력  CENTER_KEYS 중 하나라도 있으면 True
    규칙  값이 무엇인지는 안 봄. 여기 있는 값은 좌표 아니면 $s1.location 처럼
          vendor 가 나중에 푸는 참조라 지금 판정할 수 없음
    """
    return any(key in tool_input for key in CENTER_KEYS)


def _filled(value, argument: str, previous_id: str | None):
    """input 안의 @arg 와 $prev 를 실제 값으로. 중첩된 것까지.

    입력  input 조각 · 발화에서 뽑은 인자 · 앞 step 의 id(없으면 None)
    출력  같은 모양에 표시만 바뀐 것. 앞 단계가 없어 채울 수 없던 칸은 빠짐
    규칙  "@arg" 는 어절 전체가 표시일 때만 바꿈. 값의 타입이 바뀌므로
          문자열 안에 섞어 쓰지 않음
          "$prev" 로 시작하면 뒤의 경로는 그대로 두고 앞만 바꿈
          앞 단계가 없으면 그 칸을 DROP 으로 표시하고 dict · list 에서 뺌
    제약  값을 지어내지 않는다. 앞 단계가 없을 때 좌표를 만들어 넣지 않고
          칸을 통째로 뺀다
          required 인 칸이 $prev 를 쓰는데 앞 단계가 없으면 도구가 거부한다.
          그것은 배선이 틀린 것이라 여기서 가리지 않는다
    이력  예전에는 앞 단계 없이 $prev 를 만나면 ValueError 로 멈췄음.
          같은 노드가 두 자리에 쓰이면(search_ev_stations 가 키워드 뒤에도
          geocode 뒤에도 옴) 첫 자리에서 무조건 멈춰 recipe 012 · 013 이
          도구를 하나도 못 불렀음.
          ev.searchStations 의 bbox 넷이 전부 optional 이라 그 칸이 없어도
          도구가 돌고 전국을 검색한다 — 값을 지어내는 것보다 안 보내는 것이
          낫다고 보아 "빼고 부른다" 로 바꿨음.
          조영곤님이 자리에 없는 동안 대신 정한 판단임. 되돌릴 때는 이 함수와
          plan 의 inputAdapter 한 줄만 보면 됨
    """
    if isinstance(value, dict):
        filled = {
            key: _filled(item, argument, previous_id) for key, item in value.items()
        }
        return {key: item for key, item in filled.items() if item is not DROP}
    if isinstance(value, list):
        filled = [_filled(item, argument, previous_id) for item in value]
        return [item for item in filled if item is not DROP]
    if value == SPOKEN_VALUE:
        return argument
    if isinstance(value, str) and value.startswith(PREVIOUS_STEP):
        if previous_id is None:
            return DROP
        return f"${previous_id}{value[len(PREVIOUS_STEP):]}"
    return value
