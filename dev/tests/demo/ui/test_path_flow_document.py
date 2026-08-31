"""대상 : demo/ui/components/flow.py — 흐르는 표시를 얹는 문서

브라우저를 못 연다(chromium · playwright · selenium 없음, 새 의존성 금지).
그래서 **문서에 규칙과 선택자가 들어 있는지** 를 본다. 실제로 움직이는지는
사람이 눈으로 봐야 한다.

정지 그림이 안 바뀌었다는 것은 tests/demo/graph_svg/test_path_flow.py 가 본다
(PNG 가 한 바이트도 안 다름).
"""

from demo.graph_svg.dot import FLOW_CLASS as DOT_FLOW_CLASS
from demo.graph_svg.dot import HIGHLIGHT_COLOR, PATH_PENWIDTH
from demo.ui.components import flow, focus_panel, graph_section

SVG = (
    '<svg viewBox="0 0 10 10">'
    '<g id="edge1" class="edge flow"><title>a&#45;&gt;b</title>'
    '<path fill="none" stroke="#14b8a6" stroke-width="8" d="M0,0L9,9"/></g>'
    "</svg>"
)


def bottom() -> str:
    """하단 iframe 문서 한 벌."""
    return focus_panel.focus_html({"": SVG}, {"": "<div></div>"}, 0.6, [])


def top() -> str:
    """상단 iframe 문서 한 벌."""
    return graph_section.graph_fill_html(SVG)


# ------------------------------------------------------------ 두 곳이 안 어긋나는지
def test_both_sides_agree_on_the_class_name():
    """build_dot 이 붙이는 이름과 JS 가 고르는 이름이 같아야 함.

    flow.py 는 demo/graph_svg 를 import 하지 않는다(계층). 대신 이 검사가
    두 값을 붙잡는다.
    """
    assert flow.FLOW_CLASS == DOT_FLOW_CLASS


def test_the_overlay_is_thinner_than_the_line_it_rides_on():
    """원본 teal 선이 양옆에 남아야 함. 덮어버리면 원본을 바꾼 셈임."""
    assert flow.FLOW_WIDTH < PATH_PENWIDTH


# ------------------------------------------------------------ 문서에 들어 있는지
def test_the_bottom_document_carries_the_animation():
    """하단 문서에 애니메이션 규칙과 값이 들어 있어야 함."""
    doc = bottom()

    assert "@keyframes recipeflow" in doc
    assert "stroke-dashoffset" in doc
    assert f"{flow.FLOW_PERIOD_SECONDS}" in doc
    assert f"{flow.FLOW_DASH}" in doc
    assert f"{flow.FLOW_GAP}" in doc


def test_the_document_selects_only_the_marked_edges():
    """선택자가 class 로만 골라야 함. 색 · 굵기로 고르면 다른 경로가 함께 걸림."""
    script = flow.flow_script()

    assert f'CLS = "{flow.FLOW_CLASS}"' in script
    assert '"g." + CLS' in script
    assert flow.flow_script() in bottom()
    # 색 · 굵기로 고른 흔적이 없어야 한다.
    assert HIGHLIGHT_COLOR.lower() not in script.lower()
    assert "stroke-width=" not in script


def test_the_overlay_is_a_copy_and_never_touches_the_original():
    """사본을 붙일 뿐이어야 함. 원본 <path> 를 고치는 호출이 없어야 함."""
    script = flow.flow_script()

    assert "cloneNode" in script
    # 원본에 손대는 흔적. 사본에만 setAttribute 를 쓴다.
    assert "line.setAttribute" not in script
    assert "line.style" not in script
    assert "removeChild" not in script


def test_the_overlay_stands_down_for_reduced_motion():
    """움직임을 원하지 않는 사람에게는 아무것도 안 얹음. 화면이 지금과 같아짐."""
    assert "prefers-reduced-motion" in flow.flow_script()


def test_it_reattaches_when_the_bottom_swaps_the_svg():
    """하단은 노드를 누를 때마다 SVG 를 통째로 갈아끼움. 그때 다시 얹어야 함."""
    assert "MutationObserver" in flow.flow_script()


def test_nothing_escapes_when_the_dom_is_not_what_we_expect():
    """어느 단계에서도 예외를 안 올림. 시연 중에 그래프가 죽는 것이 가장 나쁨."""
    script = flow.flow_script()

    assert script.count("try {") >= 4
    assert script.count("catch (e) {}") >= 4


# ------------------------------------------------------------ 상단
def test_the_top_gets_the_same_script():
    """위아래가 한 벌을 씀. 한쪽만 붙이면 언젠가 다르게 움직임."""
    assert flow.flow_script() in top()
    assert flow.flow_script() in bottom()


def test_nothing_flows_on_the_top_graph():
    """상단은 실선을 안 그리므로 걸리는 엣지가 없음.

    같은 스크립트가 걸려 있어도 고를 것이 없어 아무 일도 안 일어남.
    실제 상단 SVG 에 표시가 없다는 것은 build_dot 쪽에서 봄(draw_solid=False).
    """
    from demo.graph_svg.dot import build_dot

    dot = build_dot(
        {"a": {"name": "A"}, "b": {"name": "B"}},
        {("a", "b"): "X"},
        {},
        highlight=[("a", "b")],
        draw_solid=False,
    )

    assert f'class="{flow.FLOW_CLASS}"' not in dot
