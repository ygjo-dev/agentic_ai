"""프롬프트에 넣을 menu 를 요청마다 가르는 것.

LLM 을 부르지 않는다. 어느 문장이 프롬프트에 실리는가만 본다.

**관문 둘이다.**
  발화가 화면을 안 가리키면 「마흔여섯째」 이전과 같은 마흔 줄이 실린다
  낱말이 걸려도 문맥에 값이 없으면 마흔 줄이다 — 없는 것을 제안하면
  LLM 이 고르고 나서 `_without_dropped` 에 지워진다

recipe id 를 박지 않는다. 온톨로지가 바뀌면 번호가 통째로 밀리므로 경로 첫 칸으로
가른다 — `_menu_for` 가 쓰는 기준과 같은 것이다.

★ 이 갈래는 월요일 시연을 위한 임시방편이다. NOTES.md 「마흔여덟째」를 본다.
"""

import json

import yaml

from demo.api.services import ontology_service, resolve_service, step_service
from orchestrator.schemas.response_schema import NO_MATCH
from workflows.static.menu.load import load_menu

# 저쪽 평상시. 우클릭 전이라 selectedLocation 이 null 이다.
BBOX_ONLY = {
    "view": {"bbox": [[127.1598, 36.4853], [127.4956, 36.7547]]},
    "selectedLocation": None,
}

# 우클릭까지 한 뒤.
BOTH = {
    **BBOX_ONLY,
    "selectedLocation": {"lon": 127.3277, "lat": 36.62, "label": "관심 지점"},
}


def recipes_in(menu: str) -> set:
    """그 menu 문자열에 실린 recipe id."""
    return set((yaml.safe_load(menu) or {}).get("recipes") or {})


def starting_at(*node_ids) -> set:
    """경로 첫 칸이 그 노드인 recipe id 전부."""
    found = set()
    for recipe_id in ontology_service.recipe_ids():
        path = ontology_service.path_of(recipe_id)
        if path and path[0]["node_id"] in node_ids:
            found.add(recipe_id)
    return found


def spoken_recipes() -> set:
    """화면에서 안 오는 시작 데이터에서 출발하는 recipe. 「기존 마흔」이다."""
    return set(ontology_service.recipe_ids()) - starting_at(*step_service.CONTEXT_STARTS)


def test_평범한_발화는_화면_recipe_를_아예_안_본다():
    """menu 가 길어져 판정이 16 내린 것이 이번 변경의 까닭이다.

    문맥이 와 있어도 발화가 화면을 안 가리키면 화면 줄은 실리지 않는다.
    """
    menu = resolve_service._menu_for("오송역 CCTV 보여줘", BOTH)

    assert recipes_in(menu) == spoken_recipes()


def test_문맥이_아예_없으면_기존_마흔이다():
    """문맥을 안 보내는 부름은 이 변경 전과 같은 menu 를 봐야 한다."""
    menu = resolve_service._menu_for("오송역 CCTV 보여줘", None)

    assert recipes_in(menu) == spoken_recipes()


def test_화면을_가리켜도_값이_없으면_기존_마흔이다():
    """없는 것을 제안하면 LLM 이 고르고 나서 후보에서 지워진다.

    값이 있는지는 이미 있는 context_starts 가 센다. 새 기준을 만들지 않는다.
    """
    menu = resolve_service._menu_for("여기 CCTV 보여줘", None)

    assert recipes_in(menu) == spoken_recipes()


def test_보이는_범위만_왔으면_찍은_지점_recipe_는_안_실린다():
    """저쪽 평상시(우클릭 전)가 이 자리다.

    찍은 지점에서 출발하는 recipe 는 그때 골라도 좌표가 없어 못 쓴다.
    """
    menu = resolve_service._menu_for("지금 보이는 곳 CCTV 보여줘", BBOX_ONLY)

    assert recipes_in(menu) == starting_at("visible_extent")
    assert not recipes_in(menu) & starting_at("picked_point")


