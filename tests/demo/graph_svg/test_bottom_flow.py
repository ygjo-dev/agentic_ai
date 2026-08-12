"""대상 : demo/graph_svg/dot.py · build.py — 하단은 실행 경로다

상단이 "무엇이 무엇과 관련되는가" 라면 하단은 **"무엇 다음에 무엇이 오는가"** 다.
그 차이를 화면에서 만드는 것은 세 가지다.

  화살표   켜진 길에만 붙는다. 배경 실선은 방향이 없다
  순번     경로가 하나로 확정될 때만. 여럿이면 겹쳐서 못 읽는다
  색       teal 해석 결과 · 분홍 자동 승격 · amber 승인 대기

배경 실선은 그대로 둔다 — 강조 안 된 경로도 보여야 지도 역할을 한다.
그리고 **평행 엣지를 추가하지 않는다.** 엣지 수가 조합마다 달라지면 레이아웃이
흔들린다(검증된 제약).
"""

import re
import shutil

import pytest

from demo.graph_svg.build import chain_edges, mark_from_registration
from demo.graph_svg.dot import (
    HIGHLIGHT_COLOR,
    NEW_COLOR,
    ORDER_FONTSIZE,
    PATH_ARROWSIZE,
    PATH_PENWIDTH,
    REVIEW_COLOR,
    build_dot,
)
from demo.graph_svg.graphviz import layout_positions, render_svg
from demo.graph_svg.layout_store import NEATO_FRESH_ATTRS

NODES = {
    "load_cctv_platform": {"name": "승강장 CCTV 불러오기"},
    "analyze_congestion": {"name": "승강장 혼잡도 분석"},
    "generate_word": {"name": "Word 생성"},
    "generate_ppt": {"name": "PPT 생성"},
}
SOLID = {
    ("load_cctv_platform", "analyze_congestion"): "MediaData",
    ("analyze_congestion", "generate_word"): "AnalysisResult",
    ("analyze_congestion", "generate_ppt"): "AnalysisResult",
}
DOTTED = {("generate_ppt", "generate_word"): ["output_kind: document"]}
PATH = [
    ("load_cctv_platform", "analyze_congestion"),
    ("analyze_congestion", "generate_word"),
]
OTHER = [
    ("load_cctv_platform", "analyze_congestion"),
    ("analyze_congestion", "generate_ppt"),
]


def edge_line(dot: str, frm: str, to: str) -> str:
    lines = [
        line.strip()
        for line in dot.splitlines()
        if re.search(rf'"{frm}"\s*->\s*"{to}"', line)
    ]
    assert len(lines) == 1, f"평행 엣지가 생겼다 — 레이아웃이 흔들린다: {lines}"
    return lines[0]


# ================================================================ 화살표
def test_the_chosen_path_gets_arrows():
    """방향이 보여야 "무엇 다음에 무엇" 이 읽힌다.

    평행 엣지를 더하지 않는다 — 이미 있는 엣지의 속성만 바꾼다(edge_line 이 본다).
    """
    dot = build_dot(NODES, SOLID, DOTTED, highlight=PATH)

    for frm, to in PATH:
        line = edge_line(dot, frm, to)
        assert "dir=forward" in line, line
        assert f"arrowsize={PATH_ARROWSIZE}" in line, line
        assert "dir=none" not in line, line


def test_the_background_solid_edges_have_no_arrow():
    """배경 실선까지 화살표가 붙으면 화살표가 아무것도 말하지 않는다."""
    dot = build_dot(NODES, SOLID, DOTTED, highlight=PATH)

    background = edge_line(dot, "analyze_congestion", "generate_ppt")

    assert "dir=none" in background
    assert "dir=forward" not in background
    assert "arrowsize" not in background


def test_registered_and_pending_paths_get_arrows_too():
    """셋 다 실행 경로다. 화살표가 없으면 등록 결과가 배경으로 읽힌다."""
    dot = build_dot(
        NODES, SOLID, DOTTED,
        mark_edges=[("load_cctv_platform", "analyze_congestion")],
        review_edges=[("analyze_congestion", "generate_ppt")],
    )

    for frm, to in (
        ("load_cctv_platform", "analyze_congestion"),
        ("analyze_congestion", "generate_ppt"),
    ):
        assert "dir=forward" in edge_line(dot, frm, to), (frm, to)


