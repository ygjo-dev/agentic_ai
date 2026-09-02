"""동 하나가 그 구역에 얼마나 걸치는지 재서 「일부」 표시를 붙인다.

**왜 재나.** 도달 지역 · 음영 지역 줄에는 동 이름만 나온다. 그 동의 거의
전부가 구역에 드는 곳과 귀퉁이만 스치는 곳이 화면에서 똑같이 보인다. 의왕역
30분 겹에서 고천동은 99.17% 가 도달 범위 안이고 세류동은 0.16% 다. 두 이름이
나란히 놓이면 읽는 사람은 둘을 같은 것으로 읽는다.

**무엇을 재나.**

    걸침 비율 = (동 경계 ∩ 구역) 의 넓이 / 동 경계의 넓이

구역은 줄마다 다르다. 도달 지역 줄은 **도달권 폴리곤**이고, 음영 지역 줄은
**볼록 껍질 − 도달권**이다. 넓이 29.96 · 18.42 를 낸 것과 같은 도형을 봐야
같은 줄의 이름과 수가 같은 것을 말한다.

**shapely 로 잰다** (2026-09-02 에 `.venv` 에 넣었다. shapely 2.1.2).
교집합 넓이를 바로 재므로 격자로 어림하지 않는다 — 어림하면 문턱 언저리의
동이 격자 간격에 따라 붙었다 떨어졌다 한다.

★ **경위도를 그대로 넣는다. 미터로 안 바꾼다.** 이 파일이 내놓는 것은 넓이가
아니라 **넓이의 비**다. 경도에 cos(위도) 를 곱하는 것은 x 축에 상수를 곱하는
일이고, 분자와 분모가 함께 그 상수배가 되므로 **비는 글자 그대로 안 변한다.**
구면 면적소의 cos 이 동 하나 안(위도 0.03°)에서 변하는 몫은 0.03% 다.
`geometry_area` 를 안 쓰는 까닭이 이것이다 — 그 함수는 도형 하나의 넓이를
구면에서 재고, 여기서 필요한 것은 같은 자리에 놓인 두 도형의 비다.

**경계는 시군구마다 한 번 부른다.** `adminBoundary.searchBoundaries` 의 `code`
는 **접두어**라 시군구 다섯 자리에 `layer="emd"` 를 주면 그 시군구 읍면동이
한 번에 온다 (실측 : `41410` 군포시 -> 9건 · `41430` 의왕시 -> 11건).
인구를 세는 자리(execution/district_population)와 같은 길이다. **다만 칸
이름이 다르다** — 인구 도구는 `level` 이고 이 도구는 `layer` 다. `level` 을
보내면 조용히 무시되고 기본값 `sigungu` 로 떨어져 시군구 한 줄만 온다
(실측 : `code="41410"` · `level="emd"` -> 군포시 1건).

★ **`includeGeometry=true` 를 안 보내면 도형이 안 온다.** 기본이 false 라
코드 · 이름 · 계층 요약만 온다.

★ **`simplifyM` 을 안 쓴다.** 호출이 가벼워지는지 재 봤는데 **얻을 것이 없다**
(2026-09-02 실측, 군포시 9동).

    안 줄임      꼭짓점 743   28,126 바이트   0.11초
    simplifyM=10        923   32,589 바이트   0.08초   <- 되레 는다
    simplifyM=30        463   21,187 바이트   0.07초
    simplifyM=100       232   15,485 바이트   0.07초

경계가 처음부터 성기다(동 하나에 꼭짓점 여든 남짓). 관문은 바이트가 아니라
**호출 수**이고 그것은 simplifyM 으로 안 준다. 줄이면 걸침 비율만 흔들린다.

**못 재면 아무것도 안 붙인다.** 경계를 못 받은 동 · 코드가 안 실려 온 동은
이름만 그대로 낸다. 「(일부)」가 안 붙은 것이 「전부 걸친다」는 뜻이 되지만,
안 잰 것을 잰 것처럼 적는 것보다 낫다.
"""

import asyncio

from execution import district_population, reach_districts, step_service
from vendor_to_be_deleted.asap.workflow_answer import reach_features

