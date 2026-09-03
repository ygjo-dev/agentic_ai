"""출발지를 중심으로 한 반경 원. **견줌과 음영 지역이 같은 원을 본다.**

원을 쓰는 자리가 둘이고 둘이 한 원을 봐야 한다.

    도달 범위의 견줌   (원 ∩ 도달) ÷ 원      execution/execute_service
    음영 지역          원 − 도달             execution/shadow_districts

**둘이 각자 원을 그리면 검산이 안 선다.** `(원 ∩ 도달) + (원 − 도달) = 원`
이 소수 둘째 자리까지 맞아야 하는데 반지름도 꼭짓점 수도 그리는 식도 조금만
다르면 그 자리에서 갈린다. 그래서 셋을 이 파일 하나에 둔다.

**위도를 보정해 그린다.** 경도 한 도의 길이가 위도가 올라갈수록 짧아진다.
보정을 안 하면 남북으로 눌린 타원이 된다 — 위도 37.32° 에서 경도 쪽 각거리가
1.26배 벌어져야 원이 된다.

**꼭짓점은 360개다.** 안에 그린 정 n 각형은 원보다 좁고 모자란 몫이 대략
2π²/3n² 이다. 관문이 0.1% 이고 360 은 그 스무 배 아래다
(2026-09-03 실측, 위도 37.32011°·반지름 5km).

    꼭짓점    잰 넓이(km²)   πr²(78.5398) 에 견준 오차
        90       78.4760          -0.081%
       180       78.5239          -0.020%
       360       78.5358          -0.005%   <- 지금
       720       78.5388          -0.001%
      1440       78.5396          -0.000%

**넓이를 여기 안 적는다.** πr² 를 상수로 박으면 위도를 안 본 수가 되고,
무엇보다 도달 면적을 잰 자(`geometry_area`)와 다른 자로 잰 수가 된다. 두
넓이의 비를 낼 것이라 같은 자로 재야 한다.

**중심은 도달권 응답이 들고 온다.** `compute_isochrone` 이 `origin` 칸에
자기가 받은 좌표를 그대로 돌려준다 (2026-09-03 실측). 그 한 자리에서 둘이
읽으므로 중심이 갈릴 수가 없다 — 호출 인자에서 한 번, 응답에서 한 번 읽으면
같은 값이어도 원천이 둘이 된다.

**shapely 로 자른다** (2026-09-02 에 `.venv` 에 넣었다. shapely 2.1.2).
경위도를 그대로 넣는다 — 자르는 일은 좌표계를 안 가리고, 잘라 낸 도형의
넓이는 `geometry_area` 가 구면에서 다시 잰다.
"""

import math

from vendor_to_be_deleted.asap.workflow_answer import EARTH_RADIUS_M

# 원의 반지름(km). **사람이 정한 값이다.** 재서 나온 수가 아니다.
#
# 「반경 5km 안에서 얼마나 갈 수 있나」가 도시계획에서 쓰는 말이라 골랐다
# (2026-09-02). 시군구 넓이는 장소마다 표가 있어야 하는데 원은 아무 장소에나
# 선다 — 그 표를 걷어낸 자리가 이 한 줄이다 (2026-09-03 「아흔째」).
RADIUS_KM = 5.0

# 원을 폴리곤으로 그릴 때의 꼭짓점 수. 위 모듈 주석의 표가 근거다.
SEGMENTS = 360

# 도달권 응답에서 중심점을 읽는 칸.
ORIGIN_KEY = "origin"
ORIGIN_LON_KEY = "lon"
ORIGIN_LAT_KEY = "lat"

# 위선이 0 으로 줄어드는 극에서 나눗셈이 터지지 않게 막는 바닥.
MIN_COS = 0.01


