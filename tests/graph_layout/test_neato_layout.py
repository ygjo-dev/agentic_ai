"""neato 배치 검증.

이 작업의 핵심 성질 두 가지를 고정한다.
  (1) 모든 노드를 고정하고 -n 으로 그리면 하이라이트가 어떻게 바뀌어도 좌표가 같다.
  (2) 노드를 하나 추가해도 기존 노드는 움직이지 않는다.

(1)은 예전에 시행착오로 지키던 성질인데, -n 은 배치를 아예 계산하지 않으므로
이제는 구조적으로 보장된다.
"""

import re
import shutil

import pytest

from frontend.components.graph_section import (
    DOTTED_LEN,
    HIGHLIGHT_COLOR,
    MARK_SOLID_PENWIDTH,
    NEW_COLOR,
    _run_graphviz,
    NEATO_ATTRS,
    NEATO_FRESH_ATTRS,
    NODE_ATTRS,
    SOLID_LEN,
    build_dot,
    layout_positions,
    render_svg,
    wrap_label,
)

pytestmark = pytest.mark.skipif(
    shutil.which("neato") is None, reason="graphviz 가 설치되어 있지 않다"
)

NODES = {
    "load_cctv_platform": {"name": "승강장 CCTV 불러오기"},
    "load_inspection_car_image": {"name": "검측차 이미지 불러오기"},
    "analyze_congestion": {"name": "승강장 혼잡도 분석"},
    "detect_structure_crack": {"name": "구조물 균열 분석"},
    "generate_word": {"name": "Word 생성"},
}
SOLID = {
    ("load_cctv_platform", "analyze_congestion"): "MediaData",
    ("load_inspection_car_image", "detect_structure_crack"): "MediaData",
    ("analyze_congestion", "generate_word"): "AnalysisResult",
    ("detect_structure_crack", "generate_word"): "AnalysisResult",
}
DOTTED = {("load_cctv_platform", "load_inspection_car_image"): ["source: cctv"]}

PATH_A = [("load_cctv_platform", "analyze_congestion"), ("analyze_congestion", "generate_word")]
PATH_B = [
    ("load_inspection_car_image", "detect_structure_crack"),
    ("detect_structure_crack", "generate_word"),
]


def fresh_positions(nodes=NODES, solid=SOLID, dotted=DOTTED):
    """핀 없는 최초 배치. 겹침 제거를 쓸 수 있는 유일한 경우다."""
    return layout_positions(
        build_dot(nodes, solid, dotted, spring=True, graph_attrs=NEATO_FRESH_ATTRS)
    )


def svg_node_coords(svg: str) -> dict[str, tuple[float, float]]:
    """SVG 에서 노드 중심 좌표를 뽑는다."""
    coords = {}
    for block in re.findall(r'<g id="node\d+" class="node">(.*?)</g>', svg, re.S):
        title = re.search(r"<title>([a-z_]+)</title>", block)
        pos = re.search(r'text-anchor="middle" x="([-\d.]+)" y="([-\d.]+)"', block)
        if title and pos:
            coords[title.group(1)] = (float(pos.group(1)), float(pos.group(2)))
    return coords


def anchored(positions, keys):
    """첫 노드를 원점으로 옮긴 상대 좌표. 평행이동은 화면에 안 보인다."""
    ox, oy = positions[keys[0]]
    return {k: (positions[k][0] - ox, positions[k][1] - oy) for k in keys}


# ------------------------------------------------------------ DOT 출력
def test_positions_emit_pinned_pos():
    dot = build_dot(NODES, SOLID, DOTTED, positions={"generate_word": (12.5, 34.0)})

    assert 'pos="12.5,34.0!"' in dot


def test_pos_comes_after_label():
    """테스트들이 노드 줄을 '"id" [label=' 로 찾는다. 순서가 바뀌면 깨진다."""
    dot = build_dot(NODES, SOLID, DOTTED, positions={"generate_word": (1.0, 2.0)})

    line = next(l for l in dot.splitlines() if '"generate_word" [' in l)
    assert line.strip().startswith('"generate_word" [label=')
    assert line.index("label=") < line.index("pos=")


def test_without_positions_no_pos():
    assert "pos=" not in build_dot(NODES, SOLID, DOTTED)


