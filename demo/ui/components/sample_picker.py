"""Sample 선택 컴포넌트.

목록에는 발화만 보여준다. 상태(SELECT/CLARIFY/NO_MATCH)와 recipe id 를
같이 노출하면 답을 미리 알려주는 셈이라 시연에서 의미가 없다.

기대값은 자료로만 남겨둔다. 예전에는 정답 경로를 그래프에 함께 그렸지만,
그러려면 프론트엔드가 recipe 파일을 읽어 노드 사슬을 펼쳐야 했다.
도메인 조회를 백엔드로 옮기면서 정답 경로 표시는 걷어냈다.
"""

import streamlit as st

# (발화, 기대 status, 기대 recipe_id, 기대 후보)
#
# recipe 6개가 두 갈래다 — 승강장 CCTV(001~003) · 궤도 검측차(004~006).
# 각 갈래 안에서는 분석까지냐 Word 냐 PPT 냐로 갈린다.
# 그래서 **무엇으로 시작하는가** 와 **어디서 끝나는가** 를 둘 다 밝혀야 하나로 좁혀진다.
SAMPLES = [
    # SELECT : 발화가 Recipe 하나로 유일하게 결정.
    # 분석에서 끝나므로 보고서까지 가는 002/003 은 후보가 아니다.
    ("승강장 CCTV 영상으로 혼잡도를 분석해줘", "SELECT", "recipe_001", ["recipe_001"]),
    # 시작(검측차)과 산출 형식(PPT)을 둘 다 밝혀 하나로 좁혀진다.
    ("궤도 검측차 영상으로 균열을 찾아서 PPT 로 만들어줘", "SELECT", "recipe_006", ["recipe_006"]),
    # CLARIFY : Recipe 후보가 2개 이상으로 갈린다.
    # 산출 형식이 갈림 (Word / PPT)
    ("승강장 혼잡도를 분석하고 보고서로 만들어줘", "CLARIFY", None, ["recipe_002", "recipe_003"]),
    # 산출 형식이 갈림 (Word / PPT)
    ("궤도 상태를 분석해서 보고서로 만들어줘", "CLARIFY", None,
     ["recipe_005", "recipe_006"]),
    # NO_MATCH : Menu 에 없는 기능
    ("승객 민원 추세를 분석해줘", "NO_MATCH", None, []),
    ("오늘 지하철 요금 알려줘", "NO_MATCH", None, []),
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
