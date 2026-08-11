"""build_dot() 검증. 계산 결과를 Graphviz DOT 문자열로 옮긴다."""

import re
import shutil

import pytest

from demo.ui.components.graph_section import build_dot, render_svg

NODES = {
    "load_cctv_platform": {"name": "승강장 CCTV 불러오기"},
    "analyze_congestion": {"name": "승강장 혼잡도 분석"},
    "generate_word": {"name": "Word 생성"},
    "generate_ppt": {"name": "PPT 생성"},
}

SOLID = {
    ("load_cctv_platform", "analyze_congestion"): "MediaData",
    ("analyze_congestion", "generate_word"): "AnalysisResult",
}

DOTTED = {("generate_ppt", "generate_word"): ["output_kind: document"]}

HIGHLIGHT = [
    ("load_cctv_platform", "analyze_congestion"),
    ("analyze_congestion", "generate_word"),
]


def edge_lines(dot: str, frm: str, to: str) -> list[str]:
    """해당 쌍을 그리는 엣지 줄만 뽑는다."""
    return [
        line.strip()
        for line in dot.splitlines()
        if re.search(rf'"{frm}"\s*->\s*"{to}"', line)
    ]


# ------------------------------------------------------------ 기본 그래프
def test_solid_edge_has_no_arrow():
    """레시피 연결은 방향 없는 선이다. 화살표는 선택된 경로에만 붙는다."""
    dot = build_dot(NODES, SOLID, DOTTED)

    for line in edge_lines(dot, "load_cctv_platform", "analyze_congestion"):
        assert "dir=none" in line, line


def test_solid_edge_carries_no_interface_label():
    """같은 인터페이스 이름이 열 개 넘게 반복되면 화면이 라벨로 덮인다.

    무엇이 흐르는지는 열 위치로 읽는다.
    """
    dot = build_dot(NODES, SOLID, DOTTED)

    for line in edge_lines(dot, "load_cctv_platform", "analyze_congestion"):
        assert "label=" not in line, line

    assert "MediaData" not in dot
    assert "AnalysisResult" not in dot


def test_solid_edge_still_accepts_the_interface_value():
    """시그니처는 그대로다. 나중에 툴팁 등으로 쓸 수 있어야 한다."""
    dot = build_dot(NODES, {("load_cctv_platform", "analyze_congestion"): "MediaData"}, {})

    assert edge_lines(dot, "load_cctv_platform", "analyze_congestion")


def test_dotted_edge_is_dashed_and_has_no_arrow():
    dot = build_dot(NODES, SOLID, DOTTED)

    lines = edge_lines(dot, "generate_ppt", "generate_word")
    assert lines
    for line in lines:
        assert "style=dashed" in line, line
        assert "dir=none" in line, line


def test_dotted_edge_does_not_use_constraint_false():
    """constraint=false 는 브라우저 Graphviz(WASM)에서 레이아웃이 끝나지 않는다.

    네이티브 dot 은 즉시 끝내므로 subprocess 검증으로는 잡히지 않았고,
    화면만 비었다.
    """
    dot = build_dot(NODES, SOLID, DOTTED)

    assert "constraint=false" not in dot


def test_dotted_edge_color_differs_from_solid():
    """굵기 차이만으로는 실선과 점선이 구분되지 않는다."""
    from demo.ui.components.graph_section import DOTTED_COLOR, PLAIN_COLOR

    assert DOTTED_COLOR != PLAIN_COLOR

    dot = build_dot(NODES, SOLID, DOTTED)

    dotted_line = edge_lines(dot, "generate_ppt", "generate_word")[0]
    assert DOTTED_COLOR in dotted_line

    solid_line = edge_lines(dot, "load_cctv_platform", "analyze_congestion")[0]
    assert DOTTED_COLOR not in solid_line


def test_dotted_label_color_matches_the_line():
    from demo.ui.components.graph_section import DOTTED_COLOR

    line = build_dot(NODES, SOLID, DOTTED)
    dotted_line = edge_lines(line, "generate_ppt", "generate_word")[0]

    assert f'fontcolor="{DOTTED_COLOR}"' in dotted_line


