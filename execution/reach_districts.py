"""도달권 폴리곤 안에 어느 행정동이 드는지 모은다. **vendor 를 안 지나는 실행이다.**

**왜 vendor 를 안 지나나.** `adminBoundary.findBoundaryByPoint` 는 점 하나에
답한다. 구역 하나가 어느 동들에 걸치는지 알려면 그 안에서 점을 여럿 뽑아
각각 불러야 하는데, vendor 의 `_execute_generic_mcp_workflow` 는 step 하나에
호출 하나다. 게다가 **부를 점은 앞 단계 응답이 와야 알 수 있다** — 도달권
폴리곤이 손에 들어오기 전에는 step 으로 적을 좌표가 없다. 그래서 배선의
`sampled` 표시가 붙은 노드는 execute_service 가 vendor 뒤에 여기로 보낸다.

**Gateway 가 60초에 100건에서 끊는다** (2026-09-01 실측 : 창이 빈 뒤 한 건씩
세어 100건째 다음이 429. 100건을 보내는 데 7.6초밖에 안 걸리므로 시간이 아니라
건수가 자다. `KRRI_ASAP/ASAP-Gateway/src/middleware/rateLimit.ts` 와 그
컨테이너의 `RATE_LIMIT_MAX=100` · `RATE_LIMIT_WINDOW_MS=60000` 이 근거다).

**예산이 그 한도를 넘는다. 그래서 나눠 부른다.** 예산 118건 + geocode 1 +
isochrone 1 = 120 건이라 한 창에 안 들어간다. CHUNK 건을 보내고 창이 빌 때까지
쉬었다가 나머지를 보낸다. 429 를 맞으면 한 번 더 쉬고 그 점만 다시 부른다 —
express-rate-limit 의 창이 고정창이라 언제 열리는지 우리가 모르고, 리허설에서
같은 발화를 이어 치면 앞 발화가 쓴 건수가 아직 창에 남아 있기 때문이다.

**격자 간격을 폴리곤이 정한다.** 간격을 상수로 박으면 구역이 넓을 때 점이
수백 개가 되어 창을 여러 번 기다리고, 좁을 때는 한두 개만 남아 걸치는 동을
통째로 빠뜨린다. 넓이를 세로 나누어 `간격 = √(넓이 / 예산)` 으로 잡으면
구역이 어떻든 점 수가 예산 언저리에서 논다.

**빠뜨리는 것이 있다. 그것을 알고 쓴다** (2026-09-01 실측, NOTES.md
「일흔아홉째」). 의왕역 30분 겹에서 격자를 좁혀 가며 센 것이다.

    1500m   13점   동 12
    1000m   29점   동 17
     750m   51점   동 17
     500m  118점   동 20     <- 지금 예산이 서는 자리
     250m  482점   동 25     <- 바닥. 넓이추정 30.12 km² 로 실측 29.96 과 맞다

**500m 에서도 다섯을 못 찾는다** — 군포 대야미동 · 수원 권선구 장지동 ·
수원 장안구 정자동 · 수원 팔달구 매산로1가 · 안양 만안구 안양동. 전부 겹의
가장자리에 조금 걸치는 동이라 격자 사이로 빠진다. 250m 로 내리면 482건이고
창을 다섯 번 기다려야 해서 시연에서 쓸 수 없다.

**그래서 화면에 수를 안 쓴다.** 「스물이다」도 「외 N곳」도 우리가 찾은 수이지
실제 수가 아니다. 이름만 늘어놓고 세지 않는다.
"""

import asyncio
import math

from vendor_to_be_deleted.asap.mcp_client import mcp_client
from vendor_to_be_deleted.asap.workflow_answer import (
    DISTRICTS_KEY,
    reach_features,
    geometry_area,
)

# 한 발화에서 이 노드가 쓸 호출 수. 위 모듈 주석의 예산이다.
#
# 118 은 의왕역 30분 겹에서 500m 격자가 되는 값이다(√(29.96 km² / 118) = 504m).
# 32(968m)에서는 동 열다섯을 찾았고 118 에서는 스물을 찾는다.
SAMPLE_BUDGET = 118

# 한 창에 보낼 최대 건수.
#
# 창이 빈 뒤 한 건씩 세면 **정확히 100건이 지나고 101번째가 429** 다
# (2026-09-01 실측 : 100건에 9.8초. 그 사이 창은 안 열린다). 같은 발화가
# geocode 와 isochrone 으로 두 건을 이미 썼으므로 98이 남고, 셋을 더 뺐다.
CHUNK = 95

