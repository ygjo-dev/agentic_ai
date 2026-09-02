"""도달 범위에 둘러싸였으나 닿지 않는 곳(음영 지역)을 재고 그 안의 행정동을 모은다.

**뜻을 여기 적는다. 나중에 이 수를 다시 못 세면 못 쓴다.**

    음영 지역 = 도달 범위 조각들의 볼록 껍질 − 도달 범위

「30분에 못 가는 곳 전부」가 아니다. 그러면 부산과 제주가 든다. 도달 범위에
둘러싸인 자리, 곧 **가까운데 안 닿는 자리**라야 뜻이 있다. 볼록 껍질이 그
「둘러싸였다」를 재는 자다 — 도달한 조각들을 고무줄로 두른 것이 껍질이고,
그 안에서 도달 범위를 뺀 나머지가 조각 사이에 남은 틈이다.

**잔 조각을 먼저 버린다.** 껍질은 제일 바깥 점 몇 개가 정하므로 멀리 떨어진
작은 조각 하나가 껍질을 통째로 부풀린다. 의왕역 30분 겹에서 잰 것이다
(2026-09-01, NOTES.md 「여든째」).

    조각 여섯   27.57 · 1.30 · 0.99 · 0.052 · 0.037 · 0.017 km²  (합 29.96)
    안 버리면   껍질 63.20 km²   음영 33.29 km²
    셋을 버리면 껍질 48.27 km²   음영 18.42 km²

7km 밖의 0.05 km² 조각 하나가 껍질을 1.31배로 만든다. 그 조각과 본체 사이는
「둘러싸인 곳」이 아니라 그냥 안 간 곳이다.

**문턱을 전체 넓이의 몫으로 잡는다.** 실측에서 남길 것과 버릴 것 사이가
3.3% 대 0.17% 로 스무 배 벌어져 있어 그 사이 어디를 잡아도 같은 답이다.
상수 km² 로 박으면 구역이 작을 때 전부 버리고 클 때 하나도 못 버린다.

**행정동은 도달 지역과 같은 방식으로 뽑는다** — 격자 점 + findBoundaryByPoint.
점을 부르는 일도 창을 기다리는 일도 execution/reach_districts 가 한다.

**얼마나 빠뜨리는지 쟀다** (2026-09-01, 같은 겹).

    750m   32점   넓이추정 18.00 km²   동 16
    500m   75점   넓이추정 18.75 km²   동 19
    250m  289점   넓이추정 18.06 km²   동 24   <- 바닥

**넓이추정이 재서 얻은 18.42 km² 와 맞는 것이 점 안팎 판정의 검산이다.**
격자가 틀렸으면 이 수부터 어긋난다.

**그래서 화면에 동의 수를 안 쓴다.** 도달 지역과 같은 까닭이다 — 이름은
실제로 그 안에서 나온 것이라 참이고, 몇 곳인지는 격자가 정하는 값이라 참이
아니다.
"""

import math

from execution import reach_districts
from vendor_to_be_deleted.asap.workflow_answer import (
    SHADOW_AREA_KEY,
    SHADOW_CUTOFF_KEY,
    SHADOW_DISTRICTS_KEY,
    SHADOW_KEY,
    geometry_area,
    reach_features,
)

# 껍질을 만들 때 남길 조각의 최소 몫. 전체 넓이에 대한 비율이다.
#
# 의왕역 30분 겹에서 남는 것이 셋(92.0% · 4.3% · 3.3%)이고 버리는 것이
# 셋(0.17% · 0.12% · 0.06%)이다. 위 모듈 주석의 표가 근거다.
FRAGMENT_SHARE = 0.01

# 한 발화에서 이 노드가 쓸 호출 수.
#
# 도달 지역의 118 과 합쳐 188 이다. CHUNK 95 로 나누면 95 + 93 이라 창을
# 한 번만 기다린다 — 도달 지역만 있을 때와 같다. 71 부터 두 번이 된다.
# 음영 18.42 km² 에서 √(18.42 km² / 70) = 513m 라 도달 지역의 504m 와
# 거의 같은 격자다.
SAMPLE_BUDGET = 70