# ★ 「일부」를 붙이는 문턱. **사람이 정한 값이다. 재서 나온 수가 아니다.**
#
# 「그 동이 통째로 들어야 이름만 적고, 그에 못 미치면 일부라고 부른다」는 뜻이다.
# 데이터가 여기서 갈린다는 근거는 없다. 바꾸려면 이 한 줄만 고치면 된다.
#
# 처음에 0.30 으로 뒀다가 0.90 으로 올렸다(2026-09-02). 0.30 에서는 화면에
# 나가는 열 곳이 46.74~99.17% 라 **도달 지역 줄에 하나도 안 붙었다** — 그 열을
# 자르는 차례(격자 점 수)가 걸침의 어림이라 앞자리에 큰 것만 남는 탓이다.
# 의왕역 30분 겹에서 동마다 몇 %가 나왔는지는 NOTES.md 「여든넷째」에 있다.
PARTIAL_SHARE = 0.90

# 경계를 물을 노드. 배선표에서 server_id · tool 을 이 이름으로 찾는다.
#
# 도구 이름을 여기 안 적는다. 배선을 고치면 여기가 따라 움직인다.
BOUNDARY_NODE = "search_admin_boundaries"

# 물을 행정구역 층과 한 번에 받을 최대 건수.
#
# ★ 칸 이름이 `layer` 다. 인구 도구의 `level` 과 다르다 (모듈 주석).
# 시군구 하나의 읍면동을 한 번에 다 받아야 한다. 잘리면 그 시군구의 뒤쪽
# 동이 조용히 「못 잰 동」이 되어 「(일부)」가 안 붙는다.
BOUNDARY_LAYER = "emd"
BOUNDARY_LIMIT = 500

# 도형을 함께 달라는 표시. 기본이 false 라 안 보내면 요약만 온다.
BOUNDARY_GEOMETRY = True

# 응답에서 읽을 칸. 도형은 items 가 아니라 features 로 온다.
FEATURES_KEY = "features"
PROPERTIES_KEY = "properties"
GEOMETRY_KEY = "geometry"
FEATURE_CODE_KEY = "code"

# 동 한 줄에 얹는 칸. workflow_answer 가 PARTIAL_KEY 를 읽어 꼬리표를 붙인다.
#
# **판정을 여기서 한다.** 화면이 문턱과 견주게 두면 사람이 정한 값이 재는
# 쪽과 그리는 쪽 둘로 갈린다. 답을 짓는 자리(vendor_to_be_deleted)가
# execution 을 거꾸로 부르게 되는 것도 막는다.
#
# 잰 비율을 함께 담는다. 화면은 안 쓰지만 결과를 들여다볼 때 왜 그 동에
# 「(일부)」가 붙었는지가 그 자리에 있어야 한다.
SHARE_KEY = "share"
PARTIAL_KEY = "partial"

# 껍질을 담아 둔 칸. shadow_districts 가 넣은 것을 그대로 읽는다.
HULL_KEY = "hull"


async def attach(
    item: dict, previous: dict, user_context: dict, sent: int, cache: dict
) -> tuple:
    """trace 항목 하나의 동들에 걸침 비율을 얹음. (항목, 창에 보낸 수).

    입력  reach_districts · shadow_districts 가 낸 항목 · 도달권 계산의 응답 ·
          권한 · 이 창에 이미 보낸 건수 · 발화 하나가 이어 쓰는 경계 보관
    출력  같은 항목. 잰 동에는 SHARE_KEY 와 PARTIAL_KEY 가 붙음
    규칙  동 목록이 놓인 자리를 인구와 같은 자리에서 찾음. 음영 지역을 먼저 봄
          잴 구역이 줄마다 다름. 도달 지역은 도달권, 음영 지역은 껍질 − 도달권
          문턱과 견주는 일을 여기서 함. 화면은 판정을 읽기만 함
          못 잰 동에는 아무것도 안 얹음. 화면이 이름만 냄
    제약  항목을 새로 만들지 않는다.
          부르는 쪽이 이미 id 를 붙여 두었고 인구도 그 자리에 얹혀 있다
    """
    found = district_population.holder(item.get("result"))
    if found is None:
        return item, sent

    holder, districts = found
    region = _region(holder, previous)
    if region is None:
        return item, sent

    shares, sent = await measure(districts, region, user_context, sent, cache)
    for entry in districts:
        share = shares.get(entry.get(reach_districts.EMD_CODE_KEY))
        if share is not None:
            entry[SHARE_KEY] = share
            entry[PARTIAL_KEY] = share < PARTIAL_SHARE
    return item, sent


