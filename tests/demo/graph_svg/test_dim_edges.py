"""대상 : demo/graph_svg/dot.py — dim_edges 의 순수 동작

등록 장면은 색 하나가 뜻 하나다. 짙은 주황(PATH_NEW)이 "고른 실행 경로",
옅은 주황(PATH_NEW_DIM)이 "선택에서 빠진 실행 경로" 다.

여기서 보는 것은 문자열 규칙뿐이다 — **완성된 SVG 에서 색이 실제로 갈리는지는
tests/demo/api/test_register_colours.py 가 본다.** 단위 테스트만 두면 조립부가
인자를 안 넘겨도 통과한다(group_attrs · review_edges 에서 두 번 당했다).
"""

import inspect

from demo.graph_svg.dot import (
    PATH_NEW,
    PATH_NEW_DIM,
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

SHARED = ("load_cctv_platform", "analyze_congestion")
TAIL = ("analyze_congestion", "generate_word")


def edge_line(dot: str, edge: tuple[str, str]) -> str:
    """실선 한 줄. 점선도 같은 쌍을 쓸 수 있으므로 style=dashed 는 뺌."""
    frm, to = edge
    return next(
        line
        for line in dot.splitlines()
        if f'"{frm}" -> "{to}" [' in line and "dashed" not in line
    )


# ------------------------------------------------------------ 기본값
def test_omitting_dim_edges_changes_nothing():
    """새 인자는 기본값에서 출력이 한 글자도 달라지지 않아야 함."""
    assert build_dot(NODES, SOLID, DOTTED, dim_edges=()) == build_dot(
        NODES, SOLID, DOTTED
    )
    assert build_dot(NODES, SOLID, DOTTED, mark_edges=[SHARED], dim_edges=()) == (
        build_dot(NODES, SOLID, DOTTED, mark_edges=[SHARED])
    )


def test_dim_edges_is_keyword_only():
    """키워드 전용이어야 위치 인자에 기대는 호출이 조용히 어긋나지 않음.

    목록 전체를 박아둠. 인자가 늘거나 이름이 바뀌면 여기가 먼저 알려줌.
    """
    params = inspect.signature(build_dot).parameters

    keyword_only = {
        name for name, param in params.items() if param.kind is param.KEYWORD_ONLY
    }
    assert keyword_only == {
        "positions",
        "spring",
        "graph_attrs",
        "dotted_labels",
        "draw_solid",
        "dotted_penwidth",
        "node_attrs",
        "group_attrs",
        "mark_nodes",
        "mark_edges",
        "mark_dotted",
        "dim_edges",
        "mark_color",
        "edge_color",
        "dotted_color",
    }


# ------------------------------------------------------------ 우선순위
def test_mark_beats_dim_on_the_same_edge():
    """경로들이 앞 구간을 공유함. 짙은 쪽이 이겨야 길이 끊겨 보이지 않음."""
    dot = build_dot(NODES, SOLID, DOTTED, mark_edges=[SHARED], dim_edges=[SHARED, TAIL])

    assert PATH_NEW in edge_line(dot, SHARED)
    assert PATH_NEW_DIM not in edge_line(dot, SHARED)
    assert PATH_NEW_DIM in edge_line(dot, TAIL)


# ------------------------------------------------------------ 그리기
def test_dim_edges_keep_the_arrow_and_get_no_order():
    """옅어도 실행 경로. 방향은 보이고 순번은 안 붙음.

    순번은 highlight_paths 가 정확히 하나일 때의 규칙이고, 등록 장면은
    highlight_paths 를 아예 쓰지 않음.
    """
    dot = build_dot(NODES, SOLID, DOTTED, dim_edges=[TAIL])
    line = edge_line(dot, TAIL)

    assert "dir=forward" in line
    assert "arrowsize=" in line
    assert f"penwidth={PATH_PENWIDTH}" in line
    assert "xlabel" not in dot
