"""
Frontend Streamlit 진입점.

화면은 두 단이다.
  위쪽 = 온톨로지 전체(지식). 왼쪽에 입력, 오른쪽에 그래프.
  아래쪽 = 거기서 뽑아낸 답(결과).

비전공자가 배석한 자리에서 시연되므로 개발용 문구는 DEMO_DEBUG 로 감춘다.
다만 실패 메시지는 언제나 보여준다 — 시연 중에 실패했는데 화면이 조용하면
무엇이 잘못됐는지 아무도 모른다.
"""

import sys
import time
from pathlib import Path

import streamlit as st

# demo/ui/main.py -> demo/ui -> demo -> 저장소 뿌리. 한 단계 깊어졌다.
REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

from demo.ui import api_client, config, styles, theme
from demo.ui.api_client import ApiError
from demo.ui.components.focus_panel import render_focus_section
from demo.ui.components.graph_section import render_graph_section
from demo.ui.components.input_section import render_input_section
from demo.ui.components.node_form import render_node_form
from demo.ui.components.path_panel import render_band, skeleton_markup
from demo.ui.components.review_gate import gate_height, render_review_gate
from demo.ui.components.sample_picker import render_sample_picker

ASK, REGISTER = "사용자 질문", "노드 등록"


# ================================================================ Helper
def _is_registration(view) -> bool:
    """지금 화면이 등록 결과를 보여주는 중인가.

    강조는 그동안만 켜진다 — 상단과 하단이 같은 장면을 말하게 하려는 것이다.
    """
    return isinstance(view, dict) and view.get("kind") == "register" and "result" in view


def render_mode(view) -> tuple[str, dict | None]:
    """지금 장면의 render 모드와 강조 원본.

    등록 결과일 때만 mark 를 넘긴다. 무엇을 강조로 바꿀지는 서버가 정한다 —
    화면이 new_solid_edges 같은 도메인 형태를 알 필요가 없다.
    """
    if _is_registration(view):
        return "register", view["result"]
    if isinstance(view, dict) and view.get("kind") == "resolve":
        return "resolve", None
    return "plain", None


def recipe_ids_to_show(view) -> list[str]:
    """강조할 recipe 목록. 등록은 새로 생긴 것, 해석은 고른 것과 후보들."""
    if not isinstance(view, dict) or "error" in view:
        return []

    result = view.get("result") or {}
    if view.get("kind") == "register":
        return list(result.get("recipe_ids") or [])

    wanted = [result.get("recipe_id"), *(result.get("candidate_recipe_ids") or [])]
    return list(dict.fromkeys(r for r in wanted if r))


def format_elapsed(seconds: float) -> str:
    """Run 클릭부터 응답까지 걸린 시간을 초단위로 표시. 60초 이상이면 분:초로 표시."""
    if seconds < 60:
        return f"{seconds:.1f}초"
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes)}분 {rest:.1f}초"


# ================================================================ UI 설정
st.set_page_config(page_title="Recipe Resolver", layout="wide")

ratios = config.layout_ratios()

if config.DEBUG:
    st.title("Recipe Resolver Frontend")
    st.caption("Backend 호출을 통한 Recipe 선택")

st.session_state.setdefault("utterance", "")
# 화면은 한 번에 한 장면만 말한다. view 하나로 상단 강조와 하단 내용이 함께 정해진다.
#   kind="resolve"  -> 상단 기본 그래프 + 하단 경로 사슬
#   kind="register" -> 상단 새 노드 강조 + 하단 등록 결과
# 등록 뒤 Run 을 누르면 view 가 덮여 강조가 자연히 꺼진다.
st.session_state.setdefault("view", None)
# 탭은 st.tabs 가 아니라 session_state 에 묶는다. 노드 등록 뒤 st.rerun() 이
# 돌 때 선택이 초기화되면 시연이 끊긴다.
st.session_state.setdefault("side_tab", ASK)

# ================================================================ 그래프 조회
# 노드 등록 폼이 인터페이스 목록을 쓰므로 화면을 그리기 전에 한 번 받아둔다.
try:
    graph, graph_stale = api_client.get_graph()
except ApiError:
    graph, graph_stale = None, False

