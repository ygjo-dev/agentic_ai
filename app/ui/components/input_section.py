"""입력 줄. 발화 · Run · KRRI_ASAP 연동 자리를 한 줄에 둔다."""

import streamlit as st


def render_input_section():
    """사용자 입력을 받는 한 줄.

    출력  (utterance, run_clicked, follow_slot)
          follow_slot 은 연동 스위치를 그릴 빈 자리. 채우는 것은 화면 맨 끝임
    규칙  그래프가 높이를 다 쓰도록 한 줄로 둠. 입력칸 이름은 placeholder 가 대신함
    """
    field, run, follow = st.columns([0.62, 0.1, 0.28], gap="small")

    with field:
        utterance = st.text_input(
            "발화",
            key="utterance",
            placeholder="발화를 입력하세요 — 예) 승강장 CCTV 동영상으로 혼잡도를 분석해줘",
            label_visibility="collapsed",
        )
    with run:
        run_clicked = st.button("Run", type="primary", use_container_width=True)
    with follow:
        # 자리만 잡아 둔다. 따라 보기 조각이 새 회차를 보면 전체 rerun 을 걸기
        # 때문에, 여기서 채우면 Run 클릭이 그 rerun 에 삼켜진다.
        follow_slot = st.container(key="follow_slot")

    return utterance, run_clicked, follow_slot