# 격자가 이보다 촘촘해지지 않게 막는 바닥.
MIN_STEP_M = 50.0

# 결과에 껍질 도형을 담는 칸.
#
# 자를 겹(SHADOW_CUTOFF_KEY)도 함께 담는다. 답 문구가 「30분 도달 범위에
# 둘러싸인」이라고 말하는데 그 수를 코드에 적지 않으려는 것이다.
#
# 화면에 테두리를 그리는 자리가 이것을 읽는다(execute_service._shadow_commands).
# 답 문장은 이 칸을 안 본다 — workflow_answer 는 넓이와 동 이름만 읽는다.
HULL_KEY = "hull"


async def run(tool: dict, previous: dict, user_context: dict, sent: int = 0) -> tuple:
    """음영 지역의 넓이와 그 안의 행정동을 trace 항목 하나로. (항목, 창에 보낸 수).

    입력  TOOL_OF 한 줄 · 도달권 계산의 응답 · Gateway 에 보낼 권한 ·
          이 창에 이미 보낸 건수
    출력  vendor 의 trace 항목과 같은 모양. result 아니면 error 하나를 담음.
          id 는 안 붙임. 부르는 쪽이 노드 id 로 붙임
    규칙  도달 지역과 같은 겹을 봄. 제일 큰 cutoff 하나임
          틈이 없으면 error 를 담음. 0.00 km² 라고 적으면 잰 것처럼 보임
          동을 한 곳도 못 찾아도 넓이는 냄. 넓이는 폴리곤에서 잰 것이라
          점 뽑기가 실패해도 참임
          같은 동이 여러 점에서 나오면 한 번만 담음. 점이 많이 걸린 차례로
          앞에 둠
    제약  앞 sampled 노드의 결과를 받지 않는다.
          이 노드가 읽는 것은 도달권 폴리곤이고 도달 지역이 내놓는 것은
          동 이름뿐이다. 부르는 쪽이 도달권 응답을 그대로 넘긴다
    """
    cutoff, geometry = _widest(previous)
    if geometry is None:
        return _failed(tool, "도달권 폴리곤이 없어 음영 지역을 내지 못했습니다."), sent

    hull, area = shadow_of(geometry)
    if hull is None or area <= 0:
        return _failed(tool, "도달 범위에 둘러싸인 틈이 없습니다."), sent

    points = sample_points(hull, geometry, area, SAMPLE_BUDGET)
    hits: dict = {}
    failures = 0
    if points:
        hits, failures, sent = await reach_districts.gather(
            tool, points, user_context, sent
        )

    return {
        "server_id": tool["server_id"],
        "tool": tool["tool"],
        "input": {"points": len(points), "failed": failures},
        "result": {
            SHADOW_KEY: {
                SHADOW_AREA_KEY: area / 1_000_000,
                SHADOW_CUTOFF_KEY: cutoff,
                SHADOW_DISTRICTS_KEY: reach_districts.districts_in_order(hits),
                HULL_KEY: hull,
            }
        },
    }, sent