def test_defaults_are_byte_identical_to_omitting_the_new_arguments():
    """새 인자를 안 넘겼을 때 출력이 예전과 완전히 같아야 한다.

    tests/graph_rendering 의 40여 개가 기존 출력 문자열에 의존한다.
    """
    assert build_dot(NODES, SOLID, DOTTED) == build_dot(
        NODES, SOLID, DOTTED,
        positions=None, spring=False, graph_attrs=(),
        dotted_labels=True, node_attrs=(),
        mark_nodes=(), mark_edges=(), mark_dotted=(), mark_color=None,
        edge_color=None, dotted_color=None,
    )


def test_every_keyword_only_argument_is_covered_by_the_identity_test():
    """위 테스트가 새 인자를 빠뜨리면 회귀 방어가 뚫린다.

    인자를 더하고 위 테스트에 열거하는 것을 잊으면 여기서 잡힌다.
    """
    import inspect

    keyword_only = {
        name
        for name, param in inspect.signature(build_dot).parameters.items()
        if param.kind is inspect.Parameter.KEYWORD_ONLY
    }

    assert keyword_only == {
        "positions", "spring", "graph_attrs", "dotted_labels", "node_attrs",
        "mark_nodes", "mark_edges", "mark_dotted", "mark_color",
        "edge_color", "dotted_color",
    }


# ------------------------------------------------------------ 노드 축소
def test_dotted_labels_off_removes_the_label():
    """점선 라벨이 화면을 어지럽히고 노드 사이 공간을 잡아먹는다."""
    dot = build_dot(NODES, SOLID, DOTTED, dotted_labels=False)

    assert "source: cctv" not in dot
    assert "label=" not in next(l for l in dot.splitlines() if "dashed" in l)


def test_dotted_labels_on_by_default():
    assert "source: cctv" in build_dot(NODES, SOLID, DOTTED)


def test_node_attrs_land_on_the_node_line():
    """값을 박아두지 않는다 — 글씨 크기는 화면을 재서 바뀌는 값이고,
    여기서 지키려는 성질은 "넘긴 것이 전부 node 줄에 실린다" 뿐이다."""
    dot = build_dot(NODES, SOLID, DOTTED, node_attrs=NODE_ATTRS)

    node_line = next(l for l in dot.splitlines() if l.strip().startswith("node ["))
    for attr in NODE_ATTRS:
        assert attr in node_line


def test_wrap_label_folds_at_the_middle_space():
    assert wrap_label("승강장 CCTV 불러오기") == "승강장 CCTV\\n불러오기"


def test_wrap_label_leaves_names_without_spaces_alone():
    assert wrap_label("Word생성") == "Word생성"


def test_wrap_label_never_splits_inside_a_word():
    """글자 중간에서 자르면 한글이 안 읽힌다."""
    for name in (node["name"] for node in NODES.values()):
        for part in wrap_label(name).split("\\n"):
            assert part in name


# penwidth= 안의 "width=" 에 걸리면 안 된다. 강조된 노드를 잴 때 실제로 물렸다.
_WIDTH_ATTR = re.compile(r"(?<![a-zA-Z])width=([\d.]+)")


def max_node_width(dot: str) -> float:
    """neato 가 계산한 가장 넓은 노드의 폭(pt)."""
    out = _run_graphviz(dot, "neato", ["-Tdot"])
    flat = re.sub(r'"?[\w]+"?\s*->\s*"?[\w]+"?\s*\[[^\]]*\];', " ", re.sub(r"\s+", " ", out))
    widths = [
        float(m.group(1))
        for block in re.finditer(r'"?[A-Za-z_]\w*"?\s*\[([^\]]*)\]\s*;', flat)
        for m in [_WIDTH_ATTR.search(block.group(1))]
        if m
    ]
    return max(widths) * 72  # 인치 -> 포인트


def test_width_helper_is_not_fooled_by_penwidth():
    """penwidth=2 를 width=2 로 잘못 읽으면 강조된 노드가 144pt 로 잡힌다.

    실측 스크립트에서 실제로 물렸던 함정이라 헬퍼에 테스트를 붙여 둔다.
    """
    plain = max_node_width(build_dot(NODES, SOLID, DOTTED))
    marked = max_node_width(build_dot(NODES, SOLID, DOTTED, mark_nodes=set(NODES)))

    assert plain == marked


def test_shrinking_makes_nodes_narrower():
    """가로 폭이 줄어야 새 노드가 들어갈 자리가 생긴다."""
    plain = max_node_width(
        build_dot(NODES, SOLID, DOTTED, spring=True, graph_attrs=NEATO_FRESH_ATTRS)
    )
    shrunk = max_node_width(
        build_dot(
            {k: {**v, "name": wrap_label(v["name"])} for k, v in NODES.items()},
            SOLID, DOTTED,
            spring=True, graph_attrs=NEATO_FRESH_ATTRS,
            node_attrs=NODE_ATTRS, dotted_labels=False,
        )
    )

    assert shrunk < plain * 0.75, f"{plain:.0f} -> {shrunk:.0f}"


