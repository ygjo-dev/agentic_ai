"""Sample 선택 컴포넌트.

목록에는 발화만 보여준다. 상태(SELECT/CLARIFY/NO_MATCH)와 recipe id 를
같이 노출하면 답을 미리 알려주는 셈이라 시연에서 의미가 없다.

기대값은 자료로만 남겨둔다. 예전에는 정답 경로를 그래프에 함께 그렸지만,
그러려면 프론트엔드가 recipe 파일을 읽어 노드 사슬을 펼쳐야 했다.
도메인 조회를 백엔드로 옮기면서 정답 경로 표시는 걷어냈다.

recipe 2개가 한 갈래다 — 말한 장소로 시작해 좌표에서 끝나느냐(001)
CCTV 조회까지 가느냐(002). 시작이 같으므로 **어디서 끝나는가** 하나로 갈린다.
아래 둘이 그 갈림이다.
"""

import streamlit as st

# (발화, 기대 status, 기대 recipe_id, 기대 후보)
#
# 이 목록이 보여주는 것
#   어디서 끝나는지가 갈린다    좌표까지 · CCTV 조회까지
#
# **아직 안 쟀다.** 001 은 002 의 앞토막이라 끝점이 실제로 갈리는지가 관건이고,
# 그것은 실행기를 붙인 화면에서 본다. 예전 발화 넷과 측정값은 NOTES.md.
SAMPLES = [
    # SELECT : 좌표에서 끝나므로 CCTV 조회까지 가는 002 는 후보가 아니다.
    ("오송역 좌표 알려줘", "SELECT", "recipe_001", ["recipe_001"]),
    # SELECT : CCTV 를 밝혀 002 로 유일하게 결정.
    ("오송역 CCTV 보여줘", "SELECT", "recipe_002", ["recipe_002"]),
]

PLACEHOLDER = "(직접 입력)"

EXPECTED_BY_UTTERANCE = {
    utterance: {"status": status, "recipe_id": recipe_id, "candidate_recipe_ids": candidates}
    for utterance, status, recipe_id, candidates in SAMPLES
}


def use_sample():
    """콤보박스 선택 콜백. 발화를 입력란에 넣음."""
    choice = st.session_state.get("sample_choice")

    if choice == PLACEHOLDER:
        return

    st.session_state["utterance"] = choice


def render_sample_picker():
    """샘플 콤보박스. 발화 문자열만 노출함."""
    st.selectbox(
        "Sample",
        [PLACEHOLDER, *(utterance for utterance, *_ in SAMPLES)],
        key="sample_choice",
        on_change=use_sample,
    )
