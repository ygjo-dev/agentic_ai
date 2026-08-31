"""프롬프트에 넣을 menu 를 요청마다 가르는 것.

LLM 을 부르지 않는다. 어느 문장이 프롬프트에 실리는가만 본다.

**관문 둘이다.**
  발화가 화면을 안 가리키면 「마흔여섯째」 이전과 같이 말로 시작하는
  recipe 줄만 실린다
  낱말이 걸려도 문맥에 값이 없으면 그 줄만이다 — 없는 것을 제안하면
  LLM 이 고르고 나서 `_without_dropped` 에 지워진다

recipe id 를 박지 않는다. 온톨로지가 바뀌면 번호가 통째로 밀리므로 경로 첫 칸으로
가른다 — `_menu_for` 가 쓰는 기준과 같은 것이다.

★ 이 갈래는 월요일 시연을 위한 임시방편이다. NOTES.md 「마흔여덟째」를 본다.
"""

import json

import yaml

from app.api.services.streamlit import screen_service
from execution import step_service
from orchestrator import resolve_service
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
    for recipe_id in screen_service.recipe_ids():
        path = screen_service.path_of(recipe_id)
        if path and path[0]["node_id"] in node_ids:
            found.add(recipe_id)
    return found


def spoken_recipes() -> set:
    """화면에서 안 오는 시작 데이터에서 출발하는 recipe. 말로 시작하는 것 전부다.

    수를 안 적는다. recipe 가 늘면 함께 느는 값이라 적어 두면 낡는다.
    """
    return set(screen_service.recipe_ids()) - starting_at(*step_service.CONTEXT_STARTS)


def test_an_ordinary_utterance_never_even_sees_the_screen_recipes():
    """menu 가 길어져 판정이 16 내린 것이 이번 변경의 까닭이다.

    문맥이 와 있어도 발화가 화면을 안 가리키면 화면 줄은 실리지 않는다.
    """
    menu = resolve_service._menu_for("오송역 CCTV 보여줘", BOTH)

    assert recipes_in(menu) == spoken_recipes()


def test_no_context_at_all_gives_the_spoken_start_recipes():
    """문맥을 안 보내는 부름은 이 변경 전과 같은 menu 를 봐야 한다."""
    menu = resolve_service._menu_for("오송역 CCTV 보여줘", None)

    assert recipes_in(menu) == spoken_recipes()


def test_pointing_at_the_screen_without_values_gives_the_spoken_start_recipes():
    """없는 것을 제안하면 LLM 이 고르고 나서 후보에서 지워진다.

    값이 있는지는 이미 있는 context_starts 가 센다. 새 기준을 만들지 않는다.
    """
    menu = resolve_service._menu_for("여기 CCTV 보여줘", None)

    assert recipes_in(menu) == spoken_recipes()


def test_visible_extent_alone_does_not_carry_the_picked_point_recipes():
    """저쪽 평상시(우클릭 전)가 이 자리다.

    찍은 지점에서 출발하는 recipe 는 그때 골라도 좌표가 없어 못 쓴다.
    """
    menu = resolve_service._menu_for("지금 보이는 곳 CCTV 보여줘", BBOX_ONLY)

    assert recipes_in(menu) == starting_at("visible_extent")
    assert not recipes_in(menu) & starting_at("picked_point")


def test_both_arriving_carries_every_screen_recipe():
    """우클릭 뒤에는 찍은 지점과 보이는 범위가 함께 후보가 된다."""
    menu = resolve_service._menu_for("여기 CCTV 보여줘", BOTH)

    assert recipes_in(menu) == starting_at("picked_point", "visible_extent")


def test_a_split_menu_is_shorter_than_menu_yaml_either_way():
    """짧게 만드는 것이 이번 변경의 목적이다."""
    whole = load_menu()

    for utterance, context in (
        ("오송역 CCTV 보여줘", BOTH),
        ("여기 CCTV 보여줘", BOTH),
        ("지금 보이는 곳 CCTV 보여줘", BBOX_ONLY),
    ):
        assert len(resolve_service._menu_for(utterance, context)) < len(whole)


def test_a_split_menu_is_still_valid_yaml():
    """머리말이 남아야 프롬프트에 실린 것을 사람이 읽을 수 있다."""
    parsed = yaml.safe_load(resolve_service._menu_for("여기 CCTV 보여줘", BOTH))

    assert parsed["version"]
    assert parsed["recipes"]


