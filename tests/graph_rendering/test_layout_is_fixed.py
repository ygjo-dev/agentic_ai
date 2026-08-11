"""레이아웃 고정 검증.

결과가 올 때마다 노드가 움직이면 화면이 깜빡이고 어디를 보던 중이었는지
잃는다. 어떤 강조 조합에서도 노드 좌표가 같아야 한다.

과거 실측:
  하이라이트 없음 543x256 / recipe_013 547x242 / 후보2개 543x289 / 후보4개 543x293
원인은 두 가지였다.
  (1) 강조를 평행 엣지로 그려 조합마다 엣지 수가 달라졌다.
  (2) 순번을 label 로 붙여 Graphviz 가 라벨 공간을 확보했다.
지금은 (1) 기존 엣지의 색만 바꾸고 (2) 순번을 xlabel 로 붙여 해결했다.
"""

import re
import shutil

import pytest

from demo.api.graph_svg.dot import build_dot
from demo.api.graph_svg.graphviz import render_svg
from ontology.graph import (
    dotted_edges,
    highlight_edges,
    load_ontology,
    recipe_nodes,
    solid_edges,
)

pytestmark = pytest.mark.skipif(
    shutil.which("dot") is None, reason="graphviz 가 설치되어 있지 않다"
)


def layout(**kwargs):
    """SVG 에서 노드 중심 좌표와 캔버스 크기를 뽑는다."""
    svg = render_svg(
        build_dot(
            load_ontology()["nodes"],
            solid_edges(),
            dotted_edges(),
            **kwargs,
        )
    )

    coords = {}
    for block in re.findall(r'<g id="node\d+" class="node">(.*?)</g>', svg, re.S):
        title = re.search(r"<title>([a-z_]+)</title>", block)
        pos = re.search(r'text-anchor="middle" x="([-\d.]+)" y="([-\d.]+)"', block)
        if title and pos:
            coords[title.group(1)] = (round(float(pos.group(1)), 1), round(float(pos.group(2)), 1))

    size = re.search(r'<svg width="(\d+)pt" height="(\d+)pt"', svg)
    return coords, (int(size.group(1)), int(size.group(2)))


P = highlight_edges

COMBOS = {
    "하이라이트 없음": {},
    "SELECT 3단(순번)": {"highlight": P("recipe_013"), "highlight_nodes": recipe_nodes("recipe_013")},
    "SELECT 1단(엣지 0)": {"highlight_nodes": recipe_nodes("recipe_001")},
    "CLARIFY 후보 2개": {"highlight_paths": [P("recipe_023"), P("recipe_027")]},
    "CLARIFY 후보 4개": {
        "highlight_paths": [P(r) for r in ("recipe_015", "recipe_019", "recipe_023", "recipe_027")]
    },
}


@pytest.fixture(scope="module")
def baseline():
    return layout()


@pytest.mark.parametrize("name", list(COMBOS))
def test_node_coordinates_never_move(baseline, name):
    base_coords, _ = baseline
    coords, _ = layout(**COMBOS[name])

    assert coords == base_coords, f"{name} 에서 노드가 움직였다."


@pytest.mark.parametrize("name", list(COMBOS))
def test_canvas_size_never_changes(baseline, name):
    _, base_size = baseline
    _, size = layout(**COMBOS[name])

    assert size == base_size, f"{name} 에서 캔버스 크기가 달라졌다."


def test_order_uses_xlabel_not_label():
    """label 을 쓰면 Graphviz 가 공간을 확보해 노드가 밀린다."""
    dot = build_dot(
        load_ontology()["nodes"],
        solid_edges(),
        dotted_edges(),
        highlight=P("recipe_013"),
    )

    highlight_lines = [line for line in dot.splitlines() if "penwidth=3" in line]
    assert highlight_lines
    for line in highlight_lines:
        assert "label=" not in line.replace("xlabel=", ""), line


def test_highlight_adds_no_extra_edge():
    """평행 엣지를 추가하면 조합마다 엣지 수가 달라져 레이아웃이 흔들린다."""
    plain = build_dot(load_ontology()["nodes"], solid_edges(), dotted_edges())
    lit = build_dot(
        load_ontology()["nodes"],
        solid_edges(),
        dotted_edges(),
        highlight=P("recipe_013"),
    )

    def edge_count(dot):
        return len([line for line in dot.splitlines() if "->" in line])

    assert edge_count(plain) == edge_count(lit)
