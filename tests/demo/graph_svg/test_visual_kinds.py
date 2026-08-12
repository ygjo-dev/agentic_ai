"""대상 : demo/graph_svg/dot.py — 노드 종류와 선 종류가 눈으로 갈린다

시연 화면에서 세 가지가 한눈에 구분돼야 한다.

  대상(group) 노드 vs 기능 노드 — 실행할 수 있는 것과 개념은 다른 것이다
  점선 vs 실선                 — 관계와 실행 순서는 다른 것이다
  강조 경로 vs 나머지           — 강조가 주인공이고 점선은 배경이다

**시각을 바꿔도 배치는 안 흔들려야 한다.** 좌표를 전부 고정하고 neato -n 으로
그리므로 구조적으로 보장되지만, 그 보장이 깨지면 화면에서만 드러난다.
"""

import re
import shutil

import pytest

from demo.graph_svg.dot import (
    DOTTED_COLOR_BOTTOM,
    DOTTED_PENWIDTH,
    EDGE_COLOR,
    GROUP_ATTRS,
    GROUP_ATTRS_TOP,
    GROUP_COLOR,
    HIGHLIGHT_COLOR,
    NODE_ATTRS,
    build_dot,
)
from demo.graph_svg.graphviz import layout_positions, render_svg
from demo.graph_svg.layout_store import NEATO_ATTRS, NEATO_FRESH_ATTRS

NODES = {
    "group_track": {"kind": "group", "name": "궤도"},
    "load_track_image": {
        "kind": "function", "name": "궤도 검측 이미지 불러오기",
        "inputs": [], "outputs": ["ImageData"],
    },
    "detect_track_crack": {
        "kind": "function", "name": "궤도 균열 검출",
        "inputs": ["ImageData"], "outputs": ["AnalysisResult"],
    },
    "generate_word": {
        "kind": "function", "name": "Word 보고서 생성",
        "inputs": ["AnalysisResult"], "outputs": ["DocumentData"],
    },
}
SOLID = {
    ("load_track_image", "detect_track_crack"): "ImageData",
    ("detect_track_crack", "generate_word"): "AnalysisResult",
}
DOTTED = {("detect_track_crack", "group_track"): ["about"]}
PATH = [("load_track_image", "detect_track_crack"),
        ("detect_track_crack", "generate_word")]


def node_line(dot: str, node_id: str) -> str:
    return next(l for l in dot.splitlines() if f'"{node_id}" [label=' in l)


def dotted_line(dot: str) -> str:
    return next(l for l in dot.splitlines() if "dashed" in l)


def solid_line(dot: str) -> str:
    return next(
        l for l in dot.splitlines()
        if "->" in l and "dashed" not in l and "dir=none" in l
    )


# ================================================================ group 노드
def test_a_group_node_is_drawn_differently_from_a_function():
    """대상 노드가 기능 노드와 똑같이 생기면 개념과 실행이 구분되지 않는다.

    도형(ellipse)과 색 둘 다로 가른다. 색만으로는 색약인 사람이 못 가르고,
    프로젝터에서도 색이 뭉개진다.
    """
    dot = build_dot(NODES, SOLID, DOTTED, group_attrs=GROUP_ATTRS)

    group = node_line(dot, "group_track")
    assert "shape=ellipse" in group
    assert GROUP_COLOR in group

    for function_id in ("load_track_image", "detect_track_crack", "generate_word"):
        line = node_line(dot, function_id)
        assert "shape=ellipse" not in line, function_id
        assert GROUP_COLOR not in line, function_id


def test_without_group_attrs_every_node_looks_the_same():
    """새 인자는 기본값에서 출력을 한 글자도 바꾸지 않는다.

    tests/graph_svg 의 여러 검사가 기존 출력 문자열에 의존한다. 새 인자를
    더할 때마다 그것들이 깨지면 리팩터링 안전망이 사라진다.
    """
    assert build_dot(NODES, SOLID, DOTTED) == build_dot(
        NODES, SOLID, DOTTED, group_attrs=()
    )
    assert "shape=ellipse" not in build_dot(NODES, SOLID, DOTTED)


def test_a_marked_group_still_shows_it_is_new():
    """등록 강조가 group 스타일보다 뒤에 온다.

    Graphviz 는 같은 속성이 두 번 나오면 나중 것을 쓴다(실측). 순서가 뒤집히면
    새로 생긴 것이 group 색에 묻혀 등록 장면이 안 읽힌다.
    """
    dot = build_dot(
        NODES, SOLID, DOTTED, group_attrs=GROUP_ATTRS, mark_nodes={"group_track"}
    )

    line = node_line(dot, "group_track")
    assert "shape=ellipse" in line, "도형은 그대로여야 한다"
    assert line.index(GROUP_COLOR) < line.rindex("color="), "강조가 뒤에 와야 이긴다"


# ================================================================ 점선과 실선
def test_a_dotted_edge_is_brighter_and_thicker_than_a_solid_one():
    """관계와 실행 순서는 다른 것이다. 색상만으로는 다크 배경에서 안 갈린다.

    예전 점선(#5B55A0, 배경 대비 2.93)은 실선(2.41)과 거의 같은 밝기였다.
    밝기와 굵기를 함께 올려야 구분된다. 파선 간격은 못 바꾼다 — Graphviz 가
    stroke-dasharray="5,2" 를 고정으로 내보내고 penwidth 를 올려도 그대로다.
    """
    dot = build_dot(NODES, SOLID, DOTTED, dotted_color=DOTTED_COLOR_BOTTOM,
                    edge_color=EDGE_COLOR)

    dashed, plain = dotted_line(dot), solid_line(dot)

    assert DOTTED_COLOR_BOTTOM in dashed
    assert DOTTED_COLOR_BOTTOM != EDGE_COLOR
    assert f"penwidth={DOTTED_PENWIDTH}" in dashed
    assert "penwidth" not in plain, "실선은 기본 굵기다 — 점선이 더 굵어야 갈린다"
    assert DOTTED_PENWIDTH > 1