def test_the_remaining_lines_differ_from_menu_yaml_by_not_one_character():
    """menu.yaml 을 안 고친다. 읽은 문자열에서 블록을 뺄 뿐이다."""
    whole = load_menu()
    split = resolve_service._menu_for("여기 CCTV 보여줘", BOTH)

    for line in split.splitlines():
        assert line in whole.splitlines()


def test_not_one_screen_word_matches_the_thirty_one_spoken_utterances():
    """낱말을 부분 문자열로 찾으므로 헛걸림이 생기면 기존 판정이 흔들린다.

    "오송역 근처" 는 "이 근처" 가 아니고 "오송역 위치" 도 "이 위치" 가 아니다.
    check_resolve 를 여기서 import 하는 것은 목록을 베껴 적지 않으려는 것이다.

    2026-08-30 에 정답표가 서른여섯이 되면서 이름을 고쳤다. 32~36 번은 화면
    낱말이 걸리라고 넣은 발화라 이 시험이 볼 것이 아니다 — 그 다섯은 아래
    시험이 본다. 보는 것은 그대로다.
    """
    from dev.tools.check_resolve import EXTENSION_LAST, UTTERANCES

    걸린_것 = [
        u
        for n, u, _, _ in UTTERANCES
        if n <= EXTENSION_LAST and resolve_service._points_at_screen(u)
    ]

    assert 걸린_것 == []


def test_all_five_screen_utterances_in_the_answer_key_match_a_screen_word():
    """하나라도 안 걸리면 그 줄은 화면 recipe 를 아예 못 보고 재어진다.

    걸려야 menu 에 화면 recipe 가 실린다. 안 걸리면 말로 시작하는 recipe 만
    보게 되어
    기대값에 닿을 길이 없는데, 표에는 그냥 빗나감으로 찍혀 발화가 나쁜 것인지
    낱말이 안 걸린 것인지가 안 갈린다.
    """
    from dev.tools.check_resolve import EXTENSION_LAST, UTTERANCES

    화면_다섯 = [u for n, u, _, _ in UTTERANCES if n > EXTENSION_LAST]

    assert len(화면_다섯) == 5
    assert all(resolve_service._points_at_screen(u) for u in 화면_다섯)


def test_all_four_utterances_pointing_at_the_screen_match():
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


def test_an_utterance_pointing_at_the_screen_carries_only_the_screen_lines_in_the_prompt():
    """단위가 아니라 실제로 채워진 프롬프트를 본다.

    _menu_for 가 맞아도 _resolve_full 이 안 쓰면 아무것도 안 달라진다.
    """
    llm = OneShotLLM(ANSWER)

    resolve_service.resolve("여기 CCTV 보여줘", llm, 200, context=BOTH)

    실린_것 = recipes_in(menu_block(llm.prompts[0]))
    assert 실린_것 == starting_at("picked_point", "visible_extent")


def test_an_ordinary_utterance_carries_only_the_spoken_start_recipes_in_the_prompt():
    llm = OneShotLLM(ANSWER)

    resolve_service.resolve("오송역 CCTV 보여줘", llm, 200, context=BOTH)

    assert recipes_in(menu_block(llm.prompts[0])) == spoken_recipes()


# ── 거르는 함수 ─────────────────────────────────────────────────────


def test_without_an_argument_it_is_the_menu_yaml_original_verbatim():
    """옛 부름이 한 글자도 달라지면 안 된다. _candidate_lines 가 그것을 쓴다."""
    from paths import MENU_YAML_PATH

    assert load_menu() == MENU_YAML_PATH.read_text(encoding="utf-8")


def test_an_unknown_id_is_treated_as_absent_rather_than_an_error():
    """온톨로지가 바뀌는 중에 프롬프트가 죽는 것보다 낫다."""
    menu = load_menu({"recipe_없음"})

    assert not recipes_in(menu)
    assert "version" in menu


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

    2026-08-30 에 기본을 bbox 에서 both 로 바꿨다. bbox 뿐이면 찍은 지점
    recipe 아홉이 menu 에도 축 선택지에도 안 실려 아예 못 재어진다.
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