def test_spring_sets_edge_lengths():
    """점선이 실선보다 짧아야 같은 특성끼리 서로 끌어당겨 모인다."""
    dot = build_dot(NODES, SOLID, DOTTED, spring=True)

    solid_lines = [l for l in dot.splitlines() if "dir=none" in l and "dashed" not in l]
    dotted_lines = [l for l in dot.splitlines() if "dashed" in l]

    assert solid_lines and all(f"len={SOLID_LEN}" in l for l in solid_lines)
    assert dotted_lines and all(f"len={DOTTED_LEN}" in l for l in dotted_lines)


def test_solid_edges_are_longer_than_dotted():
    """실선이 길어야 가로로 펴지고, 점선이 짧아야 같은 특성끼리 모인다."""
    assert SOLID_LEN > DOTTED_LEN


def test_without_spring_no_len():
    assert "len=" not in build_dot(NODES, SOLID, DOTTED)


def test_graph_attrs_land_on_the_graph_line():
    dot = build_dot(NODES, SOLID, DOTTED, graph_attrs=NEATO_FRESH_ATTRS)

    graph_line = next(l for l in dot.splitlines() if l.strip().startswith("graph ["))
    assert "inputscale=72" in graph_line
    assert "overlap=voronoi" in graph_line


def test_no_stages_means_no_rank_block():
    """열 정렬을 그만뒀다. rank=same 이 남으면 여전히 열이 생긴다."""
    assert "rank=same" not in build_dot(NODES, SOLID, DOTTED, spring=True)


# ------------------------------------------------------------ mark 레이어
DOTTED_PAIR = ("load_cctv_platform", "load_inspection_car_image")


def dotted_line(dot: str) -> str:
    return next(l for l in dot.splitlines() if "dashed" in l)


def test_mark_nodes_use_the_new_colour():
    dot = build_dot(NODES, SOLID, DOTTED, mark_nodes={"generate_word"})

    line = next(l for l in dot.splitlines() if '"generate_word" [label=' in l)
    assert NEW_COLOR in line
    assert "penwidth=2" in line


def test_mark_edges_use_the_new_colour():
    edge = ("load_cctv_platform", "analyze_congestion")
    dot = build_dot(NODES, SOLID, DOTTED, mark_edges={edge})

    line = next(l for l in dot.splitlines() if '"load_cctv_platform" -> "analyze_congestion"' in l)
    assert NEW_COLOR in line
    # 새 recipe 는 조연이라 얇다. 주인공은 노드가 어디에 붙었느냐다.
    assert f"penwidth={MARK_SOLID_PENWIDTH}" in line


def test_mark_edges_get_no_order_label():
    """등록 강조는 실행 순서가 아니라 '새로 생긴 것' 이다."""
    edge = ("load_cctv_platform", "analyze_congestion")
    dot = build_dot(NODES, SOLID, DOTTED, highlight=[edge], mark_edges={edge})

    line = next(l for l in dot.splitlines() if '"load_cctv_platform" -> "analyze_congestion"' in l)
    assert "xlabel" not in line, line


def test_mark_dotted_colours_only_the_named_pair():
    dot = build_dot(NODES, SOLID, DOTTED, mark_dotted={DOTTED_PAIR})

    assert NEW_COLOR in dotted_line(dot)


def test_mark_dotted_accepts_either_order():
    """점선은 방향이 없다. 어느 순서로 받아도 같은 쌍이어야 한다."""
    forward = build_dot(NODES, SOLID, DOTTED, mark_dotted={DOTTED_PAIR})
    backward = build_dot(NODES, SOLID, DOTTED, mark_dotted={DOTTED_PAIR[::-1]})

    assert forward == backward


def test_marked_dotted_keeps_dashed_and_dir_none():
    """실선/점선을 이 두 속성으로 가른다. 강조해도 유지돼야 한다."""
    line = dotted_line(build_dot(NODES, SOLID, DOTTED, mark_dotted={DOTTED_PAIR}))

    assert "style=dashed" in line
    assert "dir=none" in line