def test_the_dotted_line_never_outshines_the_chosen_path():
    """점선은 배경 정보이고 선택된 실행 경로가 주인공이다.

    이 위계가 뒤집히면 화면에서 관계가 답보다 먼저 눈에 들어온다.
    배경(#0E1117) 대비비로 잰다 — 실선 < 점선 < 강조 순이어야 한다.
    """
    def contrast(hex_color, background="#0E1117"):
        def luminance(value):
            channels = (int(value[i:i + 2], 16) / 255 for i in (1, 3, 5))
            adjusted = [
                c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                for c in channels
            ]
            return sum(w * c for w, c in zip((0.2126, 0.7152, 0.0722), adjusted))

        first, second = luminance(hex_color), luminance(background)
        return (max(first, second) + 0.05) / (min(first, second) + 0.05)

    solid, dashed, chosen = (
        contrast(EDGE_COLOR), contrast(DOTTED_COLOR_BOTTOM), contrast(HIGHLIGHT_COLOR)
    )

    assert solid < dashed < chosen, (solid, dashed, chosen)
    assert dashed > solid * 2, f"점선이 실선보다 확실히 밝아야 한다: {dashed:.2f} vs {solid:.2f}"


# ================================================================ 배치 불변
@pytest.mark.skipif(shutil.which("neato") is None, reason="graphviz 가 없다")
def test_the_visual_style_never_moves_a_node():
    """도형과 색을 바꿔도 좌표와 캔버스가 그대로여야 한다.

    노드를 눌러 좁히거나 등록 강조가 켜질 때 지도가 흔들리면 보던 자리를 잃는다.
    좌표를 전부 고정하고 neato -n 으로 그려 구조적으로 보장하지만, 그 보장이
    깨지면 화면에서만 드러나므로 여기서 못을 박는다.
    """
    positions = layout_positions(
        build_dot(NODES, SOLID, DOTTED, spring=True, graph_attrs=NEATO_FRESH_ATTRS)
    )

    def drawn(**kwargs):
        svg = render_svg(
            build_dot(NODES, SOLID, DOTTED, positions=positions, spring=True,
                      node_attrs=NODE_ATTRS, graph_attrs=NEATO_ATTRS, **kwargs),
            "neato", no_layout=True,
        )
        coords = {}
        for block in re.findall(r'<g id="node\d+" class="node">(.*?)</g>', svg, re.S):
            title = re.search(r"<title>([a-z_]+)</title>", block)
            pos = re.search(r'text-anchor="middle" x="([-\d.]+)" y="([-\d.]+)"', block)
            if title and pos:
                coords[title.group(1)] = (
                    round(float(pos.group(1)), 1), round(float(pos.group(2)), 1)
                )
        size = re.search(r'viewBox="([^"]+)"', svg)
        return coords, size.group(1)

    # 스타일은 고정하고 강조만 바꾼다. 프로덕션이 그렇게 부른다 — 한 화면 안의
    # 변형들은 전부 같은 group_attrs 로 그려지고, 달라지는 것은 강조뿐이다.
    base_coords, base_box = drawn(group_attrs=GROUP_ATTRS)
    assert base_coords, "노드 좌표를 하나도 못 읽었다 — 검사가 무력하다"

    for name, kwargs in (
        ("경로 강조", {"highlight": PATH}),
        ("노드 강조", {"highlight_nodes": ["detect_track_crack"]}),
        ("등록 강조", {"mark_nodes": {"group_track"}}),
        ("점선 강조", {"mark_dotted": [("detect_track_crack", "group_track")]}),
    ):
        coords, box = drawn(group_attrs=GROUP_ATTRS, **kwargs)
        assert coords == base_coords, f"{name} 에서 노드가 움직였다"
        assert box == base_box, f"{name} 에서 캔버스가 달라졌다"


@pytest.mark.skipif(shutil.which("neato") is None, reason="graphviz 가 없다")
def test_the_top_and_bottom_styles_have_the_same_geometry():
    """상단과 하단은 색만 다르고 크기는 같아야 한다.

    둘은 한 화면에 함께 뜨고 같은 좌표 파일을 쓴다. 도형이나 굵기가 갈리면
    노드 크기가 달라져 위아래가 미묘하게 어긋나 보인다.

    실측으로 알아낸 것 : ellipse 는 box 보다 크다. group 스타일을 켜고 끄면
    캔버스가 커지면서 모든 노드가 통째로 5pt 씩 밀린다(화면에는 평행이동이라
    안 보이지만, 위아래가 서로 다른 도형을 쓰면 진짜로 어긋난다).
    """
    geometry = lambda attrs: [  # noqa: E731 — 색만 지운 속성 목록
        attr for attr in attrs if not attr.startswith(("color=", "fontcolor="))
    ]

    assert geometry(GROUP_ATTRS) == geometry(GROUP_ATTRS_TOP)
    assert GROUP_ATTRS != GROUP_ATTRS_TOP, "색은 달라야 한다 — 상단이 한 단계 옅다"
