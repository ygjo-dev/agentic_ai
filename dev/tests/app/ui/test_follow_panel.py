"""KRRI_ASAP 회차 하나를 화면이 아는 장면으로 바꾸는 것.

Streamlit 을 안 띄운다. 순수 함수 셋만 본다 — 그리는 것은 화면을 보면 알고,
**화면을 봐도 모르는 것은 raw JSON 이 샜는지다.** 그것을 여기서 막는다.
"""

import json

from app.ui.components import follow_panel

# GET /recent 가 주는 회차 한 건. 실행까지 간 것. 단계는 이벤트에서 옮겨 적은 것이고
# 답(KRRI Gemini)에는 번호 줄이 없다.
TURN = {
    "seq": 10,
    "at": 1_756_000_300.0,
    "utterance": "오송역 CCTV 보여줘",
    "status": "SELECT",
    "argument": "오송역",
    "recipe_id": "recipe_036",
    "candidate_recipe_ids": ["recipe_036"],
    "steps": [
        {"node": "resolve", "start_message": "발화를 해석하고 있습니다...", "end_message": "SELECT recipe_036", "failed": False},
        {"node": "geocode_place", "start_message": "geo.geocode 호출 중입니다...", "end_message": "geo.geocode 완료", "failed": False},
        {"node": "find_cctv", "start_message": "road.getCctv 호출 중입니다...", "end_message": "road.getCctv 완료", "failed": False},
    ],
    "execution_status": "success",
    "answer": "오송역 주변 15km 안에서 CCTV 3대를 찾았습니다.",
}

# /recent 가 답에서 단계 줄을 잘라 두던 때의 회차 모양. 화면이 여전히 그릴 수 있어야 한다.
LEGACY_TURN = {
    "seq": 7,
    "at": 1_756_000_000.0,
    "utterance": "오송역 CCTV 보여줘",
    "status": "SELECT",
    "given": "spoken_place",
    "want": "cctv",
    "about": "road",
    "argument": "오송역",
    "recipe_id": "recipe_002",
    "candidate_recipe_ids": ["recipe_002"],
    "head": "오송역 CCTV 를 조회했습니다.",
    "steps": [
        {"node": "n_geocode", "line": "1. geo.geocode        오송역 → 충북 청주시"},
        {"node": "n_cctv", "line": "2. road.getCctv       minX=127.31  83건"},
    ],
    "answer": "\n".join(
        [
            "오송역 CCTV 를 조회했습니다.",
            "",
            "1. geo.geocode        오송역 → 충북 청주시",
            "2. road.getCctv       minX=127.31  83건",
        ]
    ),
}

# 되묻기 회차. 단계가 없고 머리말이 후보 목록이다.
CLARIFY_TURN = {
    "seq": 8,
    "at": 1_756_000_100.0,
    "utterance": "오송역 인구 구성 알려줘",
    "status": "CLARIFY",
    "recipe_id": None,
    "candidate_recipe_ids": ["recipe_011", "recipe_045"],
    "steps": [
        {"node": "resolve", "start_message": "발화를 해석하고 있습니다...", "end_message": "CLARIFY", "failed": False},
    ],
    "execution_status": None,
    "answer": "어느 것을 보시겠습니까?\n  1  인구 통계 조회\n  2  장소 좌표 변환 -> 인구 통계 조회",
}

# 문서 검색 회차. 한 단계가 여러 줄이다 — 건수 줄 아래에 문서 조각이 붙는다.
RAG_TURN = {
    "seq": 9,
    "at": 1_756_000_200.0,
    "utterance": "문서에서 철도안전법 관련 내용 찾아줘",
    "status": "SELECT",
    "recipe_id": "recipe_013",
    "candidate_recipe_ids": ["recipe_013"],
    "head": "철도안전법 문서를 조회했습니다.",
    "steps": [
        {
            "node": "search_documents",
            "line": "\n".join(
                [
                    "1. knowledge.query   6건",
                    "   「철도안전법(법률)(제21188호)(20260303).pdf」 1쪽 · \"법제처 1 국가법령정보센터…\"",
                    "   「철도안전법(법률)(제21188호)(20260303).pdf」 2쪽 · \"법제처 2 국가법령정보센터…\"",
                ]
            ),
        }
    ],
    "answer": "",
}