# 창이 비기를 기다리는 시간(초). 창이 60초라 조금 더 준다.
#
# 고정창이라 언제 열리는지 우리가 모른다. 창 길이만큼 기다리면 어느
# 시작점에서든 반드시 새 창이다.
WINDOW_WAIT_S = 62

# 한도에 걸린 응답을 가르는 조각. mcp_client 가 상태 코드를 안 올리고
# 본문을 문자열에 담아 오므로 문자열에서 가른다 (실측 : "Client error
# '429 Too Many Requests' for url …").
RATE_LIMIT_MARK = "429"

# 격자가 이보다 촘촘해지지 않게 막는 바닥. 폴리곤이 아주 작을 때 간격이
# 0 으로 수렴해 같은 점을 되풀이해 부르는 것을 막는다.
MIN_STEP_M = 50.0

# 위도 1도의 길이(m). 경도는 위도에 따라 줄어들어 cos 을 곱한다.
METERS_PER_DEGREE_LAT = 110574.0
METERS_PER_DEGREE_LON = 111320.0

# 응답에서 읽을 것. 층 이름으로 고른다.
#
# items 의 차례(시도 · 시군구 · 읍면동)로 집지 않는다. 바다를 찍으면 0건이고
# (probe_out 의 서해바다·동해바다) 층이 빠진 채로 오는 자리가 있을 수 있는데,
# 차례로 집으면 그때 엉뚱한 층을 읍면동으로 읽는다.
ITEMS_KEY = "items"
LAYER_KEY = "layerId"
NAME_KEY = "name"
SIGUNGU_LAYER = "sigungu"
EMD_LAYER = "emd"

SIGUNGU_KEY = "sigungu"
EMD_KEY = "emd"


async def run(tool: dict, previous: dict, user_context: dict, sent: int = 0) -> tuple:
    """도달권 안의 행정동을 모아 trace 항목 하나로. (항목, 창에 보낸 수).

    입력  TOOL_OF 한 줄 · 앞 단계(도달권 계산)의 응답 · Gateway 에 보낼 권한 ·
          이 창에 이미 보낸 건수. 앞 sampled 노드가 쓰고 넘긴 것임
    출력  vendor 의 trace 항목과 같은 모양. result 아니면 error 하나를 담음.
          id 는 안 붙임. 부르는 쪽이 노드 id 로 붙임
          창 셈을 함께 냄. 다음 sampled 노드가 이어 세야 함
    규칙  제일 큰 겹 하나만 봄. 겹이 누적이라 안쪽 겹은 이미 그 안에 듦.
          넓이를 재는 자리와 같은 겹을 봐야 두 줄이 같은 것을 말함
          CHUNK 건마다 창이 빌 때까지 쉼. 예산이 Gateway 한도보다 큼
          점 하나가 터져도 멈추지 않음. 나머지로 답함
          한 점도 못 얻으면 error 를 담음. 빈 목록을 성공으로 내놓으면
          「걸치는 동이 없다」는 거짓이 화면에 박힘
          같은 동이 여러 점에서 나오면 한 번만 담음. 점이 많이 떨어진
          차례로 앞에 둠 — 넓게 걸치는 곳이 먼저 읽혀야 함
    제약  점 수를 화면에 내보내지 않는다.
          몇 점이 걸렸는지는 격자 간격이 정하는 값이라 사람이 읽어서 뜻을
          알 수 없다. 차례를 정하는 데만 쓴다
    """
    geometry = _widest(previous)
    if geometry is None:
        return _failed(tool, "도달권 폴리곤이 없어 행정동을 찾지 못했습니다."), sent

    points = sample_points(geometry, SAMPLE_BUDGET)
    if not points:
        return _failed(tool, "도달권 안에서 찍을 지점을 얻지 못했습니다."), sent

    hits, failures, sent = await gather(tool, points, user_context, sent)
    if not hits:
        return _failed(tool, "도달권 안의 행정동을 찾지 못했습니다."), sent

    return {
        "server_id": tool["server_id"],
        "tool": tool["tool"],
        "input": {"points": len(points), "failed": failures},
        "result": {DISTRICTS_KEY: districts_in_order(hits)},
    }, sent


