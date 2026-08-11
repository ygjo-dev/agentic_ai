"""정답 경로(샘플 기대값) 표시 검증.

샘플로 실행했을 때만 정답 경로를 다른 색으로 함께 그린다.
실제와 겹치면 두 색이 모두 보여야 한다 — 겹쳤다는 것 자체가 정보다.
"""

import re

from frontend.components.graph_section import (
    EXPECTED_COLOR,
    HIGHLIGHT_COLOR,
    build_dot,
)

NODES = {
    "load_cctv_platform": {"name": "승강장 CCTV 불러오기"},
    "load_inspection_car_image": {"name": "검측차 이미지 불러오기"},
    "analyze_congestion": {"name": "승강장 혼잡도 분석"},
    "detect_structure_crack": {"name": "구조물 균열 분석"},
    "generate_word": {"name": "Word 생성"},
}
SOLID = {
    ("load_cctv_platform", "analyze_congestion"): "MediaData",
    ("load_cctv_platform", "detect_structure_crack"): "MediaData",
    ("load_inspection_car_image", "detect_structure_crack"): "MediaData",
    ("analyze_congestion", "generate_word"): "AnalysisResult",
    ("detect_structure_crack", "generate_word"): "AnalysisResult",
}

ACTUAL = [
    ("load_cctv_platform", "analyze_congestion"),
    ("analyze_congestion", "generate_word"),
]
OTHER = [
    ("load_inspection_car_image", "detect_structure_crack"),
    ("detect_structure_crack", "generate_word"),
]


def edge_line(dot: str, frm: str, to: str) -> str:
    return next(
        line for line in dot.splitlines() if re.search(rf'"{frm}"\s*->\s*"{to}"', line)
    )


# ------------------------------------------------------------ 정답 경로 표시
def test_expected_path_uses_a_different_colour():
    dot = build_dot(NODES, SOLID, {}, expected_paths=[OTHER])

    line = edge_line(dot, "load_inspection_car_image", "detect_structure_crack")
    assert EXPECTED_COLOR in line, line
    assert HIGHLIGHT_COLOR not in line, line


def test_expected_colour_differs_from_highlight():
    """두 색이 같으면 실제와 정답을 구별할 수 없다."""
    assert EXPECTED_COLOR != HIGHLIGHT_COLOR


def test_without_expected_no_expected_colour():
    """직접 입력한 발화에는 정답이 없다."""
    dot = build_dot(NODES, SOLID, {}, highlight=ACTUAL)

    assert EXPECTED_COLOR not in dot


def test_expected_paths_none_is_same_as_omitted():
    assert build_dot(NODES, SOLID, {}, highlight=ACTUAL) == build_dot(
        NODES, SOLID, {}, highlight=ACTUAL, expected_paths=None
    )


# ------------------------------------------------------------ 겹침 / 어긋남
def test_matching_paths_show_both_colours():
    """일치하면 같은 엣지에 겹친다. 그래도 두 색이 다 보여야 한다."""
    dot = build_dot(NODES, SOLID, {}, highlight=ACTUAL, expected_paths=[ACTUAL])

    line = edge_line(dot, "load_cctv_platform", "analyze_congestion")
    assert HIGHLIGHT_COLOR in line, line
    assert EXPECTED_COLOR in line, line
    assert f"{HIGHLIGHT_COLOR}:{EXPECTED_COLOR}" in line, "colorList 로 나란히 그려야 한다."


def test_diverging_paths_show_two_branches():
    """어긋나면 실제와 정답이 각각 다른 색으로 갈라져 보인다."""
    dot = build_dot(NODES, SOLID, {}, highlight=ACTUAL, expected_paths=[OTHER])

    actual_line = edge_line(dot, "load_cctv_platform", "analyze_congestion")
    expected_line = edge_line(dot, "load_inspection_car_image", "detect_structure_crack")

    assert HIGHLIGHT_COLOR in actual_line and EXPECTED_COLOR not in actual_line
    assert EXPECTED_COLOR in expected_line and HIGHLIGHT_COLOR not in expected_line


def test_shared_tail_of_diverging_paths_shows_both():
    """앞은 갈라져도 뒤(생성 단계)를 공유하면 그 엣지에는 두 색이 겹친다."""
    dot = build_dot(NODES, SOLID, {}, highlight=ACTUAL, expected_paths=[OTHER])

    shared = edge_line(dot, "detect_structure_crack", "generate_word")
    assert EXPECTED_COLOR in shared

    own = edge_line(dot, "analyze_congestion", "generate_word")
    assert HIGHLIGHT_COLOR in own


# ------------------------------------------------------------ CLARIFY 정답
def test_expected_clarify_draws_every_candidate():
    """Expected 가 CLARIFY 면 후보가 여럿이다. 전부 그려야 한다."""
    dot = build_dot(NODES, SOLID, {}, expected_paths=[ACTUAL, OTHER])

    for frm, to in [*ACTUAL, *OTHER]:
        assert EXPECTED_COLOR in edge_line(dot, frm, to), f"{frm}->{to}"


# ------------------------------------------------------------ 노드
def test_expected_nodes_are_marked_too():
    dot = build_dot(NODES, SOLID, {}, expected_paths=[OTHER])

    line = next(l for l in dot.splitlines() if '"detect_structure_crack" [label=' in l)
    assert EXPECTED_COLOR in line, line


def test_node_on_both_paths_shows_both_colours():
    dot = build_dot(NODES, SOLID, {}, highlight=ACTUAL, expected_paths=[ACTUAL])

    line = next(l for l in dot.splitlines() if '"generate_word" [label=' in l)
    assert f"{HIGHLIGHT_COLOR}:{EXPECTED_COLOR}" in line, line
