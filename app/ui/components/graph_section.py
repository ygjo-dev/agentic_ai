"""상단 온톨로지 그래프. **표시만 한다.**

노드 · 엣지 · 좌표는 백엔드가 보낸다(POST /render 의 network). 여기서는
interactive graph library 에 넘겨 iframe 으로 띄울 뿐이다.

★ **2026-09-06 에 Graphviz SVG 에서 vis-network(pyvis)로 갈았다.** 예전에는
서버가 완성한 SVG 를 받아 `zoom.py` 의 자체 JS 로 확대 · 끌기를 흉내 냈다.
그림 자체는 정지 이미지라 노드를 집어 옮길 수 없었다. 지금은 그 셋이 전부
라이브러리 것이다. **같은 날 SVG 를 만들던 자리도 통째로 걷었다** —
Graphviz 는 좌표 계산에만 남는다.

그래서 이 모듈에는 Graphviz 도, 파일 입출력도, 캐시도 없다. 화면을 갈아끼울 때
버릴 수 있는 것만 남았다.
"""

import streamlit as st

from app.ui import config, styles, theme
from app.ui.components import network


def graph_fill_html(model: dict, colors: dict, height: int) -> str:
    """고정 높이 패널을 꽉 채우는 iframe 문서.

    입력  network 모형 · 색 · 픽셀 높이
    출력  iframe 에 넣을 HTML 문서
    제약  발화 해석 결과를 상단에 칠하지 않는다.
          강조 · 흐르는 표시 · 좁혀 들어가기는 전부 하단의 일임
    """
    return network.top_html(model, colors, height=height)


def show_network(model: dict, height: int, colors: dict | None = None):
    """모형을 라이브러리로 그려 iframe 에 띄움.

    입력  network 모형 · 픽셀 높이 · 색
    제약  높이를 CSS 로 주지 않는다.
          iframe 은 height 속성으로 고정되므로 CSS 로 덮을 수 없음.
          예전에 그래프가 420px 에 갇혀 폭까지 눌렸던 원인
    """
    st.components.v1.html(
        graph_fill_html(model, colors or theme.colors(), height), height=height
    )


def render_graph_section(
    rendered: dict | None = None,
    ratios: dict | None = None,
):
    """온톨로지 그래프. 무엇을 골랐는지는 하단 경로 패널이 보여줌.

    입력  rendered  POST /render 응답. network 에 그래프 모형이 들어 있음
          ratios    config.layout_ratios() 결과
    제약  발화 해석으로 이 그래프를 강조하지 않는다.
    """
    if not rendered or not rendered.get("network"):
        st.markdown(
            styles.note_markup("그래프를 불러올 수 없습니다. Backend 가 실행 중인지 확인하세요."),
            unsafe_allow_html=True,
        )
        return

    height = styles.panel_heights(ratios or config.LAYOUT)["top"]
    show_network(rendered["network"], height)
