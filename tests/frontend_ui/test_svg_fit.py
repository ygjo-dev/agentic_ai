"""SVG 를 패널에 맞추는 정규화 검증.

Graphviz 가 넣는 width/height 가 남아 있으면 고정 높이 패널 안에서
위아래 여백이 뜨거나 잘린다. 작아 보이지만 완성도 인상에 크게 기여한다.
"""

from frontend.components.graph_section import fit_svg, graph_fill_html

SVG = (
    '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
    '<svg width="591pt" height="336pt" '
    'viewBox="0.00 0.00 591.00 336.00" xmlns="http://www.w3.org/2000/svg">\n'
    "<g id=\"graph0\"><title>ontology</title></g>\n</svg>\n"
)


# ------------------------------------------------------------ fit_svg
def test_removes_width_and_height():
    out = fit_svg(SVG)

    opening = out[out.index("<svg") : out.index(">", out.index("<svg")) + 1]
    assert 'width="591pt"' not in opening
    assert 'height="336pt"' not in opening


def test_keeps_viewbox():
    """viewBox 가 사라지면 크기 정보가 아예 없어져 아무것도 안 보인다."""
    assert 'viewBox="0.00 0.00 591.00 336.00"' in fit_svg(SVG)


def test_adds_preserve_aspect_ratio():
    """비율이 깨지면 한글이 찌그러져 안 읽힌다."""
    assert 'preserveAspectRatio="xMidYMid meet"' in fit_svg(SVG)


def test_does_not_duplicate_preserve_aspect_ratio():
    once = fit_svg(SVG)

    assert fit_svg(once).count("preserveAspectRatio") == 1


def test_body_is_untouched():
    assert "<title>ontology</title>" in fit_svg(SVG)


def test_svg_without_viewbox_is_left_alone():
    """viewBox 가 없으면 크기 정보가 width/height 뿐이다. 지우면 안 된다."""
    plain = '<svg width="10pt" height="20pt"></svg>'

    assert fit_svg(plain) == plain


def test_no_svg_tag_is_left_alone():
    assert fit_svg("그냥 문자열") == "그냥 문자열"


# ------------------------------------------------------------ iframe 문서
def test_fill_html_stretches_to_the_box():
    html = graph_fill_html(SVG)

    assert "height: 100%" in html
    assert "background: transparent" in html


def test_fill_html_embeds_the_normalized_svg():
    html = graph_fill_html(SVG)

    assert 'preserveAspectRatio="xMidYMid meet"' in html
    assert 'width="591pt"' not in html
