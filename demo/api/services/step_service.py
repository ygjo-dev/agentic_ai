"""recipe 의 노드 사슬을 vendor 실행기가 받는 steps 배열로 바꾼다. **우리 코드다.**

**온톨로지는 무엇을 어떤 순서로 하는지만 말한다.** 그 노드가 어느 도구인지,
input 을 어떻게 채우는지는 온톨로지에 없다 — 아래 STEP_OF 표가 갖는다.
온톨로지에 도구 이름을 적으면 노드가 특정 MCP 서버에 묶여, 같은 일을 하는
도구로 갈아끼울 때 도메인을 고쳐야 한다.

**배선은 여기서 끝난다.** 앞 단계 결과를 다음 input 에 어떻게 넣을지는
vendor/asap/generic_mcp_executor 의 _resolve_reference 가 안다 — 도구별이 아니라
필드 이름별이라 도구가 늘어도 재사용된다. 우리는 $prev.location 처럼 "앞
단계의 무엇" 이라고만 적는다.

발화에서 온 값이 들어가는 자리가 @arg 다. 무엇을 뽑을지는 발화 해석 LLM 이
argument 로 함께 내놓고, 그것이 없을 때만 place_in 이 장소 하나를 뽑는다.
"""

import re

from demo.api.services import ontology_service

SERVER_ID = "asap-mcp-core"

# web.search · web.fetch 만 다른 MCP 서버에 있다. 나머지 마흔은 SERVER_ID 다.
# 여기를 틀리면 Gateway 가 도구를 못 찾는다 — tools.json 의 serverId 가 근거다.
WEB_SERVER_ID = "web-search"

# 좌표 하나를 지도 범위로 넓힐 때의 반경. road.getCctv 와 ev.searchStations ·
# ev.searchChargers 가 같은 값을 쓴다. vendor 의 point_radius_to_bbox 어댑터가
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

# 앞 단계를 가리키는 표시. 실제 step id 로 바꿔서 vendor 에 넘긴다.
PREVIOUS_STEP = "$prev"

# 중심 좌표와 반경을 bbox 넷으로 바꾸는 vendor 어댑터의 이름.
#
# road.getCctv 는 bbox 넷이 전부 required 라 vendor 가 저절로 건다.
# ev.searchStations · ev.searchChargers 는 넷 다 optional 이라 안 걸린다 —
# 그래서 그 둘의 단계에만 이 이름을 적는다.
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

