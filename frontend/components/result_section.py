"""결과 표시 섹션 컴포넌트."""

import streamlit as st

STATUS_BADGE = {
    "SELECT": "🟢",
    "CLARIFY": "🟡",
    "NO_MATCH": "🔴",
}


def render_result_section(result: dict, node_flow_fn):
    """
    Recipe 선택 결과를 표시.

    Args:
        result: resolve 함수의 반환값
        node_flow_fn: recipe_id -> node flow 문자열로 변환하는 함수
    """
    st.subheader("Result")

    st.markdown("##### Status")
    badge = STATUS_BADGE.get(result["status"], "⚪")
    st.markdown(f"## {badge} {result['status']}")

    st.markdown("##### Recipe")
    if result["recipe_id"]:
        st.markdown(f"**{result['recipe_id']}**")
        st.markdown(node_flow_fn(result["recipe_id"]))
    else:
        st.markdown("*없음*")

    st.markdown("##### Candidates")
    if result["candidate_recipe_ids"]:
        for cid in result["candidate_recipe_ids"]:
            st.markdown(f"- **{cid}** : {node_flow_fn(cid)}")
    else:
        st.markdown("*없음*")

    st.markdown("##### Reason")
    st.markdown(result["reason"] if result["reason"] else "*없음*")
