"""대상 : app/ui/graph_svg/dot.py — 고른 경로에만 붙는 흐름 표시(class="flow")

굵은 teal 실선은 정지 그림이라 방향이 안 읽힌다. 「쉰셋째」에서 순번(xlabel)을
뺀 뒤로 단서가 화살촉뿐이라 그 위에 흐르는 표시를 얹는다. 표시를 고르는 손잡이가
이 class 다.

**여기서 지키는 것은 둘이다.**

    고르는 범위   해석 경로(teal)에만 붙는다. 등록 경로 · 물러난 경로 ·
                  배경 실선 · 점선에는 안 붙는다
    정지 그림     class 를 넣기 전과 후의 PNG 가 한 바이트도 안 다르다.
                  보도자료 이미지가 지금과 같다는 뜻이다

문자열 규칙만 보지 않는다 — 완성된 SVG 도 함께 본다. 단위 테스트만 두면
조립부가 인자를 안 넘겨도 통과한다(group_attrs · review_edges 에서 두 번 당했다).
"""

import re
import shutil
import subprocess

import pytest

from app.ui.graph_svg.dot import (
    DOTTED_PENWIDTH,
    FLOW_CLASS,
    HIGHLIGHT_COLOR,
    PATH_ARROWSIZE,
    PATH_PENWIDTH,
    build_dot,
)

NODES = {
    "load_cctv_platform": {"name": "승강장 CCTV 불러오기"},
    "analyze_congestion": {"name": "승강장 혼잡도 분석"},
    "generate_word": {"name": "Word 생성"},
}
SOLID = {
    ("load_cctv_platform", "analyze_congestion"): "MediaData",
    ("analyze_congestion", "generate_word"): "AnalysisResult",
}
DOTTED = {("load_cctv_platform", "analyze_congestion"): ["source: cctv"]}

HEAD = ("load_cctv_platform", "analyze_congestion")
TAIL = ("analyze_congestion", "generate_word")

MARK = f'class="{FLOW_CLASS}"'


def solid_lines(dot: str) -> dict[tuple[str, str], str]:
    """실선 한 줄씩. 점선도 같은 쌍을 쓸 수 있으므로 style=dashed 는 뺌."""
    found = {}
    for line in dot.splitlines():
        match = re.search(r'"(\w+)" -> "(\w+)" \[', line)
        if match and "style=dashed" not in line:
            found[(match.group(1), match.group(2))] = line
    return found


# ------------------------------------------------------------ 고르는 범위
def test_the_chosen_path_carries_the_mark():
    """해석 경로의 엣지에만 표시가 붙음."""
    lines = solid_lines(build_dot(NODES, SOLID, DOTTED, highlight=[HEAD]))

    assert MARK in lines[HEAD]
    assert MARK not in lines[TAIL]


def test_a_plain_graph_carries_no_mark():
    """아무것도 안 고르면 표시가 하나도 없음. 기본 출력이 안 바뀜."""
    assert MARK not in build_dot(NODES, SOLID, DOTTED)


def test_dotted_edges_never_carry_the_mark():
    """점선은 실행 경로가 아님. 방향도 없어 흐를 것이 없음."""
    dot = build_dot(NODES, SOLID, DOTTED, highlight=[HEAD])

    for line in dot.splitlines():
        if "style=dashed" in line:
            assert MARK not in line


def test_the_registration_scene_carries_no_mark():
    """등록(주황) · 물러난 경로(옅은 주황)에는 안 붙음.

    굵기와 화살표가 해석 경로와 같아 굵기로 고르면 함께 걸림. 여러 갈래가
    동시에 흐르면 방향이 오히려 안 읽히므로 teal 하나만 흐름.
    """
    dot = build_dot(
        NODES, SOLID, DOTTED, mark_edges=[HEAD], dim_edges=[TAIL]
    )

    assert MARK not in dot


def test_the_mark_does_not_touch_thickness_or_colour():
    """표시를 붙여도 굵기 · 색 · 화살표가 그대로임. 고르는 손잡이일 뿐임."""
    marked = solid_lines(build_dot(NODES, SOLID, DOTTED, highlight=[HEAD]))[HEAD]

    assert "dir=forward" in marked
    assert f"arrowsize={PATH_ARROWSIZE}" in marked
    assert f"penwidth={PATH_PENWIDTH}" in marked
    assert HIGHLIGHT_COLOR in marked


# ------------------------------------------------------------ 정지 그림
graphviz = pytest.mark.skipif(
    shutil.which("neato") is None, reason="graphviz 가 설치되어 있지 않다"
)


def png(dot: str) -> bytes:
    """같은 DOT 을 화면과 같은 엔진으로 래스터화. 좌표가 없어 -n 은 안 씀."""
    return subprocess.run(
        ["neato", "-Tpng"], input=dot.encode("utf-8"), capture_output=True
    ).stdout


@graphviz
def test_the_still_picture_is_untouched():
    """표시가 있든 없든 PNG 가 같아야 함. **이것이 관문이다.**

    캡처(보도자료 이미지)는 JS 가 안 도는 곳이라 흐름이 아예 안 보인다.
    그때 지금과 다른 그림이 나오면 안 됨.
    """
    with_mark = build_dot(NODES, SOLID, DOTTED, highlight=[HEAD])
    without = with_mark.replace(f', {MARK}', "")

    assert without != with_mark        # 검사가 무력하지 않은지
    assert png(with_mark) == png(without)


@graphviz
def test_graphviz_passes_the_mark_through_to_the_svg():
    """dot 이 class 를 <g class="edge flow"> 로 그대로 내보내야 함.

    2.43.0 에서 실측함. 이것이 안 되면 브라우저가 선을 못 고름.
    """
    svg = subprocess.run(
        ["neato", "-Tsvg"],
        input=build_dot(NODES, SOLID, DOTTED, highlight=[HEAD]).encode("utf-8"),
        capture_output=True,
    ).stdout.decode("utf-8")

    flowing = re.findall(
        r'<g id="edge\d+" class="edge ' + FLOW_CLASS + r'">\s*<title>(.*?)</title>',
        svg,
    )

    assert flowing == ["load_cctv_platform&#45;&gt;analyze_congestion"]


@graphviz
def test_the_dotted_penwidth_still_reaches_the_svg():
    """음성 대조군 옆자리. 위 검사가 SVG 를 실제로 읽고 있는지 봄."""
    svg = subprocess.run(
        ["neato", "-Tsvg"],
        input=build_dot(NODES, SOLID, DOTTED).encode("utf-8"),
        capture_output=True,
    ).stdout.decode("utf-8")

    assert f'stroke-width="{DOTTED_PENWIDTH}"' in svg
