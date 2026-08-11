"""build_graph_svg 검증.

작업 3A 에서 test_interactive_html.py 를 지우면서 이 함수를 검증하는 테스트가
하나도 없어졌다. 그 구멍을 메운다.
"""

import re
import shutil

import pytest

from frontend import config
from frontend.components.graph_section import (
    build_graph_svg,
    ensure_positions,
    fit_svg,
    mark_from_registration,
    mark_key,
)

pytestmark = pytest.mark.skipif(
    shutil.which("neato") is None, reason="graphviz 가 설치되어 있지 않다"
)

GRAPH = {
    "version": "test",
    "interfaces": ["MediaData", "AnalysisResult"],
    "nodes": {
        "load_cctv_platform": {
            "name": "승강장 CCTV 불러오기", "description": "",
            "inputs": [], "outputs": ["MediaData"], "properties": {"source": "cctv"},
        },
        "analyze_congestion": {
            "name": "승강장 혼잡도 분석", "description": "",
            "inputs": ["MediaData"], "outputs": ["AnalysisResult"], "properties": {"target": "승강장"},
        },
        "generate_word": {
            "name": "Word 생성", "description": "",
            "inputs": ["AnalysisResult"], "outputs": [], "properties": {"format": "Word"},
        },
    },
    "solid_edges": [
        {"from": "load_cctv_platform", "to": "analyze_congestion", "interface": "MediaData"},
        {"from": "analyze_congestion", "to": "generate_word", "interface": "AnalysisResult"},
    ],
    "dotted_edges": [
        {"a": "load_cctv_platform", "b": "analyze_congestion", "labels": ["source: cctv"]}
    ],
}


@pytest.fixture
def positions(tmp_path, monkeypatch):
    """저장소의 layout.json 을 건드리지 않는다."""
    from frontend import layout_store

    monkeypatch.setattr(layout_store, "LAYOUT_PATH", tmp_path / "layout.json")
    return ensure_positions(GRAPH)


@pytest.fixture
def svg(positions):
    build_graph_svg.clear()
    return build_graph_svg(_graph=GRAPH, _positions=positions, version="t1")


def node_titles(svg: str) -> set[str]:
    return set(re.findall(r'<g id="node\d+" class="node">\s*<title>([^<]+)</title>', svg))


# ------------------------------------------------------------ 형태
def test_returns_one_svg_string(svg):
    """후보 조합별 여러 벌이 아니라 한 벌이다."""
    assert isinstance(svg, str)
    assert svg.count("<svg") == 1


def test_every_node_is_drawn(svg):
    assert node_titles(svg) == set(GRAPH["nodes"])


def test_no_columns(svg):
    """열 정렬을 그만뒀다. rank=same 이 남으면 여전히 열이 생긴다."""
    assert "rank=same" not in svg


def test_dotted_labels_are_hidden(svg):
    """점선 라벨이 화면을 어지럽히고 노드 사이 공간을 잡아먹는다."""
    assert "source: cctv" not in svg


def test_korean_labels_survive(svg):
    """한글이 계속 읽혀야 한다. 가독성이 하한이다."""
    assert "승강장" in svg


def test_long_names_are_folded(svg):
    """두 줄로 접히면 <text> 가 두 개 생긴다."""
    block = re.search(
        r'<g id="node\d+" class="node">\s*<title>load_cctv_platform</title>.*?</g>',
        svg, re.S,
    ).group(0)

    assert block.count("<text") == 2


def test_names_with_a_space_are_folded_too(svg):
    """공백이 있으면 짧은 이름도 접힌다 — "Word 생성" -> "Word" / "생성"."""
    block = re.search(
        r'<g id="node\d+" class="node">\s*<title>generate_word</title>.*?</g>',
        svg, re.S,
    ).group(0)

    assert block.count("<text") == 2
    assert "Word" in block and "생성" in block


# ------------------------------------------------------------ 패널 채우기
def test_svg_is_ready_to_fill_a_panel(svg):
    fitted = fit_svg(svg)

    assert "viewBox" in fitted
    assert 'preserveAspectRatio="xMidYMid meet"' in fitted


# ------------------------------------------------------------ 등록 강조
MARK = {
    "nodes": ["analyze_congestion"],
    "solid": [("load_cctv_platform", "analyze_congestion")],
    "dotted": [("load_cctv_platform", "analyze_congestion")],
}


@pytest.fixture
def marked_svg(positions):
    build_graph_svg.clear()
    return build_graph_svg(_graph=GRAPH, _positions=positions, _mark=MARK, version="t2")


def test_marked_svg_uses_the_new_colour(marked_svg):
    assert config.NEW_COLOR.lower() in marked_svg.lower()


def test_plain_svg_has_no_new_colour(svg):
    """강조는 등록 직후에만 나타난다."""
    assert config.NEW_COLOR.lower() not in svg.lower()


def test_dotted_labels_stay_hidden_even_when_marked(marked_svg):
    """등록 강조에서도 관계 글씨를 안 적는다. 발표자가 말로 설명한다."""
    assert "source: cctv" not in marked_svg


def test_marking_does_not_move_nodes(svg, marked_svg):
    """작업 2의 성질. 강조는 색과 라벨만 바꾼다."""
    assert node_titles(svg) == node_titles(marked_svg)

    def size(s):
        return re.search(r'<svg width="(\d+)pt" height="(\d+)pt"', s).groups()

    assert size(svg) == size(marked_svg)


# ------------------------------------------------------------ 캐시 키
def test_mark_changes_the_cache_key():
    """강조 여부가 SVG 를 다르게 만든다. 키에 안 들어가면 강조가 안 뜨거나 안 꺼진다."""
    assert mark_key(None) != mark_key(MARK)


def test_same_mark_gives_the_same_key():
    assert mark_key(MARK) == mark_key(dict(MARK))


def test_different_marks_give_different_keys():
    other = {**MARK, "nodes": ["generate_word"]}

    assert mark_key(MARK) != mark_key(other)


def test_mark_key_ignores_ordering():
    """같은 내용이면 순서가 달라도 같은 키여야 캐시가 헛돌지 않는다."""
    a = {"nodes": ["x", "y"], "solid": [], "dotted": []}
    b = {"nodes": ["y", "x"], "solid": [], "dotted": []}

    assert mark_key(a) == mark_key(b)


def test_empty_mark_is_plain():
    assert mark_key(None) == "plain"
    assert mark_key({}) == "plain"


# ------------------------------------------------------------ 응답 → 강조
def test_mark_from_registration_picks_the_new_things():
    mark = mark_from_registration(
        {
            "node_id": "analyze_crack_trend",
            "new_solid_edges": [{"from": "a", "to": "b", "interface": "X"}],
            "new_dotted_edges": [{"a": "c", "b": "d", "labels": ["k: v"]}],
        }
    )

    assert mark == {
        "nodes": ["analyze_crack_trend"],
        "solid": [("a", "b")],
        "dotted": [("c", "d")],
    }


@pytest.mark.parametrize(
    "result",
    [None, {}, {"error": "터졌다"}, {"reset": True}],
    ids=["없음", "빈값", "실패", "초기화"],
)
def test_no_mark_when_there_is_nothing_to_show(result):
    """실패하거나 초기화했으면 강조할 것이 없다."""
    assert mark_from_registration(result) is None
