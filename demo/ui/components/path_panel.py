"""하단 패널. 발화가 어떤 실행 경로가 됐는지, 또는 무엇이 새로 생겼는지 보여준다.

상단 그래프는 온톨로지 전체(지식)를, 여기는 거기서 뽑아낸 답(결과)을 맡는다.

Graphviz 를 쓰지 않는다 — 1/3 높이에 9노드 그래프를 또 그리면 글씨가 안 보인다.
경로는 본질적으로 선형 사슬이라 칩+화살표가 훨씬 잘 읽히고, dot 왕복이 없어
즉각적이며 애니메이션을 붙이기 쉽다.

경로를 무엇으로 채울지는 백엔드가 정한다(graph_svg/focus.py). 여기는 이름
사슬을 받아 칩으로 그리기만 한다 — 순서 계산이 두 곳에 있으면 그래프와 목록이
서로 다른 순서를 말하게 된다.

마크업 생성은 Streamlit 없이 부를 수 있는 순수 함수다(테스트 때문).
"""

import html

import streamlit as st

from demo.ui import config, styles, theme

# 안내 문구를 두지 않는다. 실행 전에는 하단 지도가 그대로 떠 있고, NO_MATCH 면
# 지도는 있는데 켜지는 길이 없다 — 문구 없이 그림으로 읽힌다.
# 발표자가 말로 설명하므로 화면에 글이 필요 없고, 글이 없으면 오류가 났을 때 티가 난다.


def chip(name: str, index: int, color: str) -> str:
    """노드 이름 하나.

    입력  이름 · 순서(등장 애니메이션용) · 테두리 색
    출력  .chip span 마크업
    제약  여기서는 이름을 두 줄로 접지 않는다.
          상단 그래프의 노드는 접혀 있지만 여기는 가로 공간이 넉넉하고,
          접으면 사슬의 흐름이 끊겨 읽힘
    """
    return (
        f'<span class="chip" style="--i:{index}; border-color:{color}">'
        f"{html.escape(name)}</span>"
    )


def link(index: int) -> str:
    """칩 사이의 화살표.

    입력  순서(등장 애니메이션용)
    출력  .link span 마크업
    제약  인터페이스 이름을 적지 않는다.
          무엇이 흘러가는지는 노드 이름만으로 읽히고, 같은 이름이 여러 줄에
          반복되면 화면이 글자로 덮임
    """
    return (
        f'<span class="link" style="--i:{index}">'
        f'<span class="arrow-line"></span>'
        f"</span>"
    )


def path_chain(names: list[str], color: str) -> str:
    """이름 사슬 하나를 칩 한 줄로.

    입력  이름 목록 · 칩 테두리 색
    출력  .chain div 마크업. 비면 빈 .chain
    제약  recipe id 를 적지 않는다.
          줄끼리는 노드 내용으로 구분되고, id 는 사람이 읽을 정보가 아님
    """
    if not names:
        return '<div class="chain"></div>'

    parts = []
    for position, name in enumerate(names):
        parts.append(chip(name, position, color))
        if position < len(names) - 1:
            parts.append(link(position))

    return f'<div class="chain">{"".join(parts)}</div>'


def chips_markup(chains: list[list[str]], color: str) -> str:
    """이름 사슬 목록 전체를 칩으로. iframe 안에 들어감.

    입력  이름 사슬 목록 · 칩 테두리 색
    출력  .chain div 여러 개. 비면 빈 문자열
    제약  안내 문구를 넣지 않는다. 옆 그래프가 이미 상태를 말함
    """
    return "".join(path_chain(names, color) for names in chains or [])


def utterance_markup(utterance: str | None) -> str:
    """입력 발화. 화면에서 가장 눈에 띄어야 하는 문장."""
    if not utterance:
        return ""
    return f'<div class="utterance">“{html.escape(utterance)}”</div>'


def registration_header(result: dict) -> str:
    """등록 결과의 머리말. 새 노드 이름과 스탯."""
    node = result.get("node") or {}
    name = node.get("name") or result.get("node_id", "")

    return (
        f'<div class="utterance">'
    )


def skeleton_markup() -> str:
    """응답을 기다리는 동안. LLM 지연이 길어 스피너만으로는 멈춘 것처럼 보임."""
    bars = "".join(f'<div class="skel-row" style="--i:{i}"></div>' for i in range(3))
    return f'<div class="skeleton">{bars}</div>'


def band_markup(view: dict | None) -> str:
    """하단 위쪽 얇은 띠. 발화(또는 새 노드 이름)뿐.

    입력  지금 장면
    출력  마크업. 장면이 없으면 빈 문자열
    제약  범례를 두지 않는다. 색이 무엇인지는 발표자가 말함
          경로 사슬을 여기 두지 않는다. 아래 iframe 이 그래프와 함께 그림
    """
    if not isinstance(view, dict):
        return ""

    if view.get("kind") == "register":
        return registration_header(view["result"])

    return utterance_markup(view.get("utterance"))


def render_band(view: dict | None):
    """띠를 그림.

    규칙  오류도 여기서 작게 처리. 실패는 DEBUG 와 무관하게 언제나 보여줌
    """
    if isinstance(view, dict) and "error" in view:
        # 실패는 DEBUG 와 무관하게 언제나 보여준다. 화면이 조용하면 더 나쁘다.
        st.markdown(styles.note_markup(view["error"]), unsafe_allow_html=True)
        return

    st.markdown(band_markup(view), unsafe_allow_html=True)

    if config.DEBUG and isinstance(view, dict) and view.get("result"):
        st.caption(f"reason : {view['result'].get('reason', '')}")
