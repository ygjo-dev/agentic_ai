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
    "bottom_left_ratio": 0.60,
    "chrome_vh": 6,             # 헤더·패딩이 먹는 높이(vh)
    # 브라우저 창 높이(px). iframe 은 height 속성으로 높이가 고정되므로
    # CSS 로 덮을 수가 없다 — 픽셀을 직접 계산해 넘겨야 한다.
    # 실측값(32인치, 전체화면 미사용). 다른 화면에서는 ?vh= 로 덮는다.
    "viewport_height": 1282,
}

# 저쪽 화면을 따라 볼 때 GET /recent 를 다시 묻는 주기(초).
#
# 3 이다. 시연장에서 바꿀 수 있게 한 곳에 둔다.
#
# 아래가 값을 고른 근거다.
#   저쪽 회차 하나가 LLM 해석 + 도구 호출이라 10초대다. 그보다 촘촘히 물어도
#   새 것이 없다 — 늦게 따라오는 값은 주기가 아니라 저쪽의 응답 시간이다
#   번호가 그대로면 화면을 다시 안 그리므로 헛되이 도는 값은 요청 하나뿐이다.
#   3초면 분당 20회이고 같은 기계의 FastAPI 라 부담이 없다
#   2초로 줄여도 사람 눈에 달라지는 것이 없고 요청만 1.5배가 된다.
#   5초는 저쪽에서 답이 나온 뒤 화면이 멈춰 있는 구간이 길어 시연에서 걸린다
FOLLOW_INTERVAL_SECONDS = 3

# 색은 여기 없다. graph_svg 가 정해 /graph 응답으로 내려보내고 theme.py 가 받는다 —
# 그래프 SVG 와 칩 · 배지가 같은 색이어야 하므로 출처가 하나여야 한다.

# 비율은 리허설 중에 새로고침만으로 맞출 수 있어야 한다. 값이 정해지면 LAYOUT 에 박는다.
_RATIO_KEYS = {
    "top": "top_ratio",
    "left": "left_ratio",
    "bleft": "bottom_left_ratio",
}


def _as_ratio(raw) -> float | None:
    """쿼리 파라미터 한 개를 비율로.

    출력  0 초과 1 미만의 float. 쓸 수 없는 값이면 None
    제약  어떤 입력에도 예외를 올리지 않는다.
          시연 중에 주소창을 잘못 건드려도 화면이 죽으면 안 됨.
          None 을 돌려 기본값으로 떨어지게 함
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
    """쿼리 파라미터 한 개를 픽셀 높이로.

    출력  MIN_VIEWPORT ~ MAX_VIEWPORT 의 int. 쓸 수 없는 값이면 None
    규칙  픽셀은 비율과 검증 규칙이 다름. 0~1 이 아니라 상식적인 화면 높이 범위
    """
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return None

    if not MIN_VIEWPORT <= value <= MAX_VIEWPORT:
        return None
    return value


def layout_ratios() -> dict:
    """LAYOUT 에 쿼리 파라미터(?top=0.7&left=0.28&vh=900)를 얹은 값.

    규칙  Streamlit 런타임 밖에서도 부를 수 있어야 해 예외는 삼키고 기본값을 씀
    """
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