def test_a_followed_view_is_highlighted_by_the_same_path_as_a_resolve_view():
    """강조 규칙을 새로 만들지 않는다. 발화를 여기서 넣었을 때와 같아야 한다."""
    from app.ui.main import recipe_ids_to_show, render_mode

    view = follow_panel.follow_view(TURN)

    assert render_mode(view) == "resolve"
    assert recipe_ids_to_show(view) == ["recipe_036"]


def test_a_clarify_highlights_its_candidate_paths_too():
    from app.ui.main import recipe_ids_to_show

    view = follow_panel.follow_view(CLARIFY_TURN)

    assert recipe_ids_to_show(view) == ["recipe_011", "recipe_045"]


def test_the_utterance_is_carried_verbatim_into_the_view():
    assert follow_panel.follow_view(TURN)["utterance"] == "오송역 CCTV 보여줘"


def test_the_steps_are_drawn_from_the_recorded_events_in_order():
    """답에 번호 줄이 없어도 단계가 그려진다. 끝 message 가 한 줄이다."""
    assert follow_panel.step_lines(TURN) == ["1. SELECT recipe_036", "2. geo.geocode 완료", "3. road.getCctv 완료"]


def test_numbered_lines_in_the_answer_are_drawn_as_the_answer_not_as_steps():
    """답의 "1. " 줄은 답 문구 안에 그대로 남는다. 단계 목록은 이벤트에서만 온다."""
    turn = {**TURN, "answer": "CCTV 3대입니다.\n\n1. 오송역 앞\n2. 오송역 뒤"}

    assert follow_panel.head_of(turn) == turn["answer"]
    assert follow_panel.step_lines(turn) == follow_panel.step_lines(TURN)


def test_a_step_that_never_ended_shows_its_start_message():
    turn = {"steps": [{"node": "n", "start_message": "geo.geocode 호출 중입니다...", "end_message": "", "failed": False}]}

    assert follow_panel.step_lines(turn) == ["1. geo.geocode 호출 중입니다..."]


def test_the_whole_answer_is_drawn_above_the_steps():
    """되묻기 회차의 후보 목록이 잘려 나가면 무엇을 고를지가 안 보인다."""
    assert follow_panel.head_of(CLARIFY_TURN) == CLARIFY_TURN["answer"]
    assert follow_panel.head_of(TURN) == TURN["answer"]


def test_a_legacy_turn_is_still_drawn_from_its_cut_lines():
    """예전 회차의 head · line 은 서버가 이미 잘라 둔 것이라 그대로 그린다."""
    assert follow_panel.head_of(LEGACY_TURN) == "오송역 CCTV 를 조회했습니다."
    assert follow_panel.step_lines(LEGACY_TURN) == [step["line"] for step in LEGACY_TURN["steps"]]
    assert follow_panel.step_lines(RAG_TURN)[0].count("\n") == 2


def test_the_string_to_be_drawn_on_screen_has_no_coordinate_arrays():
    """화면을 봐도 모르는 것을 막는 자리다. 새는 길은 /recent 응답뿐이 아니다."""
    view = follow_panel.follow_view(TURN)
    drawn = "\n".join(
        [
            json.dumps(view, ensure_ascii=False),
            follow_panel.head_of(TURN),
            *follow_panel.step_lines(TURN),
        ]
    )

    for leaked in ("geojson", "coordinates", "geometry", "FeatureCollection", "rtsp://"):
        assert leaked not in drawn


def test_the_timestamp_comes_out_in_a_readable_shape():
    assert follow_panel.at_text(TURN).count(":") == 2


def test_an_empty_timestamp_field_does_not_blow_up():
    """KRRI_ASAP 회차가 어떤 모양이어도 화면이 죽으면 안 된다."""
    assert isinstance(follow_panel.at_text({}), str)
