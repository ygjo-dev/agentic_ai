"""대상 : demo/ui/components/zoom.py — 고른 경로에 화면을 맞추는 문서

브라우저를 못 연다(chromium · playwright · selenium 없음, 새 의존성 금지).
그래서 **문서에 규칙과 선택자가 들어 있는지** 를 본다. 실제로 맞춰지는지는
사람이 눈으로 봐야 한다 (NOTES.md 「예순다섯째」의 「사람이 볼 것」).

배율이 실제로 칸에 드는지는 tests/demo/graph_svg/test_autofit_scale.py 가
완성된 SVG 로 잰다. 여기는 문서만 본다.
"""

from demo.graph_svg.dot import FLOW_CLASS as DOT_FLOW_CLASS
from demo.graph_svg.dot import HIGHLIGHT_COLOR
from demo.ui.components import flow, focus_panel, graph_section, zoom

SVG = (
    '<svg viewBox="0 0 10 10">'
    '<g id="edge1" class="edge flow"><title>a&#45;&gt;b</title>'
    '<path fill="none" stroke="#14b8a6" stroke-width="8" d="M0,0L9,9"/></g>'
    '<g id="node1" class="node"><title>a</title><path d="M0,0L1,1"/></g>'
    '<g id="node2" class="node"><title>b</title><path d="M8,8L9,9"/></g>'
    "</svg>"
)


def bottom() -> str:
    """하단 iframe 문서 한 벌."""
    return focus_panel.focus_html({"": SVG}, {"": "<div></div>"}, 0.6, [])


def top() -> str:
    """상단 iframe 문서 한 벌."""
    return graph_section.graph_fill_html(SVG)


# ------------------------------------------------------------ 무엇으로 고르는가
def test_it_selects_the_path_by_the_same_handle_the_flow_overlay_uses():
    """강조를 고르는 손잡이가 하나여야 함.

    엣지에 class 를 붙이는 곳은 build_dot 하나뿐이고(dot.FLOW_CLASS), 그것을
    읽는 쪽이 flow.py 와 여기 둘이다. 세 값이 어긋나면 자동 맞춤이 조용히
    아무 일도 안 하게 된다.
    """
    assert flow.FLOW_CLASS == DOT_FLOW_CLASS
    assert f'HL = "{flow.FLOW_CLASS}"' in bottom()


def test_it_never_selects_by_color_or_stroke_width():
    """색 · 굵기로 고르면 등록 경로 · 물러난 경로가 함께 걸림."""
    script = zoom.zoom_script("k", "#graph", flow.FLOW_CLASS)

    assert '"g." + HL' in script
    assert HIGHLIGHT_COLOR.lower() not in script.lower()
    assert "stroke-width" not in script


def test_it_measures_the_end_nodes_too_not_only_the_edges():
    """엣지만 재면 노드 이름이 칸 밖으로 나감.

    엣지 <title> 의 "꼬리->머리" 에서 끝 노드 id 를 얻어 g.node 를 함께 잰다.
    노드에는 class 가 없다 — 붙이려면 dot.py 를 고쳐야 해서 범위 밖이다.
    """
    script = zoom.zoom_script("k", "#graph", flow.FLOW_CLASS)

    assert 'split("->")' in script
    assert '"g.node"' in script
    assert "getBoundingClientRect" in script


# ------------------------------------------------------------ 언제 맞추는가
def test_it_remembers_which_path_it_already_fitted():
    """경로가 바뀔 때만 맞춰야 함. 서명을 저장소에 함께 남김."""
    script = zoom.zoom_script("k", "#graph", flow.FLOW_CLASS)

    assert "sig: fitted" in script
    assert "saved.sig" in script
    assert "sig === fitted" in script


