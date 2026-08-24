"""recipe 의 노드 사슬을 vendor 실행기가 받는 steps 배열로 바꾼다. **우리 코드다.**

**온톨로지는 무엇을 어떤 순서로 하는지만 말한다.** 그 노드가 어느 도구인지,
input 을 어떻게 채우는지는 온톨로지에 없다 — 아래 두 표가 갖는다.
온톨로지에 도구 이름을 적으면 노드가 특정 MCP 서버에 묶여, 같은 일을 하는
도구로 갈아끼울 때 도메인을 고쳐야 한다.

    TOOL_OF   노드            -> 서버 · 도구 · 답 첫 줄
    STEP_OF   (노드, 받는 타입) -> input

**같은 노드가 두 자리에 온다.** 전기차 충전소 검색은 말한 키워드 뒤에도 오고
장소 좌표 변환 뒤에도 온다. 그때 받는 것이 query 와 center 로 달라서 노드당
한 줄로는 적을 수 없다. 그래서 STEP_OF 의 키가 (노드, 받는 타입)이고, 그
타입은 온톨로지의 hasInput 선언과 1:1 이다. 어느 줄을 쓸지는 plan 이 앞
단계가 내놓는 타입을 보고 고른다 — 타입 판정은 ontology_service 를 거친다.

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

# 노드 -> 도구. **온톨로지 밖이다.**
#
#   server_id · tool  vendor 가 Gateway 에 보낼 것
#   headline          그 노드에서 끝나는 경로의 답 첫 줄
#
# **한 노드는 한 도구이고 한 headline 이다.** 받는 것이 둘이어도 부르는 도구는
# 같다. 그래서 이 표는 노드당 한 줄이고, 아래 STEP_OF 만 (노드 × 받는 타입)
# 이다. 둘을 한 표에 합치면 도구 이름과 답 문장이 줄마다 복사되고, 한 쪽만
# 고쳤을 때 조용히 어긋난다.
#
# headline 은 마지막 노드의 것만 쓰인다. 도구 이름으로는 만들 수 없는 문장이라
# (road.getCctv -> "CCTV 를 조회했습니다") 노드가 들고 있어야 한다.
TOOL_OF = {
    "geocode_place": {
        "server_id": SERVER_ID,
        "tool": "geo.geocode",
        "headline": "{arg} 좌표를 조회했습니다.",
    },
    "find_cctv": {
        "server_id": SERVER_ID,
        "tool": "road.getCctv",
        "headline": "{arg} CCTV 를 조회했습니다.",
    },
    "get_railway_section": {
        "server_id": SERVER_ID,
        "tool": "rail.getSectionGeometry",
        "headline": "{arg} 철도 구간 형상을 조회했습니다.",
    },
    "get_railway_lines": {
        "server_id": SERVER_ID,
        "tool": "geo.getRailwayLines",
        "headline": "{arg} 철도 노선을 조회했습니다.",
    },
    "find_admin_boundary_by_point": {
        "server_id": SERVER_ID,
        "tool": "adminBoundary.findBoundaryByPoint",
        "headline": "{arg} 행정구역을 조회했습니다.",
    },
    "find_election_district_by_point": {
        "server_id": SERVER_ID,
        "tool": "election.findDistrictByPoint",
        "headline": "{arg} 국회의원 지역구를 조회했습니다.",
    },
    "find_assembly_district_by_point": {
        "server_id": SERVER_ID,
        "tool": "election.findAssemblyDistrictByPoint",
        "headline": "{arg} 국회의원 전체 선거구를 조회했습니다.",
    },
    "find_assembly_pledge_district_by_point": {
        "server_id": SERVER_ID,
        "tool": "election.findAssemblyPledgeDistrictByPoint",
        "headline": "{arg} 국회의원 선거구 공약을 조회했습니다.",
    },
    "find_local_pledge_summary_by_point": {
        "server_id": SERVER_ID,
        "tool": "election.findLocalPledgeSummaryByPoint",
        "headline": "{arg} 지방선거 교통 공약을 조회했습니다.",
    },
    "search_admin_boundaries": {
        "server_id": SERVER_ID,
        "tool": "adminBoundary.searchBoundaries",
        "headline": "{arg} 행정구역 경계를 조회했습니다.",
    },
    "get_vworld_boundaries": {
        "server_id": SERVER_ID,
        "tool": "vworld.getAdministrativeBoundaries",
        "headline": "{arg} VWorld 행정경계를 조회했습니다.",
    },
    "search_population_statistics": {
        "server_id": SERVER_ID,
        "tool": "population.searchStatistics",
        "headline": "{arg} 인구 통계를 조회했습니다.",
    },
    "search_ev_stations": {
        "server_id": SERVER_ID,
        "tool": "ev.searchStations",
        "headline": "{arg} 전기차 충전소를 조회했습니다.",
    },
    "search_ev_chargers": {
        "server_id": SERVER_ID,
        "tool": "ev.searchChargers",
        "headline": "{arg} 전기차 충전기를 조회했습니다.",
    },
    "get_ev_station": {
        "server_id": SERVER_ID,
        "tool": "ev.getStation",
        "headline": "{arg} 충전소 상세를 조회했습니다.",
    },
    "search_election_districts": {
        "server_id": SERVER_ID,
        "tool": "election.searchDistricts",
        "headline": "{arg} 국회의원 지역구 목록을 조회했습니다.",
    },
    "search_assembly_districts": {
        "server_id": SERVER_ID,
        "tool": "election.searchAssemblyDistricts",
        "headline": "{arg} 국회의원 전체 선거구 목록을 조회했습니다.",
    },
    "search_assembly_pledge_districts": {
        "server_id": SERVER_ID,
        "tool": "election.searchAssemblyPledgeDistricts",
        "headline": "{arg} 국회의원 선거구 공약 목록을 조회했습니다.",
    },
    "search_local_pledge_summaries": {
        "server_id": SERVER_ID,
        "tool": "election.searchLocalPledgeSummaries",
        "headline": "{arg} 지방선거 교통 공약 목록을 조회했습니다.",
    },
    # 선거 상세 셋. 목록 검색(search_…)과 짝이고 하나를 집어 오는 쪽이다.
    "get_election_district": {
        "server_id": SERVER_ID,
        "tool": "election.getDistrict",
        "headline": "{arg} 국회의원 지역구를 조회했습니다.",
    },
    "get_assembly_district": {
        "server_id": SERVER_ID,
        "tool": "election.getAssemblyDistrict",
        "headline": "{arg} 국회의원 전체 선거구를 조회했습니다.",
    },
    "get_assembly_pledge_district": {
        "server_id": SERVER_ID,
        "tool": "election.getAssemblyPledgeDistrict",
        "headline": "{arg} 국회의원 선거구 공약을 조회했습니다.",
    },
    "get_local_pledge_summary": {
        "server_id": SERVER_ID,
        "tool": "election.getLocalPledgeSummary",
        "headline": "{arg} 지방선거 교통 공약 요약을 조회했습니다.",
    },
    "search_documents": {
        "server_id": SERVER_ID,
        "tool": "knowledge.query",
        "headline": "{arg} 문서를 조회했습니다.",
    },
    "web_search": {
        "server_id": WEB_SERVER_ID,
        "tool": "web.search",
        "headline": "{arg} 웹 검색 결과를 조회했습니다.",
    },
}

# (노드, 받는 타입) -> 그 자리에서 input 을 어떻게 채우는가. **온톨로지 밖이다.**
#
#   input        그 도구가 받는 input. @arg 와 $prev 를 쓸 수 있다
#   input_first  앞 단계가 없을 때의 input. 안 적으면 input 을 그대로 씀
#   adapter      vendor 입력 어댑터 이름. 저절로 안 걸리는 도구에만 적는다
#
# **키의 타입은 온톨로지의 hasInput 선언과 1:1 이다.** 선언에 없는 타입으로
# 줄을 적으면 plan 이 그 줄을 영영 못 고른다 — 줄을 고르는 것이 선언이기
# 때문이다. 반대로 선언에는 있는데 줄이 없으면 그 자리는 unwired 다.
# tools/check_wiring.py 가 양쪽을 센다.
#
# 예전에는 노드당 한 줄이었다. 같은 노드가 두 자리에 오는데 받는 것이 달라서
# 한 줄로는 못 적었다.
#
#   말한 장소 → 좌표 변환 → 전기차 충전소 검색     center 를 받아야 한다
#   말한 키워드 →           전기차 충전소 검색     query 를 받아야 한다
#
# 그 탓에 recipe 012 · 013 은 발화에서 온 값을 통째로 버리고 전국을 검색했다.
STEP_OF = {
    ("geocode_place", "place_name"): {"input": {"query": SPOKEN_VALUE}},

    # 앞이 무엇이냐에 따라 채우는 칸이 갈린다(2026-08-23 실측).
    #
    #   철도 구간 형상 조회 뒤   그 bbox 를 그대로 넘긴다.
    #                            rail.getSectionGeometry 의 bbox 는
    #                            [[126.868587, 36.619576], [127.328115, 37.554557]]
    #                            처럼 두 겹인데 vendor 의 _resolve_reference 가
    #                            $prev.minLon 을 bbox[0][0] 으로 푼다
    #   장소 좌표 변환 뒤        좌표를 반경 15km 로 넓힌다.
    #                            geocode 의 bbox 는 한 변이 1km 라 그것을 그대로
    #                            넘기면 0건이다
    #
    # road.getCctv 는 bbox 넷이 전부 required 라 vendor 가 어댑터를 저절로 건다.
    ("find_cctv", "map_extent"): {
        "input": {
            "minLon": f"{PREVIOUS_STEP}.minLon",
            "minLat": f"{PREVIOUS_STEP}.minLat",
            "maxLon": f"{PREVIOUS_STEP}.maxLon",
            "maxLat": f"{PREVIOUS_STEP}.maxLat",
        },
    },
    ("find_cctv", "point"): {
        "input": {"location": f"{PREVIOUS_STEP}.location", "radiusMeters": RADIUS_METERS},
    },

    ("get_railway_section", "place_name"): {"input": {"sectionName": SPOKEN_VALUE}},

    # railwayName 은 안 건드린다. stationName 과 같은 "장소 이름" 이라 줄이
    # 갈리지 않는다 — 역명으로 볼지 노선명으로 볼지는 사람이 정할 일이다.
    ("get_railway_lines", "place_name"): {"input": {"stationName": SPOKEN_VALUE}},
    ("get_railway_lines", "map_extent"): {"input": {"bbox": BBOX_FROM_PREVIOUS}},

    ("find_admin_boundary_by_point", "point"): {"input": POINT_FROM_PREVIOUS},
    ("find_election_district_by_point", "point"): {"input": POINT_FROM_PREVIOUS},
    ("find_assembly_district_by_point", "point"): {"input": POINT_FROM_PREVIOUS},
    ("find_assembly_pledge_district_by_point", "point"): {"input": POINT_FROM_PREVIOUS},
    ("find_local_pledge_summary_by_point", "point"): {"input": POINT_FROM_PREVIOUS},

    ("search_admin_boundaries", "keyword"): {"input": {"query": SPOKEN_VALUE}},
    ("search_admin_boundaries", "map_extent"): {"input": {"bbox": BBOX_FROM_PREVIOUS}},

    ("get_vworld_boundaries", "keyword"): {"input": {"query": SPOKEN_VALUE}},
    ("get_vworld_boundaries", "map_extent"): {"input": {"bbox": BBOX_FROM_PREVIOUS}},

    ("search_population_statistics", "keyword"): {"input": {"query": SPOKEN_VALUE}},
    ("search_population_statistics", "map_extent"): {"input": {"bbox": BBOX_FROM_PREVIOUS}},

    # ev.searchStations · ev.searchChargers 의 inputSchema 에 query 가 있다 —
    # "충전소명, 주소, 운영기관 키워드". 말한 키워드가 갈 자리가 여기다.
    ("search_ev_stations", "keyword"): {"input": {"query": SPOKEN_VALUE}},
    # bbox 넷이 전부 optional 이라 vendor 가 어댑터를 저절로 안 건다. 그래서
    # 이 줄에만 이름을 적는다. 오송역에서 83건이 나왔다(실측).
    ("search_ev_stations", "map_extent"): {
        "input": {"center": f"{PREVIOUS_STEP}.location", "radiusMeters": RADIUS_METERS},
        "adapter": POINT_RADIUS_TO_BBOX,
    },
    ("search_ev_chargers", "keyword"): {"input": {"query": SPOKEN_VALUE}},
    ("search_ev_chargers", "map_extent"): {
        "input": {"center": f"{PREVIOUS_STEP}.location", "radiusMeters": RADIUS_METERS},
        "adapter": POINT_RADIUS_TO_BBOX,
    },

    # ev.getStation 의 statId 는 **stationId 이지 id 가 아니다**(2026-08-23 실측).
    #
    #   statId="PL033780"            item 이 온다
    #   statId="ev_station_PL033780" item null · 0건 ·
    #                                "충전소 ev_station_PL033780를 찾지 못했거나…"
    #
    # tools/probe_out/ev.getStation.statId-stationId.json 과
    # tools/probe_out/ev.getStation.statId-id.json 이 그 둘이다.
    # 앞 단계가 없으면(말한 식별자 → 충전소 상세) 발화에서 온 값이 곧 그 번호다.
    ("get_ev_station", "station_id"): {
        "input": {"statId": f"{PREVIOUS_STEP}.items.0.stationId"},
        "input_first": {"statId": SPOKEN_VALUE},
    },

    # ── 발화에서 온 말로 찾는 것 ────────────────────────────────────
    #
    # 노드와 도구의 짝은 온톨로지 노드 description 과 tools.json description 을
    # 맞대어 정했다. 아래 셋은 2026-08-22 실측으로 query 가 실제로 거르는 것도
    # 확인했다 — 인자 없이 부르면 254 · 254 · 476 건이고 query="청주" 로 부르면
    # 4 · 5 건, query="철도" 로 부르면 206 건이다.
    ("search_election_districts", "keyword"): {"input": {"query": SPOKEN_VALUE}},

    ("search_assembly_districts", "keyword"): {"input": {"query": SPOKEN_VALUE}},
    ("search_assembly_districts", "map_extent"): {"input": {"bbox": BBOX_FROM_PREVIOUS}},

    ("search_assembly_pledge_districts", "keyword"): {"input": {"query": SPOKEN_VALUE}},
    ("search_assembly_pledge_districts", "map_extent"): {
        "input": {"bbox": BBOX_FROM_PREVIOUS},
    },

    # ── 선거 상세 셋 : 말한 이름을 그대로 보낸다 ──────────────────
    #
    # 넷 다 code 말고 **이름 칸을 따로 갖는다**(ASAP-mcp/main.py inputSchema).
    # required 는 없다.
    #
    #   election.getDistrict                name      "선거구명. 예: 서울 강서갑, 의왕과천"
    #   election.getAssemblyDistrict        name      "선거구명 또는 검색어"
    #   election.getAssemblyPledgeDistrict  name      "선거구명 또는 검색어"
    #   election.getLocalPledgeSummary      sidoName  "시도명. 예: 서울특별시"
    #
    # 눌러서 확인했다(2026-08-24). 응답 전문은 tools/probe_out/ 에 있다.
    #
    #   getDistrict               {name: "충북 청주서원"}  feature 1건
    #   getAssemblyDistrict       {name: "청주시 상당구"}  feature 1건
    #   getAssemblyPledgeDistrict {name: "청주시 상당구"}  feature 1건
    #   getLocalPledgeSummary     {sidoName: "충청북도"}   0건 · featureCount 0
    #
    # 0건인 것은 저쪽 데이터가 미적재여서다
    # (getLocalPledgeSummaryDatasetInfo 의 featureCount 0 · available false).
    # 배선이 없는 것과 데이터가 없는 것은 다르므로 그것만으로는 안 적을 이유가
    # 못 된다.
    #
    # 위 셋은 district_code 를 건네는 앞 노드가 spoken_identifier 하나뿐이라
    # 자리가 겹치지 않는다. 그래서 @arg 한 줄로 끝난다.
    # getLocalPledgeSummary 는 자리가 둘이라 아래에 따로 적는다.
    ("get_election_district", "district_code"): {"input": {"name": SPOKEN_VALUE}},
    ("get_assembly_district", "district_code"): {"input": {"name": SPOKEN_VALUE}},
    ("get_assembly_pledge_district", "district_code"): {"input": {"name": SPOKEN_VALUE}},

    # ── 지방선거 교통 공약 요약 : 한 줄이 두 자리를 맡는다 ──────────
    #
    # 이 줄만 (노드 × 받는 타입) 하나로 **두 자리**에 걸린다.
    #
    #   recipe_018  말한 식별자 -> 공약 요약                      첫 step
    #   recipe_044  말한 장소 -> 좌표 -> 행정구역 판별 -> 공약 요약  앞이 있다
    #
    # 그래서 input_first 로 갈라 적는다. 2026-08-24 에 양쪽을 다 눌렀다.
    #
    #   {sidoName: "충청북도"}  query.sidoName 으로 되받음
    #   {sidoCode: "43"}        query.sidoCode 로 되받음
    #
    # 둘 다 status not_found 인데 그것은 **저쪽 데이터가 미적재**여서다
    # (dataset.available false · featureCount 0). 인자는 파싱됐다.
    #
    # 앞 단계 쪽은 adminBoundary.findBoundaryByPoint 의 items.0 이다.
    # 여섯 지점(오송·강남·부산·제주·금산·세종)에서 items 가 늘 3건이고
    # 순서가 sido -> sigungu -> emd 로 고정이었다. items.0 이 시도이고
    # 그 code 가 두 자리 시도 코드라 sidoCode 와 맞는다. 세종처럼 시군구가
    # 없는 곳도 sigungu 자리를 같은 이름으로 채워 순서가 안 밀린다.
    # 응답 전문은 tools/probe_out/ 에 있다.
    ("get_local_pledge_summary", "admin_code"): {
        "input": {"sidoCode": f"{PREVIOUS_STEP}.items.0.code"},
        "input_first": {"sidoName": SPOKEN_VALUE},
    },

    # 아래 셋은 배선이 맞는데 도구 쪽이 지금 비어 있거나 막혀 있다(2026-08-22
    # 실측). 배선이 없는 것과 데이터가 없는 것은 다르므로 적어 둔다 — 저쪽에
    # 데이터가 들어오면 고칠 것 없이 그대로 돈다. 왜 비었는지는 각 줄 위에
    # 적었고 NOTES.md 「2026-08-22 (셋째)」 에 응답 전문 근거가 있다.
    #
    # election.searchLocalPledgeSummaries : 0건.
    #   "2026 지방선거 시도별 공약 요약 데이터를 조회하지 못했습니다."
    #   같은 데이터셋의 getDatasetInfo 도 미적재라고 답한다. 저쪽 데이터다.
    ("search_local_pledge_summaries", "keyword"): {"input": {"query": SPOKEN_VALUE}},
    ("search_local_pledge_summaries", "map_extent"): {
        "input": {"bbox": BBOX_FROM_PREVIOUS},
    },

    # knowledge.query : 0건. 지식베이스가 비었다. knowledge.listDocs 도 [] 라
    #   질의가 틀린 것이 아니라 문서가 하나도 없는 것이다.
    ("search_documents", "keyword"): {"input": {"query": SPOKEN_VALUE}},

    # web.search : 실패. "MCP tool 'web-search/web.search' is not applied for
    #   this user." 데이터가 없는 것이 아니라 우리 user_context 에 web-search
    #   서버가 안 열려 있는 것이다. KRRI_ASAP 쪽 권한이라 우리가 못 연다.
    ("web_search", "keyword"): {"input": {"query": SPOKEN_VALUE}},
}

# 아직 배선을 안 적은 (노드 × 받는 타입)과 그 이유. 다음 사람이 왜 비어 있는지
# 알아야 한다. tools/check_wiring.py 가 이 셋을 센다.
#
# **2026-08-24 에 get_local_pledge_summary × 행정구역 코드가 빠졌다.**
# 여기에 「한 줄이 두 자리에 걸려 못 적는다」고 적혀 있었다. 막고 있던 것은
# 두 자리라는 것 자체가 아니라 **앞 단계 쪽 칸 이름을 몰랐다**는 것이었고,
# adminBoundary.findBoundaryByPoint 에 데이터가 들어오면서 그것이 풀렸다.
# 자리마다 갈라 적는 input_first 로 두 자리를 다 적었다 — 위 절에 근거가 있다.
#
# 1. 응답의 어느 칸에 그 값이 오는지 아직 모른다
#
#    web_fetch × 웹 주소
#
#    web.fetch 의 required 는 url 하나이고 그 값은 앞 단계인 web.search 의
#    결과에서 꺼내야 한다. 그런데 web.search 가 권한에 막혀
#    ("MCP tool 'web-search/web.search' is not applied for this user")
#    응답 모양을 한 번도 못 봤다. **모르면 배선을 적지 않는다.**
#    예전에는 {url: @arg} 라고 적혀 있었다. 발화에서 온 말을 URL 로 쓰는
#    것이라 부르면 반드시 틀린다. 지어낸 배선이라 지웠다.
#    recipe 041 이 여기 걸린다.
#
# 2. 한 줄이 두 자리에 걸리는데 발화 쪽 자리를 적을 수가 없다
#
#    get_age_profile · get_population_trend × 행정구역 코드
#
#    **앞 단계 쪽은 이제 안다.** adminBoundary.findBoundaryByPoint 가
#    items 를 sido -> sigungu -> emd 순서로 늘 3건 내놓고(여섯 지점 실측,
#    tools/probe_out/ 참고) items.N 의 layerId 가 sido·sigungu·emd 이며
#    population 두 도구의 level enum 이 정확히 같은 낱말이다. 그래서
#    {level: $prev.items.1.layerId, code: $prev.items.1.code} 로 적을 수 있다.
#    getAgeProfile 을 세 level 로 다 눌러 봤고 다 답한다.
#
#    **막는 것은 발화 쪽 자리다.** recipe 019 · 020 은 말한 식별자가 곧
#    첫 step 이라 $prev 가 없다. 그런데 level 은 required 이고 발화에 없다 —
#    menu 가 recipe_019 를 "행정구역 코드와 기준월로 본다" 라고 적는다.
#    눌러서 확인했다(2026-08-24).
#
#      {code: "43113"}                 {"error": "level과 code가 필요합니다."}
#      {level: "", code: "43113"}      같은 오류
#      {level: "sigungu", code: "43"}  {"error": "시군구 코드는 최소 5자리여야 합니다"}
#
#    level 을 한 낱말로 박으면 자릿수가 다른 코드에서 반드시 틀린다. 발화에
#    없는 값이라 @arg 로도 못 받는다. **반만 알고 한 줄을 적으면 다른 자리가
#    틀린다** — $prev 쪽만 적어 보니 check_wiring 의 A 가 0 에서 2 로 늘었다
#    (recipe 019 · 020). 그래서 되돌렸다.
#    recipe 019 · 020 · 045 · 046 이 여기 걸린다.
#
#    코드 자릿수로 level 을 정하면 풀리지만 그것은 배선 한 줄이 아니라
#    _filled 에 변환을 넣는 일이다. 「열린 과제」에 물음으로 남긴다.
#
# 식별자 타입을 셋으로 쪼개기 전에는 여기에 "체계가 다른 식별자를 옮겨 적을
# 수 없다" 는 항목이 있었다. 그것은 온톨로지가 고쳤다 — 이제 가짜 경로 자체가
# 생기지 않는다.


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
          말한 식별자는 코드 셋을 가리키고 그중 줄이 있는 것 하나가 걸림
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
          앞 단계에서 받을 수도 발화에서 받을 수도 있는 자리가 있음
          충전소 상세 조회가 그것임. 검색 뒤에 오면 앞 결과의 stationId 를
          쓰고, 말한 식별자 뒤에 오면 발화에서 온 값이 곧 그 번호임
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
          안 부름. 배선을 안 적은 자리와 그 이유는 STEP_OF 아래 주석에 있음
    """
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
          headline  답의 첫 줄. 마지막 step 의 노드가 정함
    규칙  step id 는 s1 · s2 … 로 붙음. $prev 를 앞 step 의 id 로 바꿈
          어느 배선 줄을 쓸지는 앞 노드가 건네는 타입이 정함. wiring_at 이 그것임
          맞는 줄이 없는 노드는 step 을 만들지 않음. 데이터 노드
          (spoken_place)도 값을 준비할 뿐 부를 것이 없어 빠짐
          adapter 가 적힌 줄만 step 에 inputAdapter 칸이 생김. 없는 것은
          vendor 가 도구 스키마를 보고 스스로 정함
          앞 단계가 없어 중심 좌표 칸이 빠졌으면 inputAdapter 도 안 실음.
          걸 것이 없는데 걸면 vendor 어댑터가 ValueError 를 올림
          실행 노드가 빠져 반쪽으로 도는 것은 부르기 전에 unwired 가 막음
    제약  첫 step 의 input 에 $prev 를 쓸 수는 있으나 그 칸은 빠진 채로 나간다.
          required 인 칸이면 도구가 거부하고 그것은 배선이 틀린 것이다
    이력  예전에는 배선이 노드당 한 줄이었고 첫 step 이 $prev 를 가리키면
          _filled 이 그 칸을 빼고 불렀음. recipe 012 · 013 이 그것에 걸려
          발화에서 온 값을 버리고 전국을 검색했음. 이제 그 자리는 키워드 줄이
          걸림. _filled 의 이력 절 참고
    """
    steps: list[dict] = []
    nodes: list[str] = []
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
        step_id = f"s{len(steps) + 1}"
        step = {
            "id": step_id,
            "server_id": tool["server_id"],
            "tool": tool["tool"],
            "input": _filled(
                input_of(wiring, first=previous_id is None), argument, previous_id
            ),
        }
        if wiring.get("adapter") and _has_center(step["input"]):
            step["inputAdapter"] = wiring["adapter"]
        steps.append(step)
        nodes.append(node_id)
        headline = tool["headline"].format(arg=argument)
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
