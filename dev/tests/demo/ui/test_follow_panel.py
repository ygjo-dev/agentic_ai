"""저쪽 회차 하나를 화면이 아는 장면으로 바꾸는 것.

Streamlit 을 안 띄운다. 순수 함수 셋만 본다 — 그리는 것은 화면을 보면 알고,
**화면을 봐도 모르는 것은 raw JSON 이 샜는지다.** 그것을 여기서 막는다.
"""

import json

from demo.ui.components import follow_panel

# GET /recent 가 주는 회차 한 건. 실행까지 간 것.
TURN = {
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
    "head": "어느 것을 보시겠습니까?\n  1  인구 통계 조회\n  2  장소 좌표 변환 -> 인구 통계 조회",
    "steps": [],
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
    from demo.ui.main import recipe_ids_to_show, render_mode

    view = follow_panel.follow_view(TURN)

    assert render_mode(view) == ("resolve", None)
    assert recipe_ids_to_show(view) == ["recipe_002"]


def test_a_clarify_highlights_its_candidate_paths_too():
    from demo.ui.main import recipe_ids_to_show

    view = follow_panel.follow_view(CLARIFY_TURN)

    assert recipe_ids_to_show(view) == ["recipe_011", "recipe_045"]


def test_the_utterance_is_carried_verbatim_into_the_view():
    assert follow_panel.follow_view(TURN)["utterance"] == "오송역 CCTV 보여줘"


def test_the_preamble_is_the_answer_minus_the_step_lines():
    assert follow_panel.head_of(TURN) == "오송역 CCTV 를 조회했습니다."


def test_with_no_steps_the_whole_answer_is_the_preamble():
    """되묻기 회차의 후보 목록이 잘려 나가면 무엇을 고를지가 안 보인다."""
    assert follow_panel.head_of(CLARIFY_TURN) == CLARIFY_TURN["answer"]


def test_a_multi_line_step_is_drawn_entirely():
    """문서 조각이 잘려 나가면 「문서에서 찾아온다」가 화면에서 안 보인다."""
    assert follow_panel.head_of(RAG_TURN) == "철도안전법 문서를 조회했습니다."
    assert RAG_TURN["steps"][0]["line"].count("\n") == 2


def test_the_string_to_be_drawn_on_screen_has_no_coordinate_arrays():
    """화면을 봐도 모르는 것을 막는 자리다. 새는 길은 /recent 응답뿐이 아니다."""
    view = follow_panel.follow_view(TURN)
    drawn = "\n".join(
        [
            json.dumps(view, ensure_ascii=False),
            follow_panel.head_of(TURN),
            *(step["line"] for step in TURN["steps"]),
        ]
    )

    for leaked in ("geojson", "coordinates", "geometry", "FeatureCollection", "rtsp://"):
        assert leaked not in drawn


def test_the_timestamp_comes_out_in_a_readable_shape():
    assert follow_panel.at_text(TURN).count(":") == 2


def test_an_empty_timestamp_field_does_not_blow_up():
    """저쪽 회차가 어떤 모양이어도 화면이 죽으면 안 된다."""
    assert isinstance(follow_panel.at_text({}), str)