def test_arrow_size_follows_the_constant():
    """기본 화살표는 축소하면 점처럼 보인다. 상수 하나로 조절되어야 한다."""
    assert PATH_ARROWSIZE > 1
    assert f"arrowsize={PATH_ARROWSIZE}" in build_dot(
        NODES, SOLID, DOTTED, highlight=PATH
    )


# ================================================================ 순번 크기
def test_the_order_label_size_follows_the_constant():
    """순번은 1639pt 캔버스를 화면 폭에 맞춰 줄인 뒤에도 읽혀야 한다."""
    dot = build_dot(NODES, SOLID, DOTTED, highlight=PATH)

    line = edge_line(dot, *PATH[0])

    assert 'xlabel="1"' in line
    assert f"fontsize={ORDER_FONTSIZE}" in line
    assert ORDER_FONTSIZE > 10, "엣지 기본 크기(10)보다 확실히 커야 한다"


def test_several_paths_get_no_order_label_at_all():
    """경로가 여럿이면 순번이 겹쳐 못 읽는다. len(paths) == 1 규칙 그대로다."""
    dot = build_dot(NODES, SOLID, DOTTED, highlight_paths=[PATH, OTHER])

    assert "xlabel" not in dot
    assert f"fontsize={ORDER_FONTSIZE}" not in dot
    # 화살표는 붙는다 — 방향은 경로가 여럿이어도 겹치지 않는다.
    assert "dir=forward" in edge_line(dot, *PATH[0])


# ================================================================ 등록의 두 색
def test_accepted_and_pending_paths_are_told_apart_by_colour():
    """자동 승격은 이미 답이고 승인 대기는 아직 묻고 있는 것이다.

    색이 같으면 사람이 무엇을 승인해야 하는지 화면에서 알 수 없다.
    """
    dot = build_dot(
        NODES, SOLID, DOTTED,
        mark_edges=[("load_cctv_platform", "analyze_congestion")],
        review_edges=[("analyze_congestion", "generate_ppt")],
    )

    accepted = edge_line(dot, "load_cctv_platform", "analyze_congestion")
    pending = edge_line(dot, "analyze_congestion", "generate_ppt")

    assert NEW_COLOR in accepted and REVIEW_COLOR not in accepted
    assert REVIEW_COLOR in pending and NEW_COLOR not in pending
    assert NEW_COLOR != REVIEW_COLOR, "이 검사의 전제가 깨졌다"


def test_every_lit_path_is_thicker_than_the_background():
    """굵기가 배경(속성 없음 = 1)과 안 갈리면 등록해도 화면이 안 변한다."""
    dot = build_dot(
        NODES, SOLID, DOTTED,
        highlight=[("analyze_congestion", "generate_word")],
        mark_edges=[("load_cctv_platform", "analyze_congestion")],
        review_edges=[("analyze_congestion", "generate_ppt")],
    )

    for frm, to, color in (
        ("analyze_congestion", "generate_word", HIGHLIGHT_COLOR),
        ("load_cctv_platform", "analyze_congestion", NEW_COLOR),
        ("analyze_congestion", "generate_ppt", REVIEW_COLOR),
    ):
        line = edge_line(dot, frm, to)
        assert color in line
        assert f"penwidth={PATH_PENWIDTH}" in line, line
    assert PATH_PENWIDTH > 1