def test_둘_다_왔으면_화면_recipe_가_다_실린다():
    """우클릭 뒤에는 찍은 지점과 보이는 범위가 함께 후보가 된다."""
    menu = resolve_service._menu_for("여기 CCTV 보여줘", BOTH)

    assert recipes_in(menu) == starting_at("picked_point", "visible_extent")


def test_가른_menu_는_어느_쪽이든_menu_yaml_보다_짧다():
    """짧게 만드는 것이 이번 변경의 목적이다."""
    whole = load_menu()

    for utterance, context in (
        ("오송역 CCTV 보여줘", BOTH),
        ("여기 CCTV 보여줘", BOTH),
        ("지금 보이는 곳 CCTV 보여줘", BBOX_ONLY),
    ):
        assert len(resolve_service._menu_for(utterance, context)) < len(whole)


def test_가른_menu_도_그대로_yaml_이다():
    """머리말이 남아야 프롬프트에 실린 것을 사람이 읽을 수 있다."""
    parsed = yaml.safe_load(resolve_service._menu_for("여기 CCTV 보여줘", BOTH))

    assert parsed["version"]
    assert parsed["recipes"]


def test_남은_줄이_menu_yaml_과_한_글자도_다르지_않다():
    """menu.yaml 을 안 고친다. 읽은 문자열에서 블록을 뺄 뿐이다."""
    whole = load_menu()
    split = resolve_service._menu_for("여기 CCTV 보여줘", BOTH)

    for line in split.splitlines():
        assert line in whole.splitlines()


def test_정답표_서른한_발화에_화면_낱말이_하나도_안_걸린다():
    """낱말을 부분 문자열로 찾으므로 헛걸림이 생기면 기존 판정이 흔들린다.

    "오송역 근처" 는 "이 근처" 가 아니고 "오송역 위치" 도 "이 위치" 가 아니다.
    check_resolve 를 여기서 import 하는 것은 목록을 베껴 적지 않으려는 것이다.
    """
    from tools.check_resolve import UTTERANCES

    걸린_것 = [u for _, u, _, _ in UTTERANCES if resolve_service._points_at_screen(u)]

    assert 걸린_것 == []


def test_화면을_가리키는_발화_넷은_다_걸린다():
    """시연에서 쓸 말투다. 하나라도 빠지면 화면 recipe 를 아예 못 본다."""
    for utterance in (
        "지금 보이는 곳 CCTV 보여줘",
        "여기 CCTV 보여줘",
        "이 근처 충전소 찾아줘",
        "현재 화면 인구 알려줘",
    ):
        assert resolve_service._points_at_screen(utterance)


# ── 프롬프트에 실제로 그것이 실리는가 ───────────────────────────────


class OneShotLLM:
    """한 번 부르면 정해진 답을 내는 대역. 프롬프트를 남긴다."""

    def __init__(self, response):
        self.response = json.dumps(response)
        self.prompts = []

    def generate(self, prompt, response_schema):
        self.prompts.append(prompt)
        return self.response


ANSWER = {
    "reason": "고른 까닭",
    "given": None,
    "want": None,
    "about": None,
    "argument": None,
    "candidate_recipe_ids": [],
    "status": NO_MATCH,
    "recipe_id": None,
}


def menu_block(prompt: str) -> str:
    """프롬프트에서 menu 가 실린 자리. [Menu] 뒤부터 다음 대괄호 앞까지."""
    after = prompt.split("[Menu]", 1)[1]
    return after.split("\n[", 1)[0]


def test_화면을_가리키는_발화는_프롬프트에_화면_줄만_싣는다():
    """단위가 아니라 실제로 채워진 프롬프트를 본다.

    _menu_for 가 맞아도 _resolve_full 이 안 쓰면 아무것도 안 달라진다.
    """
    llm = OneShotLLM(ANSWER)

    resolve_service.resolve("여기 CCTV 보여줘", llm, 200, context=BOTH)

    실린_것 = recipes_in(menu_block(llm.prompts[0]))
    assert 실린_것 == starting_at("picked_point", "visible_extent")