async def gather(tool: dict, points: list, user_context: dict, sent: int) -> tuple:
    """점들을 하나씩 물어 동을 셈. (동별 점 수, 실패한 점 수, 창에 보낸 수).

    입력  TOOL_OF 한 줄 · (경도, 위도) 목록 · 권한 · 이 창에 이미 보낸 건수
    출력  {(시군구, 읍면동): 걸린 점 수} · 못 얻은 점 수 · 창에 보낸 건수
    규칙  CHUNK 건마다 창이 빌 때까지 쉬고 셈을 0으로 되돌림
          _ask 가 창을 기다렸다고 하면 그때도 셈을 되돌림. 새 창이 열린 것임
          점 하나가 터져도 멈추지 않음. 나머지로 답함
    제약  창 셈을 이 함수 안에서 새로 시작하지 않는다.
          한 발화가 sampled 노드를 둘 지난다. 뒤엣것이 0부터 다시 세면 앞
          노드가 이미 쓴 건수를 모른 채로 보내 한도에 걸린다
    """
    hits: dict = {}
    failures = 0
    for lon, lat in points:
        if sent >= CHUNK:
            await asyncio.sleep(WINDOW_WAIT_S)
            sent = 0
        result, waited = await _ask(tool, lon, lat, user_context)
        sent = 1 if waited else sent + 1
        if result is None:
            failures += 1
            continue
        found = _district_of(result)
        if found:
            hits[found] = hits.get(found, 0) + 1
    return hits, failures, sent


def districts_in_order(hits: dict) -> list:
    """동별 점 수를 화면이 읽는 목록으로. 점이 많이 걸린 차례.

    출력  [{sigungu, emd}, …]
    제약  점 수를 함께 내보내지 않는다.
          격자 간격이 정하는 값이라 사람이 읽어서 뜻을 알 수 없다
    """
    ordered = sorted(hits.items(), key=lambda pair: -pair[1])
    return [{SIGUNGU_KEY: sigungu, EMD_KEY: emd} for (sigungu, emd), _ in ordered]


async def _ask(tool: dict, lon: float, lat: float, user_context: dict) -> tuple:
    """점 하나를 물음. (응답, 창을 기다렸는가). 못 얻으면 응답이 None.

    규칙  한도에 걸리면 창이 빌 때까지 쉬고 한 번만 더 부름. 고정창이라
          언제 열리는지 모르고, 앞 발화가 쓴 건수가 창에 남아 있을 수 있음
          두 번째도 터지면 응답이 None. 그 점만 버리고 나머지로 답함
          기다렸다고 알림. 부르는 쪽이 창 셈을 0으로 되돌려야 함
    제약  되풀이해 다시 부르지 않는다.
          한도에 걸린 채로 계속 두드리면 창이 열리지 않는다
    이력  기다렸다는 것을 안 알렸음. 창이 새로 열렸는데도 부르는 쪽이 옛
          셈을 이어 세어 곧 또 기다렸고, 한 점이 터질 때마다 창 하나씩을
          기다려 백열여덟 점이 끝나지 않았음 (2026-09-01)
    """
    waited = False
    for attempt in (0, 1):
        try:
            result = mcp_client.execute_tool(
                tool["tool"],
                {"lon": lon, "lat": lat},
                user_context=user_context,
                server_id=tool["server_id"],
            )
            return result, waited
        except Exception as exc:
            if attempt or not _rate_limited(exc):
                return None, waited
            await asyncio.sleep(WINDOW_WAIT_S)
            waited = True
    return None, waited


def _rate_limited(exc: Exception) -> bool:
    """한도에 걸린 것인가.

    규칙  mcp_client 가 상태 코드를 안 올리고 본문을 문자열에 담아 옴.
          그 문자열에서 가름
    """
    return RATE_LIMIT_MARK in str(exc)


