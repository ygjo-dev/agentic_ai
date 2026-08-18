"""Backend 와 통신하는 유일한 창구.

프론트엔드는 도메인을 모른다 — 온톨로지도, registry 도, LLM 도 여기를 거쳐
백엔드에 묻는다. 나중에 온톨로지가 그래프 DB 로 바뀌어도 이 파일은 그대로다.

예외는 삼키지 않는다. requests 의 여러 예외를 ApiError 하나로 모으되,
화면이 원인별로 다른 문장을 보여줘야 하므로 kind 를 남긴다.
"""

import os

import requests
import streamlit as st

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

# 타임아웃은 하는 일에 맞춘다. LLM 이 끼는 호출만 길다.
GRAPH_TIMEOUT = 10
RENDER_TIMEOUT = 30  # Graphviz 를 여러 벌 돌린다. 캐시 적중이면 즉시 온다.
RESOLVE_TIMEOUT = 180
NODES_TIMEOUT = 180

# 마지막으로 성공한 /graph 응답을 여기 둔다. 백엔드가 잠깐 끊겨도
# 그래프가 사라지지 않아야 한다.
GRAPH_CACHE_KEY = "_graph_cache"


class ApiError(RuntimeError):
    """Backend 호출 실패. kind 는 "connection" | "timeout" | "other"."""

    def __init__(self, message: str, kind: str = "other"):
        super().__init__(message)
        self.kind = kind


def _detail_of(response) -> str:
    """오류 응답 본문의 detail. 백엔드가 원인을 적어 보냄."""
    try:
        detail = response.json().get("detail")
    except Exception:  # noqa: BLE001 — 본문이 JSON 이 아닐 수도 있다.
        detail = None
    return detail or f"HTTP {response.status_code}"


def _call(method: str, path: str, *, timeout: float, **kwargs) -> dict:
    try:
        response = requests.request(method, f"{BASE_URL}{path}", timeout=timeout, **kwargs)
    except requests.exceptions.ConnectionError as exc:
        raise ApiError(str(exc), kind="connection") from exc
    except requests.exceptions.Timeout as exc:
        raise ApiError(str(exc), kind="timeout") from exc
    except Exception as exc:  # noqa: BLE001 — 나머지도 한 종류로 모은다.
        raise ApiError(str(exc)) from exc

    if not response.ok:
        raise ApiError(_detail_of(response))

    return response.json()


def get_graph() -> tuple[dict, bool]:
    """그래프 한 벌.

    출력  (payload, is_stale)
    규칙  호출이 실패하면 마지막으로 성공한 응답을 is_stale=True 로 돌려줌.
          기다리는 동안 화면이 비면 곤란함
          캐시조차 없으면 그때는 ApiError 를 올림
    """
    try:
        payload = _call("GET", "/graph", timeout=GRAPH_TIMEOUT)
    except ApiError:
        cached = st.session_state.get(GRAPH_CACHE_KEY)
        if cached is None:
            raise
        return cached, True

    st.session_state[GRAPH_CACHE_KEY] = payload
    return payload, False


def render(mode: str = "plain", recipe_ids=None, mark: dict | None = None) -> dict:
    """화면 한 장에 필요한 SVG 와 칩 데이터.

    입력  모드 · 강조할 recipe · mark(POST /nodes 응답 그대로)
    출력  POST /render 응답
    제약  여기서 그리지 않는다. 그리기는 전부 백엔드가 하고 여기는 무엇을
          강조할지만 말함
          mark 를 여기서 줄이지 않는다. 줄이는 일은 서버가 함
    """
    return _call(
        "POST",
        "/render",
        timeout=RENDER_TIMEOUT,
        json={"mode": mode, "recipe_ids": list(recipe_ids or []), "mark": mark},
    )


def resolve(utterance: str) -> dict:
    """발화 → Recipe 선택. 경로(paths)까지 함께 옴."""
    return _call(
        "POST", "/resolve", timeout=RESOLVE_TIMEOUT, params={"utterance": utterance}
    )


def register_node(name: str, description: str, inputs: list[str], outputs: list[str]) -> dict:
    """노드 등록. 온톨로지가 바뀌므로 그래프 캐시를 버림."""
    result = _call(
        "POST",
        "/nodes",
        timeout=NODES_TIMEOUT,
        json={
            "name": name,
            "description": description,
            "inputs": inputs,
            "outputs": outputs,
        },
    )
    st.session_state.pop(GRAPH_CACHE_KEY, None)
    return result


def reset_nodes() -> dict:
    """_init 사본으로 되돌림. 등록과 마찬가지로 캐시를 버림."""
    result = _call("POST", "/nodes/reset", timeout=NODES_TIMEOUT)
    st.session_state.pop(GRAPH_CACHE_KEY, None)
    return result
