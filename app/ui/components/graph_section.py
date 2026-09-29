"""서비스 화면의 온톨로지 그래프. **iframe 하나다.**

그 문서 하나에 본 그래프 · 미니맵 · 살펴보기 칸(후보 recipe 목록 · 노드 설명)이
함께 있다(`network.main_html`). 한 문서라야 노드를 누르거나 후보를 고를 때 파이썬
왕복이 없어 즉각 반응하고 LLM 도 다시 불리지 않는다.

노드 · 엣지 · 좌표 · 변형 스타일 재료와 후보의 기능 설명은 백엔드가 보낸다(POST /render). 여기서는
장면에서 서명 · 고른 recipe · 판정 한 마디를 뽑아 문서에 넘길 뿐이다 — 엣지 굵기 ·
색 · 순번 규칙이 서버와 JS 두 곳으로 갈라지지 않게 하려는 것이다.

고른 노드(picked)는 문서 안 변수로만 둔다. 카메라는 해석 서명과 함께 창 저장소에
적어 두므로 같은 해석을 다시 그려도 화면이 안 튄다.
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
          보여줄 그림이 달라짐. 후보는 network 의 변형 키에서 옴
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


def graph_html(rendered: dict, view: dict | None, ratios: dict) -> str:
    """render 응답과 장면으로 그래프 문서 한 벌을 만듦.

    입력  POST /render 응답 · 지금 장면 · config.layout_ratios() 결과
    출력  iframe 에 넣을 HTML 문서
    규칙  목록은 늘 후보 전부임. 좁혀도 줄이 사라지지 않고 흐려질 뿐이라
          서버도 변형마다 따로 만들지 않음
    """
    order = _candidate_order(rendered)
    return network.main_html(
        rendered["network"],
        theme.colors(),
        path_panel.recipe_rows_markup(
            rendered.get("chips") or [], order,
            path_panel.chosen_recipe(view), theme.highlight(),
            rendered.get("recipes"),
        ),
        status=path_panel.recipe_status(view, len(order)),
        order=order,
        height=styles.graph_height(ratios),
        signature=_signature(rendered, view),
        side_ratio=ratios["side_ratio"],
    )


def render_graph_section(
    rendered: dict | None = None,
    view: dict | None = None,
    ratios: dict | None = None,
):
    """온톨로지 그래프 iframe 하나.

    입력  rendered  POST /render 응답. network · chips 가 들어 있음
          view      지금 장면. 서명 · 고른 recipe · 판정 한 마디를 뽑음
          ratios    config.layout_ratios() 결과
    규칙  후보가 없어도 그림. 실행 전에는 온톨로지 전체를 칸에 맞춰 보여주고,
          NO_MATCH 에서는 지도는 떠 있는데 켜지는 길이 하나도 없음
    제약  높이를 CSS 로 주지 않는다.
          iframe 은 height 속성으로 고정되므로 CSS 로 덮을 수 없음
    """
    if not rendered or not rendered.get("network"):
        st.markdown(
            styles.note_markup("그래프를 불러올 수 없습니다. Backend 가 실행 중인지 확인하세요."),
            unsafe_allow_html=True,
        )
        return

    ratios = ratios or config.LAYOUT
    st.components.v1.html(graph_html(rendered, view, ratios),
                          height=styles.graph_height(ratios))