# 색은 백엔드가 정한다. CSS 를 짜기 전에 받아둬야 칩·배지가 제 색으로 나온다.
theme.set_colors((graph or {}).get("colors"))
st.markdown(styles.page_css(ratios), unsafe_allow_html=True)

view = st.session_state.get("view")

# 그리기는 백엔드가 한다. 여기서 정하는 것은 "무엇을 강조할 장면인가" 뿐이다.
mode, mark = render_mode(view)
try:
    rendered = api_client.render(mode, recipe_ids_to_show(view), mark)
    render_error = None
except ApiError as exc:
    rendered, render_error = None, str(exc)

# ================================================================ 상단
top = st.container(key="top_panel")
with top:
    left, right = st.columns([ratios["left_ratio"], 1 - ratios["left_ratio"]], gap="medium")

    with left:
        side = st.container(key="side_panel")
        with side:
            st.segmented_control(
                "화면", [ASK, REGISTER], key="side_tab", label_visibility="collapsed"
            )
            if st.session_state["side_tab"] == REGISTER:
                render_node_form(graph)
                run_clicked = False
            else:
                _, run_clicked = render_input_section()
                render_sample_picker()

    with right:
        graph_panel = st.container(key="graph_panel")
        with graph_panel:
            if graph_stale:
                # 캐시본을 쓰는 중이다. 조용히 알리되 그래프는 계속 보여준다.
                st.markdown(
                    styles.note_markup("Backend 응답이 없어 마지막으로 받은 그래프를 보여줍니다."),
                    unsafe_allow_html=True,
                )
            if render_error:
                st.markdown(styles.note_markup(f"그래프를 그릴 수 없습니다 — {render_error}"),
                            unsafe_allow_html=True)
            render_graph_section(rendered, pulse=_is_registration(view), ratios=ratios)

# ================================================================ 하단
# 위쪽 얇은 띠(발화·범례·오류·스켈레톤)는 Streamlit, 아래 본문은 iframe 하나다.
bottom = st.container(key="bottom_panel")
with bottom:
    band = st.container(key="bottom_band")
    with band:
        band_slot = st.empty()
    # 검토 관문. 등록 직후 pending 이 있을 때만 채워진다 — 체크박스는 백엔드를
    # 불러야 해서 iframe 안이 아니라 Streamlit 위젯이다.
    gate = st.container(key="review_gate")
    body = st.container(key="bottom_body")
    with body:
        body_slot = st.empty()

    if run_clicked:
        utterance_trimmed = st.session_state.get("utterance", "").strip()
        if not utterance_trimmed:
            st.session_state["view"] = {"error": "발화를 입력하세요."}
            st.rerun()

        # 기다리는 동안 자리를 비워두지 않는다. LLM 지연이 길어 스피너만으로는
        # 멈춘 것처럼 보인다.
        body_slot.markdown(skeleton_markup(), unsafe_allow_html=True)

        started = time.perf_counter()  # Run 클릭 ~ 응답 수신까지 측정
        try:
            result = api_client.resolve(utterance_trimmed)
            st.session_state["view"] = {
                "kind": "resolve",
                "utterance": utterance_trimmed,
                "result": result,
                "elapsed": time.perf_counter() - started,
            }
        except ApiError as e:
            if e.kind == "connection":
                message = "Backend에 연결할 수 없습니다. uvicorn을 먼저 실행하세요."
            elif e.kind == "timeout":
                message = "Backend 응답 시간 초과 (180초)"
            else:
                message = f"Backend 호출 실패: {str(e)}"
            st.session_state["view"] = {"error": message}
        st.rerun()  # 결과를 하단에 그리려면 다시 한 번 돈다

    with band_slot:
        render_band(view)
    with gate:
        render_review_gate(view)

    # 관문이 자리를 차지한 만큼 iframe 을 줄인다. 안 줄이면 패널 밖으로 밀려
    # 아래가 잘린다(overflow: hidden).
    pending_count = (
        len(view["result"].get("pending") or []) if _is_registration(view) else 0
    )
    with body_slot:
        render_focus_section(rendered, view, ratios, height_offset=gate_height(pending_count))

    if config.DEBUG and isinstance(view, dict) and view.get("elapsed") is not None:
        st.metric("⏱️ Run Time", format_elapsed(view["elapsed"]))
