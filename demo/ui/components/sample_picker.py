"""Sample 선택 컴포넌트.

목록에는 발화만 보여준다. 상태(SELECT/CLARIFY/NO_MATCH)와 recipe id 를
같이 노출하면 답을 미리 알려주는 셈이라 시연에서 의미가 없다.

기대값은 자료로만 남겨둔다. 예전에는 정답 경로를 그래프에 함께 그렸지만,
그러려면 프론트엔드가 recipe 파일을 읽어 노드 사슬을 펼쳐야 했다.
도메인 조회를 백엔드로 옮기면서 정답 경로 표시는 걷어냈다.
"""

import streamlit as st

# (발화, 기대 status, 기대 recipe_id, 기대 후보)
SAMPLES = [
    # SELECT : 발화가 Recipe 하나로 유일하게 결정.
    # 소스(CCTV)를 밝혀 검측차 쪽(recipe_006)과 갈린다.
    ("승강장 CCTV 동영상으로 혼잡도를 분석해줘", "SELECT", "recipe_004", ["recipe_004"]),
    # 분석에서 끝나므로 문서 생성까지 가는 018/019 는 후보가 아니다.
    ("점검 문서로 승강장 장애 발생 빈도를 분석해줘", "SELECT", "recipe_008", ["recipe_008"]),
    ("검측차가 촬영한 본선 이미지로 구조물 균열을 분석하고 결과를 PPT 문서로 만들어줘", "SELECT", "recipe_017", ["recipe_017"]),
    # CLARIFY : Recipe 후보가 2개 이상으로 갈린다.
    # 산출 방식이 갈림 (Word / PPT)
    ("승강장 CCTV 동영상으로 혼잡도를 분석하고 결과를 문서로 만들어줘", "CLARIFY", None, ["recipe_010", "recipe_011"]),
    # 분석 방법이 갈림 (승강장을 영상으로도, 문서로도 분석 가능)
    ("승강장 상태를 분석해줘", "CLARIFY", None, ["recipe_004", "recipe_006", "recipe_008"]),
    # NO_MATCH : Menu 에 없는 기능
    ("CCTV 영상으로 열차 속도를 분석해줘", "NO_MATCH", None, []),
    ("오늘 날씨 알려줘", "NO_MATCH", None, []),
]

PLACEHOLDER = "(직접 입력)"

EXPECTED_BY_UTTERANCE = {
    utterance: {"status": status, "recipe_id": recipe_id, "candidate_recipe_ids": candidates}
    for utterance, status, recipe_id, candidates in SAMPLES
}


def use_sample():
    """콤보박스 선택 콜백. 발화를 입력란에 넣는다."""
    choice = st.session_state.get("sample_choice")

    if choice == PLACEHOLDER:
        return

    st.session_state["utterance"] = choice


def render_sample_picker():
    """샘플 콤보박스. 발화 문자열만 노출한다."""
    st.selectbox(
        "Sample",
        [PLACEHOLDER, *(utterance for utterance, *_ in SAMPLES)],
        key="sample_choice",
        on_change=use_sample,
    )
