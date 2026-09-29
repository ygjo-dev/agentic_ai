"""
Frontend Streamlit 진입점.

서비스 화면은 위에서 아래로 읽힌다.
  입력 줄   발화 · Run · KRRI_ASAP 연동
  발화 띠   해석한 발화 · 오류
  그래프    온톨로지 그래프 하나(미니맵 · 후보 recipe · 노드 설명이 같은 문서 안).
            따라 보기 회차가 있으면 오른쪽에 그 회차의 실행 기록

비전공자가 배석한 자리에서 시연되므로 개발용 문구는 DEMO_DEBUG 로 감춘다.
다만 실패 메시지는 언제나 보여준다 — 시연 중에 실패했는데 화면이 조용하면
무엇이 잘못됐는지 아무도 모른다.
"""

import sys
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# app/ui/main.py -> app/ui -> app -> 저장소 뿌리. 한 단계 깊어졌다.
REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

# api_client 가 AGENTIC_API_URL 로 백엔드를 찾으므로 그보다 먼저 읽는다.
# **화면이 백엔드에서 아는 것은 그 주소 하나뿐이다** — 언제 다른 기계로
# 나가도 여기 고칠 것이 없다.
load_dotenv(Path(REPO_ROOT) / ".env")

from app.ui import api_client, config, styles, theme
from app.ui.api_client import ApiError
from app.ui.components.follow_panel import FOLLOW_KEY, render_follow_panel, render_follow_switch
from app.ui.components.graph_section import render_graph_section
from app.ui.components.input_section import render_input_section
from app.ui.components.path_panel import render_band, skeleton_markup
from app.ui.components.testing_panel import render_test_tab


# ================================================================ Helper
def render_mode(view) -> str:
    """지금 장면의 render 모드.

    출력  발화 해석 결과면 "resolve", 그 밖에는 "plain"
    제약  무엇을 강조로 바꿀지 여기서 정하지 않는다. 서버가 정함
    """
    if isinstance(view, dict) and view.get("kind") == "resolve":
        return "resolve"
    return "plain"


def recipe_ids_to_show(view) -> list[str]:
    """강조할 recipe 목록. 해석이 고른 것과 후보들."""
    if not isinstance(view, dict) or "error" in view:
        return []

    result = view.get("result") or {}
    wanted = [result.get("recipe_id"), *(result.get("candidate_recipe_ids") or [])]
    return list(dict.fromkeys(r for r in wanted if r))


def format_elapsed(seconds: float) -> str:
    """Run 클릭부터 응답까지 걸린 시간.

    출력  60초 미만이면 "N.N초", 그 이상이면 "N분 N.N초"
    """
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
# 화면은 한 번에 한 장면만 말한다. view 하나로 발화 띠 · 그래프 강조 · 후보 목록이 함께 정해진다.
#   kind="resolve"  -> 그래프에 후보 recipe 강조 + 살펴보기 칸에 후보 목록
st.session_state.setdefault("view", None)

# ================================================================ 탭
# 테스트 탭은 「새로 실행」 · 「이어 실행」을 누를 때만 평가(/resolve)를 부른다. 열려 있을 때는 그것만 그리고 멈춘다.
# 그래프 조회 · 따라 보기 주기 요청이 테스트 화면 뒤에서 돌지 않게 탭을 게으르게 연다.
service_tab, test_tab = st.tabs(["서비스 화면", "테스트"], key="main_tabs", on_change="rerun")
if test_tab.open:
    with test_tab:
        st.markdown(styles.page_css(), unsafe_allow_html=True)
        render_test_tab(ratios)
    st.stop()

# ================================================================ 그래프 조회
# 색을 쓰므로 화면을 그리기 전에 한 번 받아둔다.
try:
    graph, graph_stale = api_client.get_screen()
except ApiError:
    graph, graph_stale = None, False

# 색은 백엔드가 정한다. CSS 를 짜기 전에 받아둬야 칩·배지가 제 색으로 나온다.
theme.set_colors((graph or {}).get("colors"))
service_tab.markdown(styles.page_css(), unsafe_allow_html=True)

view = st.session_state.get("view")

# 그리기는 백엔드가 한다. 여기서 정하는 것은 "무엇을 강조할 장면인가" 뿐이다.
try:
    rendered = api_client.render(render_mode(view), recipe_ids_to_show(view))
    render_error = None
except ApiError as exc:
    rendered, render_error = None, str(exc)

# ================================================================ 입력 줄
bar = service_tab.container(key="input_bar")
with bar:
    _, run_clicked, follow_slot = render_input_section()

# ================================================================ 발화 띠
# 해석한 발화 · 오류 · 기다리는 표시. 그래프 상태 알림도 여기 한 줄로 남긴다.
band = service_tab.container(key="band")
with band:
    band_slot = st.empty()
    if graph_stale:
        # 캐시본을 쓰는 중이다. 조용히 알리되 그래프는 계속 보여준다.
        st.markdown(
            styles.note_markup("Backend 응답이 없어 마지막으로 받은 그래프를 보여줍니다."),
            unsafe_allow_html=True,
        )
    if render_error:
        st.markdown(styles.note_markup(f"그래프를 그릴 수 없습니다 — {render_error}"),
                    unsafe_allow_html=True)

# ================================================================ 그래프
# iframe 하나다. 따라 본 회차가 있으면 그 실행 기록을 오른쪽 칸에 둔다.
# Run 을 처리하기 전에 그린다 — 해석을 기다리는 동안에도 지도가 그대로 보인다.
main = service_tab.container(key="main_panel")
with main:
    followed = (st.session_state.get(FOLLOW_KEY) and isinstance(view, dict)
                and view.get("follow"))
    if followed:
        graph_col, follow_col = st.columns(
            [1 - ratios["follow_ratio"], ratios["follow_ratio"]], gap="medium")
    else:
        graph_col, follow_col = st.container(), None

    with graph_col:
        render_graph_section(rendered, view, ratios)
    if follow_col is not None:
        with follow_col:
            with st.container(key="follow_panel"):
                render_follow_panel(view)

if run_clicked:
    utterance_trimmed = st.session_state.get("utterance", "").strip()
    if not utterance_trimmed:
        st.session_state["view"] = {"error": "발화를 입력하세요."}
        st.rerun()

    # 기다리는 동안 띠를 비워두지 않는다. LLM 지연이 길어 스피너만으로는
    # 멈춘 것처럼 보인다.
    band_slot.markdown(skeleton_markup(), unsafe_allow_html=True)

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
    st.rerun()  # 결과를 그래프에 그리려면 다시 한 번 돈다

with band_slot:
    render_band(view)

if config.DEBUG and isinstance(view, dict) and view.get("elapsed") is not None:
    st.metric("⏱️ Run Time", format_elapsed(view["elapsed"]))

# ================================================================ 따라 보기
# 맨 끝이다. 조각이 새 회차를 보면 전체 rerun 을 걸므로, 앞쪽에서 부르면
# Run 클릭이 그 rerun 에 삼켜진다.
with follow_slot:
    render_follow_switch()