# 노드 -> step. **온톨로지 밖이다.**
#
#   server_id · tool  vendor 가 Gateway 에 보낼 것
#   input             그 도구가 받는 input. @arg 와 $prev 를 쓸 수 있다
#   adapter           vendor 입력 어댑터 이름. 저절로 안 걸리는 도구에만 적는다
#   headline          그 노드에서 끝나는 경로의 답 첫 줄
#
# headline 은 마지막 노드의 것만 쓰인다. 도구 이름으로는 만들 수 없는 문장이라
# (road.getCctv -> "CCTV 를 조회했습니다") 노드가 들고 있어야 한다.
STEP_OF = {
    "geocode_place": {
        "server_id": SERVER_ID,
        "tool": "geo.geocode",
        "input": {"query": SPOKEN_VALUE},
        "headline": "{arg} 좌표를 조회했습니다.",
    },
    "find_cctv": {
        "server_id": SERVER_ID,
        "tool": "road.getCctv",
        "input": {"location": f"{PREVIOUS_STEP}.location", "radiusMeters": RADIUS_METERS},
        "headline": "{arg} CCTV 를 조회했습니다.",
    },
    "get_railway_section": {
        "server_id": SERVER_ID,
        "tool": "rail.getSectionGeometry",
        "input": {"sectionName": SPOKEN_VALUE},
        "headline": "{arg} 철도 구간 형상을 조회했습니다.",
    },
    "get_railway_lines": {
        "server_id": SERVER_ID,
        "tool": "geo.getRailwayLines",
        "input": {"stationName": SPOKEN_VALUE},
        "headline": "{arg} 철도 노선을 조회했습니다.",
    },
    "find_admin_boundary_by_point": {
        "server_id": SERVER_ID,
        "tool": "adminBoundary.findBoundaryByPoint",
        "input": {"lon": f"{PREVIOUS_STEP}.lon", "lat": f"{PREVIOUS_STEP}.lat"},
        "headline": "{arg} 행정구역을 조회했습니다.",
    },
    "find_election_district_by_point": {
        "server_id": SERVER_ID,
        "tool": "election.findDistrictByPoint",
        "input": {"lon": f"{PREVIOUS_STEP}.lon", "lat": f"{PREVIOUS_STEP}.lat"},
        "headline": "{arg} 국회의원 지역구를 조회했습니다.",
    },
    "find_assembly_district_by_point": {
        "server_id": SERVER_ID,
        "tool": "election.findAssemblyDistrictByPoint",
        "input": {"lon": f"{PREVIOUS_STEP}.lon", "lat": f"{PREVIOUS_STEP}.lat"},
        "headline": "{arg} 국회의원 전체 선거구를 조회했습니다.",
    },
    "find_assembly_pledge_district_by_point": {
        "server_id": SERVER_ID,
        "tool": "election.findAssemblyPledgeDistrictByPoint",
        "input": {"lon": f"{PREVIOUS_STEP}.lon", "lat": f"{PREVIOUS_STEP}.lat"},
        "headline": "{arg} 국회의원 선거구 공약을 조회했습니다.",
    },
    "find_local_pledge_summary_by_point": {
        "server_id": SERVER_ID,
        "tool": "election.findLocalPledgeSummaryByPoint",
        "input": {"lon": f"{PREVIOUS_STEP}.lon", "lat": f"{PREVIOUS_STEP}.lat"},
        "headline": "{arg} 지방선거 교통 공약을 조회했습니다.",
    },
    "search_admin_boundaries": {
        "server_id": SERVER_ID,
        "tool": "adminBoundary.searchBoundaries",
        "input": {"query": SPOKEN_VALUE},
        "headline": "{arg} 행정구역 경계를 조회했습니다.",
    },
    "get_vworld_boundaries": {
        "server_id": SERVER_ID,
        "tool": "vworld.getAdministrativeBoundaries",
        "input": {"query": SPOKEN_VALUE},
        "headline": "{arg} VWorld 행정경계를 조회했습니다.",
    },
    "search_population_statistics": {
        "server_id": SERVER_ID,
        "tool": "population.searchStatistics",
        "input": {"query": SPOKEN_VALUE},
        "headline": "{arg} 인구 통계를 조회했습니다.",
    },
    "search_ev_stations": {
        "server_id": SERVER_ID,
        "tool": "ev.searchStations",
        "input": {"center": f"{PREVIOUS_STEP}.location", "radiusMeters": RADIUS_METERS},
        "adapter": POINT_RADIUS_TO_BBOX,
        "headline": "{arg} 전기차 충전소를 조회했습니다.",
    },
    "search_ev_chargers": {
        "server_id": SERVER_ID,
        "tool": "ev.searchChargers",
        "input": {"center": f"{PREVIOUS_STEP}.location", "radiusMeters": RADIUS_METERS},
        "adapter": POINT_RADIUS_TO_BBOX,
        "headline": "{arg} 전기차 충전기를 조회했습니다.",
    },
    # ── 발화에서 온 말로 찾는 것 ────────────────────────────────────
    #
    # 아래 일곱은 앞 단계가 필요 없다. 받는 것이 좌표가 아니라 발화에서 온
    # 말이라 첫 step 으로도 돈다.
    #
    # 노드와 도구의 짝은 온톨로지 노드 description 과 tools.json description 을
    # 맞대어 정했다. 아래 셋은 2026-08-22 실측으로 query 가 실제로 거르는 것도
    # 확인했다 — 인자 없이 부르면 254 · 254 · 476 건이고 query="청주" 로 부르면
    # 4 · 5 건, query="철도" 로 부르면 206 건이다.
    "search_election_districts": {
        "server_id": SERVER_ID,
        "tool": "election.searchDistricts",
        "input": {"query": SPOKEN_VALUE},
        "headline": "{arg} 국회의원 지역구 목록을 조회했습니다.",
    },
    "search_assembly_districts": {
        "server_id": SERVER_ID,
        "tool": "election.searchAssemblyDistricts",
        "input": {"query": SPOKEN_VALUE},
        "headline": "{arg} 국회의원 전체 선거구 목록을 조회했습니다.",
    },
    "search_assembly_pledge_districts": {
        "server_id": SERVER_ID,
        "tool": "election.searchAssemblyPledgeDistricts",
        "input": {"query": SPOKEN_VALUE},
        "headline": "{arg} 국회의원 선거구 공약 목록을 조회했습니다.",
    },
    # 아래 넷은 배선이 맞는데 도구 쪽이 지금 비어 있거나 막혀 있다(2026-08-22
    # 실측). 배선이 없는 것과 데이터가 없는 것은 다르므로 적어 둔다 — 저쪽에
    # 데이터가 들어오면 고칠 것 없이 그대로 돈다. 왜 비었는지는 각 줄 위에
    # 적었고 NOTES.md 「2026-08-22 (셋째)」 에 응답 전문 근거가 있다.
    #
    # election.searchLocalPledgeSummaries : 0건.
    #   "2026 지방선거 시도별 공약 요약 데이터를 조회하지 못했습니다."
    #   같은 데이터셋의 getDatasetInfo 도 미적재라고 답한다. 저쪽 데이터다.
    "search_local_pledge_summaries": {
        "server_id": SERVER_ID,
        "tool": "election.searchLocalPledgeSummaries",
        "input": {"query": SPOKEN_VALUE},
        "headline": "{arg} 지방선거 교통 공약 목록을 조회했습니다.",
    },
    # knowledge.query : 0건. 지식베이스가 비었다. knowledge.listDocs 도 [] 라
    #   질의가 틀린 것이 아니라 문서가 하나도 없는 것이다.
    "search_documents": {
        "server_id": SERVER_ID,
        "tool": "knowledge.query",
        "input": {"query": SPOKEN_VALUE},
        "headline": "{arg} 문서를 조회했습니다.",
    },
    # web.search : 실패. "MCP tool 'web-search/web.search' is not applied for
    #   this user." 데이터가 없는 것이 아니라 우리 user_context 에 web-search
    #   서버가 안 열려 있는 것이다. KRRI_ASAP 쪽 권한이라 우리가 못 연다.
    "web_search": {
        "server_id": WEB_SERVER_ID,
        "tool": "web.search",
        "input": {"query": SPOKEN_VALUE},
        "headline": "{arg} 웹 검색 결과를 조회했습니다.",
    },
    # web.fetch : 안 눌러봤다. required 가 url 하나인데 probe 가 URL 을 지어내지
    #   않는다. 같은 web-search 서버라 web.search 와 같은 권한에 막힐 것으로
    #   본다 — 확인은 못 했다.
    "web_fetch": {
        "server_id": WEB_SERVER_ID,
        "tool": "web.fetch",
        "input": {"url": SPOKEN_VALUE},
        "headline": "{arg} 웹 문서를 조회했습니다.",
    },
}