def test_mark_colour_can_be_overridden():
    dot = build_dot(NODES, SOLID, DOTTED, mark_nodes={"generate_word"}, mark_color="#123456")

    line = next(l for l in dot.splitlines() if '"generate_word" [label=' in l)
    assert "#123456" in line
    assert NEW_COLOR not in line


def test_mark_wins_over_highlight():
    """둘 다 걸리면 새로 생긴 것이 먼저 눈에 띄어야 한다."""
    dot = build_dot(
        NODES, SOLID, DOTTED,
        highlight_nodes={"generate_word"}, mark_nodes={"generate_word"},
    )

    line = next(l for l in dot.splitlines() if '"generate_word" [label=' in l)
    assert NEW_COLOR in line
    assert HIGHLIGHT_COLOR not in line


def test_no_marks_means_no_new_colour_anywhere():
    """mark 를 안 넘기면 NEW_COLOR 가 문자열에 아예 없어야 한다."""
    assert NEW_COLOR not in build_dot(NODES, SOLID, DOTTED)


# ------------------------------------------------------------ 선택적 점선 라벨
def test_only_the_named_dotted_pair_gets_a_label():
    two_dotted = {
        DOTTED_PAIR: ["source: cctv"],
        ("analyze_congestion", "detect_structure_crack"): ["target: 승강장"],
    }

    dot = build_dot(NODES, SOLID, two_dotted, dotted_labels={DOTTED_PAIR})

    assert "source: cctv" in dot
    assert "target: 승강장" not in dot


def test_selective_labels_accept_either_order():
    dot = build_dot(NODES, SOLID, DOTTED, dotted_labels={DOTTED_PAIR[::-1]})

    assert "source: cctv" in dot


def test_empty_label_set_shows_nothing():
    assert "source: cctv" not in build_dot(NODES, SOLID, DOTTED, dotted_labels=set())


# ------------------------------------------------------------ 좌표 왕복
def test_inputscale_makes_the_round_trip_an_identity():
    """inputscale=72 가 없으면 좌표가 72배로 어긋나 배치가 폭발한다."""
    first = fresh_positions()

    second = layout_positions(
        build_dot(NODES, SOLID, DOTTED, positions=first, spring=True, graph_attrs=NEATO_ATTRS)
    )

    for node_id, (x, y) in first.items():
        assert abs(second[node_id][0] - x) < 0.51, node_id
        assert abs(second[node_id][1] - y) < 0.51, node_id


def test_fresh_layout_is_deterministic():
    """어느 기계에서 처음 켜도 같은 지도가 나와야 한다."""
    assert fresh_positions() == fresh_positions()


def test_every_node_gets_a_position():
    assert set(fresh_positions()) == set(NODES)


# ------------------------------------------------------------ 핵심 성질 (1)
@pytest.mark.parametrize(
    "highlight_paths",
    [None, [PATH_A], [PATH_B], [PATH_A, PATH_B]],
    ids=["없음", "후보1개", "다른후보1개", "후보2개"],
)
def test_highlight_never_moves_a_node(highlight_paths):
    """모든 노드가 고정된 상태에서 -n 은 배치를 계산하지 않는다."""
    positions = fresh_positions()

    def draw(paths):
        return render_svg(
            build_dot(
                NODES, SOLID, DOTTED,
                highlight_paths=paths, positions=positions, spring=True,
            ),
            "neato",
            no_layout=True,
        )

    base = svg_node_coords(draw(None))
    assert len(base) == len(NODES)
    assert svg_node_coords(draw(highlight_paths)) == base


def test_highlight_never_changes_the_canvas():
    positions = fresh_positions()

    def size(paths):
        svg = render_svg(
            build_dot(
                NODES, SOLID, DOTTED,
                highlight_paths=paths, positions=positions, spring=True,
            ),
            "neato",
            no_layout=True,
        )
        return re.search(r'<svg width="(\d+)pt" height="(\d+)pt"', svg).groups()

    assert size([PATH_A, PATH_B]) == size(None)


