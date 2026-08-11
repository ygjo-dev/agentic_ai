"""하단 패널 마크업 검증.

설명글을 전부 걷어냈다 — 범례 · 안내 문구 · 인터페이스 이름 · recipe id 가
화면에 없어야 한다. 발표자가 말로 설명하고, 글이 없으면 오류가 났을 때 티가 난다.
"""

from frontend import config
from frontend.components.path_panel import (
    band_markup,
    chips_markup,
    counts_markup,
    ordered_recipe_ids,
    path_chain,
    paths_markup,
    registration_header,
    skeleton_markup,
    utterance_markup,
)

STEPS = [
    {"node_id": "load_cctv_platform", "name": "승강장 CCTV 불러오기", "out_interface": "MediaData"},
    {"node_id": "analyze_congestion", "name": "승강장 혼잡도 분석", "out_interface": "AnalysisResult"},
]

SELECT = {
    "status": "SELECT",
    "recipe_id": "recipe_004",
    "candidate_recipe_ids": ["recipe_004"],
    "reason": "…",
    "paths": {"recipe_004": STEPS},
}
CLARIFY = {
    "status": "CLARIFY",
    "recipe_id": None,
    "candidate_recipe_ids": ["recipe_010", "recipe_011", "recipe_012"],
    "reason": "…",
    "paths": {"recipe_010": STEPS, "recipe_011": STEPS, "recipe_012": STEPS},
}
NO_MATCH_RESULT = {
    "status": "NO_MATCH",
    "recipe_id": None,
    "candidate_recipe_ids": [],
    "reason": "…",
    "paths": {},
}

REGISTRATION = {
    "node_id": "analyze_crack_trend",
    "node": {"name": "구조물 균열 진행 추세 분석"},
    "recipe_ids": ["recipe_022", "recipe_023"],
    "paths": {"recipe_022": STEPS, "recipe_023": STEPS},
    "new_solid_edges": [{"from": "a", "to": "b", "interface": "DocumentData"}],
    "new_dotted_edges": [{"a": "a", "b": "c", "labels": ["target: 구조물"]}],
    "counts": {"nodes": [9, 10], "recipes": [21, 27]},
}


# ------------------------------------------------------------ 상태별
def test_before_run_is_empty():
    """안내 문구를 두지 않는다. 하단 지도가 그대로 떠 있어 화면이 안 빈다."""
    assert paths_markup(None) == ""


def test_select_shows_one_chain():
    markup = paths_markup(SELECT)

    assert markup.count('class="chain"') == 1


def test_clarify_row_count_matches_candidates():
    """후보가 나란히 보이는 것 자체가 '아직 안 정해졌다' 를 보여준다."""
    markup = paths_markup(CLARIFY)

    assert markup.count('class="chain"') == len(CLARIFY["candidate_recipe_ids"])


def test_no_match_is_empty():
    """지도는 떠 있는데 켜지는 길이 없다 — 문구 없이 그림으로 읽힌다."""
    markup = paths_markup(NO_MATCH_RESULT)

    assert markup == ""


def test_select_recipe_is_not_drawn_twice():
    """recipe_id 가 후보에도 들어 있다. 한 번만 그려야 한다."""
    assert ordered_recipe_ids(SELECT) == ["recipe_004"]


# ------------------------------------------------------------ 칩 사슬
def test_chain_has_one_chip_per_node():
    chain = path_chain("recipe_004", STEPS, config.HIGHLIGHT_COLOR)

    assert chain.count('class="chip"') == 2


def test_chain_has_one_link_between_chips():
    chain = path_chain("recipe_004", STEPS, config.HIGHLIGHT_COLOR)

    assert chain.count('class="link"') == 1


def test_link_carries_no_interface_name():
    """인터페이스 이름은 안 적는다. 같은 이름이 여러 줄에 반복되면 글자로 덮인다."""
    chain = path_chain("recipe_004", STEPS, config.HIGHLIGHT_COLOR)

    assert "MediaData" not in chain
    assert "AnalysisResult" not in chain


def test_single_node_chain_has_no_link():
    chain = path_chain("recipe_001", STEPS[:1], config.HIGHLIGHT_COLOR)

    assert chain.count('class="chip"') == 1
    assert 'class="link"' not in chain


def test_empty_path_does_not_crash():
    assert path_chain("recipe_x", [], config.HIGHLIGHT_COLOR) == '<div class="chain"></div>' 


