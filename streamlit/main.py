"""
Static Workflow Streamlit Demo.
"""

import sys
from pathlib import Path

import streamlit as st
import yaml

REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

import paths
from llm_engine.ollama import OLLAMA_HOST, OLLAMA_MODEL, OllamaClient
from orchestrator.route_resolver import RouteResolutionError, resolve_route
from orchestrator.schemas.response_schema import (
    CLARIFY,
    NO_MATCH,
    RESPONSE_SCHEMA,
    SELECT,
)
from orchestrator.schemas.static_route_result import StaticRouteResult
from workflows.static.menu.load import load_menu

# ------------------------------------------------------------------ Sample
#
# 각 상태(SELECT / CLARIFY / NO_MATCH)를 대표하는 발화.
SAMPLES = [
    # SELECT : 발화가 Recipe 하나로 유일하게 결정.
    ("CCTV 군중 분석 결과를 Word 문서로 만들어줘", SELECT, "recipe_003", ["recipe_003"]),
    ("CCTV 군중 분석 결과를 관리자에게 알려줘", SELECT, "recipe_005", ["recipe_005"]),
    ("이미지 균열 분석 결과를 PPT 문서로 만들어줘", SELECT, "recipe_009", ["recipe_009"]),

    # CLARIFY : Recipe 후보가 2개 이상으로 갈린다.
    ("CCTV 군중 분석 결과를 문서로 만들어줘", CLARIFY, None, ["recipe_003", "recipe_004"]),
    ("데이터를 불러와서 분석해줘", CLARIFY, None, ["recipe_002", "recipe_007"]),
    
    # NO_MATCH : Menu 에 없는 기능
    ("CCTV 영상으로 열차 속도를 분석해줘", NO_MATCH, None, []),
    ("오늘 날씨 알려줘", NO_MATCH, None, []),
]

STATUS_BADGE = {
    SELECT: "🟢",
    CLARIFY: "🟡",
    NO_MATCH: "🔴",
}


def recipe_nodes(recipe_id: str) -> list[str]:
    """실제 recipes/<recipe_id>.yaml 에서 노드 이름을 순서 그대로 읽는다."""
    recipe_path = paths.RECIPES_DIR / f"{recipe_id}.yaml"
    if not recipe_path.exists():
        return []
    data = yaml.safe_load(recipe_path.read_text(encoding="utf-8"))
    return [step["node"] for step in data.get("steps", [])]


def node_flow(recipe_id: str) -> str:
    nodes = recipe_nodes(recipe_id)
    if not nodes:
        return "(recipe 파일 없음)"
    return " ➜ ".join(f"`{node}`" for node in nodes)


def use_sample(
    utterance: str, status: str, recipe_id: str | None, candidate_ids: list[str]
) -> None:
    st.session_state["utterance"] = utterance
    st.session_state["expected"] = {
        "status": status,
        "recipe_id": recipe_id,
        "candidate_recipe_ids": candidate_ids,
    }


def clear_expected() -> None:
    """사용자가 입력창을 직접 수정하면 더 이상 Sample 이 아니다."""
    st.session_state["expected"] = None


# ---------------------------------------------------------------------- UI

st.set_page_config(page_title="Static Workflow Demo", layout="wide")
st.title("Static Workflow Demo")
st.caption(
    f"load_menu ➜ recipe_selection.md ➜ OllamaClient({OLLAMA_MODEL} @ {OLLAMA_HOST}) "
    "➜ resolve_route ➜ StaticRouteResult"
)

st.session_state.setdefault("utterance", "")
st.session_state.setdefault("expected", None)
st.session_state.setdefault("run", None)

left, right = st.columns([1, 1], gap="large")

with left:
    st.subheader("User Input")
    st.text_input(
        "발화를 입력하세요",
        key="utterance",
        on_change=clear_expected,
        placeholder="예) CCTV로 군중을 분석해줘",
    )
    run_clicked = st.button("Run", type="primary", use_container_width=True)

    st.divider()
    st.subheader("Sample")
    for index, (utterance, status, recipe_id, candidate_ids) in enumerate(SAMPLES):
        col_button, col_flow = st.columns([3, 2])
        with col_button:
            st.button(
                utterance,
                key=f"sample_{index}",
                on_click=use_sample,
                args=(utterance, status, recipe_id, candidate_ids),
                use_container_width=True,
            )
        with col_flow:
            st.caption(f"{STATUS_BADGE.get(status, '⚪')} {status}")
            if recipe_id is not None:
                st.markdown(f"**{recipe_id}** : {node_flow(recipe_id)}")
            elif candidate_ids:
                st.markdown(" / ".join(f"**{cid}**" for cid in candidate_ids))
            else:
                st.markdown("*해당 Recipe 없음*")