def test_it_does_nothing_when_there_is_no_highlight():
    """강조가 없으면 서명이 비고, 배율을 안 건드림.

    실행 전 화면 · NO_MATCH · 상단이 전부 이 자리다.
    """
    script = zoom.zoom_script("k", "#graph", flow.FLOW_CLASS)

    assert "if (!sig || sig === fitted) return;" in script
    # 손잡이 자체를 안 넘긴 문서에서는 아예 안 돈다.
    assert 'HL = ""' in zoom.zoom_script("k")
    assert "if (!HL) return;" in script


def test_it_gives_up_quietly_when_the_box_cannot_be_measured():
    """상자를 못 재면 아무 일도 안 하고 지금처럼 둠."""
    script = zoom.zoom_script("k", "#graph", flow.FLOW_CLASS)

    assert "if (!(frame.width > 0) || !(frame.height > 0)) return;" in script
    assert "isFinite" in script


def test_nothing_escapes_when_the_dom_is_not_what_we_expect():
    """어느 단계에서도 예외를 안 올림. 시연 중에 그래프가 죽는 것이 가장 나쁨."""
    script = zoom.zoom_script("k", "#graph", flow.FLOW_CLASS)

    assert script.count("catch (e) {}") >= 6
    for guarded in ("function flowEdges", "function pieces", "function fit"):
        assert guarded in script


# ------------------------------------------------------------ 손으로 굴리는 것
def test_the_hand_controls_are_all_still_there():
    """자동으로 맞춘 뒤에도 휠 · 드래그 · 더블클릭 복귀가 다 돌아야 함."""
    doc = bottom()

    assert '"wheel"' in doc
    assert '"mousedown"' in doc
    assert '"mousemove"' in doc
    assert '"dblclick"' in doc
    assert "scale = 1; tx = 0; ty = 0;" in doc


def test_the_wheel_and_the_autofit_share_one_ceiling():
    """천장이 둘이면 자동으로 3.0 까지 간 화면에서 휠 한 칸에 2.5 로 떨어짐.

    자동 맞춤도 휠도 같은 MAX 로 자른다.
    """
    script = zoom.zoom_script("k", "#graph", flow.FLOW_CLASS)

    assert f"MAX = {zoom.MAX_SCALE}" in script
    # 휠과 맞춤이 쓰는 자르기가 같은 모양이어야 한다.
    assert script.count("Math.min(MAX, Math.max(MIN,") == 2


def test_the_reset_gesture_wins_over_the_autofit():
    """더블클릭 복귀 뒤에 다시 그려도 자동 맞춤이 되살아나면 안 됨.

    복귀는 서명을 안 지운다 — 지우면 다음 그림에서 도로 확대된다.
    """
    script = zoom.zoom_script("k", "#graph", flow.FLOW_CLASS)
    reset = script.split('"dblclick"')[1].split("});")[0]

    assert 'fitted = ""' not in reset


# ------------------------------------------------------------ 다시 그릴 때
def test_it_reattaches_when_the_bottom_swaps_the_svg():
    """하단은 노드를 누를 때마다 SVG 를 통째로 갈아끼움.

    그때 얹고 나서 맞춘다 — 순서가 뒤바뀌면 아직 안 걸린 배율로 상자를 잰다.
    """
    script = zoom.zoom_script("k", "#graph", flow.FLOW_CLASS)

    assert "function refresh() { apply(); fit(); }" in script
    assert "MutationObserver(refresh)" in script


def test_it_looks_once_more_after_the_first_frame():
    """첫 그림에서 칸이 아직 0px 이면 그때는 아무 일도 안 일어남.

    엣지가 안 바뀌니 MutationObserver 도 안 울어 부를 사람이 없다.
    """
    assert "requestAnimationFrame(fit)" in zoom.zoom_script("k", "#graph", "flow")


