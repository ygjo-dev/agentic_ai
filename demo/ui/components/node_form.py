"""노드 등록 폼 컴포넌트.

계산은 백엔드가 한다. 여기서는 입력을 받고 결과를 보여줄 뿐이다.
"""

import streamlit as st

from demo.ui import api_client, config
from demo.ui.api_client import ApiError

# 등록 샘플. inputs/outputs 는 **타입 노드 id** 다. 이름이 아니다 —
# 예전에는 자유 문자열이라 한 글자만 달라도 아무와도 안 이어졌다.
NODE_SAMPLES = [
    # 시연의 주력. "이미지" 를 받으므로 프레임 추출 뒤에 붙어 승강장 경로가
    # 통째로 하나 더 생긴다. 승강장 그룹에 점선이 붙는다.
    (
        "승강장 위험 행동 검출",
        "이미지에서 승강장 승객의 위험 행동을 검출한다.",
        ["image"],
        ["analysis"],
    ),
    # 대상이 **둘** 붙는 경우. 승강장 것도 검측차 것도 CCTV 가 찍은 것이라
    # 화질 저하는 CCTV 에 관한 일이다. LLM 이 여럿을 고를 수 있는지 보여준다.
    (
        "CCTV 화질 저하 진단",
        "영상에서 렌즈 오염으로 인한 화질 저하를 진단한다.",
        ["video"],
        ["analysis"],
    ),
    # 어느 대상에도 매이지 않는 범용 노드. 대상이 비어 점선이 안 생긴다.
    (
        "Excel 보고서 생성",
        "분석 결과를 Excel 표로 생성한다.",
        ["analysis"],
        ["output_report"],
    ),
]

PLACEHOLDER = "(직접 입력)"

SAMPLE_BY_NAME = {name: (name, desc, ins, outs) for name, desc, ins, outs in NODE_SAMPLES}


def use_node_sample():
    choice = st.session_state.get("node_sample")
    if choice == PLACEHOLDER:
        return

    name, description, inputs, outputs = SAMPLE_BY_NAME[choice]
    st.session_state["node_name"] = name
    st.session_state["node_description"] = description
    st.session_state["node_inputs"] = inputs
    st.session_state["node_outputs"] = outputs


def render_node_form(graph: dict | None = None):
    """노드 등록 폼. 등록/초기화 결과는 session_state["registration"] 에 남긴다.

    Args:
        graph: Backend 의 /graph 응답. inputs/outputs 선택지가 여기서 온다.
    """
    st.subheader("노드 등록")

    # 고르는 것은 타입 노드 id 이고, 화면에 보이는 것은 그 이름이다.
    # id 를 그대로 보여주면 사람이 못 읽고, 이름을 보내면 백엔드가 못 찾는다.
    types = list((graph or {}).get("types") or [])
    type_ids = [entry["id"] for entry in types]
    type_names = {entry["id"]: entry["name"] for entry in types}

    st.selectbox(
        "등록 샘플",
        [PLACEHOLDER, *(name for name, *_ in NODE_SAMPLES)],
        key="node_sample",
        on_change=use_node_sample,
    )

    name = st.text_input("이름", key="node_name", placeholder="예) 구조물 균열 진행 추세 분석")
    description = st.text_area(
        "설명",
        key="node_description",
        placeholder="예) 문서에서 구조물 균열 폭의 시간 변화를 분석한다.",
        height=68,
    )

    def label_of(type_id):
        return type_names.get(type_id, type_id)

    col_in, col_out = st.columns(2)
    with col_in:
        inputs = st.multiselect(
            "받는 것", type_ids, key="node_inputs", format_func=label_of
        )
    with col_out:
        outputs = st.multiselect(
            "내놓는 것", type_ids, key="node_outputs", format_func=label_of
        )

    col_register, col_reset = st.columns(2)

    with col_register:
        if st.button("등록", type="primary", use_container_width=True):
            _register(name, description, inputs, outputs)

    with col_reset:
        if st.button("초기화", use_container_width=True):
            st.session_state["confirm_reset"] = True

    if st.session_state.get("confirm_reset"):
        st.warning("등록한 노드와 recipe 가 모두 사라진다. 되돌릴 수 없다.")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("정말 초기화", use_container_width=True):
                try:
                    api_client.reset_nodes()
                except ApiError as exc:
                    st.session_state["registration"] = {"error": str(exc)}
                else:
                    st.session_state["registration"] = {"reset": True}
                    # 강조가 남으면 사라진 노드를 가리키게 된다.
                    st.session_state["view"] = None
                st.session_state["confirm_reset"] = False
                st.rerun()
        with col_no:
            if st.button("취소", use_container_width=True):
                st.session_state["confirm_reset"] = False
                st.rerun()

    _show_result()


def _register(name, description, inputs, outputs):
    if not name.strip() or not description.strip():
        st.session_state["registration"] = {"error": "이름과 설명을 입력하세요."}
        return
    if not outputs:
        st.session_state["registration"] = {"error": "outputs 를 하나 이상 고르세요."}
        return

    form = {
        "name": name.strip(),
        "description": description.strip(),
        "inputs": inputs,
        "outputs": outputs,
    }

    with st.spinner("LLM이 기존 온톨로지와 비교하는 중..."):
        try:
            result = api_client.register_node(**form)
        except ApiError as exc:
            # 백엔드가 detail 에 "DuplicateNode: ..." 처럼 예외 이름까지 적어 보낸다.
            # 화면 문구는 이관 전과 같다.
            st.session_state["registration"] = {"error": str(exc)}
            return

    st.session_state["registration"] = result
    # 하단과 상단이 같은 장면을 말하게 한다 — 등록 결과가 화면을 차지하고
    # 새로 생긴 것이 그래프에서 강조된다. 직전 발화 해석 결과는 덮어쓴다.
    st.session_state["view"] = {"kind": "register", "result": result}
    st.rerun()


def _show_result():
    result = st.session_state.get("registration")
    if not result:
        return

    if "error" in result:
        st.error(result["error"])
    elif result.get("reset"):
        st.success("초기화했다.")
    else:
        # 등록 성공/실패는 DEBUG 와 무관하게 보여준다. group 과 reason 은
        # LLM 이 왜 그렇게 판단했는지를 보는 개발용 정보라 감춘다.
        st.success(f"등록 : **{result['node_id']}**")
        if config.DEBUG:
            st.caption(f"속한 대상 : {result.get('group') or '(없음)'}")
            st.caption(f"reason : {result['reason']}")
        st.caption(f"새 recipe {len(result['recipe_ids'])}개 : {', '.join(result['recipe_ids'])}")