# ================================================================ 어댑터
def test_a_registration_carries_both_chains_as_edges():
    """/nodes 응답의 사슬을 엣지 목록으로 옮긴다.

    new_solid_edges 만으로는 경로가 끊겨 보인다 — 이미 있던 연결을 지나는
    경로가 대부분이고 그것들은 차집합에 안 잡힌다.
    """
    mark = mark_from_registration({
        "node_id": "analyze_congestion",
        "new_solid_edges": [{"from": "load_cctv_platform", "to": "analyze_congestion"}],
        "new_dotted_edges": [],
        "accepted": {
            "recipe_ids": ["recipe_900"],
            "chains": [["load_cctv_platform", "analyze_congestion", "generate_word"]],
        },
        "pending": [{
            "chain": ["load_cctv_platform", "analyze_congestion", "generate_ppt"],
            "steps": [],
        }],
    })

    assert ("analyze_congestion", "generate_word") in mark["accepted"]
    assert ("analyze_congestion", "generate_ppt") in mark["review"]
    assert not set(mark["accepted"]) & set(mark["review"]) - {
        ("load_cctv_platform", "analyze_congestion")
    }


def test_reducing_twice_gives_the_same_thing():
    """UI 가 응답을 통째로 넘겨도, 서버가 두 번 줄여도 같은 값이어야 한다."""
    raw = {
        "node_id": "analyze_congestion",
        "new_solid_edges": [], "new_dotted_edges": [],
        "accepted": {"chains": [["load_cctv_platform", "analyze_congestion"]]},
        "pending": [{"chain": ["analyze_congestion", "generate_ppt"]}],
    }
    once = mark_from_registration(raw)

    assert mark_from_registration(once) == once
    assert once["accepted"] and once["review"]


def test_chain_edges_folds_duplicates():
    """두 경로가 앞부분을 공유하면 같은 엣지가 두 번 나온다."""
    edges = chain_edges([["a", "b", "c"], ["a", "b", "d"]])

    assert edges == [("a", "b"), ("b", "c"), ("b", "d")]


# ================================================================ 배치 불변
@pytest.mark.skipif(shutil.which("neato") is None, reason="graphviz 가 없다")
def test_arrows_and_bigger_numbers_never_move_a_node():
    """화살표와 순번은 그리기지 배치가 아니다.

    xlabel 은 레이아웃에 관여하지 않는다(label 과 달리). 캔버스는 커질 수 있다 —
    글자가 그림 밖으로 나가면 bbox 가 따라 넓어진다. 그것은 재서 보고한다.
    """
    positions = layout_positions(
        build_dot(NODES, SOLID, DOTTED, spring=True, graph_attrs=NEATO_FRESH_ATTRS)
    )

    def coords(**kwargs):
        svg = render_svg(
            build_dot(NODES, SOLID, DOTTED, positions=positions, spring=True, **kwargs),
            "neato",
            no_layout=True,
        )
        found = {}
        for block in re.findall(r'<g id="node\d+" class="node">(.*?)</g>', svg, re.S):
            title = re.search(r"<title>([a-z_]+)</title>", block)
            pos = re.search(r'text-anchor="middle" x="([-\d.]+)" y="([-\d.]+)"', block)
            if title and pos:
                found[title.group(1)] = (float(pos.group(1)), float(pos.group(2)))
        return found

    base = coords()
    assert len(base) == len(NODES), "노드 좌표를 못 읽었다 — 검사가 무력하다"
    assert coords(highlight=PATH) == base
    assert coords(
        mark_edges=[PATH[0]], review_edges=[("analyze_congestion", "generate_ppt")]
    ) == base


@pytest.mark.skipif(shutil.which("neato") is None, reason="graphviz 가 없다")
def test_the_order_numbers_survive_the_bigger_font():
    """크기를 키우다 문법이 깨지면 순번이 통째로 사라진다."""
    positions = layout_positions(
        build_dot(NODES, SOLID, DOTTED, spring=True, graph_attrs=NEATO_FRESH_ATTRS)
    )

    svg = render_svg(
        build_dot(NODES, SOLID, DOTTED, highlight=PATH, positions=positions, spring=True),
        "neato",
        no_layout=True,
    )

    assert ">1<" in svg and ">2<" in svg
    # Graphviz 는 "26.00" 처럼 소수 두 자리로 내보낸다. 문자열이 아니라 수로 잰다.
    sizes = {float(s) for s in re.findall(r'font-size="([\d.]+)"', svg)}
    assert float(ORDER_FONTSIZE) in sizes, sorted(sizes)