def sample_points(geometry: dict, budget: int) -> list:
    """폴리곤 안에서 부를 점들. 못 뽑으면 빈 목록.

    입력  GeoJSON Polygon 또는 MultiPolygon · 부를 수 있는 횟수
    출력  (경도, 위도) 목록. budget 을 넘지 않음
    규칙  간격을 폴리곤 넓이가 정함. √(넓이 / 예산) 이라 구역이 어떻든 점 수가
          예산 언저리에 섬
          bbox 를 격자로 훑고 폴리곤 안에 든 점만 남김. 격자 칸의 가운데를
          찍음 — 테두리를 찍으면 옆 동이 나옴
          budget 을 넘으면 앞에서부터 잘라 냄. 격자 차례가 남북·동서로
          훑는 차례라 자른 뒤에도 한쪽에 쏠리지 않음
          구멍(고리 둘째부터)은 뺌
    제약  간격을 상수로 박지 않는다.
          넓은 구역에서 429 를 맞고 좁은 구역에서 동을 통째로 빠뜨린다
    """
    polygons = rings(geometry)
    if not polygons:
        return []

    area = geometry_area(geometry)
    if area <= 0:
        return []

    step = max(math.sqrt(area / budget), MIN_STEP_M)
    xs = [x for polygon in polygons for x, _ in polygon[0]]
    ys = [y for polygon in polygons for _, y in polygon[0]]
    min_lon, max_lon = min(xs), max(xs)
    min_lat, max_lat = min(ys), max(ys)

    middle = math.radians((min_lat + max_lat) / 2)
    delta_lat = step / METERS_PER_DEGREE_LAT
    delta_lon = step / (METERS_PER_DEGREE_LON * max(math.cos(middle), 0.01))

    points = []
    lat = min_lat + delta_lat / 2
    while lat < max_lat and len(points) < budget:
        lon = min_lon + delta_lon / 2
        while lon < max_lon and len(points) < budget:
            if inside(lon, lat, polygons):
                points.append((round(lon, 6), round(lat, 6)))
            lon += delta_lon
        lat += delta_lat
    return points


def _widest(previous: dict):
    """제일 큰 겹의 도형. 도달권 응답이 아니면 None.

    규칙  넓이를 재는 자리와 같은 겹을 고름. cutoff 가 제일 큰 것임
    """
    features = reach_features(previous)
    if not features:
        return None
    return max(features, key=lambda pair: pair[0])[1]


def rings(geometry) -> list:
    """도형을 폴리곤 목록으로. 폴리곤이 아니면 빈 목록.

    출력  [[바깥고리, 구멍…], …]
    """
    if not isinstance(geometry, dict):
        return []
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list):
        return []
    if kind == "Polygon":
        return [coordinates]
    if kind == "MultiPolygon":
        return [polygon for polygon in coordinates if isinstance(polygon, list)]
    return []


def inside(lon: float, lat: float, polygons: list) -> bool:
    """그 점이 폴리곤 안인가.

    규칙  바깥 고리 안이고 어느 구멍에도 안 들면 참
    """
    return any(
        _in_ring(lon, lat, polygon[0])
        and not any(_in_ring(lon, lat, hole) for hole in polygon[1:])
        for polygon in polygons
        if polygon
    )


def _in_ring(lon: float, lat: float, ring) -> bool:
    """닫힌 고리 하나의 안인가. 광선 교차 수로 셈.

    규칙  변을 하나씩 보며 그 위도에서 오른쪽으로 그은 광선과 만나면 뒤집음
          홀수면 안, 짝수면 밖임
    """
    if not isinstance(ring, list) or len(ring) < 3:
        return False

    inside = False
    count = len(ring)
    for index in range(count):
        x1, y1 = ring[index][0], ring[index][1]
        x2, y2 = ring[(index + 1) % count][0], ring[(index + 1) % count][1]
        if (y1 > lat) != (y2 > lat):
            crossing = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < crossing:
                inside = not inside
    return inside


def _district_of(result) -> tuple:
    """응답 하나에서 (시군구, 읍면동). 못 읽으면 빈 튜플.

    규칙  layerId 로 고름. items 의 차례로 안 집음
          둘 다 있어야 함. 읍면동만 있으면 어느 시의 동인지 못 적음
    """
    if not isinstance(result, dict):
        return ()
    items = result.get(ITEMS_KEY)
    if not isinstance(items, list):
        return ()

    by_layer = {}
    for item in items:
        if isinstance(item, dict):
            by_layer[item.get(LAYER_KEY)] = item.get(NAME_KEY)

    sigungu = by_layer.get(SIGUNGU_LAYER)
    emd = by_layer.get(EMD_LAYER)
    if isinstance(sigungu, str) and isinstance(emd, str) and sigungu and emd:
        return (sigungu.strip(), emd.strip())
    return ()


def _failed(tool: dict, message: str) -> dict:
    """터진 자리의 trace 항목. vendor 가 만드는 것과 같은 모양."""
    return {
        "server_id": tool["server_id"],
        "tool": tool["tool"],
        "input": {},
        "error": message,
    }
