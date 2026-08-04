"""
Frontend Streamlit 진입점.

UI 컴포넌트를 조합하여 화면을 구성.
Backend와 HTTP로 통신하여 정보를 받음.
"""

import sys
import time
from pathlib import Path

import streamlit as st
import yaml
import requests

REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

import paths
from frontend.components.input_section import render_input_section
from frontend.components.result_section import STATUS_BADGE, render_result_section
from frontend.components.sample_buttons import render_sample_buttons

# ================================================================ Helper
def recipe_nodes(recipe_id: str) -> list[str]:
    """실제 recipes/<recipe_id>.yaml 에서 노드 이름을 순서 그대로 읽는다."""
    recipe_path = paths.RECIPES_DIR / f"{recipe_id}.yaml"
    if not recipe_path.exists():
        return []
    data = yaml.safe_load(recipe_path.read_text(encoding="utf-8"))
    return [step["node"] for step in data.get("steps", [])]


def node_flow(recipe_id: str) -> str:
    """Node Flow를 시각화."""
    nodes = recipe_nodes(recipe_id)
    if not nodes:
        return "(recipe 파일 없음)"
    return " ➜ ".join(f"`{node}`" for node in nodes)


def format_elapsed(seconds: float) -> str:
    """Run 클릭부터 응답까지 걸린 시간을 초단위로 표시. 60초 이상이면 분:초로 표시."""
    if seconds < 60:
        return f"{seconds:.1f}초"
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes)}분 {rest:.1f}초"


# ================================================================ UI 설정
st.set_page_config(page_title="Recipe Resolver Frontend", layout="wide")
st.title("Recipe Resolver Frontend")
st.caption("Backend 호출을 통한 Recipe 선택")

st.session_state.setdefault("utterance", "")
st.session_state.setdefault("expected", None)
st.session_state.setdefault("run", None)

# ================================================================ 레이아웃
left, right = st.columns([1, 1], gap="large")

with left:
    utterance, run_clicked = render_input_section()

    st.divider()
    render_sample_buttons(node_flow)

# ================================================================ Backend 호출 및 결과 처리
with right:
    if run_clicked:
        utterance_trimmed = st.session_state.get("utterance", "").strip()
        if not utterance_trimmed:
            st.session_state["run"] = {"error": "발화를 입력하세요."}
        else:
            with st.spinner("Backend에 요청 중..."):
                started = time.perf_counter()  # Run 클릭 ~ 응답 수신까지 측정
                try:
                    response = requests.post(
                        "http://localhost:8000/resolve",
                        params={"utterance": utterance_trimmed},
                        timeout=180,
                    )
                    response.raise_for_status()
                    result = response.json()
                    st.session_state["run"] = {
                        "utterance": utterance_trimmed,
                        "result": result,
                        "expected": st.session_state["expected"],
                        "elapsed": time.perf_counter() - started,
                    }
                except requests.exceptions.ConnectionError:
                    st.session_state["run"] = {
                        "error": "Backend에 연결할 수 없습니다. uvicorn을 먼저 실행하세요."
                    }
                except requests.exceptions.Timeout:
                    st.session_state["run"] = {"error": "Backend 응답 시간 초과 (180초)"}
                except Exception as e:
                    st.session_state["run"] = {"error": f"Backend 호출 실패: {str(e)}"}

    # 결과 표시
    run = st.session_state.get("run")

    if run is None:
        st.info("좌측에서 발화를 입력하거나 Sample을 선택한 뒤 Run을 누르세요.")
    elif isinstance(run, dict) and "error" in run:
        st.error(run["error"])
    else:
        result = run["result"]
        expected = run["expected"]

        col_utterance, col_elapsed = st.columns([3, 1])
        with col_utterance:
            st.markdown(f"**입력 발화** : {run['utterance']}")
        with col_elapsed:
            if run.get("elapsed") is not None:
                st.metric("⏱️ Run Time", format_elapsed(run["elapsed"]))

        render_result_section(result, node_flow)

        # Sample 로 실행한 경우에만 Expected / Actual 을 비교.
        if expected is not None:
            st.divider()
            st.markdown("##### Expected vs Actual")
            col_expected, col_actual = st.columns(2)
            with col_expected:
                st.markdown("**Expected**")
                st.markdown(
                    f"{STATUS_BADGE.get(expected['status'], '⚪')} **{expected['status']}**"
                )
                if expected["recipe_id"]:
                    st.markdown(f"**{expected['recipe_id']}**")
                    st.markdown(node_flow(expected["recipe_id"]))
                elif expected["candidate_recipe_ids"]:
                    for candidate_id in expected["candidate_recipe_ids"]:
                        st.markdown(f"- **{candidate_id}**")
                else:
                    st.markdown("*해당 Recipe 없음*")
            with col_actual:
                st.markdown("**Actual**")
                st.markdown(
                    f"{STATUS_BADGE.get(result['status'], '⚪')} **{result['status']}**"
                )
                if result["recipe_id"]:
                    st.markdown(f"**{result['recipe_id']}**")
                    st.markdown(node_flow(result["recipe_id"]))
                elif result["candidate_recipe_ids"]:
                    for candidate_id in result["candidate_recipe_ids"]:
                        st.markdown(f"- **{candidate_id}**")
                else:
                    st.markdown("*해당 Recipe 없음*")

            matched = (
                result["status"] == expected["status"]
                and result["recipe_id"] == expected["recipe_id"]
                and set(result["candidate_recipe_ids"]) == set(expected["candidate_recipe_ids"])
            )

            if matched:
                st.success("✓ Expected와 Actual이 일치한다.")
            else:
                st.error("✗ Expected와 Actual이 일치하지 않는다.")
