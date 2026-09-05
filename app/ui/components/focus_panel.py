"""하단 본문. 해석 그래프와 recipe 칩 목록을 한 문서에 담는다.

둘을 한 iframe 에 넣는 이유 : 나누면 클릭마다 Streamlit 재실행이라 반응이 굼뜨다.
문서 안에서 처리하면 파이썬 왕복이 없어 즉각 반응하고 LLM 도 다시 불리지 않는다.

그래프 모형과 칩 데이터는 백엔드가 미리 만들어 보낸다(POST /render). 여기서는
고르고 그리기만 한다 — 엣지 굵기 · 색 · 순번 규칙이 서버와 JS 두 곳으로
갈라지지 않게 하려는 것이다.

★ **2026-09-06 에 Graphviz SVG 에서 vis-network(pyvis)로 갈았다.** 변형마다
SVG 를 한 장씩 만들어 innerHTML 로 바꿔 끼우던 것을, 라이브러리 그래프 하나에
파이썬이 만든 스타일 표를 갈아 끼우는 것으로 바꿨다. **JS 는 여전히 색을
하나도 모른다** — 표에서 골라 DataSet.update 에 넘길 뿐이다.

고른 노드(picked)는 이 문서 안 변수로만 둔다 — 다시 그릴 때마다 전체로
돌아가는 것이 맞다. 확대 · 끌기는 라이브러리가 제 안에 들고 있어 우리가
저장하지 않는다.
"""

import streamlit as st

from app.ui import config, styles, theme
from app.ui.components import network, path_panel


def chip_color(view: dict | None) -> str:
    """칩 색.

    출력  등록 장면이면 theme.new(), 그 밖에는 theme.highlight()
    규칙  등록 장면만 다른 색을 씀. 무엇이 새로 생겼는지가 주인공
    """
    if isinstance(view, dict) and view.get("kind") == "register":
        return theme.new()
    return theme.highlight()


def render_focus_section(
    rendered: dict | None = None,
    view: dict | None = None,
    ratios: dict | None = None,
):
    """하단 본문. 해석 그래프와 recipe 칩 목록을 한 iframe 에 담음.

    입력  rendered  POST /render 응답. variants · chips · focus 가 들어 있음
          view      지금 장면. 칩 색을 고르는 데만 씀
          ratios    config.layout_ratios() 결과
    규칙  후보가 없어도 그림. 실행 전에는 위아래가 같은 지도로 채워진 채
          시작하고, NO_MATCH 에서는 지도는 떠 있는데 켜지는 길이 하나도 없음.
          문구 없이 그림으로 읽힘
    제약  iframe 을 없애지 않는다. 항상 있어야 결과가 생길 때 화면이 안 튐
    """
    if not rendered or not rendered.get("network"):
        return

    color = chip_color(view)
    chips = rendered.get("chips") or {}
    ratios = ratios or config.LAYOUT
    height = styles.panel_heights(ratios)["bottom"]

    st.components.v1.html(
        network.bottom_html(
            rendered["network"],
            theme.colors(),
            {key: path_panel.chips_markup(chains, color) for key, chains in chips.items()},
            left_ratio=ratios["bottom_left_ratio"],
            clickable=(rendered.get("focus") or {}).get("last_nodes") or [],
            height=height,
        ),
        height=height,
    )
