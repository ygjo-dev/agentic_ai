"""화면 설정. 색 · 비율 · 디버그 표시 여부.

이 화면은 비전공자가 배석한 자리에서 시연된다. 개발용 문구가 보이면
"만들다 만 것" 으로 읽히므로 DEBUG 로 갈라둔다.
"""

import os

import streamlit as st

# 개발 중에만 켠다. 시연에서는 꺼져 있어야 한다.
DEBUG = os.environ.get("DEMO_DEBUG", "0") == "1"

LAYOUT = {
    # 상단이 차지하는 화면 높이 비율. 하단 그래프가 종횡비 0.65 라 1/3 로는
    # 폭을 20% 밖에 못 쓴다. 절반으로 올려야 읽을 만해진다.
    "top_ratio": 0.5,
    "left_ratio": 0.33,         # 상단 좌측(입력) 비율
    # 하단 좌측(해석 그래프) 비율. 나머지가 칩 목록.
    # 그래프는 높이에 걸려 있어서 이 값을 키워도 그래프가 커지지는 않는다 —
    # 칩 사슬이 폭을 다 안 쓰니 줄이는 것뿐이다.
    "bottom_left_ratio": 0.75,
    "chrome_vh": 6,             # 헤더·패딩이 먹는 높이(vh)
    # 브라우저 창 높이(px). iframe 은 height 속성으로 높이가 고정되므로
    # CSS 로 덮을 수가 없다 — 픽셀을 직접 계산해 넘겨야 한다.
    # 실측값(32인치, 전체화면 미사용). 다른 화면에서는 ?vh= 로 덮는다.
    "viewport_height": 1282,
}

# 배경이 투명이라 어느 테마에도 얹힌다. 색은 중간 톤으로 골라 밝은 배경에서도 읽힌다.
HIGHLIGHT_COLOR = "#14B8A6"  # 선택된 경로. 노드 테두리와 엣지에만 쓴다.
DOTTED_COLOR = "#7F77DD"  # 특성 관련. 실선과 확실히 구분되어야 한다.
PLAIN_COLOR = "#8C93A1"  # 그 밖의 모든 것.
# 새로 등록된 노드. 위 둘과 충분히 떨어진 분홍 계열로 골랐다 —
# teal(180°) · 보라(245°) 사이에서 330° 가 가장 멀다.
NEW_COLOR = "#F2589D"

# ------------------------------------------------------------ 시각 위계
# 선이 뒤로 물러나고 노드가 앞으로 나오게 값을 배경(#0E1117) 대비비로 골랐다.
#   강조 7.6  >  노드 테두리 8.8(가늘다)  >  점선 2.9  >  실선 2.4  >  상단 1.5
# 32인치 모니터라 이 정도 섬세한 대비가 통한다. 프로젝터면 더 벌려야 한다.
NODE_BORDER = "#A9B1C0"  # 노드 테두리. 선보다 밝아야 앞으로 나온다.
NODE_FILL = "#171B26"    # 노드 배경. 배경과 거의 같아(1.10) 카드처럼 뜬다.

# 하단 = 답(주인공), 상단 = 배경 지도(참조용). 상단을 더 흐리게 둔다.
EDGE_COLOR = "#4A5262"         # 하단 실선
EDGE_COLOR_TOP = "#2F3542"     # 상단 실선
DOTTED_COLOR_BOTTOM = "#5B55A0"  # 하단 점선
DOTTED_COLOR_TOP = "#3E3A6B"     # 상단 점선
# 상단 노드도 낮춘다 — 선만 흐리게 하면 상단 노드가 하단과 같은 무게로 경쟁한다.
NODE_BORDER_TOP = "#5A6474"

# 비율은 리허설 중에 새로고침만으로 맞출 수 있어야 한다. 값이 정해지면 LAYOUT 에 박는다.
_RATIO_KEYS = {
    "top": "top_ratio",
    "left": "left_ratio",
    "bleft": "bottom_left_ratio",
}


def _as_ratio(raw) -> float | None:
    """쿼리 파라미터 한 개를 비율로. 쓸 수 없는 값이면 None.

    시연 중에 주소창을 잘못 건드려도 화면이 죽으면 안 된다. 어떤 입력에도
    예외를 올리지 않고 None 을 돌려 기본값으로 떨어지게 한다.
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None

    if not 0.0 < value < 1.0:  # 0 이하 · 1 이상 · nan 모두 여기서 걸린다
        return None
    return value


# 픽셀 값은 비율과 검증 규칙이 다르다. 0~1 이 아니라 상식적인 화면 높이 범위다.
_PIXEL_KEYS = {"vh": "viewport_height"}
MIN_VIEWPORT, MAX_VIEWPORT = 400, 8000


def _as_pixels(raw) -> int | None:
    """쿼리 파라미터 한 개를 픽셀 높이로. 쓸 수 없는 값이면 None."""
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return None

    if not MIN_VIEWPORT <= value <= MAX_VIEWPORT:
        return None
    return value


def layout_ratios() -> dict:
    """LAYOUT 에 쿼리 파라미터(?top=0.7&left=0.28&vh=900)를 얹은 값."""
    ratios = dict(LAYOUT)

    try:
        params = st.query_params
    except Exception:  # noqa: BLE001 — Streamlit 런타임 밖에서도 부를 수 있어야 한다
        return ratios

    for keys, parse in ((_RATIO_KEYS, _as_ratio), (_PIXEL_KEYS, _as_pixels)):
        for key, field in keys.items():
            try:
                raw = params.get(key)
            except Exception:  # noqa: BLE001
                continue
            value = parse(raw)
            if value is not None:
                ratios[field] = value

    return ratios