def shadow_of(geometry: dict) -> tuple:
    """음영 지역의 껍질과 넓이. (껍질 도형, 넓이 m²). 못 재면 (None, 0).

    입력  도달권 한 겹의 GeoJSON Polygon 또는 MultiPolygon
    출력  볼록 껍질 도형 · 그 안에서 도달 범위를 뺀 넓이
    규칙  전체 넓이의 FRAGMENT_SHARE 에 못 미치는 조각은 껍질에서 뺌
          껍질 안에 든 조각의 넓이만 뺌. 남긴 조각은 껍질이 그것들로 만들어져
          늘 안에 듦. 버린 조각은 가운뎃점으로 가름
          꼭짓점이 셋 미만이면 (None, 0). 두를 것이 없음
    제약  넓이를 격자로 세지 않는다.
          껍질도 조각도 폴리곤이라 구면 식으로 바로 잰다. 격자로 세면
          간격이 답을 흔든다
    """
    polygons = reach_districts.rings(geometry)
    if not polygons:
        return None, 0.0

    areas = [geometry_area({"type": "Polygon", "coordinates": p}) for p in polygons]
    total = sum(areas)
    if total <= 0:
        return None, 0.0

    kept = [index for index, area in enumerate(areas) if area >= total * FRAGMENT_SHARE]
    corners = convex_hull(
        [tuple(point[:2]) for index in kept for point in polygons[index][0]]
    )
    if len(corners) < 3:
        return None, 0.0

    hull = {"type": "Polygon", "coordinates": [corners + [corners[0]]]}
    reached = sum(areas[index] for index in kept)
    reached += sum(
        areas[index]
        for index in range(len(polygons))
        if index not in kept and _centre_inside(polygons[index], hull)
    )
    return hull, geometry_area(hull) - reached


def convex_hull(points: list) -> list:
    """점들을 두르는 볼록 껍질의 꼭짓점. 세 점을 못 세우면 빈 목록.

    입력  (경도, 위도) 목록
    출력  껍질 꼭짓점 목록. 반시계 방향. 첫 점을 끝에 다시 담지 않음
    규칙  단조 사슬로 아래쪽과 위쪽을 따로 훑어 이음
          경위도를 그대로 씀. 위도 보정은 축마다 상수를 곱하는 것이고
          볼록 껍질은 그런 변환에 안 흔들림
    """
    unique = sorted(set(points))
    if len(unique) < 3:
        return []

    def turn(origin, first, second) -> float:
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (
            first[1] - origin[1]
        ) * (second[0] - origin[0])

    halves = []
    for sequence in (unique, list(reversed(unique))):
        side: list = []
        for point in sequence:
            while len(side) >= 2 and turn(side[-2], side[-1], point) <= 0:
                side.pop()
            side.append(point)
        halves.append(side[:-1])
    return halves[0] + halves[1]


def sample_points(hull: dict, reached: dict, area: float, budget: int) -> list:
    """음영 지역 안에서 부를 점들. 못 뽑으면 빈 목록.

    입력  껍질 도형 · 도달권 도형 · 음영 넓이(m²) · 부를 수 있는 횟수
    출력  (경도, 위도) 목록. budget 을 넘지 않음
    규칙  껍질 안이고 도달 범위 밖인 점만 남김. 그 둘이 음영 지역의 뜻임
          간격을 음영 넓이가 정함. √(넓이 / 예산) 이라 점 수가 예산 언저리에 섬
          버린 잔 조각도 도달 범위로 봄. 그 안은 실제로 닿는 곳임
          격자 칸의 가운데를 찍음. 테두리를 찍으면 옆 동이 나옴
    제약  껍질 넓이로 간격을 잡지 않는다.
          껍질의 절반 남짓만 음영이라 점이 예산의 절반밖에 안 남는다
    """
    hull_polygons = reach_districts.rings(hull)
    reached_polygons = reach_districts.rings(reached)
    if not hull_polygons or area <= 0:
        return []

    step = max(math.sqrt(area / budget), MIN_STEP_M)
    xs = [x for x, _ in hull_polygons[0][0]]
    ys = [y for _, y in hull_polygons[0][0]]
    min_lon, max_lon = min(xs), max(xs)
    min_lat, max_lat = min(ys), max(ys)

    middle = math.radians((min_lat + max_lat) / 2)
    delta_lat = step / reach_districts.METERS_PER_DEGREE_LAT
    delta_lon = step / (
        reach_districts.METERS_PER_DEGREE_LON * max(math.cos(middle), 0.01)
    )

    points = []
    lat = min_lat + delta_lat / 2
    while lat < max_lat and len(points) < budget:
        lon = min_lon + delta_lon / 2
        while lon < max_lon and len(points) < budget:
            if reach_districts.inside(lon, lat, hull_polygons) and not (
                reach_districts.inside(lon, lat, reached_polygons)
            ):
                points.append((round(lon, 6), round(lat, 6)))
            lon += delta_lon
        lat += delta_lat
    return points