def test_marking_never_moves_a_node():
    """등록 강조를 켜도 좌표와 캔버스가 그대로여야 한다.

    이 테스트는 회귀를 잡는 장치가 아니라 우리가 기대는 성질을 기록해 둔 것이다.
    실측해 보니 neato 는 핀이 없고 배치를 실제로 계산할 때조차 엣지 라벨이
    노드 위치에 영향을 주지 않는다(9노드 · 점선 4개로 확인, 0/9 이동).
    라벨이 공간을 확보해 노드를 밀어내는 것은 dot 엔진의 성질이다.

    따라서 이 테스트는 어떤 구현으로도 실패시키기 어렵다. 판별력이 있는 것은
    아래 test_positions_actually_pin_the_layout 이다.
    """
    positions = fresh_positions()

    def draw(**kwargs):
        return render_svg(
            build_dot(
                NODES, SOLID, DOTTED,
                positions=positions, spring=True, node_attrs=NODE_ATTRS, **kwargs,
            ),
            "neato",
            no_layout=True,
        )

    base = draw(dotted_labels=False)
    marked = draw(
        dotted_labels={DOTTED_PAIR},
        mark_nodes={"analyze_congestion"},
        mark_edges={("load_cctv_platform", "analyze_congestion")},
        mark_dotted={DOTTED_PAIR},
    )

    assert svg_node_coords(base) == svg_node_coords(marked)
    assert len(svg_node_coords(base)) == len(NODES)

    def size(svg):
        return re.search(r'<svg width="(\d+)pt" height="(\d+)pt"', svg).groups()

    assert size(base) == size(marked)


def test_positions_actually_pin_the_layout():
    """좌표를 넘기면 그 좌표대로 그려져야 한다.

    판별력 확인 : 서로 다른 좌표를 주면 결과도 달라야 한다. positions 를
    무시하는 구현(예: build_graph_svg 에서 positions= 를 빠뜨림)이면 두 결과가
    같아져 여기서 잡힌다.

    노드 하나만 옮긴다. 전부 같은 만큼 옮기면 캔버스 정규화가 흡수해 버려
    화면상 차이가 없다 — 그러면 이 테스트가 아무것도 판별하지 못한다.
    """
    positions = fresh_positions()
    one = sorted(positions)[0]
    moved = {**positions, one: (positions[one][0] + 120, positions[one][1] + 60)}

    def draw(pos):
        return render_svg(
            build_dot(NODES, SOLID, DOTTED, positions=pos, spring=True,
                      node_attrs=NODE_ATTRS, dotted_labels=False),
            "neato",
            no_layout=True,
        )

    assert svg_node_coords(draw(positions)) != svg_node_coords(draw(moved))


def test_reviving_dotted_labels_never_moves_a_node():
    """3A 에서 숨긴 라벨을 되살려도 노드가 밀리면 안 된다."""
    positions = fresh_positions()

    def draw(dotted_labels):
        return render_svg(
            build_dot(
                NODES, SOLID, DOTTED,
                positions=positions, spring=True, node_attrs=NODE_ATTRS,
                dotted_labels=dotted_labels,
            ),
            "neato",
            no_layout=True,
        )

    assert svg_node_coords(draw(False)) == svg_node_coords(draw(True))


def test_order_labels_survive_no_layout():
    """후보가 하나로 좁혀지면 순번이 보여야 한다. -n 에서도 살아있어야 한다."""
    positions = fresh_positions()

    svg = render_svg(
        build_dot(
            NODES, SOLID, DOTTED,
            highlight_paths=[PATH_A], positions=positions, spring=True,
        ),
        "neato",
        no_layout=True,
    )

    assert ">1<" in svg and ">2<" in svg


# ------------------------------------------------------------ 핵심 성질 (2)
def test_adding_a_node_does_not_move_the_existing_ones():
    """시연의 핵심 장면. 지도가 재배치되면 "화면이 리셋됐다" 로 보인다."""
    before = fresh_positions()

    nodes = {**NODES, "analyze_crack_trend": {"name": "구조물 균열 추세 분석"}}
    solid = {**SOLID, ("load_inspection_car_image", "analyze_crack_trend"): "MediaData"}
    after = layout_positions(
        build_dot(nodes, solid, DOTTED, positions=before, spring=True, graph_attrs=NEATO_ATTRS)
    )

    assert "analyze_crack_trend" in after

    # 절대좌표는 캔버스 정규화로 평행이동할 수 있다. 화면에 보이는 것은 상대배치다.
    keys = sorted(before)
    expected = anchored(before, keys)
    actual = anchored(after, keys)
    for node_id in keys:
        assert abs(actual[node_id][0] - expected[node_id][0]) < 0.51, node_id
        assert abs(actual[node_id][1] - expected[node_id][1]) < 0.51, node_id


def test_both_configs_use_the_same_layout_model():
    """최초와 증분이 다른 모델이면 새 노드가 다른 규칙으로 놓여 어색해진다."""
    assert "model=subset" in NEATO_ATTRS
    assert "model=subset" in NEATO_FRESH_ATTRS


