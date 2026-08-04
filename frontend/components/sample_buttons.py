"""Sample 버튼 컴포넌트."""

import streamlit as st

from frontend.components.result_section import STATUS_BADGE

# 각 상태를 대표하는 발화
SAMPLES = [
    # SELECT : 발화가 Recipe 하나로 유일하게 결정.
    ("CCTV 군중 분석 결과를 Word 문서로 만들어줘", "SELECT", "recipe_003", ["recipe_003"]),
    ("CCTV 군중 분석 결과를 관리자에게 알려줘", "SELECT", "recipe_005", ["recipe_005"]),
    ("이미지 균열 분석 결과를 PPT 문서로 만들어줘", "SELECT", "recipe_009", ["recipe_009"]),
    # CLARIFY : Recipe 후보가 2개 이상으로 갈린다.
    ("CCTV 군중 분석 결과를 문서로 만들어줘", "CLARIFY", None, ["recipe_003", "recipe_004"]),
    ("데이터를 불러와서 분석해줘", "CLARIFY", None, ["recipe_002", "recipe_007"]),
    # NO_MATCH : Menu 에 없는 기능
    ("CCTV 영상으로 열차 속도를 분석해줘", "NO_MATCH", None, []),
    ("오늘 날씨 알려줘", "NO_MATCH", None, []),
]


def use_sample(utterance: str, status: str, recipe_id: str | None, candidate_ids: list[str]):
    """Sample 선택 콜백."""
    st.session_state["utterance"] = utterance
    st.session_state["expected"] = {
        "status": status,
        "recipe_id": recipe_id,
        "candidate_recipe_ids": candidate_ids,
    }


def render_sample_buttons(node_flow_fn):
    """
    Sample 버튼들을 렌더링.

    Args:
        node_flow_fn: recipe_id -> node flow 문자열로 변환하는 함수
    """
    st.subheader("Sample")
    for idx, (utterance, status, recipe_id, candidate_ids) in enumerate(SAMPLES):
        col_btn, col_flow = st.columns([3, 2])
        with col_btn:
            st.button(
                utterance,
                key=f"sample_{idx}",
                on_click=use_sample,
                args=(utterance, status, recipe_id, candidate_ids),
                use_container_width=True,
            )
        with col_flow:
            st.caption(f"{STATUS_BADGE.get(status, '⚪')} {status}")
            if recipe_id:
                st.markdown(f"**{recipe_id}** : {node_flow_fn(recipe_id)}")
            elif candidate_ids:
                st.markdown(" / ".join(f"**{cid}**" for cid in candidate_ids))
            else:
                st.markdown("*해당 Recipe 없음*")