def dashes(hull: dict, dash_m: float, gap_m: float) -> list:
    """껍질 테두리를 점선으로 끊은 조각들. 끊을 것이 없으면 빈 목록.

    입력  껍질 도형 · 한 획의 길이(m) · 사이 틈의 길이(m)
    출력  [[(경도, 위도), …], …] 조각마다 꼭짓점 둘 이상
    규칙  고리를 따라 걸으며 dash_m 만큼 긋고 gap_m 만큼 쉼
          획이 변 가운데서 끝나면 그 자리를 끼워 넣음. 꼭짓점에서만 끊으면
          변 길이에 따라 획이 들쭉날쭉해짐
          길이는 위도 보정한 평면으로 잼. 8km 남짓이라 구면과 안 갈림
    제약  선 하나로 내보내지 않는다.
          저쪽 화면에 line-dasharray 가 없다(ASAP-web MapLibre2DMap 의
          managed line 레이어, 읽기만 했다). 점선은 조각을 나눠야 나온다
    """
    ring = hull.get("coordinates", [[]])[0] if isinstance(hull, dict) else []
    if len(ring) < 3 or dash_m <= 0 or gap_m <= 0:
        return []

    middle = math.radians(sum(point[1] for point in ring) / len(ring))
    lon_m = reach_districts.METERS_PER_DEGREE_LON * math.cos(middle)
    lat_m = reach_districts.METERS_PER_DEGREE_LAT

    segments = []
    current = []
    drawing = True
    left = dash_m
    for start, end in zip(ring, ring[1:]):
        span = math.hypot((end[0] - start[0]) * lon_m, (end[1] - start[1]) * lat_m)
        walked = 0.0
        if drawing:
            current = [tuple(start[:2])]
        while span - walked > left:
            walked += left
            share = walked / span
            cut = (
                round(start[0] + (end[0] - start[0]) * share, 6),
                round(start[1] + (end[1] - start[1]) * share, 6),
            )
            if drawing:
                current.append(cut)
                segments.append(current)
                current = []
            else:
                current = [cut]
            drawing = not drawing
            left = dash_m if drawing else gap_m
        left -= span - walked
        if drawing:
            current.append(tuple(end[:2]))

    if drawing and len(current) > 1:
        segments.append(current)
    return [segment for segment in segments if len(segment) > 1]


def _widest(previous: dict) -> tuple:
    """제일 큰 겹. (자를 겹의 분, 도형). 도달권 응답이 아니면 (None, None).

    규칙  도달 지역 · 면적 줄과 같은 겹을 고름. cutoff 가 제일 큰 것임
          겹의 분을 함께 냄. 화면 문구가 「30분 도달 범위」라고 말해야 하고
          그 수는 배선이 정함
    """
    features = reach_features(previous)
    if not features:
        return None, None
    return max(features, key=lambda pair: pair[0])


def _centre_inside(polygon: list, hull: dict) -> bool:
    """그 조각의 가운뎃점이 껍질 안인가.

    규칙  바깥 고리 꼭짓점의 평균을 가운뎃점으로 씀. 조각이 작아 오목해도
          그 점이 조각 밖으로 크게 벗어나지 않음
    """
    outer = polygon[0] if polygon else []
    if not outer:
        return False
    lon = sum(point[0] for point in outer) / len(outer)
    lat = sum(point[1] for point in outer) / len(outer)
    return reach_districts.inside(lon, lat, reach_districts.rings(hull))


def _failed(tool: dict, message: str) -> dict:
    """터진 자리의 trace 항목. vendor 가 만드는 것과 같은 모양."""
    return {
        "server_id": tool["server_id"],
        "tool": tool["tool"],
        "input": {},
        "error": message,
    }
