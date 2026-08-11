"""패널 높이 계산 검증.

`st.components.v1.html` 은 iframe 을 height 속성으로 고정해 만든다. 바깥에
height:100% 를 줘도 iframe 자신은 안 바뀐다 — 예전에 그래프가 420px 에 갇혀
종횡비 때문에 폭까지 눌렸던 원인이다. 그래서 픽셀을 파이썬에서 계산한다.

계산이 틀리면 화면이 뷰포트를 넘쳐 세로 스크롤이 생기거나, 반대로 남는 공간이
생긴다. 둘 다 시연 중에 손댈 수 없는 사고라 여기서 고정한다.
"""

import pytest

from frontend import config, styles


def ratios(**overrides) -> dict:
    return {**config.LAYOUT, **overrides}


# ------------------------------------------------------------ 계산
def test_heights_follow_the_formula():
    """식을 그대로 되짚는다. 상수가 바뀌면 여기서 함께 드러난다."""
    r = ratios(viewport_height=1000, top_ratio=0.5, chrome_vh=6)

    heights = styles.panel_heights(r)

    assert heights["top"] == int(1000 * 0.5 - 60 - styles.PANEL_PADDING)
    assert heights["bottom"] == int(
        1000 * 0.5 - styles.BAND_HEIGHT - styles.PANEL_PADDING - styles.PAGE_PADDING
    )


def test_taller_viewport_gives_taller_panels():
    small = styles.panel_heights(ratios(viewport_height=900))
    large = styles.panel_heights(ratios(viewport_height=1440))

    assert large["top"] > small["top"]
    assert large["bottom"] > small["bottom"]


def test_top_ratio_moves_height_between_the_two_panels():
    low = styles.panel_heights(ratios(top_ratio=0.4))
    high = styles.panel_heights(ratios(top_ratio=0.6))

    assert high["top"] > low["top"]
    assert high["bottom"] < low["bottom"]


def test_tiny_viewport_still_leaves_something_visible():
    """작은 화면에서 음수 높이가 나오면 iframe 이 통째로 사라진다."""
    heights = styles.panel_heights(ratios(viewport_height=config.MIN_VIEWPORT))

    assert heights["top"] >= 200
    assert heights["bottom"] >= 200


def test_heights_are_integers():
    """st.components.v1.html 의 height 는 픽셀 정수다."""
    heights = styles.panel_heights(ratios(viewport_height=1281))

    assert isinstance(heights["top"], int)
    assert isinstance(heights["bottom"], int)


# ------------------------------------------------------------ 세로 스크롤 (핵심)
@pytest.mark.parametrize("viewport", [900, 1080, 1282, 1440, 2160])
@pytest.mark.parametrize("top_ratio", [0.4, 0.5, 0.6])
def test_panels_never_overflow_the_viewport(viewport, top_ratio):
    """상단 + 하단 + 크롬 + 여백의 합이 뷰포트를 넘으면 세로 스크롤이 생긴다.

    지금 화면이 250px 가량 넘쳐 하단이 잘리고 있던 바로 그 증상이다.
    """
    r = ratios(viewport_height=viewport, top_ratio=top_ratio)
    heights = styles.panel_heights(r)

    chrome = viewport * r["chrome_vh"] / 100
    total = (
        heights["top"]
        + heights["bottom"]
        + chrome
        + styles.BAND_HEIGHT
        + styles.PANEL_PADDING * 2
        + styles.PAGE_PADDING
    )

    assert total <= viewport, f"{total - viewport:.0f}px 넘친다"


def test_the_overflow_check_can_actually_fail():
    """위 검사의 판별력. 여백을 하나 빠뜨리면 넘치는 것이 보여야 한다.

    무력한 테스트가 지금까지 여러 번 나왔다. 합이 뷰포트 이하라는 단언은
    높이를 아주 작게 잡아도 통과하므로, 반대로 "빠뜨리면 터진다" 를 함께 잰다.
    """
    viewport = 1282
    r = ratios(viewport_height=viewport)
    naive_top = viewport * r["top_ratio"]          # 크롬·여백을 안 뺀 값
    naive_bottom = viewport * (1 - r["top_ratio"])

    total = (
        naive_top
        + naive_bottom
        + viewport * r["chrome_vh"] / 100
        + styles.BAND_HEIGHT
        + styles.PANEL_PADDING * 2
        + styles.PAGE_PADDING
    )

    assert total > viewport


# ------------------------------------------------------------ ?vh= 오버라이드
def test_vh_query_param_overrides_the_viewport(monkeypatch):
    monkeypatch.setattr(config.st, "query_params", {"vh": "900"})

    assert config.layout_ratios()["viewport_height"] == 900


@pytest.mark.parametrize(
    "raw",
    ["0", "-100", "abc", "", "nan", str(config.MIN_VIEWPORT - 1), str(config.MAX_VIEWPORT + 1)],
)
def test_bad_vh_values_fall_back_to_the_default(monkeypatch, raw):
    """시연 중에 주소창을 잘못 건드려도 화면이 죽으면 안 된다."""
    monkeypatch.setattr(config.st, "query_params", {"vh": raw})

    assert config.layout_ratios()["viewport_height"] == config.LAYOUT["viewport_height"]


def test_vh_accepts_a_float_string(monkeypatch):
    """브라우저가 넘겨주는 innerHeight 는 소수점이 붙을 수 있다."""
    monkeypatch.setattr(config.st, "query_params", {"vh": "1080.5"})

    assert config.layout_ratios()["viewport_height"] == 1080


def test_ratio_params_still_work_alongside_vh(monkeypatch):
    """픽셀 경로를 더하면서 비율 경로를 깨뜨리지 않았는지."""
    monkeypatch.setattr(config.st, "query_params", {"vh": "1000", "top": "0.7"})

    r = config.layout_ratios()
    assert (r["viewport_height"], r["top_ratio"]) == (1000, 0.7)


def test_vh_is_not_accepted_as_a_ratio(monkeypatch):
    """0~1 검증 경로로 새면 900 이 통째로 버려진다."""
    monkeypatch.setattr(config.st, "query_params", {"top": "900"})

    assert config.layout_ratios()["top_ratio"] == config.LAYOUT["top_ratio"]