# 아직 배선을 안 적은 노드와 그 이유. 다음 사람이 왜 비어 있는지 알아야 한다.
#
# 1. 앞 단계가 내놓는 식별자와 이 도구가 받는 식별자의 체계가 다르다
#
#    get_election_district · get_assembly_district · get_assembly_pledge_district
#    get_ev_station
#
#    앞 단계가 find_admin_boundary_by_point 이고 그것이 내놓는 것은 행정구역
#    코드다. 위 넷이 받는 것은 선거구 코드(code · name)와 충전소 번호(statId)라
#    체계가 다르다. 값을 옮겨 적을 수가 없어 배선을 안 적었다.
#    온톨로지의 식별자 타입이 셋을 하나로 묶은 탓이다. NOTES.md
#    「적을 수 없었던 경로」 참고.
#    recipe 042 · 043 · 044 · 048 이 여기 걸린다. 앞 단계 없이 이 도구만 부르는
#    recipe 015 · 016 · 017 · 021 도 같은 이유로 막힌다 — 발화에서 온 말을
#    선거구 코드나 충전소 번호로 그대로 쓸 수는 없다.
#
# 2. 받을 것은 행정구역 코드가 맞지만 어느 필드에 오는지 아직 모른다
#
#    get_local_pledge_summary · get_age_profile · get_population_trend
#
#    population.getAgeProfile · population.getTrend 는 level 과 code 를 받고
#    그것이 행정구역 코드다. 다만 adminBoundary.findBoundaryByPoint 가 그 코드를
#    어떤 필드 이름으로 내놓는지 여전히 모른다.
#    2026-08-22 에 눌렀고 0건이었다 — "행정구역 DB 데이터가 없거나 PostGIS
#    연결을 사용할 수 없습니다". features 가 비어 있어 필드 이름을 볼 것이
#    없었다. 저쪽 PostGIS 에 경계가 적재되면 응답을 보고 적는다.
#    getDatasetInfo 가 layers 의 codeField 로 ctprvn_cd · SIG_CD · emd_cd 를
#    말하지만 그것은 shapefile 의 컬럼 이름이지 응답 필드 이름이 아니다.
#    짐작으로 적지 않는다.
#    recipe 018 · 019 · 020 · 045 · 046 · 047 이 여기 걸린다.

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