def test_chain_falls_back_to_node_id_when_name_missing():
    chain = path_chain("recipe_x", [{"node_id": "some_node"}], config.HIGHLIGHT_COLOR)

    assert "some_node" in chain


def test_chips_are_staggered_for_the_animation():
    """왼쪽에서 오른쪽으로 그려지듯 등장해야 한다."""
    chain = path_chain("recipe_004", STEPS, config.HIGHLIGHT_COLOR)

    assert "--i:0" in chain and "--i:1" in chain


# ------------------------------------------------------------ 이스케이프
def test_node_names_are_escaped():
    """노드 이름은 사용자가 등록한 값이다. 그대로 넣으면 마크업이 깨진다."""
    chain = path_chain("r", [{"node_id": "x", "name": "<script>alert(1)</script>"}], "#fff")

    assert "<script>" not in chain
    assert "&lt;script&gt;" in chain


def test_recipe_id_is_not_shown():
    """id 는 사람이 읽을 정보가 아니다. 줄끼리는 노드 내용으로 구분된다."""
    assert "recipe_004" not in path_chain("recipe_004", STEPS, "#fff")


def test_utterance_is_escaped():
    assert "&lt;script&gt;" in utterance_markup("<script>alert(1)</script>")


def test_empty_utterance_renders_nothing():
    assert utterance_markup(None) == ""
    assert utterance_markup("") == ""


# ------------------------------------------------------------ 스탯
def test_counts_show_before_and_after():
    markup = counts_markup({"nodes": [9, 10], "recipes": [21, 27]})

    assert ">9<" in markup and ">10<" in markup
    assert ">21<" in markup and ">27<" in markup


def test_counts_label_each_row():
    markup = counts_markup({"nodes": [9, 10], "recipes": [21, 27]})

    assert "노드" in markup and "Recipe" in markup


def test_missing_counts_render_nothing():
    assert counts_markup(None) == ""
    assert counts_markup({}) == ""


def test_malformed_counts_are_skipped():
    """한쪽이 망가져도 나머지는 보여준다."""
    markup = counts_markup({"nodes": [9], "recipes": [21, 27]})

    assert ">21<" in markup


# ------------------------------------------------------------ 등록 결과 (띠)
def test_registration_header_shows_the_new_node_name():
    markup = registration_header(REGISTRATION)

    assert "구조물 균열 진행 추세 분석" in markup
    assert "새 노드" in markup


def test_registration_header_uses_the_new_colour():
    assert config.NEW_COLOR in registration_header(REGISTRATION)


def test_registration_header_includes_the_counts():
    assert ">10<" in registration_header(REGISTRATION)


def test_registration_chains_moved_to_the_iframe():
    """사슬은 띠가 아니라 아래 iframe 이 그래프와 함께 그린다."""
    assert 'class="chain"' not in registration_header(REGISTRATION)


# ------------------------------------------------------------ 칩 목록 (iframe)
def test_chips_markup_draws_one_chain_per_recipe():
    markup = chips_markup(CLARIFY["paths"], CLARIFY["candidate_recipe_ids"], "#fff")

    assert markup.count('class="chain"') == 3


def test_chips_markup_empty_is_blank():
    """비면 빈 칸이다. 옆 그래프가 이미 상태를 말한다."""
    assert chips_markup({}, [], "#fff") == ""


# ------------------------------------------------------------ 띠
def test_band_before_run_is_empty():
    assert band_markup(None) == ""


def test_band_shows_only_the_utterance():
    """하단에 유일하게 남는 텍스트다. 무엇에 대한 답인지 알려준다."""
    markup = band_markup({"kind": "resolve", "utterance": "승강장 상태를 분석해줘", "result": SELECT})

    assert "승강장 상태를 분석해줘" in markup


def test_band_has_no_legend():
    """색이 무엇인지는 발표자가 말한다."""
    markup = band_markup({"kind": "resolve", "utterance": "발화", "result": SELECT})

    assert "선택된 경로" not in markup
    assert "같은 특성" not in markup


def test_band_switches_to_registration_header():
    markup = band_markup({"kind": "register", "result": REGISTRATION})

    assert "새 노드" in markup
    assert "같은 특성" not in markup


def test_skeleton_has_rows():
    """기다리는 동안 자리를 비워두지 않는다."""
    assert skeleton_markup().count("skel-row") == 3