def circle(lon: float, lat: float, radius_km: float = RADIUS_KM) -> dict:
    """그 점을 중심으로 한 반경 radius_km 원. GeoJSON Polygon.

    입력  중심의 경도 · 위도 · 반지름(km)
    출력  꼭짓점 SEGMENTS 개짜리 Polygon. 첫 점이 끝에 한 번 더 들어 닫힘
    규칙  중심에서 잰 각거리를 도로 바꿈. 경도 쪽은 그 위도의 위선이 짧아진
          만큼 벌림
          도 환산에 도달 면적을 재는 자와 **같은 지구 반지름**을 씀. 다른
          상수를 쓰면 원만 0.4% 어긋나 두 넓이의 비가 자를 두 개 섞은 값이 됨
    제약  넓이를 함께 안 낸다.
          이 함수가 내놓는 것은 도형이고, 그 넓이는 도달 면적을 잰 것과 같은
          `geometry_area` 가 잰다
    """
    span = math.degrees(radius_km * 1000 / EARTH_RADIUS_M)
    delta_lon = span / max(math.cos(math.radians(lat)), MIN_COS)

    ring = [
        [
            lon + delta_lon * math.sin(2 * math.pi * index / SEGMENTS),
            lat + span * math.cos(2 * math.pi * index / SEGMENTS),
        ]
        for index in range(SEGMENTS)
    ]
    ring.append(list(ring[0]))
    return {"type": "Polygon", "coordinates": [ring]}


def origin_of(previous: dict):
    """도달권 응답이 들고 온 중심점. (경도, 위도). 없으면 None.

    입력  compute_isochrone 의 응답
    출력  원을 세울 점
    규칙  응답의 origin 칸 하나만 봄. 호출 인자를 안 봄 — 같은 값이어도
          원천이 둘이 되면 두 자리가 갈릴 자리가 생김
          bool 은 수로 안 봄
    """
    if not isinstance(previous, dict):
        return None
    origin = previous.get(ORIGIN_KEY)
    if not isinstance(origin, dict):
        return None

    lon = _number(origin.get(ORIGIN_LON_KEY))
    lat = _number(origin.get(ORIGIN_LAT_KEY))
    if lon is None or lat is None:
        return None
    return lon, lat


def intersection(first: dict, second: dict):
    """두 도형이 겹치는 자리. GeoJSON. 안 겹치거나 못 세우면 None."""
    return _cut(first, second, "intersection")


def difference(first: dict, second: dict):
    """앞 도형에서 뒤 도형을 뺀 나머지. GeoJSON. 남는 것이 없으면 None."""
    return _cut(first, second, "difference")


def _cut(first: dict, second: dict, operation: str):
    """도형 둘을 shapely 로 자름. 못 자르면 None.

    규칙  스스로 겹치는 고리는 buffer(0) 으로 폄. 도달권 폴리곤에 그런 것이
          섞여 있고 안 펴면 자르다 터짐
          빈 도형은 None. 넓이가 0 이라 잰 것처럼 낼 수 없음
    제약  경위도를 미터로 안 바꾼다.
          자르는 일은 좌표계를 안 가리고, 나온 도형의 넓이는 geometry_area 가
          구면에서 다시 잰다
    """
    left = _shape(first)
    right = _shape(second)
    if left is None or right is None:
        return None

    try:
        cut = getattr(left, operation)(right)
    except Exception:
        return None
    return None if cut.is_empty else _geojson(cut)


def _shape(geometry):
    """GeoJSON 한 벌을 shapely 도형으로. 못 세우면 None."""
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


def _geojson(polygon) -> dict:
    """shapely 도형을 GeoJSON 으로. **꼭짓점을 목록으로 편다.**

    규칙  shapely 의 mapping 은 좌표를 튜플로 낸다. geometry_area 도 저쪽
          화면에 나가는 JSON 도 목록을 받으므로 여기서 한 번 편다
    """
    from shapely.geometry import mapping

    drawn = mapping(polygon)
    return {"type": drawn["type"], "coordinates": _lists(drawn["coordinates"])}


def _lists(value):
    """튜플이 섞인 좌표 더미를 목록만으로."""
    if isinstance(value, (list, tuple)):
        return [_lists(item) for item in value]
    return value


def _number(value):
    """실수 값. 수가 아니면 None. bool 은 수로 안 봄."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
