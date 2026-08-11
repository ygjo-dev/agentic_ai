"""노드 등록 폼 컴포넌트.

계산은 백엔드가 한다. 여기서는 입력을 받고 결과를 보여줄 뿐이다.
"""

import streamlit as st

from demo.ui import api_client, config
from demo.ui.api_client import ApiError

# 등록 샘플. inputs/outputs 는 온톨로지 인터페이스를 그대로 쓴다.
NODE_SAMPLES = [
    # 시연의 주력. 궤도 점검 보고서는 지금 어느 recipe 에도 안 들어가 실선이 0개다 —
    # 이 노드를 등록하면 그 끊긴 자리가 이어지고 궤도 그룹에 점선이 붙는다.
    (
        "궤도 결함 이력 요약",
        "궤도 점검 보고서에서 결함이 어떻게 이어져 왔는지 요약한다.",
        ["DocumentData"],
        ["AnalysisResult"],
    ),
    # 기상 도메인 쪽에 붙는 경우.
    (
        "적설 영향 분석",
        "기상 관측값에서 적설이 운행에 미치는 영향을 분석한다.",
        ["WeatherData"],
        ["AnalysisResult"],
    ),
    # 어느 대상에도 매이지 않는 범용 노드. subject 가 비어 점선이 안 생긴다.
    (
        "Excel 보고서 생성",
        "분석 결과를 Excel 표로 생성한다.",
        ["AnalysisResult"],
        ["DocumentData"],
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

    interfaces = list((graph or {}).get("interfaces") or [])

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

    col_in, col_out = st.columns(2)
    with col_in:
        # 불러오기 노드는 입력이 없다. 비워둘 수 있어야 한다.
        inputs = st.multiselect("inputs", interfaces, key="node_inputs")
    with col_out:
        outputs = st.multiselect("outputs", interfaces, key="node_outputs")

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
        # 등록 성공/실패는 DEBUG 와 무관하게 보여준다. properties 와 reason 은
        # LLM 이 왜 그렇게 판단했는지를 보는 개발용 정보라 감춘다.
        st.success(f"등록 : **{result['node_id']}**")
        if config.DEBUG:
            st.caption(f"properties : {result['properties'] or '(없음)'}")
            st.caption(f"reason : {result['reason']}")
        st.caption(f"새 recipe {len(result['recipe_ids'])}개 : {', '.join(result['recipe_ids'])}")