# ------------------------------------------------------------ 상단
def test_the_top_gets_the_same_script_but_has_nothing_to_fit():
    """위아래가 한 벌을 씀. 상단에는 class="flow" 엣지가 없어 안 걸림.

    상단 SVG 에 표시가 없다는 것은 build_dot 쪽에서 봄(draw_solid=False) —
    tests/demo/ui/test_path_flow_document.py 가 같은 것을 지킨다.
    """
    from demo.graph_svg.dot import build_dot

    same = zoom.zoom_script(zoom.TOP_KEY, highlight_class=flow.FLOW_CLASS)
    assert same in top()

    dot = build_dot(
        {"a": {"name": "A"}, "b": {"name": "B"}},
        {("a", "b"): "X"},
        {},
        highlight=[("a", "b")],
        draw_solid=False,
    )
    assert f'class="{flow.FLOW_CLASS}"' not in dot


def test_the_two_graphs_keep_separate_memories():
    """상단 · 하단이 배율도 서명도 따로 기억해야 함."""
    assert zoom.TOP_KEY != zoom.BOTTOM_KEY
    assert f'KEY = "{zoom.TOP_KEY}"' in top()
    assert f'KEY = "{zoom.BOTTOM_KEY}"' in bottom()


# ------------------------------------------------------------ 상수
def test_the_padding_is_real_but_small():
    """여백이 0 이면 선이 칸 테두리에 닿고, 크면 확대가 죽음."""
    assert 0 < zoom.FIT_PAD < 523 / 4


# ------------------------------------------------------------ 화면 한 장으로
# 여기까지는 컴포넌트를 직접 불러 만든 문서를 봤다. 조립부가 인자를 안 넘겨도
# 통과할 수 있는 자리라(「쉰넷째」가 group_attrs · review_edges 에서 두 번 당했다)
# main.py 를 통째로 돌려 실제로 화면에 나가는 문서도 함께 본다.
def app_documents() -> list[str]:
    """AppTest 로 main.py 를 한 번 돌려 iframe 문서를 전부 모음.

    출력  문서 문자열 목록(상단 · 하단)
    규칙  8000 이 안 뜬 자리에서는 그래프가 아예 안 나가므로 건너뜀
    """
    import pytest
    import requests

    from demo.ui import api_client

    # api_client.get_graph 를 안 쓴다 — 그쪽은 st.session_state 를 만지고
    # 실패해도 마지막 캐시로 답해서 "서버가 떴는가" 를 못 가린다.
    try:
        answer = requests.get(f"{api_client.BASE_URL}/graph", timeout=api_client.GRAPH_TIMEOUT)
        answer.raise_for_status()
    except Exception as exc:  # 서버가 없다 · 응답이 이상하다
        pytest.skip(f"8000 이 안 답한다: {exc}")

    from streamlit.testing.v1 import AppTest

    from paths import REPO_ROOT

    app = AppTest.from_file(str(REPO_ROOT / "demo" / "ui" / "main.py"), default_timeout=180)
    app.run()
    assert not app.exception, f"화면이 죽었다: {app.exception}"

    found = []

    def walk(node):
        proto = getattr(node, "proto", None)
        if proto is not None and "<script>" in str(proto):
            found.append(str(proto))
        children = getattr(node, "children", None)
        for child in (children.values() if isinstance(children, dict) else (children or [])):
            if not isinstance(child, int):
                walk(child)

    walk(app._tree)
    return found


def test_the_running_app_ships_both_documents_with_the_autofit_in_them():
    """화면 한 장에 상단 · 하단 두 문서가 나가고 둘 다 자동 맞춤을 싣고 있어야 함.

    상단에도 실리는 것이 맞다 — 한 벌을 쓴다. 상단에는 걸릴 엣지가 없어
    아무 일도 안 한다(위 test_the_top_gets_the_same_script_but_has_nothing_to_fit).
    """
    docs = app_documents()

    assert len(docs) == 2, f"iframe 문서가 둘이어야 하는데 {len(docs)} 개다"
    blob = "\n".join(docs)
    for rule in ('HL = ', flow.FLOW_CLASS, "sig: fitted", "requestAnimationFrame(fit)"):
        assert rule in blob
    for key in (zoom.TOP_KEY, zoom.BOTTOM_KEY):
        assert key in blob
