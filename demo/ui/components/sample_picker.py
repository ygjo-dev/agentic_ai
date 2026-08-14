"""Sample 선택 컴포넌트.

목록에는 발화만 보여준다. 상태(SELECT/CLARIFY/NO_MATCH)와 recipe id 를
같이 노출하면 답을 미리 알려주는 셈이라 시연에서 의미가 없다.

기대값은 자료로만 남겨둔다. 예전에는 정답 경로를 그래프에 함께 그렸지만,
그러려면 프론트엔드가 recipe 파일을 읽어 노드 사슬을 펼쳐야 했다.
도메인 조회를 백엔드로 옮기면서 정답 경로 표시는 걷어냈다.

recipe 6개가 두 갈래다 — 승강장 CCTV(001~003) · 궤도 검측차(004~006).
각 갈래 안에서는 분석까지냐 Word 냐 PPT 냐로 갈린다. 그래서 **무엇으로
시작하는가** 와 **어디서 끝나는가** 를 둘 다 밝혀야 하나로 좁혀진다.
아래 넷은 그 갈림 중 실측으로 재현되는 것만 남긴 것이다.
"""

import streamlit as st

# (발화, 기대 status, 기대 recipe_id, 기대 후보)
#
# 넷 다 실측으로 골랐다.
#   2026-08-15 · qwen2.5:7b · _init(recipe 6) · 각 10회 (NO_MATCH 는 5회)
#   10/10 · 10/10 · 10/10 · 5/5
#
# 이 목록이 보여주는 것
#   대상이 갈린다                        승강장 · 궤도
#   어디서 끝나는지가 갈린다              분석까지 · 문서까지
#   형식을 안 밝히면 후보가 둘로 갈린다    CLARIFY
#   영역 밖이면 안 한다                   NO_MATCH
#
# 무엇이 빠졌는가 — 이것이 중요하다
#   **형식을 지정해 하나로 좁히는 발화가 없다.** "Word로 만들어줘" 가 9/10 이라
#   뺐다. 그래서 이 목록만으로는 "형식을 밝히면 하나가 된다" 를 못 보여준다.
#   필요하면 발표자가 직접 "궤도 균열 확인한 거 Word로 만들어줘" 를 친다 —
#   10에 1번은 {004, 005} 로 갈린다.
#
#   recipe_005 · recipe_006 은 이 목록으로는 한 번도 안 켜진다.
#
# 온톨로지나 menu 가 바뀌면 다시 재야 한다 (tools/check_resolve.py).
SAMPLES = [
    # SELECT : 발화가 Recipe 하나로 유일하게 결정.
    # 분석에서 끝나므로 보고서까지 가는 002/003 은 후보가 아니다.
    ("승강장에 사람이 얼마나 몰렸는지 분석해줘", "SELECT", "recipe_001", ["recipe_001"]),
    # 대상(궤도 검측차)이 갈라서 001~003 은 후보가 아니다.
    ("검측차 영상에서 레일 갈라진 데 있는지 확인해줘", "SELECT", "recipe_004", ["recipe_004"]),
    # CLARIFY : 산출 형식을 안 밝혀 Word / PPT 로 갈린다.
    ("승강장 혼잡도 결과를 문서로 정리해줘", "CLARIFY", None, ["recipe_002", "recipe_003"]),
    # NO_MATCH : 이 시스템의 영역 밖이다.
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
