"""하단 패널. 발화가 어떤 실행 경로가 됐는지, 또는 무엇이 새로 생겼는지 보여준다.

상단 그래프는 온톨로지 전체(지식)를, 여기는 거기서 뽑아낸 답(결과)을 맡는다.

Graphviz 를 쓰지 않는다 — 1/3 높이에 9노드 그래프를 또 그리면 글씨가 안 보인다.
경로는 본질적으로 선형 사슬이라 칩+화살표가 훨씬 잘 읽히고, dot 왕복이 없어
즉각적이며 애니메이션을 붙이기 쉽다.

마크업 생성은 Streamlit 없이 부를 수 있는 순수 함수다(테스트 때문).
"""

import html

import streamlit as st

from frontend import config, focus, styles

# 안내 문구를 두지 않는다. 실행 전에는 하단 지도가 그대로 떠 있고, NO_MATCH 면
# 지도는 있는데 켜지는 길이 없다 — 문구 없이 그림으로 읽힌다.
# 발표자가 말로 설명하므로 화면에 글이 필요 없고, 글이 없으면 오류가 났을 때 티가 난다.


def chip(name: str, index: int, color: str) -> str:
    """노드 이름 하나. 순서대로 나타나도록 index 를 넘긴다.

    상단 그래프의 노드는 두 줄로 접혀 있지만 여기서는 한 줄로 둔다 —
    가로 공간이 넉넉하고, 접으면 사슬의 흐름이 끊겨 읽힌다.
    """
    return (
        f'<span class="chip" style="--i:{index}; border-color:{color}">'
        f"{html.escape(name)}</span>"
    )


def link(index: int) -> str:
    """칩 사이의 화살표.

    인터페이스 이름은 적지 않는다. 무엇이 흘러가는지는 노드 이름만으로 읽히고,
    같은 이름이 여러 줄에 반복되면 화면이 글자로 덮인다.
    """
    return (
        f'<span class="link" style="--i:{index}">'
        f'<span class="arrow-line"></span>'
        f"</span>"
    )


def path_chain(recipe_id: str, steps: list[dict], color: str) -> str:
    """recipe 하나를 칩 사슬 한 줄로.

    recipe id 는 적지 않는다. 줄끼리는 노드 내용으로 구분되고, id 는 사람이
    읽을 정보가 아니다. recipe_id 인자는 호출부의 형태를 유지하려고 남긴다.
    """
    if not steps:
        return '<div class="chain"></div>'

    parts = []
    for position, step in enumerate(steps):
        name = str(step.get("name") or step.get("node_id", ""))
        parts.append(chip(name, position, color))
        if position < len(steps) - 1:
            parts.append(link(position))

    return f'<div class="chain">{"".join(parts)}</div>'


# 순서 계산은 frontend/focus.py 가 한다 — 그래프 쪽도 같은 순서를 써야 한다.
ordered_recipe_ids = focus.ordered_recipe_ids


def chips_markup(paths: dict, recipe_ids: list[str], color: str) -> str:
    """recipe 목록 전체를 칩 사슬로. iframe 안에 들어간다.

    비면 빈 칸이다. 안내 문구를 넣지 않는다 — 옆 그래프가 이미 상태를 말한다.
    """
    return "".join(
        path_chain(recipe_id, (paths or {}).get(recipe_id) or [], color)
        for recipe_id in recipe_ids
    )


def paths_markup(result: dict | None, color: str | None = None) -> str:
    """결과의 경로 사슬. 후보가 없으면 빈 문자열이다.

    CLARIFY 는 후보를 나란히 둔다. 클릭으로 좁히지 않는다 — 여럿이 보이는 것
    자체가 "아직 안 정해졌다" 를 말해준다.
    """
    if not result:
        return ""

    return chips_markup(
        result.get("paths") or {},
        ordered_recipe_ids(result),
        color or config.HIGHLIGHT_COLOR,
    )


def utterance_markup(utterance: str | None) -> str:
    """입력 발화. 화면에서 가장 눈에 띄어야 하는 문장이다."""
    if not utterance:
        return ""
    return f'<div class="utterance">“{html.escape(utterance)}”</div>'


def counts_markup(counts: dict | None) -> str:
    """노드 9 → 10, Recipe 21 → 27.

    이 숫자가 비전공자에게 "시스템이 스스로 확장됐다" 를 보여주는 장치다.
    """
    if not counts:
        return ""

    stats = []
    for label, key in (("노드", "nodes"), ("Recipe", "recipes")):
        pair = counts.get(key) or []
        if len(pair) != 2:
            continue
        before, after = pair
        stats.append(
            f'<span class="stat"><span class="stat-label">{label}</span>'
            f'<span class="stat-before">{before}</span>'
            f'<span class="stat-arrow">→</span>'
            f'<span class="stat-after">{after}</span></span>'
        )

    return f'<div class="stats">{"".join(stats)}</div>' if stats else ""


def registration_header(result: dict) -> str:
    """등록 결과의 머리말. 새 노드 이름과 스탯."""
    node = result.get("node") or {}
    name = node.get("name") or result.get("node_id", "")

    return (
        f'<div class="utterance">'
        f'<span class="new-badge" style="background:{config.NEW_COLOR}">새 노드</span> '
        f"{html.escape(str(name))}</div>" + counts_markup(result.get("counts"))
    )


def skeleton_markup() -> str:
    """응답을 기다리는 동안. LLM 지연이 길어 스피너만으로는 멈춘 것처럼 보인다."""
    bars = "".join(f'<div class="skel-row" style="--i:{i}"></div>' for i in range(3))
    return f'<div class="skeleton">{bars}</div>'


def band_markup(view: dict | None) -> str:
    """하단 위쪽 얇은 띠. 발화(또는 새 노드 이름)뿐이다.

    범례는 두지 않는다 — 색이 무엇인지는 발표자가 말한다.
    경로 사슬도 여기 없다. 아래 iframe 이 그래프와 함께 그린다.
    """
    if not isinstance(view, dict):
        return ""

    if view.get("kind") == "register":
        return registration_header(view["result"])

    return utterance_markup(view.get("utterance"))


def render_band(view: dict | None):
    """띠를 그린다. 오류도 여기서 작게 처리한다."""
    if isinstance(view, dict) and "error" in view:
        # 실패는 DEBUG 와 무관하게 언제나 보여준다. 화면이 조용하면 더 나쁘다.
        st.markdown(styles.note_markup(view["error"]), unsafe_allow_html=True)
        return

    st.markdown(band_markup(view), unsafe_allow_html=True)

    if config.DEBUG and isinstance(view, dict) and view.get("result"):
        st.caption(f"reason : {view['result'].get('reason', '')}")
