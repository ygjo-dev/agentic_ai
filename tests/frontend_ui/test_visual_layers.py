"""시각 위계 검증.

선이 뒤로 물러나고 노드가 앞으로 나와야 한다. 지금까지는 노드 테두리와 실선이
같은 색이라 엣지만 옅게 할 수가 없었고, Graphviz 가 노드와 엣지를 섞어 내서
엣지 절반이 노드 위를 지나갔다.
"""

import re
import shutil

import pytest

from frontend import config
from frontend.components.graph_section import (
    MARK_DOTTED_PENWIDTH,
    MARK_SOLID_PENWIDTH,
    NODE_ATTRS,
    NODE_ATTRS_TOP,
    build_dot,
    stack_nodes_on_top,
)

NODES = {
    "a": {"name": "가 노드"},
    "b": {"name": "나 노드"},
    "c": {"name": "다 노드"},
}
SOLID = {("a", "b"): "X", ("b", "c"): "Y"}
DOTTED = {("a", "c"): ["k: v"]}


# ------------------------------------------------------------ 엣지 색 분리
def test_edge_color_lands_on_the_edge_defaults_line():
    dot = build_dot(NODES, SOLID, DOTTED, edge_color="#123456")

    edge_line = next(l for l in dot.splitlines() if l.strip().startswith("edge ["))
    assert '#123456' in edge_line


def test_edge_color_does_not_touch_the_node_line():
    """노드 테두리는 그대로 둬야 선이 뒤로 물러나는 원근이 생긴다."""
    dot = build_dot(NODES, SOLID, DOTTED, edge_color="#123456")

    node_line = next(l for l in dot.splitlines() if l.strip().startswith("node ["))
    assert "#123456" not in node_line


def test_dotted_color_changes_only_the_dashed_lines():
    dot = build_dot(NODES, SOLID, DOTTED, dotted_color="#654321")

    dashed = [l for l in dot.splitlines() if "dashed" in l]
    assert dashed and all("#654321" in l for l in dashed)

    edge_line = next(l for l in dot.splitlines() if l.strip().startswith("edge ["))
    assert "#654321" not in edge_line


def test_default_colours_are_the_old_constants():
    """기본값에서 출력이 안 바뀌어야 tests/graph_rendering 이 살아 있다."""
    plain = build_dot(NODES, SOLID, DOTTED)

    assert plain == build_dot(
        NODES, SOLID, DOTTED,
        edge_color=config.PLAIN_COLOR, dotted_color=config.DOTTED_COLOR,
    )


