"""build_dot() 의 다중 경로 강조 검증 (CLARIFY 후보).

후보가 여럿이면 경로를 모두 강조하되 순번은 붙이지 않는다.
같은 엣지를 공유하는 경로가 많아 라벨이 겹치기 때문이다.
"""

import re

from frontend.components.graph_section import build_dot

NODES = {
    "load_cctv_platform": {"name": "승강장 CCTV 불러오기"},
    "load_inspection_car_image": {"name": "검측차 이미지 불러오기"},
    "detect_structure_crack": {"name": "구조물 균열 분석"},
    "generate_word": {"name": "Word 생성"},
    "generate_ppt": {"name": "PPT 생성"},
}
SOLID = {
    ("load_cctv_platform", "detect_structure_crack"): "MediaData",
    ("load_inspection_car_image", "detect_structure_crack"): "MediaData",
    ("detect_structure_crack", "generate_word"): "AnalysisResult",
    ("detect_structure_crack", "generate_ppt"): "AnalysisResult",
}

# recipe_015 / recipe_019 처럼 뒷부분(균열 -> Word)을 공유하는 두 경로.
PATH_A = [
    ("load_cctv_platform", "detect_structure_crack"),
    ("detect_structure_crack", "generate_word"),
]
PATH_B = [
    ("load_inspection_car_image", "detect_structure_crack"),
    ("detect_structure_crack", "generate_word"),
]


def bold_lines(dot: str) -> list[str]:
    return [line.strip() for line in dot.splitlines() if "penwidth=3" in line]


def bold_edge(dot: str, frm: str, to: str) -> list[str]:
    return [
        line
        for line in bold_lines(dot)
        if re.search(rf'"{frm}"\s*->\s*"{to}"', line)
    ]


# ------------------------------------------------------------ 합집합 강조
def test_two_paths_highlight_both():
    dot = build_dot(NODES, SOLID, {}, highlight_paths=[PATH_A, PATH_B])

    assert bold_edge(dot, "load_cctv_platform", "detect_structure_crack")
    assert bold_edge(dot, "load_inspection_car_image", "detect_structure_crack")
    assert bold_edge(dot, "detect_structure_crack", "generate_word")


def test_shared_edge_is_drawn_once():
    """두 경로가 공유하는 엣지를 두 번 그리면 선이 겹쳐 두꺼워 보인다."""
    dot = build_dot(NODES, SOLID, {}, highlight_paths=[PATH_A, PATH_B])

    assert len(bold_edge(dot, "detect_structure_crack", "generate_word")) == 1


def test_edge_outside_every_path_stays_plain():
    dot = build_dot(NODES, SOLID, {}, highlight_paths=[PATH_A, PATH_B])

    assert not bold_edge(dot, "detect_structure_crack", "generate_ppt")


# ------------------------------------------------------------ 순번 규칙
def test_multiple_paths_have_no_order_label():
    """여러 경로가 같은 엣지를 공유하면 순번이 겹쳐 읽을 수 없다."""
    dot = build_dot(NODES, SOLID, {}, highlight_paths=[PATH_A, PATH_B])

    for line in bold_lines(dot):
        assert "label=" not in line, line


def test_single_path_gets_order_labels():
    """하나로 좁혀지면 순서를 읽을 수 있어야 한다."""
    dot = build_dot(NODES, SOLID, {}, highlight_paths=[PATH_A])

    assert 'label="1"' in bold_edge(dot, "load_cctv_platform", "detect_structure_crack")[0]
    assert 'label="2"' in bold_edge(dot, "detect_structure_crack", "generate_word")[0]


def test_single_path_via_highlight_paths_matches_highlight():
    """highlight_paths=[p] 와 highlight=p 는 같은 그림이어야 한다."""
    one = build_dot(NODES, SOLID, {}, highlight_paths=[PATH_A])
    other = build_dot(NODES, SOLID, {}, highlight=PATH_A)

    assert one == other


# ------------------------------------------------------------ 노드 강조
def test_nodes_of_all_paths_are_emphasised():
    dot = build_dot(NODES, SOLID, {}, highlight_paths=[PATH_A, PATH_B])

    for node_id in (
        "load_cctv_platform",
        "load_inspection_car_image",
        "detect_structure_crack",
        "generate_word",
    ):
        line = next(l for l in dot.splitlines() if f'"{node_id}" [label=' in l)
        assert "penwidth=2" in line, line


def test_node_outside_every_path_stays_plain():
    dot = build_dot(NODES, SOLID, {}, highlight_paths=[PATH_A, PATH_B])

    line = next(l for l in dot.splitlines() if '"generate_ppt" [label=' in l)
    assert "penwidth=2" not in line, line


def test_empty_paths_highlight_nothing():
    dot = build_dot(NODES, SOLID, {}, highlight_paths=[])

    assert not bold_lines(dot)
    assert "penwidth=2" not in dot