def test_dotted_label_keeps_key_and_value():
    """value 만 남기면 무엇을 공유하는지 화면에서 알 수 없다."""
    dot = build_dot(NODES, SOLID, DOTTED)

    assert "output_kind: document" in dot


def test_node_label_is_the_korean_name_not_the_id():
    dot = build_dot(NODES, SOLID, DOTTED)

    assert "승강장 CCTV 불러오기" in dot
    assert 'label="load_cctv_platform"' not in dot


def test_layout_is_left_to_right():
    assert "rankdir=LR" in build_dot(NODES, SOLID, DOTTED)


def test_background_is_transparent():
    """흰 카드가 다크 테마 위에 얹히면 겉돈다."""
    assert 'bgcolor="transparent"' in build_dot(NODES, SOLID, DOTTED)


def test_node_text_and_border_have_an_explicit_color():
    """배경이 투명이면 기본 검정 글자는 다크 배경에서 읽히지 않는다."""
    from demo.ui.components.graph_section import PLAIN_COLOR

    dot = build_dot(NODES, SOLID, DOTTED)
    node_defaults = [line for line in dot.splitlines() if line.strip().startswith("node [")]

    assert node_defaults
    assert f'color="{PLAIN_COLOR}"' in node_defaults[0]
    assert f'fontcolor="{PLAIN_COLOR}"' in node_defaults[0]


def test_all_nodes_share_one_neutral_color():
    """종류별로 색을 나누면 하이라이트가 묻힌다. 색은 강조에만 쓴다."""
    from demo.ui.components.graph_section import HIGHLIGHT_COLOR

    dot = build_dot(NODES, SOLID, DOTTED)
    node_lines = [
        line for line in dot.splitlines() if re.match(r'\s*"\w+"\s*\[label=', line)
    ]

    assert len(node_lines) == len(NODES)
    for line in node_lines:
        assert "color=" not in line.split("label=")[1], line
        assert HIGHLIGHT_COLOR not in line, line


# ------------------------------------------------------------ 하이라이트
def test_without_highlight_nothing_is_bold():
    """결과가 없거나 NO_MATCH 면 굵은 선이 하나도 없어야 한다."""
    dot = build_dot(NODES, SOLID, DOTTED, highlight=None)

    assert "penwidth=3" not in dot


def test_highlighted_edge_has_an_arrow():
    dot = build_dot(NODES, SOLID, DOTTED, highlight=HIGHLIGHT)

    lines = edge_lines(dot, "load_cctv_platform", "analyze_congestion")
    bold = [line for line in lines if "penwidth=3" in line]
    assert bold, lines
    for line in bold:
        assert "dir=none" not in line, line


def test_highlighted_edges_are_numbered_in_order():
    """순번이 있어야 어느 쪽으로 흐르는지 읽힌다."""
    dot = build_dot(NODES, SOLID, DOTTED, highlight=HIGHLIGHT)

    first = edge_lines(dot, "load_cctv_platform", "analyze_congestion")
    second = edge_lines(dot, "analyze_congestion", "generate_word")

    assert any('label="1"' in line and "penwidth=3" in line for line in first), first
    assert any('label="2"' in line and "penwidth=3" in line for line in second), second


def test_unhighlighted_edge_stays_plain():
    """하이라이트에 없는 실선은 굵어지지 않는다."""
    dot = build_dot(
        NODES,
        SOLID,
        DOTTED,
        highlight=[("load_cctv_platform", "analyze_congestion")],
    )

    for line in edge_lines(dot, "analyze_congestion", "generate_word"):
        assert "penwidth=3" not in line, line
        assert "dir=none" in line, line


def node_line(dot: str, node_id: str) -> str:
    return next(
        line for line in dot.splitlines() if re.match(rf'\s*"{node_id}"\s*\[label=', line)
    )


def test_highlighted_path_nodes_get_a_thicker_border():
    """어느 노드를 거치는지 선만 눈으로 따라가게 두지 않는다."""
    from demo.ui.components.graph_section import HIGHLIGHT_COLOR

    dot = build_dot(NODES, SOLID, DOTTED, highlight=HIGHLIGHT)

    for node_id in ("load_cctv_platform", "analyze_congestion", "generate_word"):
        line = node_line(dot, node_id)
        assert "penwidth=2" in line, line
        assert HIGHLIGHT_COLOR in line, line


