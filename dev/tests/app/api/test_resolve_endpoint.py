"""`POST /resolve` 와 창구의 오류 매핑.

**LLM 을 부르지 않는다.** resolve_service 를 대역으로 바꾸고 창구만 본다.

지키는 것은 셋이다.
  발화와 모델만 지나간다 — 지도 문맥을 안 받는다. 고르는 것은 LLM 뿐이고
  문맥이 필요한지는 실행 직전에 execution 이 본다
  프롬프트에 실리는 menu 는 menu.yaml 원문 전부다
  예상 못 한 오류의 원문이 client 로 안 나간다 — 서버 로그로만 간다
"""

import logging

import pytest
from fastapi.testclient import TestClient

from app.api import main as backend_main
from app.api.services.streamlit.screen_service import UnknownRenderMode

NO_MATCH = "NO_MATCH"

# KRRI_ASAP 이 /chat/stream 으로 보내는 문맥과 같은 모양. /resolve 는 이것을
# 받지 않는다 — 아래 시험이 그 자리를 지킨다.
MAP_CONTEXT = {
    "view": {"bbox": [[127.1598, 36.4853], [127.4956, 36.7547]]},
    "selectedLocation": None,
}


@pytest.fixture
def seen(monkeypatch):
    """resolve_service.resolve 가 무엇을 받았는지만 남기는 대역."""
    captured = {}

    def fake_resolve(utterance, llm_client, reason_max_length):
        captured["utterance"] = utterance
        captured["reason_max_length"] = reason_max_length
        return {"status": NO_MATCH, "recipe_id": None, "candidate_recipe_ids": []}

    monkeypatch.setattr(backend_main.resolve_service, "resolve", fake_resolve)
    return captured


# ── 무엇이 지나가는가 ───────────────────────────────────────────────


def test_the_utterance_is_a_query_parameter(seen):
    """발화는 query 다. 백엔드가 그렇게 받고 화면과 계기판이 그렇게 보낸다."""
    with TestClient(backend_main.app) as client:
        response = client.post("/resolve", params={"utterance": "오송역 CCTV 보여줘"})

    assert response.status_code == 200
    assert seen["utterance"] == "오송역 CCTV 보여줘"


def test_the_resolve_endpoint_does_not_take_a_map_context():
    """**고르는 것과 부를 수 있는 것을 가른다.**

    문맥을 여기서 받으면 「무엇을 골랐는가」에 「지금 부를 수 있는가」가 섞인다.
    실행에 쓰는 문맥은 /chat/stream 이 그대로 받는다.
    """
    import inspect

    parameters = inspect.signature(backend_main.resolve_endpoint).parameters

    assert "context" not in parameters
    assert list(parameters) == ["utterance", "model"]


def test_a_context_in_the_body_is_ignored_instead_of_rejected(seen):
    """옛 부름이 문맥을 실어 보내도 422 가 나면 안 된다.

    계기판과 화면을 한 번에 갈지 못하므로, 남은 본문은 조용히 버려지고 발화만
    지나가야 한다.
    """
    with TestClient(backend_main.app) as client:
        response = client.post(
            "/resolve", params={"utterance": "여기 CCTV 보여줘"}, json=MAP_CONTEXT
        )

    assert response.status_code == 200
    assert seen["utterance"] == "여기 CCTV 보여줘"


def test_the_menu_in_the_prompt_is_the_menu_yaml_verbatim():
    """프롬프트에 실리는 것이 파일에 적힌 그것이어야 한다.

    자수를 재서 표에 적는 값이라 한 글자만 달라도 옛 판과 못 견준다.
    """
    from paths import MENU_YAML_PATH
    from workflows.static.menu.load import load_menu

    assert load_menu() == MENU_YAML_PATH.read_text(encoding="utf-8")


# ── 오류가 나갈 때 ──────────────────────────────────────────────────


def test_an_unexpected_error_never_carries_its_own_text_to_the_client(monkeypatch):
    """**vendor 예외에는 Gateway 응답 본문 · 내부 URL · 저장소 경로가 들어 있다.**

    이 응답은 KRRI_ASAP 시스템까지 나간다. 원문은 서버 로그에만 남긴다.
    """
    새면_안_되는_것 = (
        "Server error '500 Internal Server Error' for url "
        "'http://localhost:3000/api/tools/execute' Response body: {\"detail\": ...} "
        "/home/ubuntu/source/agentic_ai/ontology/ontology.yaml"
    )

    def boom(utterance, llm_client, reason_max_length):
        raise RuntimeError(새면_안_되는_것)

    monkeypatch.setattr(backend_main.resolve_service, "resolve", boom)

    with TestClient(backend_main.app, raise_server_exceptions=False) as client:
        response = client.post("/resolve", params={"utterance": "아무 말"})

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail == backend_main.INTERNAL_ERROR_DETAIL
    for 조각 in ("localhost:3000", "Response body", "/home/ubuntu", "RuntimeError"):
        assert 조각 not in detail, f"내부 원문이 샜다: {조각}"


def test_the_real_cause_is_written_to_the_server_log(monkeypatch, caplog):
    """client 에서 감춘 만큼 서버에서는 보여야 한다. 없으면 원인을 못 찾는다."""

    def boom(utterance, llm_client, reason_max_length):
        raise RuntimeError("무엇이 터졌는지 여기 적힌다")

    monkeypatch.setattr(backend_main.resolve_service, "resolve", boom)

    with caplog.at_level(logging.ERROR, logger=backend_main.logger.name):
        with TestClient(backend_main.app, raise_server_exceptions=False) as client:
            client.post("/resolve", params={"utterance": "아무 말"})

    assert "무엇이 터졌는지 여기 적힌다" in caplog.text
    assert "Traceback" in caplog.text, "traceback 이 없으면 어디서 터졌는지 모른다"


def test_a_domain_error_still_says_what_was_wrong(monkeypatch):
    """422 는 「요청이 잘못됐거나 LLM 이 계약을 어겼다」다. 그 문구는 남는다.

    500 과 함께 뭉뚱그리면 화면이 사람에게 무엇을 고치라고 말할 수 없다.
    """

    def refuse(mode, recipe_ids, mark):
        raise UnknownRenderMode("그런 mode 는 없다: 이상한것")

    monkeypatch.setattr(backend_main.screen_service, "render", refuse)

    with TestClient(backend_main.app) as client:
        response = client.post(
            "/render", json={"mode": "이상한것", "recipe_ids": [], "mark": None}
        )

    assert response.status_code == 422
    assert "그런 mode 는 없다" in response.json()["detail"]
