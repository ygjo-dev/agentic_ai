"""recipe 의 노드 사슬을 vendor 실행기가 받는 steps 배열로 바꾼다. **우리 코드다.**

**온톨로지는 무엇을 어떤 순서로 하는지만 말한다.** 그 노드가 어느 도구인지,
input 을 어떻게 채우는지는 온톨로지에 없다 — 아래 두 표가 갖는다.
온톨로지에 도구 이름을 적으면 노드가 특정 MCP 서버에 묶여, 같은 일을 하는
도구로 갈아끼울 때 도메인을 고쳐야 한다.

    TOOL_OF   노드            -> 실행 수단 · 답 첫 줄
    STEP_OF   (노드, 받는 타입) -> input

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
# tools/probe_out/), items.N.layerId 의 낱말이 population 두 도구의 level
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
    "get_age_profile": {
        "server_id": SERVER_ID,
        "tool": "population.getAgeProfile",
        "headline": "{arg} 연령대별 인구 구성을 조회했습니다.",
    },
    "get_population_trend": {
        "server_id": SERVER_ID,
        "tool": "population.getTrend",
        "headline": "{arg} 인구 변화 추이를 조회했습니다.",
    },
    "search_ev_stations": {
        "server_id": SERVER_ID,
        "tool": "ev.searchStations",
        "headline": "{arg} 전기차 충전소를 조회했습니다.",
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

    # **도구가 아닌 유일한 줄이다.** server_id · tool 대신 command 를 적는다.
    # plan 이 그 칸이 있는지로 갈라 vendor 에 넘길 step 대신 지도 명령을 만든다.
    #
    # 한 줄에 둘 다 적지 않는다. 도구도 부르고 명령도 내는 노드가 생기면 그때
    # 다시 정한다 — 지금 그런 노드가 없는데 미리 두면 안 쓰이는 분기가 남는다.
    "show_facility": {
        "command": SHOW_FACILITY_COMMAND,
        "headline": "{arg} 시설물을 화면에 띄웠습니다.",
    },
}

# (노드, 받는 타입) -> 그 자리에서 input 을 어떻게 채우는가. **온톨로지 밖이다.**
#
#   input        그 도구가 받는 input. @arg 와 $prev 를 쓸 수 있다
#   input_first  앞 단계가 없을 때의 input. 안 적으면 input 을 그대로 씀.
#                **저쪽 화면의 지도 문맥이 들어오는 자리다** (2026-08-28) —
#                지도 범위와 지점 좌표를 받는 열다섯 줄이 이것을 적었다.
#                그 자리에 오는 앞 노드는 보이는 범위 · 찍은 지점 둘뿐이고,
#                문맥이 없으면 resolve 가 그 후보를 아예 안 내놓는다
#   adapter      vendor 입력 어댑터 이름. 저절로 안 걸리는 도구에만 적는다
#   arg_field    (어미, 칸 이름). 발화에서 온 값이 그 어미로 끝나면 @arg 가
#                든 칸의 이름을 그것으로 바꾼다. **값 판단이 배선표에 들어오는
#                유일한 칸이다** — 왜 열었는지는 NOTES.md 「쉰째」에 있다
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
    #
    # 첫 자리(input_first)는 보이는 범위에서 곧장 온다. 저쪽 화면의
    # current-view-cctv 가 하는 것과 같은 일이다 — 그쪽도
    # $context.view.bbox 네 칸을 road.getCctv 에 그대로 넣는다
    # (KRRI_ASAP/ASAP-orchestrator/plugins/current-view-cctv/plugin.md 의
    #  Tool Input. 읽기만 했다).
    ("find_cctv", "map_extent"): {
        "input": {
            "minLon": f"{PREVIOUS_STEP}.minLon",
            "minLat": f"{PREVIOUS_STEP}.minLat",
            "maxLon": f"{PREVIOUS_STEP}.maxLon",
            "maxLat": f"{PREVIOUS_STEP}.maxLat",
        },
        "input_first": {
            "minLon": BBOX_FROM_CONTEXT[0],
            "minLat": BBOX_FROM_CONTEXT[1],
            "maxLon": BBOX_FROM_CONTEXT[2],
            "maxLat": BBOX_FROM_CONTEXT[3],
        },
    },
    # 첫 자리는 찍은 지점에서 곧장 온다. 저쪽 cctv-around-point 와 같은 꼴이고
    # (center + radiusMeters -> point_radius_to_bbox), 반경만 다르다 — 저쪽
    # 기본값은 1000m 이지만 우리는 이미 재본 값 RADIUS_METERS 를 쓴다.
    # 재보지 않은 숫자를 새로 들이지 않는다.
    ("find_cctv", "point"): {
        "input": {"location": f"{PREVIOUS_STEP}.location", "radiusMeters": RADIUS_METERS},
        "input_first": {"location": SELECTED_LOCATION, "radiusMeters": RADIUS_METERS},
    },

    ("get_railway_section", "place_name"): {"input": {"sectionName": SPOKEN_VALUE}},

    # 역명으로 볼지 노선명으로 볼지를 값이 정한다. 예전 주석은 "사람이 정할
    # 일이다" 였고 그 일이 왔다 (2026-08-29 「쉰째」).
    #
    # 둘을 함께 보내는 길은 닫혀 있다 — 저쪽이 두 절을 AND 로 이어서 같은
    # 값이면 0건이다 (2026-08-27 「서른다섯째」). 맞는 칸 하나만 보낸다.
    #
    # tools/check_inputs.py 의 ★ 표에서 railwayName(S) 은 안 사라진다.
    # 그 도구는 STEP_OF 를 정적으로 읽어 여기 적힌 stationName 만 본다.
    ("get_railway_lines", "place_name"): {
        "input": {"stationName": SPOKEN_VALUE},
        "arg_field": (RAILWAY_LINE_SUFFIX, "railwayName"),
    },
    ("get_railway_lines", "map_extent"): {
        "input": {"bbox": BBOX_FROM_PREVIOUS},
        "input_first": {"bbox": BBOX_FROM_CONTEXT},
    },

    # 첫 자리는 찍은 지점에서 곧장 온다. 앞 단계에서 오든 문맥에서 오든
    # 받는 모양은 lon · lat 로 같고 값의 출처만 다르다.
    ("find_admin_boundary_by_point", "point"): {
        "input": POINT_FROM_PREVIOUS,
        "input_first": POINT_FROM_CONTEXT,
    },
    ("find_election_district_by_point", "point"): {
        "input": POINT_FROM_PREVIOUS,
        "input_first": POINT_FROM_CONTEXT,
    },
    ("find_assembly_district_by_point", "point"): {
        "input": POINT_FROM_PREVIOUS,
        "input_first": POINT_FROM_CONTEXT,
    },
    ("find_assembly_pledge_district_by_point", "point"): {
        "input": POINT_FROM_PREVIOUS,
        "input_first": POINT_FROM_CONTEXT,
    },
    ("find_local_pledge_summary_by_point", "point"): {
        "input": POINT_FROM_PREVIOUS,
        "input_first": POINT_FROM_CONTEXT,
    },

    ("search_admin_boundaries", "keyword"): {"input": {"query": SPOKEN_VALUE}},
    ("search_admin_boundaries", "map_extent"): {
        "input": {"bbox": BBOX_FROM_PREVIOUS},
        "input_first": {"bbox": BBOX_FROM_CONTEXT},
    },

    ("get_vworld_boundaries", "keyword"): {"input": {"query": SPOKEN_VALUE}},
    ("get_vworld_boundaries", "map_extent"): {
        "input": {"bbox": BBOX_FROM_PREVIOUS},
        "input_first": {"bbox": BBOX_FROM_CONTEXT},
    },

    ("search_population_statistics", "keyword"): {"input": {"query": SPOKEN_VALUE}},
    ("search_population_statistics", "map_extent"): {
        "input": {"bbox": BBOX_FROM_PREVIOUS},
        "input_first": {"bbox": BBOX_FROM_CONTEXT},
    },

    # 인구 두 도구는 자리가 하나다. 앞 단계는 지점 행정구역 판별
    # (adminBoundary.findBoundaryByPoint)뿐이고, 발화에서 곧바로 오는 자리는
    # 없다 — 사람이 "43113" 이라고 말하지 않아 온톨로지에서
    # `말한 식별자 is-a 행정구역 코드` 를 뗐다. 그래서 level 이 발화에 없어
    # 못 적던 것이 풀린다. 받는 모양의 근거는 ADMIN_LEVEL_FROM_PREVIOUS 에 있다.
    ("get_age_profile", "admin_code"): {"input": ADMIN_LEVEL_FROM_PREVIOUS},
    ("get_population_trend", "admin_code"): {"input": ADMIN_LEVEL_FROM_PREVIOUS},

    # ev.searchStations 의 inputSchema 에 query 가 있다 —
    # "충전소명, 주소, 운영기관 키워드". 말한 키워드가 갈 자리가 여기다.
    ("search_ev_stations", "keyword"): {"input": {"query": SPOKEN_VALUE}},
    # bbox 넷이 전부 optional 이라 vendor 가 어댑터를 저절로 안 건다. 그래서
    # 이 줄에만 이름을 적는다. 오송역에서 83건이 나왔다(실측).
    #
    # 첫 자리(input_first)에는 어댑터를 안 건다. 보이는 범위는 이미 사각형이라
    # 중심 좌표로 되돌렸다가 다시 넓힐 까닭이 없고, ev.searchStations 는
    # bbox 를 평평한 네 수로 받는다. plan 이 어댑터를 거는 조건도 중심 좌표
    # 칸이 남아 있을 때뿐이라(_has_center) 이 벌에는 저절로 안 걸린다.
    #
    # ★ 그 말은 맞았는데 정작 보내던 것이 {"bbox": …} 한 칸이었다
    #   (2026-08-30 「예순째」에 고쳤다). ev.searchStations 의 inputSchema 에
    #   bbox 라는 칸은 없다 — minLon · minLat · maxLon · maxLat 평평한 넷이고
    #   넷 다 optional 이다(ASAP-mcp/main.py:532). 모르는 칸이라 버려져
    #   범위를 아무리 좁혀도 전국 92,821건에서 상한 500건이 왔다.
    #
    #   왜 어긋났나. a238b48 이 input_first 열다섯 줄을 한 번에 더하면서
    #   **옆의 input 이 쓰는 모양을 그대로 베끼고 $prev 만 문맥으로 바꿨다.**
    #   그 규칙이 나머지 열넷에는 맞았다 — 그 도구들의 input 이 이미
    #   {"bbox": BBOX_FROM_PREVIOUS} 이거나(선거 계열 · 노선 · 행정경계 · 인구)
    #   평평한 넷이었다(road.getCctv). 이 줄만 옆의 input 이
    #   center + radiusMeters + 어댑터라 베낄 bbox 꼴이 없었고, 그래서 옆줄
    #   대신 일반 관용구인 {"bbox": …} 로 적었다. 바로 위에 스키마를 옳게
    #   적어 놓고도 줄이 그것을 안 따랐다.
    #
    #   같은 자리 넷(get_railway_lines · search_admin_boundaries ·
    #   get_vworld_boundaries · search_population_statistics)은 **안 고쳤다.**
    #   그 넷은 스키마가 진짜로 bbox 배열을 받는다(2026-08-30 확인,
    #   NOTES.md 「예순째」의 스키마 확인 표).
    ("search_ev_stations", "map_extent"): {
        "input": {"center": f"{PREVIOUS_STEP}.location", "radiusMeters": RADIUS_METERS},
        "adapter": POINT_RADIUS_TO_BBOX,
        "input_first": {
            "minLon": BBOX_FROM_CONTEXT[0],
            "minLat": BBOX_FROM_CONTEXT[1],
            "maxLon": BBOX_FROM_CONTEXT[2],
            "maxLat": BBOX_FROM_CONTEXT[3],
        },
    },

    # ev.getStation 의 statId 는 **stationId 이지 id 가 아니다**(2026-08-23 실측).
    #
    #   statId="PL033780"            item 이 온다
    #   statId="ev_station_PL033780" item null · 0건 ·
    #                                "충전소 ev_station_PL033780를 찾지 못했거나…"
    #
    # tools/probe_out/ev.getStation.statId-stationId.json 과
    # tools/probe_out/ev.getStation.statId-id.json 이 그 둘이다.
    #
    # 자리가 하나다. 발화에서 곧바로 오는 자리는
    # `말한 식별자 is-a 충전소 번호` 를 떼면서 사라졌다(2026-08-26) —
    # 사람은 "PL033780" 이라고 말하지 않는다. 앞 단계는 전기차 충전소 검색뿐이다.
    ("get_ev_station", "station_id"): {
        "input": {"statId": f"{PREVIOUS_STEP}.items.0.stationId"},
    },

    # ── 발화에서 온 말로 찾는 것 ────────────────────────────────────
    #
    # 노드와 도구의 짝은 온톨로지 노드 description 과 tools.json description 을
    # 맞대어 정했다. 아래 셋은 2026-08-22 실측으로 query 가 실제로 거르는 것도
    # 확인했다 — 인자 없이 부르면 254 · 254 · 476 건이고 query="청주" 로 부르면
    # 4 · 5 건, query="철도" 로 부르면 206 건이다.
    ("search_election_districts", "keyword"): {"input": {"query": SPOKEN_VALUE}},

    ("search_assembly_districts", "keyword"): {"input": {"query": SPOKEN_VALUE}},
    ("search_assembly_districts", "map_extent"): {
        "input": {"bbox": BBOX_FROM_PREVIOUS},
        "input_first": {"bbox": BBOX_FROM_CONTEXT},
    },

    ("search_assembly_pledge_districts", "keyword"): {"input": {"query": SPOKEN_VALUE}},
    ("search_assembly_pledge_districts", "map_extent"): {
        "input": {"bbox": BBOX_FROM_PREVIOUS},
        "input_first": {"bbox": BBOX_FROM_CONTEXT},
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

    # ── 지방선거 교통 공약 요약 : 배선 줄이 하나다 ────────────────
    #
    #   recipe_056  말한 장소 -> 좌표 -> 행정구역 판별 -> 공약 요약
    #   recipe_052  찍은 지점 -> 행정구역 판별 -> 공약 요약
    #
    # 경로는 둘인데 앞 노드는 둘 다 지점 행정구역 판별이라 줄은 하나다.
    # 발화에서 곧바로 오는 자리는 없다. `말한 식별자 is-a 행정구역 코드` 를
    # 떼면서 그 경로가 사라졌다.
    #
    # 2026-08-24 에 {sidoCode: "43"} 을 눌렀다. query.sidoCode 로 되받았고
    # status 는 not_found 인데 그것은 **저쪽 데이터가 미적재**여서다
    # (dataset.available false · featureCount 0). 인자는 파싱됐다.
    #
    # 앞 단계는 adminBoundary.findBoundaryByPoint 의 items.0 이다.
    # 여섯 지점(오송·강남·부산·제주·금산·세종)에서 items 가 늘 3건이고
    # 순서가 sido -> sigungu -> emd 로 고정이었다. items.0 이 시도이고
    # 그 code 가 두 자리 시도 코드라 sidoCode 와 맞는다. 세종처럼 시군구가
    # 없는 곳도 sigungu 자리를 같은 이름으로 채워 순서가 안 밀린다.
    # 응답 전문은 tools/probe_out/ 에 있다.
    ("get_local_pledge_summary", "admin_code"): {
        "input": {"sidoCode": f"{PREVIOUS_STEP}.items.0.code"},
    },

    # 아래 둘은 배선이 맞는데 도구 쪽이 지금 비어 있거나 막혀 있다(2026-08-22
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
        "input_first": {"bbox": BBOX_FROM_CONTEXT},
    },

    # knowledge.query : 문서 둘이 들어 있다(2026-08-26 실측 — 철도안전법 47쪽 ·
    #   철도안전법 시행규칙 52쪽). "지식베이스가 비었다" 는 2026-08-22 기록이고
    #   그 뒤 문서가 적재됐다.
    #
    #   k 는 돌려받을 조각 수다(tools.json, 기본 4). 6 인 근거 : "철도 안전
    #   교육" 실측에서 k=4 는 시행규칙 조각이 1건인데 k=6 은 법 4 · 시행규칙 2
    #   로 두 문서가 다 보인다. k=10 은 5 · 5 로 더 고르지만 화면은 조각
    #   두셋만 실으므로 응답만 무거워진다. 문서가 늘어 보여줄 문서가 조각
    #   두셋으로 안 덮이면 그때 올린다 (NOTES.md 「서른한째」).
    #
    #   문서를 지정하는 filter_docs 는 안 보낸다. 발화 해석이 인자를 하나만
    #   돌려줘 문서 이름과 검색어를 따로 못 뽑는데, 의미 검색이라 검색어에
    #   문서 이름이 섞이면 그 문서 조각이 위로 온다(2026-08-26 실측 —
    #   "철도안전법 시행규칙 교육" k=4 에서 시행규칙 4/4건). NOTES.md 「열린 과제」.
    ("search_documents", "keyword"): {"input": {"query": SPOKEN_VALUE, "k": 6}},

    # web.search : 실패. "MCP tool 'web-search/web.search' is not applied for
    #   this user." 데이터가 없는 것이 아니라 우리 user_context 에 web-search
    #   서버가 안 열려 있는 것이다. KRRI_ASAP 쪽 권한이라 우리가 못 연다.
    ("web_search", "keyword"): {"input": {"query": SPOKEN_VALUE}},

    # 이 input 은 도구 인자가 아니라 지도 명령의 args 다. 칸 이름은 저쪽
    # 화면이 읽는 이름 그대로여야 한다 (useChat.getFacilityName 이
    # args.facilityName 만 본다).
    #
    # **발화에서 온 값을 그대로 넘긴다.** 저쪽은 skill.md 의 「Facility Aliases」
    # 표로 낱말을 시설물명으로 바꾼다("제3터널" -> "시험 제3터널"). 그 표는
    # 저쪽 설정이고 우리 온톨로지에는 그것을 둘 자리가 없어 베끼지 않았다.
    # NOTES.md 「마흔아홉째」에 남은 격차로 적었다.
    ("show_facility", "place_name"): {"input": {"facilityName": SPOKEN_VALUE}},
}

# 아직 배선을 안 적은 (노드 × 받는 타입)과 그 이유. 다음 사람이 왜 비어 있는지
# 알아야 한다. tools/check_wiring.py 가 이것을 센다. 하나뿐이다.
#
# 응답의 어느 칸에 그 값이 오는지 아직 모른다
#
#   web_fetch × 웹 주소
#
#   web.fetch 의 required 는 url 하나이고 그 값은 앞 단계인 web.search 의
#   결과에서 꺼내야 한다. 그런데 web.search 가 권한에 막혀
#   ("MCP tool 'web-search/web.search' is not applied for this user")
#   응답 모양을 한 번도 못 봤다. **모르면 배선을 적지 않는다.**
#   예전에는 {url: @arg} 라고 적혀 있었다. 발화에서 온 말을 URL 로 쓰는
#   것이라 부르면 반드시 틀린다. 지어낸 배선이라 지웠다.
#   recipe 050(말한 키워드 -> 웹 검색 -> 웹 문서 가져오기)이 여기 걸린다.
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
    제약  첫 step 의 input 에 $prev 를 쓸 수는 있으나 그 칸은 빠진 채로 나간다.
          required 인 칸이면 도구가 거부하고 그것은 배선이 틀린 것이다
    이력  예전에는 배선이 노드당 한 줄이었고 첫 step 이 $prev 를 가리키면
          _filled 이 그 칸을 빼고 불렀음. recipe 012 · 013 이 그것에 걸려
          발화에서 온 값을 버리고 전국을 검색했음. 이제 그 자리는 키워드 줄이
          걸림. _filled 의 이력 절 참고
    """
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