def _region(holder: dict, previous: dict):
    """그 줄이 말하는 구역의 shapely 도형. 못 만들면 None.

    규칙  껍질이 실려 있으면 음영 지역 줄임. 껍질에서 도달권을 뺌
          없으면 도달 지역 줄임. 도달권 그대로임
          제일 큰 겹 하나를 봄. 넓이를 낸 자리와 같은 겹이어야 함
    """
    features = reach_features(previous)
    if not features:
        return None
    reach = _shape(max(features, key=lambda pair: pair[0])[1])
    if reach is None:
        return None

    hull = _shape(holder.get(HULL_KEY))
    if hull is None:
        return reach
    shadow = hull.difference(reach)
    return shadow if not shadow.is_empty else None


async def measure(
    districts: list, region, user_context: dict, sent: int, cache: dict
) -> tuple:
    """동마다 구역에 걸치는 비율. ({읍면동 코드: 비율}, 창에 보낸 수).

    입력  reach_districts.districts_in_order 가 낸 목록 · 잴 구역의 도형 ·
          권한 · 이 창에 이미 보낸 건수 · 발화 하나가 이어 쓰는 경계 보관
    출력  잰 동만 담은 dict. 한 곳도 못 재면 빈 dict
    규칙  시군구마다 한 번만 부름. 같은 시군구가 보관에 있으면 안 부름
          보관을 발화 하나가 sampled 노드 둘에 걸쳐 함께 씀. 도달 지역과
          음영 지역이 같은 시군구를 많이 나눠 가짐
          CHUNK 건마다 창이 빌 때까지 쉼. 점 뽑기 · 인구와 같은 셈을 이어 씀
          코드가 없는 동은 못 잼. 이름으로는 경계를 못 고름
          넓이가 0인 동은 건너뜀. 나누면 터짐
    제약  동마다 부르지 않는다.
          시군구 접두어 한 번에 그 읍면동 경계가 전부 온다. 동마다 부르면
          호출이 여섯에서 마흔으로 는다
    """
    tool = step_service.TOOL_OF.get(BOUNDARY_NODE)
    if tool is None or region is None:
        return {}, sent

    wanted = district_population.wanted(districts)
    if not wanted:
        return {}, sent

    for sigungu_code in dict.fromkeys(code for code, _ in wanted):
        if sigungu_code in cache:
            continue
        if sent >= reach_districts.CHUNK:
            await asyncio.sleep(reach_districts.WINDOW_WAIT_S)
            sent = 0
        result, waited = await reach_districts.ask(
            tool,
            {
                "code": sigungu_code,
                "layer": BOUNDARY_LAYER,
                "limit": BOUNDARY_LIMIT,
                "includeGeometry": BOUNDARY_GEOMETRY,
            },
            user_context,
        )
        sent = 1 if waited else sent + 1
        cache[sigungu_code] = _read(result)

    shares = {}
    for sigungu_code, emd_code in wanted:
        boundary = cache.get(sigungu_code, {}).get(emd_code)
        if boundary is None or boundary.area <= 0:
            continue
        shares[emd_code] = boundary.intersection(region).area / boundary.area
    return shares, sent


def _read(result) -> dict:
    """시군구 응답 하나를 {읍면동 코드: 도형} 으로. 못 읽으면 빈 칸.

    규칙  도형은 items 가 아니라 features 로 옴. 코드는 properties 에 있음
          못 세운 도형은 안 담음. 그 동이 「못 잰 동」이 됨
    """
    if not isinstance(result, dict):
        return {}
    features = result.get(FEATURES_KEY)
    if not isinstance(features, list):
        return {}

    boundaries = {}
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get(PROPERTIES_KEY)
        if not isinstance(properties, dict):
            continue
        code = properties.get(FEATURE_CODE_KEY)
        polygon = _shape(feature.get(GEOMETRY_KEY))
        if isinstance(code, str) and code and polygon is not None:
            boundaries[code] = polygon
    return boundaries


def _shape(geometry):
    """GeoJSON 한 벌을 shapely 도형으로. 못 세우면 None.

    규칙  스스로 겹치는 고리는 buffer(0) 으로 폄. 행정경계 shapefile 에
          그런 것이 섞여 있고, 안 펴면 intersection 이 터짐
          빈 도형은 None. 넓이가 0이라 나눌 수 없음
    제약  여기서 미터로 안 바꾼다.
          내놓는 것이 넓이가 아니라 넓이의 비다 (모듈 주석)
    """
    if not isinstance(geometry, dict):
        return None
    try:
        from shapely.geometry import shape

        polygon = shape(geometry)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        return None if polygon.is_empty else polygon
    except Exception:
        return None