def test_평범한_발화는_프롬프트에_기존_마흔만_싣는다():
    llm = OneShotLLM(ANSWER)

    resolve_service.resolve("오송역 CCTV 보여줘", llm, 200, context=BOTH)

    assert recipes_in(menu_block(llm.prompts[0])) == spoken_recipes()


# ── 거르는 함수 ─────────────────────────────────────────────────────


def test_인자를_안_주면_menu_yaml_원문_그대로다():
    """옛 부름이 한 글자도 달라지면 안 된다. _candidate_lines 가 그것을 쓴다."""
    from paths import MENU_YAML_PATH

    assert load_menu() == MENU_YAML_PATH.read_text(encoding="utf-8")


def test_없는_id_를_줘도_오류가_아니라_없는_것으로_본다():
    """온톨로지가 바뀌는 중에 프롬프트가 죽는 것보다 낫다."""
    menu = load_menu({"recipe_없음"})

    assert not recipes_in(menu)
    assert "version" in menu


# ── /resolve 가 문맥을 받는가 ───────────────────────────────────────


def test_resolve_엔드포인트가_본문으로_문맥을_받는다(monkeypatch):
    """Streamlit 과 check_resolve 가 그 길로 보낸다.

    저쪽 화면은 /chat 으로 오고 이 자리를 안 지난다.
    """
    from fastapi.testclient import TestClient

    from demo.api import main as backend_main

    받은_것 = {}

    def fake_resolve(utterance, llm_client, reason_max_length, narrow=None, context=None):
        받은_것["utterance"] = utterance
        받은_것["context"] = context
        return {"status": NO_MATCH, "recipe_id": None, "candidate_recipe_ids": []}

    monkeypatch.setattr(backend_main.resolve_service, "resolve", fake_resolve)

    with TestClient(backend_main.app) as client:
        client.post("/resolve", params={"utterance": "여기 CCTV 보여줘"}, json=BBOX_ONLY)

    assert 받은_것["context"] == BBOX_ONLY


def test_문맥을_안_보내면_None_으로_들어간다(monkeypatch):
    """--context none 과 옛 부름이 이 자리를 지난다."""
    from fastapi.testclient import TestClient

    from demo.api import main as backend_main

    받은_것 = {}

    def fake_resolve(utterance, llm_client, reason_max_length, narrow=None, context=None):
        받은_것["context"] = context
        return {"status": NO_MATCH, "recipe_id": None, "candidate_recipe_ids": []}

    monkeypatch.setattr(backend_main.resolve_service, "resolve", fake_resolve)

    with TestClient(backend_main.app) as client:
        client.post("/resolve", params={"utterance": "오송역 CCTV 보여줘"})

    assert 받은_것["context"] is None


# ── 화면과 도구가 같은 고정값을 쓰는가 ──────────────────────────────


def test_check_resolve_의_세_가지_문맥():
    """없음 · bbox 만 · 둘 다. 기본은 bbox 다 — 저쪽 평상시와 같다."""
    from tools import check_resolve

    assert check_resolve.CONTEXT == check_resolve.CONTEXT_BBOX

    check_resolve.CONTEXT = check_resolve.CONTEXT_NONE
    try:
        assert check_resolve._context_payload() is None

        check_resolve.CONTEXT = check_resolve.CONTEXT_BBOX
        assert check_resolve._context_payload()["selectedLocation"] is None
        assert check_resolve._context_payload()["view"]["bbox"]

        check_resolve.CONTEXT = check_resolve.CONTEXT_BOTH
        assert check_resolve._context_payload()["selectedLocation"]["lon"]
    finally:
        check_resolve.CONTEXT = check_resolve.CONTEXT_BBOX


def test_화면과_도구가_같은_bbox_를_쓴다():
    """둘이 어긋나면 "시연과 같은 조건" 이라는 말이 거짓이 된다."""
    from demo.ui import config as ui_config
    from tools import check_resolve

    assert check_resolve.ui_config is ui_config
    assert ui_config.map_context()["view"]["bbox"] == ui_config.FIXED_VIEW_BBOX