def test_node_off_the_path_keeps_the_plain_style():
    dot = build_dot(NODES, SOLID, DOTTED, highlight=HIGHLIGHT)

    line = node_line(dot, "generate_ppt")
    assert "penwidth=2" not in line, line


def test_without_highlight_no_node_is_emphasised():
    dot = build_dot(NODES, SOLID, DOTTED, highlight=None)

    assert "penwidth=2" not in dot


def test_single_node_path_is_emphasised_via_highlight_nodes():
    """1단 recipe 는 엣지가 0개다. 엣지에서 유도하면 아무것도 강조되지 않는다."""
    dot = build_dot(
        NODES, SOLID, DOTTED, highlight=[], highlight_nodes=["load_cctv_platform"]
    )

    assert "penwidth=2" in node_line(dot, "load_cctv_platform")
    assert "penwidth=2" not in node_line(dot, "analyze_congestion")
    assert "penwidth=3" not in dot, "엣지가 없으므로 굵은 선도 없어야 한다."


def test_explicit_highlight_nodes_win_over_the_edges():
    dot = build_dot(
        NODES, SOLID, DOTTED, highlight=HIGHLIGHT, highlight_nodes=["generate_ppt"]
    )

    assert "penwidth=2" in node_line(dot, "generate_ppt")
    assert "penwidth=2" not in node_line(dot, "load_cctv_platform")


def test_repeated_edge_gets_one_number_per_visit():
    """루프가 생겨 같은 엣지를 두 번 지나면 순번이 둘 다 나와야 한다.

    엣지 리스트를 집합으로 다뤘다면 여기서 하나로 뭉개진다.
    엣지는 한 번만 그리므로(레이아웃 고정) 번호를 이어 붙인다.
    """
    dot = build_dot(
        NODES,
        SOLID,
        DOTTED,
        highlight=[
            ("load_cctv_platform", "analyze_congestion"),
            ("analyze_congestion", "generate_word"),
            ("load_cctv_platform", "analyze_congestion"),
        ],
    )

    line = edge_lines(dot, "load_cctv_platform", "analyze_congestion")[0]
    assert 'xlabel="1, 3"' in line, line
    assert 'xlabel="2"' in edge_lines(dot, "analyze_congestion", "generate_word")[0]


# ------------------------------------------------------------ 문법
def test_output_is_a_digraph_block():
    dot = build_dot(NODES, SOLID, DOTTED, highlight=HIGHLIGHT)

    assert dot.strip().startswith("digraph")
    assert dot.strip().endswith("}")
    assert dot.count("{") == dot.count("}")


@pytest.mark.parametrize("highlight", [None, HIGHLIGHT])
def test_graphviz_accepts_the_output(highlight):
    """문법이 깨지면 화면에 아무것도 뜨지 않는다.

    프로덕션과 같은 경로(render_svg)로 검증한다. 예전에는 여기서 subprocess 를
    직접 불렀는데, 그러면 테스트가 프로덕션과 다른 코드를 검증하게 된다.
    """
    if not shutil.which("dot"):
        pytest.skip("graphviz 가 설치되어 있지 않다")

    svg = render_svg(build_dot(NODES, SOLID, DOTTED, highlight=highlight))

    assert svg.lstrip().startswith("<?xml"), svg[:200]
    assert "<svg" in svg


def test_graphviz_accepts_the_real_ontology():
    """실제 데이터로도 파싱되는지 본다. 고정 데이터만 쓰면 놓치는 게 있다."""
    from ontology.graph import (
        dotted_edges,
        highlight_edges,
        load_ontology,
        recipe_nodes,
        solid_edges,
    )

    if not shutil.which("dot"):
        pytest.skip("graphviz 가 설치되어 있지 않다")

    svg = render_svg(
        build_dot(
            load_ontology()["nodes"],
            solid_edges(),
            dotted_edges(),
            highlight=highlight_edges("recipe_013"),
            highlight_nodes=recipe_nodes("recipe_013"),
        )
    )

    assert "<svg" in svg
    assert "승강장 CCTV 불러오기" in svg, "한글 라벨이 SVG 에 실리지 않았다."