def test_fresh_layout_is_deterministic_under_subset():
    """어느 기계에서 처음 켜도 같은 지도가 나와야 한다."""
    assert fresh_positions() == fresh_positions()


def test_overlap_removal_is_not_used_when_pinning():
    """overlap 은 고정(!)을 무시하고 재배치한다 — 핀이 있으면 쓰면 안 된다.

    실측으로 388~710pt 씩 움직였다. 이 테스트는 그 설정이 되살아나는 것을 막는다.
    """
    assert "overlap" not in " ".join(NEATO_ATTRS)
    assert "overlap=voronoi" in " ".join(NEATO_FRESH_ATTRS)


# ------------------------------------------------------------ 조밀한 그래프
# 노드가 적으면 겹칠 일이 없어 overlap 설정이 결과를 바꾸지 않는다. 그러면
# "핀이 지켜지는가" 를 검증해도 통과해 버려 회귀를 못 잡는다. 아래 fixture 는
# 겹침이 실제로 생길 만큼 조밀해서 잘못된 설정이면 노드가 움직인다.
DENSE_NODES = {f"n{i}": {"name": f"아주 긴 한글 노드 이름 {i}"} for i in range(10)}
DENSE_SOLID = {(f"n{i}", f"n{i + 1}"): "X" for i in range(9)}
DENSE_DOTTED = {
    (f"n{i}", f"n{j}"): ["k: v"]
    for i in range(10)
    for j in range(i + 1, 10)
    if (i + j) % 3 == 0
}


# 이 짝은 그래프비즈 기본 배치 모델로 잰다. model=subset 은 노드를 워낙 넓게
# 벌려서 voronoi 가 고칠 겹침이 아예 안 생긴다 — 노드 10·16·24개, 라벨 길이
# 1배·3배까지 6조합을 재봤지만 전부 drift 0.05 로 성질이 관측되지 않았다.
# 기본 모델에서는 그대로 드러난다(0.0000 vs 98.01).
#
# 여기서 검증하는 것은 "overlap 제거는 고정(!)을 무시한다" 는 Graphviz 의 성질이지
# 특정 모델의 동작이 아니다. 프로덕션 설정이 그 성질에 걸리지 않는지는
# test_overlap_removal_is_not_used_when_pinning 이 상수를 직접 봐서 지킨다.
BARE_ATTRS = ("inputscale=72",)
BARE_FRESH_ATTRS = ("inputscale=72", "overlap=voronoi")


def dense_after_adding(graph_attrs):
    """조밀한 그래프에 노드를 하나 더한 뒤의 (이전 좌표, 이후 좌표).

    spring 을 끈다. 엣지 길이를 주면 노드가 넓게 퍼져 겹칠 일이 없어지고,
    그러면 overlap 제거가 할 일이 없어 이 검증이 무의미해진다.
    좁게 붙여 놓아야 "overlap 은 고정을 무시한다" 를 실제로 드러낼 수 있다.
    """
    before = layout_positions(
        build_dot(
            DENSE_NODES, DENSE_SOLID, DENSE_DOTTED,
            graph_attrs=BARE_FRESH_ATTRS,
        )
    )
    after = layout_positions(
        build_dot(
            {**DENSE_NODES, "새노드": {"name": "새 노드"}},
            {**DENSE_SOLID, ("n0", "새노드"): "X"},
            DENSE_DOTTED,
            positions=before, graph_attrs=graph_attrs,
        )
    )
    return before, after


def worst_drift(before, after):
    keys = sorted(before)
    expected, actual = anchored(before, keys), anchored(after, keys)
    return max(
        max(abs(actual[k][0] - expected[k][0]), abs(actual[k][1] - expected[k][1]))
        for k in keys
    )


def test_dense_graph_keeps_pinned_nodes_still():
    """겹침이 생길 만큼 조밀해도 고정한 노드는 움직이지 않아야 한다."""
    before, after = dense_after_adding(BARE_ATTRS)

    assert worst_drift(before, after) < 0.51


def test_dense_graph_would_move_if_overlap_removal_were_used():
    """위 테스트가 판별력이 있음을 증명한다.

    잘못된 설정(핀이 있는데 overlap 제거)을 쓰면 실제로 노드가 움직인다.
    이 테스트가 깨지면 위 테스트는 무엇이든 통과시키는 셈이 된다.
    """
    before, after = dense_after_adding(BARE_FRESH_ATTRS)

    assert worst_drift(before, after) > 1.0
