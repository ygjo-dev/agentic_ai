"""대상 : demo/graph_svg/dot.py · build.py — 상단은 관계 지도다

상단과 하단이 둘 다 실선과 점선을 그리면 같은 그림이 두 번 뜬다. 그러면 두
패널이 각각 무엇을 말하는지 구분되지 않는다. 이 파일이 고정하는 것은 하나다.

  **상단은 점선(관계)만 그린다. 실선(실행 순서)은 하단이 맡는다.**

그리고 그 대가로 배치가 흔들리지 않는지 — 전 노드가 핀이고 neato -n 이라
선을 빼도 좌표를 다시 계산하지 않는다는 성질에 기대고 있으므로, 그 성질이
깨지면 화면에서만 드러난다. 여기서 못을 박는다.
"""

import re
import shutil

import pytest

from demo.graph_svg.dot import (
    DOTTED_PENWIDTH,
    DOTTED_PENWIDTH_TOP,
    MARK_DOTTED_RATIO,
    NEW_COLOR,
    REVIEW_COLOR,
    build_dot,
)
from demo.graph_svg.graphviz import layout_positions, render_svg
from demo.graph_svg.layout_store import NEATO_FRESH_ATTRS

NODES = {
    "group_track": {"kind": "group", "name": "궤도"},
    "load_cctv_platform": {"name": "승강장 CCTV 불러오기"},
    "analyze_congestion": {"name": "승강장 혼잡도 분석"},
    "generate_word": {"name": "Word 생성"},
}
SOLID = {
    ("load_cctv_platform", "analyze_congestion"): "MediaData",
    ("analyze_congestion", "generate_word"): "AnalysisResult",
}
DOTTED = {("analyze_congestion", "group_track"): ["about"]}


def solid_lines(dot: str) -> list[str]:
    """실선 문장. 점선은 style=dashed 로 갈린다."""
    return [
        line.strip()
        for line in dot.splitlines()
        if "->" in line and "dashed" not in line
    ]


def dotted_lines(dot: str) -> list[str]:
    return [line.strip() for line in dot.splitlines() if "dashed" in line]


# ================================================================ 실선이 없다
def test_the_relation_map_draws_no_solid_edge():
    """상단에 실선이 있으면 하단과 같은 그림이 된다.

    빼는 것이지 숨기는 것이 아니다 — DOT 에 문장 자체가 없어야 한다.
    """
    dot = build_dot(NODES, SOLID, DOTTED, draw_solid=False)

    assert solid_lines(dot) == []
    assert dotted_lines(dot), "점선까지 사라지면 상단이 빈 화면이 된다"
    for node_id in NODES:
        assert f'"{node_id}" [label=' in dot, node_id


def test_solid_edges_are_drawn_by_default():
    """기본값은 지금까지의 동작이다. 하단이 이 경로로 그려진다."""
    assert len(solid_lines(build_dot(NODES, SOLID, DOTTED))) == len(SOLID)


def test_a_review_edge_needs_a_solid_canvas():
    """검토 표시는 실선 문법이다. 실선을 안 그리는 화면에는 갈 곳이 없다.

    상단에 남으면 "관계만 그린다" 는 규칙이 검토 표시 하나로 뚫린다.
    """
    edge = ("generate_word", "load_cctv_platform")  # SOLID 에 없다 — 선을 새로 긋는다

    with_solid = build_dot(NODES, SOLID, DOTTED, review_edges=[edge])
    without = build_dot(NODES, SOLID, DOTTED, review_edges=[edge], draw_solid=False)

    assert REVIEW_COLOR in with_solid, "이 검사의 전제가 깨졌다"
    assert REVIEW_COLOR not in without
    assert solid_lines(without) == []


