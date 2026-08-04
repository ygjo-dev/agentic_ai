"""입력 섹션 컴포넌트."""

import streamlit as st


def render_input_section():
    """
    사용자 입력을 받는 영역을 렌더링.

    Returns:
        tuple: (utterance, run_clicked)
    """
    st.subheader("User Input")

    utterance = st.text_input(
        "발화를 입력하세요",
        key="utterance",
        placeholder="예) CCTV로 군중을 분석해줘",
    )
    run_clicked = st.button("Run", type="primary", use_container_width=True)

    return utterance, run_clicked
