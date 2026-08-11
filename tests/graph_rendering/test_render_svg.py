"""render_svg() 검증. 서버에서 네이티브 dot 으로 SVG 를 완성한다.

브라우저 WASM Graphviz 대신 서버에서 그리는 이유는 graph_section.py 모듈
docstring 에 적어두었다. 여기서는 그 변환이 실제로 되는지와, 실패가 조용히
넘어가지 않는지를 본다.
"""

import shutil

import pytest

from demo.ui.components.graph_section import (
    GraphvizFailed,
    GraphvizNotFound,
    build_dot,
    render_svg,
)

pytestmark = pytest.mark.skipif(
    shutil.which("dot") is None, reason="graphviz 가 설치되어 있지 않다"
)

NODES = {
    "load_cctv_platform": {"name": "승강장 CCTV 불러오기"},
    "analyze_congestion": {"name": "승강장 혼잡도 분석"},
}
SOLID = {("load_cctv_platform", "analyze_congestion"): "MediaData"}


# ------------------------------------------------------------ 정상 변환
def test_returns_an_svg_document():
    svg = render_svg("digraph { a -> b; }")

    assert "<svg" in svg
    assert svg.lstrip().startswith("<?xml")


def test_korean_node_label_survives_the_conversion():
    """인코딩을 UTF-8 로 못박지 않으면 한글이 깨지거나 dot 이 실패한다."""
    svg = render_svg(build_dot(NODES, SOLID, {}))

    assert "승강장 CCTV 불러오기" in svg
    assert "승강장 혼잡도 분석" in svg


def test_svg_carries_its_own_size():
    """iframe 높이를 이 값에서 계산하므로 없으면 그래프가 잘린다."""
    svg = render_svg(build_dot(NODES, SOLID, {}))

    assert 'width="' in svg and 'height="' in svg


# ------------------------------------------------------------ 실패 처리
def test_broken_dot_raises_instead_of_returning_empty():
    """조용히 빈 문자열을 돌려주면 화면만 비고 원인을 알 수 없다."""
    with pytest.raises(GraphvizFailed):
        render_svg("이건 DOT 이 아니다 {{{")


def test_failure_message_keeps_the_dot_stderr():
    """무엇이 잘못됐는지 화면에 보여주려면 원인이 메시지에 남아야 한다."""
    with pytest.raises(GraphvizFailed) as error_info:
        render_svg("digraph { a -> ; }")

    assert str(error_info.value).strip() != ""


def test_missing_dot_binary_raises_not_found(monkeypatch):
    """dot 이 없는 환경에서도 조용히 비지 않고 설치 안내가 나와야 한다."""
    monkeypatch.setattr(
        "demo.ui.components.graph_section.shutil.which", lambda name: None
    )

    with pytest.raises(GraphvizNotFound) as error_info:
        render_svg("digraph { a -> b; }")

    assert "dot" in str(error_info.value)


def test_not_found_and_failed_are_distinguishable():
    """설치 문제와 DOT 문법 오류는 사용자가 할 일이 다르다."""
    assert not issubclass(GraphvizNotFound, GraphvizFailed)
    assert not issubclass(GraphvizFailed, GraphvizNotFound)
