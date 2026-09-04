"""프롬프트에 실리는 menu 와, /resolve 가 지도 문맥을 받는 길.

**LLM 을 부르지 않는다.**

★ 2026-09-04 에 `test_menu_split.py` 를 지우면서 그 파일에서 살려 온 다섯이다.
menu 를 요청마다 가르던 임시방편(`_menu_for` · `SCREEN_WORDS`)이 없어져 열넷은
지킬 것이 사라졌지만, 아래 다섯이 보는 것은 그 갈래가 아니라 **menu 원문**과
**문맥이 오는 길**이라 그대로 산다. 무엇을 지우고 무엇을 살렸는지는
NOTES.md 「아흔여섯째」에 있다.
"""

from workflows.static.menu.load import load_menu

# 저쪽 평상시. 우클릭 전이라 selectedLocation 이 null 이다.
BBOX_ONLY = {
    "view": {"bbox": [[127.1598, 36.4853], [127.4956, 36.7547]]},
    "selectedLocation": None,
}

NO_MATCH = "NO_MATCH"


# ── 프롬프트에 실리는 menu ──────────────────────────────────────────


def test_the_menu_is_the_menu_yaml_original_verbatim():
    """프롬프트에 실리는 것이 파일에 적힌 그것이어야 한다.

    자수를 재서 표에 적는 값이라 한 글자만 달라도 옛 판과 못 견준다.
    ★ 2026-09-04 에 걸러 싣던 길을 걷어 이제 언제나 원문 전부다.
    """
    from paths import MENU_YAML_PATH

    assert load_menu() == MENU_YAML_PATH.read_text(encoding="utf-8")


# ── /resolve 가 문맥을 받는가 ───────────────────────────────────────


def test_the_resolve_endpoint_takes_the_context_in_the_request_body(monkeypatch):
    """Streamlit 과 check_resolve 가 그 길로 보낸다.

    저쪽 화면은 /chat 으로 오고 이 자리를 안 지난다.
    """
    from fastapi.testclient import TestClient

    from app.api import main as backend_main

    받은_것 = {}

    def fake_resolve(utterance, llm_client, reason_max_length, context=None):
        받은_것["utterance"] = utterance
        받은_것["context"] = context
        return {"status": NO_MATCH, "recipe_id": None, "candidate_recipe_ids": []}

    monkeypatch.setattr(backend_main.resolve_service, "resolve", fake_resolve)

    with TestClient(backend_main.app) as client:
        client.post("/resolve", params={"utterance": "여기 CCTV 보여줘"}, json=BBOX_ONLY)

    assert 받은_것["context"] == BBOX_ONLY


def test_not_sending_a_context_arrives_as_None(monkeypatch):
    """--context none 과 옛 부름이 이 자리를 지난다."""
    from fastapi.testclient import TestClient

    from app.api import main as backend_main

    받은_것 = {}

    def fake_resolve(utterance, llm_client, reason_max_length, context=None):
        받은_것["context"] = context
        return {"status": NO_MATCH, "recipe_id": None, "candidate_recipe_ids": []}

    monkeypatch.setattr(backend_main.resolve_service, "resolve", fake_resolve)

    with TestClient(backend_main.app) as client:
        client.post("/resolve", params={"utterance": "오송역 CCTV 보여줘"})

    assert 받은_것["context"] is None


# ── 화면과 도구가 같은 고정값을 쓰는가 ──────────────────────────────


def test_the_three_contexts_of_check_resolve():
    """없음 · bbox 만 · 둘 다. 기본은 both 다 — 저쪽에서 우클릭한 뒤와 같다.

    2026-08-30 에 기본을 bbox 에서 both 로 바꿨다. bbox 뿐이면 찍은 지점에서
    출발하는 recipe 가 후보에서 빠져 아예 못 재어진다.
    """
    from dev.tools import check_resolve

    assert check_resolve.CONTEXT == check_resolve.CONTEXT_BOTH

    check_resolve.CONTEXT = check_resolve.CONTEXT_NONE
    try:
        assert check_resolve._context_payload() is None

        check_resolve.CONTEXT = check_resolve.CONTEXT_BBOX
        assert check_resolve._context_payload()["selectedLocation"] is None
        assert check_resolve._context_payload()["view"]["bbox"]

        check_resolve.CONTEXT = check_resolve.CONTEXT_BOTH
        assert check_resolve._context_payload()["selectedLocation"]["lon"]
    finally:
        check_resolve.CONTEXT = check_resolve.CONTEXT_BOTH


def test_the_screen_and_the_tool_use_the_same_bbox():
    """둘이 어긋나면 "시연과 같은 조건" 이라는 말이 거짓이 된다."""
    from app.ui import config as ui_config
    from dev.tools import check_resolve

    assert check_resolve.ui_config is ui_config
    assert ui_config.map_context()["view"]["bbox"] == ui_config.FIXED_VIEW_BBOX
