"""대상 : demo/graph_svg/ — 레이아웃 고정

레이아웃 고정 검증. **실제 온톨로지로** 프로덕션과 같은 경로를 태운다.

결과가 올 때마다 노드가 움직이면 화면이 깜빡이고 어디를 보던 중이었는지
잃는다. 어떤 강조 조합에서도 노드 좌표가 같아야 한다.

과거 실측:
  하이라이트 없음 543x256 / recipe_013 547x242 / 후보2개 543x289 / 후보4개 543x293
원인은 두 가지였다.
  (1) 강조를 평행 엣지로 그려 조합마다 엣지 수가 달라졌다.
  (2) 순번을 label 로 붙여 Graphviz 가 라벨 공간을 확보했다.
지금은 (1) 기존 엣지의 색만 바꾸고 (2) 순번을 xlabel 로 붙여 해결했다.

여기에 더해 **좌표를 전부 고정하고 neato -n 으로 그린다.** 배치를 아예 계산하지
않으므로 좌표가 같다는 것이 구조적으로 보장된다. 예전에는 핀 없이 dot 으로 그려
"xlabel 은 노드를 안 민다" 는 성질에만 기대고 있었는데, 그건 그래프 모양에 따라
달라진다 — 온톨로지를 바꾸자 실제로 14pt 씩 밀렸다. 프로덕션은 그때도 핀을 쓰고
있었으므로 화면은 멀쩡했다. 검사가 프로덕션과 다른 경로를 보고 있었던 것이다.
"""

import re
import shutil

import pytest

from demo.graph_svg.dot import NODE_ATTRS, build_dot
from demo.graph_svg.graphviz import render_svg
from demo.graph_svg.layout_store import NEATO_ATTRS, NEATO_FRESH_ATTRS
from demo.graph_svg.graphviz import layout_positions
from demo.api.services.ontology_service import domain_graph
from ontology.graph import highlight_edges, recipe_nodes

pytestmark = pytest.mark.skipif(
    shutil.which("neato") is None, reason="graphviz 가 설치되어 있지 않다"
)


def pinned_positions():
    """실제 온톨로지의 좌표 한 벌. 저장소의 layout.json 은 건드리지 않는다."""
    return layout_positions(
        build_dot(
            *domain_graph(),
            spring=True,
            graph_attrs=NEATO_FRESH_ATTRS,
        )
    )


POSITIONS = pinned_positions() if shutil.which("neato") else {}


def layout(**kwargs):
    """SVG 에서 노드 중심 좌표와 캔버스 크기를 뽑는다. 프로덕션과 같은 경로다."""
    svg = render_svg(
        build_dot(
            *domain_graph(),
            positions=POSITIONS,
            spring=True,
            node_attrs=NODE_ATTRS,
            graph_attrs=NEATO_ATTRS,
            **kwargs,
        ),
        "neato",
        no_layout=True,
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

# 실재하는 recipe 만 쓴다. 없는 번호를 넣으면 경로가 빈 리스트가 되어 강조가
# 하나도 안 걸리고, 검사가 조용히 무력해진다(예전 COMBOS 에 그런 항목이 있었다).
CANDIDATES = ["recipe_002", "recipe_003", "recipe_005", "recipe_006"]

COMBOS = {
    "하이라이트 없음": {},
    "SELECT 4단(순번)": {"highlight": P("recipe_002"), "highlight_nodes": recipe_nodes("recipe_002")},
    "SELECT 노드만(엣지 0)": {"highlight_nodes": ["track_car_cctv_video"]},
    "CLARIFY 후보 2개": {"highlight_paths": [P(r) for r in CANDIDATES[:2]]},
    "CLARIFY 후보 4개": {"highlight_paths": [P(r) for r in CANDIDATES]},
}


def test_every_combo_actually_highlights_something():
    """COMBOS 가 무력하지 않은지 먼저 본다.

    없는 recipe 를 가리키면 경로가 비어 강조가 하나도 안 걸리고, 그러면
    "좌표가 안 움직인다" 는 단언이 아무것도 검증하지 못한다.
    """
    for name, kwargs in COMBOS.items():
        if name == "하이라이트 없음":
            continue
        paths = kwargs.get("highlight_paths") or [kwargs.get("highlight") or []]
        assert any(paths) or kwargs.get("highlight_nodes"), name


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
    dot = build_dot(*domain_graph(), highlight=P("recipe_002"))

    highlight_lines = [line for line in dot.splitlines() if "penwidth=3" in line]
    assert highlight_lines
    for line in highlight_lines:
        assert "label=" not in line.replace("xlabel=", ""), line


def test_highlight_adds_no_extra_edge():
    """평행 엣지를 추가하면 조합마다 엣지 수가 달라져 레이아웃이 흔들린다."""
    plain = build_dot(*domain_graph())
    lit = build_dot(*domain_graph(), highlight=P("recipe_002"))

    def edge_count(dot):
        return len([line for line in dot.splitlines() if "->" in line])

    assert edge_count(plain) == edge_count(lit)