def unwired(recipe_id: str) -> list[str]:
    """아직 도구가 안 붙은 노드.

    입력  recipe id
    출력  STEP_OF 에 없는 실행 노드 id 목록. 경로 순서. 전부 있으면 빈 목록
    규칙  실행 노드만 셈. 데이터 노드는 부를 것이 없어 세지 않음
          부르는 쪽(execute_service.run)이 비어 있지 않으면 도구를 하나도
          안 부름. 배선을 안 적은 노드와 그 이유는 STEP_OF 아래 주석에 있음
    """
    return [
        node_id
        for node_id in ontology_service.executable_in(recipe_id)
        if node_id not in STEP_OF
    ]


def plan(recipe_id: str, argument: str) -> dict:
    """recipe 한 벌을 vendor 가 받는 실행 계획으로.

    입력  recipe id · 발화에서 뽑은 인자. 장소일 수도 키워드일 수도 식별자일
          수도 있음. 어느 것인지는 여기서 안 가름
    출력  steps  vendor 의 intent["steps"] 에 그대로 들어갈 배열
          nodes  steps 와 같은 길이. steps[i] 를 만든 노드 id
          headline  답의 첫 줄. 마지막 step 의 노드가 정함
    규칙  step id 는 s1 · s2 … 로 붙음. $prev 를 앞 step 의 id 로 바꿈
          STEP_OF 에 없는 노드는 step 을 만들지 않음. 데이터 노드
          (spoken_place)는 값을 준비할 뿐 부를 것이 없음
          adapter 가 있는 노드만 step 에 inputAdapter 칸이 생김. 없는 것은
          vendor 가 도구 스키마를 보고 스스로 정함
          앞 단계가 없어 중심 좌표 칸이 빠졌으면 inputAdapter 도 안 실음.
          걸 것이 없는데 걸면 vendor 어댑터가 ValueError 를 올림
          실행 노드가 빠져 반쪽으로 도는 것은 부르기 전에 unwired 가 막음
    제약  첫 step 의 input 에 $prev 를 쓸 수는 있으나 그 칸은 빠진 채로 나간다.
          required 인 칸이면 도구가 거부하고 그것은 배선이 틀린 것이다
    이력  예전에는 첫 step 이 $prev 를 가리키면 _filled 이 ValueError 로
          멈췄음. recipe 012 · 013 이 그것에 걸려 도구를 하나도 못 불렀음.
          _filled 의 이력 절 참고
    """
    steps: list[dict] = []
    nodes: list[str] = []
    headline = ""
    previous_id = None

    for entry in ontology_service.path_of(recipe_id):
        node_id = entry["node_id"]
        wiring = STEP_OF.get(node_id)
        if wiring is None:
            continue

        step_id = f"s{len(steps) + 1}"
        step = {
            "id": step_id,
            "server_id": wiring["server_id"],
            "tool": wiring["tool"],
            "input": _filled(wiring["input"], argument, previous_id),
        }
        if wiring.get("adapter") and _has_center(step["input"]):
            step["inputAdapter"] = wiring["adapter"]
        steps.append(step)
        nodes.append(node_id)
        headline = wiring["headline"].format(arg=argument)
        previous_id = step_id

    return {"steps": steps, "nodes": nodes, "headline": headline}


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