def test_top_is_fainter_than_bottom():
    """상단은 배경 지도, 하단이 답이다. 시선이 아래로 가야 한다."""
    def luminance(value):
        parts = [int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        channels = [
            c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in parts
        ]
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    assert luminance(config.EDGE_COLOR_TOP) < luminance(config.EDGE_COLOR)
    assert luminance(config.DOTTED_COLOR_TOP) < luminance(config.DOTTED_COLOR_BOTTOM)
    assert luminance(config.NODE_BORDER_TOP) < luminance(config.NODE_BORDER)


def test_edges_are_fainter_than_node_borders():
    """선이 노드보다 밝으면 선이 앞으로 나와 난잡해진다."""
    def luminance(value):
        parts = [int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        channels = [
            c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in parts
        ]
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    assert luminance(config.EDGE_COLOR) < luminance(config.NODE_BORDER)


# ------------------------------------------------------------ 노드 채우기
def test_node_attrs_carry_a_fill():
    """채우기가 없으면 순서를 바꿔도 선이 노드를 통과해 비친다."""
    joined = " ".join(NODE_ATTRS)

    assert "filled" in joined
    assert config.NODE_FILL in joined


def test_top_node_attrs_only_differ_in_the_border():
    assert config.NODE_BORDER_TOP in " ".join(NODE_ATTRS_TOP)
    assert config.NODE_FILL in " ".join(NODE_ATTRS_TOP)


def test_fill_never_lands_on_a_node_statement_line():
    """노드 줄에 color= 가 있으면 tests/graph_rendering 이 깨진다.

    fillcolor= 도 color= 를 품고 있어 반드시 기본 줄에만 있어야 한다.
    """
    dot = build_dot(NODES, SOLID, DOTTED, node_attrs=NODE_ATTRS)

    statements = [l for l in dot.splitlines() if re.match(r'\s*"\w+"\s*\[label=', l)]
    assert statements
    for line in statements:
        assert "color=" not in line.split("label=")[1], line


# ------------------------------------------------------------ 등록 강조 배분
def test_new_solid_is_thinner_than_a_selected_path():
    """등록 장면의 주인공은 노드가 어디에 붙었냐다. recipe 는 스탯이 말한다."""
    assert MARK_SOLID_PENWIDTH < 3


def test_new_dotted_is_thicker_than_a_plain_one():
    assert MARK_DOTTED_PENWIDTH > 2


def test_dotted_labels_never_appear_even_when_marked():
    dot = build_dot(
        NODES, SOLID, DOTTED,
        mark_dotted={("a", "c")}, dotted_labels=False,
    )

    assert "k: v" not in dot


# ------------------------------------------------------------ SVG 후처리
SVG = (
    '<?xml version="1.0"?>\n<svg width="10pt" height="10pt" viewBox="0 0 10 10">\n'
    '<g id="graph0" class="graph" transform="scale(1)">\n'
    "<title>ontology</title>\n"
    '<g id="node1" class="node">\n<title>a</title>\n<path d="M1"/>\n</g>\n'
    '<g id="edge1" class="edge">\n<title>a&#45;&gt;b</title>\n<path d="M2"/>\n</g>\n'
    '<g id="node2" class="node">\n<title>b</title>\n<path d="M3"/>\n</g>\n'
    '<g id="edge2" class="edge">\n<title>b&#45;&gt;c</title>\n<path d="M4"/>\n</g>\n'
    "</g>\n</svg>\n"
)


def element_order(svg: str) -> list[str]:
    return re.findall(r'<g id="(node\d+|edge\d+)"', svg)


def test_every_node_comes_after_every_edge():
    """SVG 는 나온 순서대로 그린다. 뒤에 오는 것이 위에 얹힌다."""
    order = element_order(stack_nodes_on_top(SVG))

    kinds = ["N" if o.startswith("node") else "E" for o in order]
    assert kinds == sorted(kinds, key=lambda k: k == "N")
    assert kinds[-1] == "N"


def test_input_really_was_interleaved():
    """판별력 확인 — 원본이 이미 정렬돼 있으면 위 테스트가 무의미하다."""
    kinds = ["N" if o.startswith("node") else "E" for o in element_order(SVG)]

    assert kinds != sorted(kinds, key=lambda k: k == "N")


def test_counts_are_preserved():
    out = stack_nodes_on_top(SVG)

    assert out.count('class="node"') == SVG.count('class="node"')
    assert out.count('class="edge"') == SVG.count('class="edge"')


def test_node_content_survives():
    out = stack_nodes_on_top(SVG)

    assert '<title>a</title>' in out and '<title>b</title>' in out
    assert 'd="M1"' in out and 'd="M3"' in out


def test_nodes_stay_inside_the_graph_group():
    out = stack_nodes_on_top(SVG)

    assert out.rstrip().endswith("</g>\n</svg>") or out.rstrip().endswith("</g></svg>")
    assert out.index('id="node1"') < out.rindex("</g>")


def test_svg_without_nodes_is_untouched():
    plain = '<svg><g id="graph0" class="graph"><title>x</title></g></svg>'

    assert stack_nodes_on_top(plain) == plain


def test_not_an_svg_is_untouched():
    assert stack_nodes_on_top("그냥 문자열") == "그냥 문자열"


# ------------------------------------------------------------ 실제 렌더
@pytest.mark.skipif(shutil.which("neato") is None, reason="graphviz 가 없다")
def test_real_render_puts_every_node_last():
    from frontend.components.graph_section import layout_positions, render_svg

    positions = layout_positions(build_dot(NODES, SOLID, DOTTED, spring=True))
    svg = render_svg(
        build_dot(NODES, SOLID, DOTTED, positions=positions, spring=True,
                  node_attrs=NODE_ATTRS),
        "neato", no_layout=True,
    )

    order = element_order(stack_nodes_on_top(svg))
    kinds = ["N" if o.startswith("node") else "E" for o in order]

    assert kinds.count("N") == len(NODES)
    assert kinds[-kinds.count("N"):] == ["N"] * kinds.count("N")
