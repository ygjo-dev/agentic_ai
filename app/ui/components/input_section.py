"""입력 섹션 컴포넌트."""

import streamlit as st

from app.ui import config


def render_input_section():
    """사용자 입력을 받는 영역.

    출력  (utterance, run_clicked)
    규칙  지도 문맥이 고정값이라는 것을 한 줄로 밝힘. 이 화면에는 지도가 없는데
          "여기" 나 "지금 보이는 곳" 이 통하므로, 무엇을 보고 있는 셈인지
          안 적으면 시연장에서 오해를 부름
    """
    st.subheader("User Input")

    utterance = st.text_input(
        "발화를 입력하세요",
        key="utterance",
        placeholder="예) 승강장 CCTV 동영상으로 혼잡도를 분석해줘",
    )
    run_clicked = st.button("Run", type="primary", use_container_width=True)
    st.caption(config.FIXED_VIEW_LABEL)

    return utterance, run_clicked
