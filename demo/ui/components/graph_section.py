"""상단 온톨로지 그래프. **표시만 한다.**

SVG 는 백엔드가 완성해서 보낸다. 여기서는 iframe 문서로 감싸고 줌을 붙일 뿐이다.
예전에는 이 파일이 프로세스를 띄워 Graphviz 를 돌리고 좌표 파일까지 썼는데,
브라우저 없이 도는 일이라 서버(`demo/graph_svg/`)로 옮겼다.

그래서 이 모듈에는 Graphviz 도, 파일 입출력도, 캐시도 없다. 화면을 갈아끼울 때
버릴 수 있는 것만 남았다.
"""

import streamlit as st

from demo.ui import config, styles, theme
from demo.ui.components import zoom

# 새로 생긴 것이 잠깐 두근거린다. 짧게 두 번만 — 계속 깜빡이면 시선을 뺏는다.
_PULSE_CSS = """
@keyframes markpulse {
  0%   { opacity: 1; }
  50%  { opacity: 0.35; }
  100% { opacity: 1; }
}
g.node [stroke="MARK"], g.edge [stroke="MARK"] {
  animation: markpulse 0.6s ease-in-out 2;
}
"""


def graph_fill_html(svg: str, pulse: bool = False) -> str:
    """고정 높이 패널을 꽉 채우는 iframe 문서.

    iframe 배경은 기본 흰색이라 다크 테마에서 흰 카드로 뜬다. DOT 의
    bgcolor="transparent" 는 SVG 안쪽만 투명하게 하므로 여기서 한 번 더 덮는다.
    SVG 는 비율을 유지한 채 상자에 맞춘다(크기 속성은 서버가 이미 뺐다).

    pulse 는 방금 등록된 것에만 준다. CSS 애니메이션이라 JS 가 없다.
    """
    extra = _PULSE_CSS.replace("MARK", theme.new().lower()) if pulse else ""

    return (
        "<style>"
        "html, body { background: transparent; margin: 0; padding: 0;"
        " height: 100%; overflow: hidden; }"
        "#graph { width: 100%; height: 100%; overflow: hidden; }"
        "svg { width: 100%; height: 100%; display: block; }"
        f"{zoom.ZOOM_CSS}"
        f"{extra}"
        "</style>"
        f'<div id="graph">{svg}</div>'
        f"{zoom.zoom_script(zoom.TOP_KEY)}"
    )


def show_graph(svg: str, height: int, pulse: bool = False):
    """SVG 를 iframe 으로 띄운다.

    높이를 픽셀로 받는다. iframe 은 height 속성으로 고정되므로 CSS 로 덮을 수
    없다 — 그게 예전에 그래프가 420px 에 갇혀 폭까지 눌렸던 원인이다.
    """
    st.components.v1.html(graph_fill_html(svg, pulse), height=height)


def render_graph_section(
    rendered: dict | None = None,
    pulse: bool = False,
    ratios: dict | None = None,
):
    """온톨로지 그래프. 무엇을 골랐는지는 하단 경로 패널이 보여준다.

    발화 해석으로는 이 그래프를 강조하지 않는다. 노드를 등록했을 때만
    새로 생긴 것을 강조한다 — 그때가 "어디에 들어갔는지" 를 보여줄 장면이다.

    Args:
        rendered: POST /render 응답. top 에 상단 SVG 가 들어 있다.
        pulse: 방금 등록했는가. 두근거림은 그때만 준다.
    """
    if not rendered or not rendered.get("top"):
        st.markdown(
            styles.note_markup("그래프를 불러올 수 없습니다. Backend 가 실행 중인지 확인하세요."),
            unsafe_allow_html=True,
        )
        return

    height = styles.panel_heights(ratios or config.LAYOUT)["top"]
    show_graph(rendered["top"], height, pulse=pulse)