# ----------------------------------------------------------------- Run
if run_clicked:
    utterance = st.session_state["utterance"].strip()
    if not utterance:
        st.session_state["run"] = {"error": "발화를 입력하세요."}
    else:
        try:
            with st.spinner("Ollama 로 Route Resolution 수행 중..."):
                data = resolve_route(
                    prompt=paths.RECIPE_SELECTION_PROMPT_PATH.read_text(
                        encoding="utf-8"
                    ),
                    variables={"menu": load_menu(), "utterance": utterance},
                    response_schema=RESPONSE_SCHEMA,
                    llm_client=OllamaClient(),
                )
            result = StaticRouteResult(**data)
            st.session_state["run"] = {
                "utterance": utterance,
                "result": result,
                "expected": st.session_state["expected"],
            }
        except RouteResolutionError as exc:
            st.session_state["run"] = {"error": f"Route Resolution 실패: {exc}"}
        except OSError as exc:
            st.session_state["run"] = {
                "error": (
                    f"Ollama 에 연결할 수 없다: {exc}\n\n"
                    f"- 연결 주소: {OLLAMA_HOST}\n"
                    "- 해결 방법: `ollama serve` 로 데몬을 띄운 뒤 다시 실행한다. "
                    "주소가 다르면 `OLLAMA_HOST` 환경변수로 지정한다."
                )
            }

# --------------------------------------------------------------- 결과 시각화(화면 우측)
with right:
    st.subheader("Result")
    run = st.session_state["run"]

    if run is None:
        st.info("좌측에서 발화를 입력하거나 Sample 을 선택한 뒤 Run 을 누르세요.")
    elif "error" in run:
        st.error(run["error"])
    else:
        result: StaticRouteResult = run["result"]
        expected = run["expected"]

        st.markdown(f"**입력 발화** : {run['utterance']}")

        st.markdown("##### Status")
        badge = STATUS_BADGE.get(result.status, "⚪")
        st.markdown(f"## {badge} {result.status}")

        st.markdown("##### Recipe")
        if result.recipe_id:
            st.markdown(f"**{result.recipe_id}**")
            st.markdown(node_flow(result.recipe_id))
        else:
            st.markdown("*없음*")

        st.markdown("##### Candidates")
        if result.candidate_recipe_ids:
            for candidate_id in result.candidate_recipe_ids:
                st.markdown(f"- **{candidate_id}** : {node_flow(candidate_id)}")
        else:
            st.markdown("*없음*")

        st.markdown("##### Reason")
        st.markdown(result.reason if result.reason else "*없음*")

        # Sample 로 실행한 경우에만 Expected / Actual 을 비교.
        if expected is not None:
            st.divider()
            st.markdown("##### Expected vs Actual")
            col_expected, col_actual = st.columns(2)
            with col_expected:
                st.markdown("**Expected**")
                st.markdown(
                    f"{STATUS_BADGE.get(expected['status'], '⚪')} "
                    f"**{expected['status']}**"
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
                    f"{STATUS_BADGE.get(result.status, '⚪')} **{result.status}**"
                )
                if result.recipe_id:
                    st.markdown(f"**{result.recipe_id}**")
                    st.markdown(node_flow(result.recipe_id))
                elif result.candidate_recipe_ids:
                    for candidate_id in result.candidate_recipe_ids:
                        st.markdown(f"- **{candidate_id}**")
                else:
                    st.markdown("*해당 Recipe 없음*")

            matched = (
                result.status == expected["status"]
                and result.recipe_id == expected["recipe_id"]
                and set(result.candidate_recipe_ids)
                == set(expected["candidate_recipe_ids"])
            )

            if matched:
                st.success("Expected 와 Actual 이 일치한다.")
            else:
                st.error("Expected 와 Actual 이 일치하지 않는다.")