# ================================================================ 점선 굵기
def test_the_dotted_width_follows_the_constant():
    """굵기는 화면을 보고 사람이 낮출 값이다. 상수 하나만 고치면 되어야 한다."""
    top = build_dot(NODES, SOLID, DOTTED, draw_solid=False,
                    dotted_penwidth=DOTTED_PENWIDTH_TOP)

    assert all(f"penwidth={DOTTED_PENWIDTH_TOP}" in line for line in dotted_lines(top))
    assert DOTTED_PENWIDTH_TOP > DOTTED_PENWIDTH, "상단 점선은 하단보다 굵다"


def test_omitting_the_width_keeps_the_old_one():
    assert all(
        f"penwidth={DOTTED_PENWIDTH}" in line
        for line in dotted_lines(build_dot(NODES, SOLID, DOTTED))
    )


def test_a_new_dotted_edge_never_gets_thinner_than_a_plain_one():
    """등록 강조를 절댓값으로 박으면 상단에서 새 점선이 배경보다 가늘어진다.

    새로 생긴 것이 배경보다 옅으면 등록 장면이 안 읽힌다. 배수로 두는 이유다.
    """
    pair = next(iter(DOTTED))
    top = build_dot(NODES, SOLID, DOTTED, draw_solid=False,
                    dotted_penwidth=DOTTED_PENWIDTH_TOP, mark_dotted=[pair])

    line = dotted_lines(top)[0]
    width = float(re.search(r"penwidth=([\d.]+)", line).group(1))

    assert NEW_COLOR in line
    assert width > DOTTED_PENWIDTH_TOP, width
    assert MARK_DOTTED_RATIO > 1


# ================================================================ 배치 (핵심)
@pytest.mark.skipif(shutil.which("neato") is None, reason="graphviz 가 없다")
def test_removing_the_solid_edges_never_moves_a_node():
    """★ 전 노드가 핀이고 neato -n 이라 선을 빼도 배치를 다시 계산하지 않는다.

    이 성질이 없으면 상단에서 실선을 걷어내는 순간 지도가 통째로 재배치되고,
    위아래가 서로 다른 자리를 가리키게 된다. 캔버스까지 함께 본다 — 좌표가
    같아도 캔버스가 달라지면 축소 배율이 갈려 위아래 크기가 어긋난다.
    """
    positions = layout_positions(
        build_dot(NODES, SOLID, DOTTED, spring=True, graph_attrs=NEATO_FRESH_ATTRS)
    )

    def drawn(**kwargs):
        svg = render_svg(
            build_dot(NODES, SOLID, DOTTED, positions=positions, spring=True, **kwargs),
            "neato",
            no_layout=True,
        )
        coords = {}
        for block in re.findall(r'<g id="node\d+" class="node">(.*?)</g>', svg, re.S):
            title = re.search(r"<title>([a-z_]+)</title>", block)
            pos = re.search(r'text-anchor="middle" x="([-\d.]+)" y="([-\d.]+)"', block)
            if title and pos:
                coords[title.group(1)] = (float(pos.group(1)), float(pos.group(2)))
        return coords, re.search(r'viewBox="([^"]+)"', svg).group(1)

    with_solid, box = drawn()
    assert len(with_solid) == len(NODES), "노드 좌표를 못 읽었다 — 검사가 무력하다"

    without_solid, box_without = drawn(draw_solid=False)

    assert without_solid == with_solid
    assert box_without == box


@pytest.mark.skipif(shutil.which("neato") is None, reason="graphviz 가 없다")
def test_a_thicker_dotted_line_never_moves_a_node():
    """굵기는 색과 같다 — 그리기지 배치가 아니다."""
    positions = layout_positions(
        build_dot(NODES, SOLID, DOTTED, spring=True, graph_attrs=NEATO_FRESH_ATTRS)
    )

    def coords(width):
        svg = render_svg(
            build_dot(NODES, SOLID, DOTTED, positions=positions, spring=True,
                      draw_solid=False, dotted_penwidth=width),
            "neato",
            no_layout=True,
        )
        return re.findall(r'text-anchor="middle" x="([-\d.]+)" y="([-\d.]+)"', svg)

    assert coords(DOTTED_PENWIDTH_TOP) == coords(DOTTED_PENWIDTH)
