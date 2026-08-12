"""검토 관문. 대상이 어긋나는 경로를 사람이 골라 승인한다.

자동 승격된 경로는 여기 안 온다 — 그것은 아래 iframe 이 새 recipe 칩 사슬로
보여준다. 여기 오는 것은 crosses_groups 가 표시한 애매한 것뿐이고, 검토 대상이
0개면 아무것도 그리지 않는다 — 물을 게 없으면 안 묻는다.

설명글은 없다. 자동 승격(분홍 칩, iframe 안)과 검토 대상(amber 칩 + 체크박스,
Streamlit 위젯)은 색과 배치로 갈린다.

체크박스는 iframe 밖 Streamlit 위젯이다. 승인은 백엔드 호출이라 파이썬으로
돌아와야 하고, iframe 안 JS 는 파이썬을 못 부른다.
"""

import html

import streamlit as st

from demo.ui import api_client, theme
from demo.ui.api_client import ApiError
from demo.ui.components import path_panel


def review_chip(step: dict, index: int) -> str:
    """검토 대상 경로의 칩 하나. 대상이 붙은 노드는 그 대상 이름을 함께 단다.

    어긋남은 대상끼리 비교해야 보인다 — 이름만 늘어놓으면 어디서 어긋나는지
    사람이 온톨로지를 외우고 있어야 한다. 대상 이름은 그룹 노드와 같은 색이라
    상단 그래프의 타원과 이어 읽힌다.
    """
    name = html.escape(step.get("name") or step.get("node_id", ""))
    about = step.get("about") or []
    tail = (
        f'<span class="chip-about" style="color:{theme.get("group")}">'
        f"{html.escape('·'.join(about))}</span>"
        if about
        else ""
    )
    return (
        f'<span class="chip" style="--i:{index}; border-color:{theme.get("review")}">'
        f"{name}{tail}</span>"
    )


def review_chain(entry: dict) -> str:
    """검토 대상 경로 한 줄. 칩과 화살표는 자동 승격 사슬과 같은 문법이다."""
    steps = entry.get("steps") or []
    parts = []
    for position, step in enumerate(steps):
        parts.append(review_chip(step, position))
        if position < len(steps) - 1:
            parts.append(path_panel.link(position))
    return f'<div class="chain">{"".join(parts)}</div>'


def gate_height(pending_count: int) -> int:
    """관문이 차지하는 픽셀. 하단 iframe 높이에서 뺀다.

    안 빼면 iframe 이 패널 밖으로 밀려 아래가 잘린다(overflow: hidden).
    한 줄 ~40px + 버튼 줄 ~54px. 줄이 많으면 CSS max-height 가 스크롤로 접는다.
    """
    if not pending_count:
        return 0
    return min(pending_count, 6) * 40 + 54


def render_review_gate(view) -> None:
    """검토 대상 목록 + 승인 버튼. 등록 직후 pending 이 있을 때만 나타난다.

    체크는 전부 해제 상태로 시작한다 — 기본값이 승인이면 사람이 안 보고
    넘기게 되고, 그러면 관문이 없는 것과 같다. 승인을 누르면 고른 것만
    recipe 가 되고 안 고른 것은 조용히 사라진다.
    """
    if not isinstance(view, dict) or view.get("kind") != "register":
        return
    result = view.get("result") or {}
    pending = result.get("pending") or []
    if not pending:
        return

    picked = []
    for index, entry in enumerate(pending):
        col_check, col_chain = st.columns([0.05, 0.95], gap="small")
        with col_check:
            # 등록마다 노드 id 가 달라 체크 상태가 다음 등록으로 새지 않는다.
            checked = st.checkbox(
                "승인",
                key=f"review_{result.get('node_id', '')}_{index}",
                label_visibility="collapsed",
            )
        with col_chain:
            st.markdown(review_chain(entry), unsafe_allow_html=True)
        if checked:
            picked.append(entry["chain"])

    if st.button("승인", key="review_approve"):
        _approve(result, picked)


def _approve(result: dict, picked: list[list[str]]) -> None:
    """고른 경로를 승인하고 등록 결과에 합친다.

    counts 는 recipe 만 승인 후 값으로 바꾼다 — 노드 쌍까지 갈아끼우면
    "노드 12 → 13" 이 "13 → 13" 이 되어 등록 장면의 스탯이 사라진다.
    pending 을 비우면 상단 그래프의 검토 표시와 이 관문이 함께 사라진다.
    """
    try:
        approved = api_client.approve_chains(picked)
    except ApiError as exc:
        st.error(str(exc))
        return

    counts = dict(result.get("counts") or {})
    if approved.get("counts", {}).get("recipes"):
        before = (counts.get("recipes") or [0, 0])[0]
        counts["recipes"] = [before, approved["counts"]["recipes"][1]]

    # 승인한 경로를 자동 승격 쪽으로 옮긴다. 하단에서 amber 였던 길이 분홍이
    # 되고, 고르지 않은 것은 pending 이 비면서 그대로 사라진다.
    accepted = dict(result.get("accepted") or {})
    accepted["recipe_ids"] = [
        *(accepted.get("recipe_ids") or []), *approved["recipe_ids"]
    ]
    accepted["chains"] = [*(accepted.get("chains") or []), *picked]

    merged = {
        **result,
        "recipe_ids": [*(result.get("recipe_ids") or []), *approved["recipe_ids"]],
        "paths": {**(result.get("paths") or {}), **(approved.get("paths") or {})},
        # 승인으로 처음 생긴 실선은 이제 "새로 생긴 것" 이다. 분홍으로 강조된다.
        "new_solid_edges": [
            *(result.get("new_solid_edges") or []),
            *(approved.get("new_solid_edges") or []),
        ],
        "accepted": accepted,
        "counts": counts,
        "pending": [],
        "version": approved.get("version", result.get("version")),
    }

    st.session_state["registration"] = merged
    st.session_state["view"] = {"kind": "register", "result": merged}
    st.rerun()
