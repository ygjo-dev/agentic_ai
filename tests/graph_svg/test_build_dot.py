"""대상 : demo/api/graph_svg/dot.py — build_dot()

build_dot() 검증. 계산 결과를 Graphviz DOT 문자열로 옮긴다.
"""

import re
import shutil

import pytest

from demo.api.graph_svg.dot import build_dot
from demo.api.graph_svg.graphviz import render_svg

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
def test_dotted_edge_does_not_use_constraint_false():
    """constraint=false 는 브라우저 Graphviz(WASM)에서 레이아웃이 끝나지 않는다.

    네이티브 dot 은 즉시 끝내므로 subprocess 검증으로는 잡히지 않았고,
    화면만 비었다.
    """
    dot = build_dot(NODES, SOLID, DOTTED)

    assert "constraint=false" not in dot


# ------------------------------------------------------------ 하이라이트
def test_highlighted_edges_are_numbered_in_order():
    """순번이 있어야 어느 쪽으로 흐르는지 읽힌다."""
    dot = build_dot(NODES, SOLID, DOTTED, highlight=HIGHLIGHT)

    first = edge_lines(dot, "load_cctv_platform", "analyze_congestion")
    second = edge_lines(dot, "analyze_congestion", "generate_word")

    assert any('label="1"' in line and "penwidth=3" in line for line in first), first
    assert any('label="2"' in line and "penwidth=3" in line for line in second), second


def node_line(dot: str, node_id: str) -> str:
    return next(
        line for line in dot.splitlines() if re.match(rf'\s*"{node_id}"\s*\[label=', line)
    )


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
