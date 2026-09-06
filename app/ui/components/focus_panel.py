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


def _signature(rendered: dict, view: dict | None = None) -> str:
    """이 **해석 한 번**의 서명. 좁혀 들어가기를 한 번만 돌리는 기준이다.

    입력  POST /render 응답 · 지금 장면
    출력  발화 · 후보 · 그 해석을 가리키는 값을 이은 문자열
    규칙  발화를 넣음. 서로 다른 발화가 우연히 같은 후보를 골라도 그때는
          새 해석이므로 다시 한 번 보여줘야 함
          같은 발화를 다시 눌렀을 때도 새 해석임. view 가 그때마다 새로
          만들어지므로 그 안의 값(잰 시간, 또는 회차 번호)이 그것을 가리킴
          후보 recipe 와 온톨로지 version 도 넣음. 둘 중 하나만 바뀌어도
          보여줄 그림이 달라짐. 후보는 network 의 변형 키에서 옴 —
          옛 focus 칸이 말하던 것과 같은 값이고 원천이 하나로 줄었음
    제약  화면을 다시 그리는 것만으로 값이 바뀌지 않게 한다.
          Streamlit 은 무엇을 누르든 스크립트를 다시 도는데 그때마다
          값이 바뀌면 확대가 되풀이됨
    """
    후보 = sorted(_candidate_order(rendered))

    발화, 회차 = "", ""
    if isinstance(view, dict):
        발화 = view.get("utterance") or ""
        # 같은 발화를 다시 눌러도 새 해석이다. 그것을 가리키는 값이
        # 발화로 온 것에는 잰 시간, 회차를 따라온 것에는 회차 번호다.
        회차 = str(view.get("elapsed") or (view.get("follow") or {}).get("seq") or "")

    return "|".join([rendered.get("version", ""), ",".join(후보), 발화, 회차])


def _candidate_order(rendered: dict) -> list[str]:
    """목록 줄 차례에 맞춘 recipe id.

    출력  줄 수와 같은 길이의 recipe id 목록
    규칙  서버가 후보를 낸 차례가 곧 줄 차례임. 변형 키에서 빈 것을 빼면
          그것이 후보 하나씩이고 그 차례가 chips 와 같음
    제약  여기서 차례를 다시 매기지 않는다.
          두 곳이 정하면 목록과 그래프가 서로 다른 후보를 가리킴
    """
    variants = (rendered.get("network") or {}).get("variants") or {}
    return [key for key in variants if key]


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

    입력  rendered  POST /render 응답. network · chips 가 들어 있음
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
    ratios = ratios or config.LAYOUT
    height = styles.panel_heights(ratios)["bottom"]

    # 목록은 늘 후보 전부다. 좁혀도 줄이 사라지지 않고 흐려질 뿐이라
    # 서버도 변형마다 따로 만들지 않는다.
    전부 = rendered.get("chips") or []

    st.components.v1.html(
        network.bottom_html(
            rendered["network"],
            theme.colors(),
            path_panel.chips_markup(전부, color),
            left_ratio=ratios["bottom_left_ratio"],
            # 줄 차례에 맞춘 recipe id. 어느 줄이 고른 후보인지 가리는 데 쓴다.
            order=_candidate_order(rendered),
            height=height,
            signature=_signature(rendered, view),
        ),
        height=height,
    )
