"""줌·팬 스크립트 검증.

JS 라 브라우저 없이는 동작을 못 돌린다. 그래서 여기서 지키는 것은 **동작이
아니라 배선**이다 — 스크립트가 두 문서에 다 들어갔는지, 같은 한 벌인지,
저장 키가 갈렸는지, 사고를 막는 장치(5px 임계값·capture 단계 클릭 차단)가
문서에 실려 있는지. 실제 손짓은 사람이 눈으로 확인하고 NOTES.md 에 적는다.
"""

import re

from frontend.components import focus_panel, graph_section, zoom

SVG = '<svg width="10pt" height="10pt"></svg>'


def top_html() -> str:
    return graph_section.graph_fill_html(SVG)


def bottom_html() -> str:
    return focus_panel.focus_html({"": SVG}, {"": "<div></div>"})


# ------------------------------------------------------------ 한 벌인가 (핵심)
def test_both_panels_embed_the_generated_script_verbatim():
    """두 문서가 zoom_script 결과를 그대로 담는다.

    "줌이 있다" 가 아니라 "**같은 생성 함수**가 만든 것이 들어 있다" 를 본다.
    한쪽에 손으로 베껴 넣으면 여기서 걸린다 — 그게 막으려는 사고다.
    """
    assert zoom.zoom_script(zoom.TOP_KEY) in top_html()
    assert zoom.zoom_script(zoom.BOTTOM_KEY) in bottom_html()


def test_the_two_scripts_differ_only_in_the_storage_key():
    """키 말고 다른 데서 갈라지면 한쪽만 고쳐진 것이다."""
    top = zoom.zoom_script(zoom.TOP_KEY)
    bottom = zoom.zoom_script(zoom.BOTTOM_KEY)

    assert top != bottom
    assert top.replace(zoom.TOP_KEY, "KEY") == bottom.replace(zoom.BOTTOM_KEY, "KEY")


def test_each_panel_remembers_its_own_scale():
    """상단·하단이 키를 공유하면 한쪽을 확대할 때 다른 쪽이 함께 튄다."""
    assert zoom.TOP_KEY != zoom.BOTTOM_KEY
    assert zoom.BOTTOM_KEY not in top_html()
    assert zoom.TOP_KEY not in bottom_html()


def test_the_key_actually_reaches_the_script_body():
    """치환이 안 되면 두 문서가 같은 자리표(placeholder)를 쓰게 된다.

    위 "키 말고 같다" 단언은 치환이 통째로 실패해도 통과하므로 따로 본다.
    """
    body = zoom.zoom_script(zoom.TOP_KEY)

    assert f'var KEY = "{zoom.TOP_KEY}"' in body
    assert "__" not in body.replace("__recipeZoom", "")


# ------------------------------------------------------------ 문서가 안 깨지는가
def test_script_tags_are_balanced():
    for html in (top_html(), bottom_html()):
        assert html.count("<script") == html.count("</" "script>")


def test_the_bottom_document_still_has_its_own_script():
    """줌을 더하면서 노드 좁히기 스크립트를 밀어내지 않았는지."""
    html = bottom_html()

    assert "const DATA = " in html
    assert html.count("<script") == 2


def test_the_top_document_wraps_the_svg_in_the_zoom_container():
    """transform 을 걸 상자가 없으면 스크립트가 조용히 아무 일도 안 한다."""
    html = top_html()

    assert '<div id="graph">' in html
    assert re.search(r'<div id="graph">\s*<svg', html)


def test_the_svg_still_fills_the_box():
    """줌 상자를 끼우면서 기존 채움 규칙을 잃지 않았는지."""
    assert "svg { width: 100%; height: 100%; display: block; }" in top_html()


# ------------------------------------------------------------ 사고 방지 장치
def test_drag_is_told_apart_from_click():
    """임계값이 없으면 그래프를 옮길 때마다 후보가 좁혀지고 전체로 복귀한다."""
    body = zoom.zoom_script(zoom.TOP_KEY)

    assert f"THRESHOLD = {zoom.DRAG_THRESHOLD}" in body
    assert zoom.DRAG_THRESHOLD >= 3  # 손떨림을 흡수할 만큼은 되어야 한다


def test_the_swallowed_click_is_caught_before_the_narrowing_handler():
    """잡기(capture) 단계가 아니면 노드 핸들러가 먼저 돌아 이미 늦는다."""
    body = zoom.zoom_script(zoom.TOP_KEY)

    listener = re.search(r'addEventListener\("click".*?\}, true\)', body, re.S)
    assert listener, "click 리스너가 capture 단계로 붙어 있지 않다"
    assert "stopPropagation" in listener.group(0)


def test_scale_is_clamped():
    """한계가 없으면 휠 한 번에 화면 밖으로 날아가 시연이 끊긴다."""
    body = zoom.zoom_script(zoom.TOP_KEY)

    assert f"MIN = {zoom.MIN_SCALE}" in body
    assert f"MAX = {zoom.MAX_SCALE}" in body
    assert "Math.min(MAX, Math.max(MIN," in body
    assert 0 < zoom.MIN_SCALE < 1 < zoom.MAX_SCALE


def test_double_click_resets():
    """시연 중에 길을 잃었을 때 빠져나올 길."""
    body = zoom.zoom_script(zoom.TOP_KEY)

    reset = re.search(r'addEventListener\("dblclick".*?\}\);', body, re.S)
    assert reset and "scale = 1" in reset.group(0)


def test_wheel_is_not_passive():
    """passive 면 preventDefault 가 무시돼 페이지가 함께 스크롤된다."""
    body = zoom.zoom_script(zoom.TOP_KEY)

    assert "{passive: false}" in body


def test_redrawn_svg_keeps_the_zoom():
    """하단은 노드를 누를 때마다 SVG 를 갈아끼운다. 그때 transform 이 날아간다."""
    assert "MutationObserver" in zoom.zoom_script(zoom.BOTTOM_KEY)


# ------------------------------------------------------------ 저장소 폴백
def load_body(script: str) -> str:
    """읽기 함수만 잘라낸다.

    문서 전체에서 이름만 찾으면 무력하다 — 읽기 쪽 폴백을 통째로 지워도
    쓰기 쪽에 같은 이름이 남아 있어 통과해 버린다(실제로 확인했다).
    """
    return re.search(r"function load\(\) \{.*?\n  \}", script, re.S).group(0)


def test_storage_falls_back_three_ways():
    """어느 단계가 막혀도 예외로 화면이 죽지 않아야 한다.

    읽는 쪽에 세 단계가 다 있어야 한다. 하나라도 빠지면 그 환경에서는
    Run 을 누를 때마다 배율이 1로 돌아간다.
    """
    body = load_body(zoom.zoom_script(zoom.TOP_KEY))

    order = [
        body.index("sessionStorage"),   # 1차
        body.index("window.parent"),    # 2차 — 부모 창 전역
        body.index("return memory"),    # 3차 — 이 문서 안 변수
    ]
    assert order == sorted(order), "폴백 순서가 뒤집혔다"


def test_every_storage_access_is_guarded():
    """try 없이 만지면 스토리지가 막힌 환경에서 스크립트가 통째로 죽는다."""
    body = zoom.zoom_script(zoom.TOP_KEY)

    for line in body.splitlines():
        if "sessionStorage" in line or "__recipeZoom" in line:
            assert "try" in line or line.strip().startswith(("var", "if", "top.")), line

    assert body.count("catch (e) {}") >= 4
