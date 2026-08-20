"""대상 : demo/graph_svg/ — 배치 불변식. **눈이 못 보는 것을 본다**

`demo/` 는 시연용이고 통째로 사라질 계층이라 그 테스트는 대부분 지웠다.
이 파일만 남는 이유는 하나다 — 여기 있는 것은 **화면을 봐도 확인할 수 없다.**

```
로직 오염   "말이 안 되는 경로가 등록됐다"   화면을 보면 안다
배치 오염   "노드가 3pt 움직였다"            화면을 봐도 모른다
```

3pt 는 안 보이고 30pt 면 이미 시연이 깨진 뒤다. 그래서 사람의 눈을 대신하는
장면 테스트는 버리고, 눈이 못 보는 것만 남겼다.

여기 있는 단언 대부분은 **몇 주에 걸쳐 실측으로 알아낸 배치 성질**이다.
어떤 강조 조합에서도 좌표가 같다 · 노드를 등록해도 기존 노드가 안 움직인다 ·
`inputscale=72` · 핀이 있으면 `overlap` 금지 · 순번은 `xlabel`.
**지우면 다시 알아낼 방법이 없다.**

원래 있던 곳 (전부 이 파일로 옮겼고 그 파일들은 지웠다) :
`test_neato_layout.py` · `test_bottom_flow.py` · `test_top_relations.py` ·
`test_visual_kinds.py` · `test_build_dot.py`(연기 감지 하나).
**본문은 옮기기만 했다.** 실측으로 얻은 단언이라 손대면 무엇을 재던 것인지 잃는다.
"""

import re
import shutil

import pytest

from demo.api.services.ontology_service import domain_graph
from demo.graph_svg.dot import (
    DOTTED_PENWIDTH,
    DOTTED_PENWIDTH_TOP,
    GROUP_ATTRS,
    GROUP_ATTRS_TOP,
    NODE_ATTRS,
    build_dot,
)
from demo.graph_svg.graphviz import layout_positions, render_svg
from demo.graph_svg.layout_store import NEATO_ATTRS, NEATO_FRESH_ATTRS

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
# test_bottom_flow.py 에서 옮겨온 검사가 이 이름을 쓴다. 그 파일의 PATH 와 같은
# 사슬이다 — 불러오기 -> 분석 -> 생성.
PATH = PATH_A

DOTTED_PAIR = ("load_cctv_platform", "load_inspection_car_image")


def fresh_positions(nodes=NODES, solid=SOLID, dotted=DOTTED):
    """핀 없는 최초 배치. 겹침 제거를 쓸 수 있는 유일한 경우."""
    return layout_positions(
        build_dot(nodes, solid, dotted, spring=True, graph_attrs=NEATO_FRESH_ATTRS)
    )


def svg_node_coords(svg: str) -> dict[str, tuple[float, float]]:
    """SVG 에서 노드 중심 좌표를 뽑음."""
    coords = {}
    for block in re.findall(r'<g id="node\d+" class="node">(.*?)</g>', svg, re.S):
        title = re.search(r"<title>([a-z_]+)</title>", block)
        pos = re.search(r'text-anchor="middle" x="([-\d.]+)" y="([-\d.]+)"', block)
        if title and pos:
            coords[title.group(1)] = (float(pos.group(1)), float(pos.group(2)))
    return coords


def anchored(positions, keys):
    """첫 노드를 원점으로 옮긴 상대 좌표. 평행이동은 화면에 안 보임."""
    ox, oy = positions[keys[0]]
    return {k: (positions[k][0] - ox, positions[k][1] - oy) for k in keys}


# ------------------------------------------------------------ DOT 출력
def test_positions_emit_pinned_pos():
    dot = build_dot(NODES, SOLID, DOTTED, positions={"generate_word": (12.5, 34.0)})

    assert 'pos="12.5,34.0!"' in dot


def test_pos_comes_after_label():
    """테스트들이 노드 줄을 '"id" [label=' 로 찾음. 순서가 바뀌면 깨짐."""
    dot = build_dot(NODES, SOLID, DOTTED, positions={"generate_word": (1.0, 2.0)})

    line = next(l for l in dot.splitlines() if '"generate_word" [' in l)
    assert line.strip().startswith('"generate_word" [label=')
    assert line.index("label=") < line.index("pos=")


def test_without_positions_no_pos():
    assert "pos=" not in build_dot(NODES, SOLID, DOTTED)


# ------------------------------------------------------------ 좌표 왕복
def test_inputscale_makes_the_round_trip_an_identity():
    """inputscale=72 가 없으면 좌표가 72배로 어긋나 배치가 폭발함."""
    first = fresh_positions()

    second = layout_positions(
        build_dot(NODES, SOLID, DOTTED, positions=first, spring=True, graph_attrs=NEATO_ATTRS)
    )

    for node_id, (x, y) in first.items():
        assert abs(second[node_id][0] - x) < 0.51, node_id
        assert abs(second[node_id][1] - y) < 0.51, node_id


def test_fresh_layout_is_deterministic():
    """어느 기계에서 처음 켜도 같은 지도가 나와야 함."""
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
    """모든 노드가 고정된 상태에서 -n 은 배치를 계산하지 않음."""
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
    """등록 강조를 켜도 좌표와 캔버스가 그대로여야 함.

    이 테스트는 회귀를 잡는 장치가 아니라 우리가 기대는 성질을 기록해 둔 것.
    실측해 보니 neato 는 핀이 없고 배치를 실제로 계산할 때조차 엣지 라벨이
    노드 위치에 영향을 주지 않음(9노드 · 점선 4개로 확인, 0/9 이동).
    라벨이 공간을 확보해 노드를 밀어내는 것은 dot 엔진의 성질임.

    따라서 이 테스트는 어떤 구현으로도 실패시키기 어려움. 판별력이 있는 것은
    아래 test_positions_actually_pin_the_layout 임.
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


def test_dimming_never_moves_a_node():
    """좁히면 빠진 경로가 옅어짐. 그때 지도가 흔들리면 보던 자리를 잃음.

    옅은 경로도 화살표를 달고 굵기가 배경 실선과 다름. 색만 바꾸는 것이
    아니므로 좌표와 캔버스를 함께 봄.
    """
    positions = fresh_positions()

    def draw(**kwargs):
        return render_svg(
            build_dot(
                NODES, SOLID, DOTTED,
                positions=positions, spring=True, node_attrs=NODE_ATTRS,
                dotted_labels=False, **kwargs,
            ),
            "neato",
            no_layout=True,
        )

    def size(svg):
        return re.search(r'<svg width="(\d+)pt" height="(\d+)pt"', svg).groups()

    base = draw(mark_edges=PATH_A)
    narrowed = draw(mark_edges=PATH_B, dim_edges=PATH_A)

    assert len(svg_node_coords(base)) == len(NODES)
    assert svg_node_coords(narrowed) == svg_node_coords(base)
    assert size(narrowed) == size(base)


def test_positions_actually_pin_the_layout():
    """좌표를 넘기면 그 좌표대로 그려져야 함.

    판별력 확인 : 서로 다른 좌표를 주면 결과도 달라야 함. positions 를
    무시하는 구현(예 : build_graph_svg 에서 positions= 를 빠뜨림)이면 두 결과가
    같아져 여기서 잡힘.

    노드 하나만 옮김. 전부 같은 만큼 옮기면 캔버스 정규화가 흡수해 버려
    화면상 차이가 없음. 그러면 이 테스트가 아무것도 판별하지 못함.
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
    """3A 에서 숨긴 라벨을 되살려도 노드가 밀리면 안 됨."""
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
    """후보가 하나로 좁혀지면 순번이 보여야 함. -n 에서도 살아있어야 함."""
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
    """시연의 핵심 장면. 지도가 재배치되면 "화면이 리셋됐다" 로 보임."""
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
    """최초와 증분이 다른 모델이면 새 노드가 다른 규칙으로 놓여 어색해짐."""
    assert "model=subset" in NEATO_ATTRS
    assert "model=subset" in NEATO_FRESH_ATTRS


def test_fresh_layout_is_deterministic_under_subset():
    """어느 기계에서 처음 켜도 같은 지도가 나와야 함."""
    assert fresh_positions() == fresh_positions()


def test_overlap_removal_is_not_used_when_pinning():
    """overlap 은 고정(!)을 무시하고 재배치함. 핀이 있으면 쓰면 안 됨.

    실측으로 388~710pt 씩 움직였음. 이 테스트는 그 설정이 되살아나는 것을 막음.
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

    spring 을 끔. 엣지 길이를 주면 노드가 넓게 퍼져 겹칠 일이 없어지고,
    그러면 overlap 제거가 할 일이 없어 이 검증이 무의미해짐.
    좁게 붙여 놓아야 "overlap 은 고정을 무시한다" 를 실제로 드러낼 수 있음.
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
    """겹침이 생길 만큼 조밀해도 고정한 노드는 움직이지 않아야 함."""
    before, after = dense_after_adding(BARE_ATTRS)

    assert worst_drift(before, after) < 0.51


def test_dense_graph_would_move_if_overlap_removal_were_used():
    """위 테스트가 판별력이 있음을 증명함.

    잘못된 설정(핀이 있는데 overlap 제거)을 쓰면 실제로 노드가 움직임.
    이 테스트가 깨지면 위 테스트는 무엇이든 통과시키는 셈이 됨.
    """
    before, after = dense_after_adding(BARE_FRESH_ATTRS)

    assert worst_drift(before, after) > 1.0


# ------------------------------------------------------------ 화살표와 순번
# test_bottom_flow.py 에서 옮겨왔다.
@pytest.mark.skipif(shutil.which("neato") is None, reason="graphviz 가 없다")
def test_arrows_and_bigger_numbers_never_move_a_node():
    """화살표와 순번은 그리기지 배치가 아님.

    xlabel 은 레이아웃에 관여하지 않음(label 과 달리). 캔버스는 커질 수 있음.
    글자가 그림 밖으로 나가면 bbox 가 따라 넓어짐. 그것은 재서 보고함.
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
        mark_edges=[PATH[0]]
    ) == base


# ------------------------------------------------------------ 실선 · 점선 굵기
# test_top_relations.py 에서 옮겨왔다. 그 파일의 그래프 대신 이 파일의 그래프로
# 잰다 — 두 검사가 보는 것은 "실선을 빼도 · 점선을 굵혀도 좌표가 같다" 이고,
# 어느 그래프든 실선과 점선이 하나씩 있으면 그대로 성립한다.
@pytest.mark.skipif(shutil.which("neato") is None, reason="graphviz 가 없다")
def test_removing_the_solid_edges_never_moves_a_node():
    """★ 전 노드가 핀이고 neato -n 이라 선을 빼도 배치를 다시 계산하지 않음.

    이 성질이 없으면 상단에서 실선을 걷어내는 순간 지도가 통째로 재배치되고,
    위아래가 서로 다른 자리를 가리키게 됨. 캔버스까지 함께 봄. 좌표가
    같아도 캔버스가 달라지면 축소 배율이 갈려 위아래 크기가 어긋남.
    """
    positions = layout_positions(
        build_dot(NODES, SOLID, DOTTED, spring=True, graph_attrs=NEATO_FRESH_ATTRS)
    )

    def drawn(**kwargs):
        svg = render_svg(
            build_dot(NODES, SOLID, DOTTED, positions=positions, spring=True, **kwargs),
            "neato",
            no_layout=True,
        )
        coords = {}
        for block in re.findall(r'<g id="node\d+" class="node">(.*?)</g>', svg, re.S):
            title = re.search(r"<title>([a-z_]+)</title>", block)
            pos = re.search(r'text-anchor="middle" x="([-\d.]+)" y="([-\d.]+)"', block)
            if title and pos:
                coords[title.group(1)] = (float(pos.group(1)), float(pos.group(2)))
        return coords, re.search(r'viewBox="([^"]+)"', svg).group(1)

    with_solid, box = drawn()
    assert len(with_solid) == len(NODES), "노드 좌표를 못 읽었다 — 검사가 무력하다"

    without_solid, box_without = drawn(draw_solid=False)

    assert without_solid == with_solid
    assert box_without == box


@pytest.mark.skipif(shutil.which("neato") is None, reason="graphviz 가 없다")
def test_a_thicker_dotted_line_never_moves_a_node():
    """굵기는 색과 같음. 그리기지 배치가 아님."""
    positions = layout_positions(
        build_dot(NODES, SOLID, DOTTED, spring=True, graph_attrs=NEATO_FRESH_ATTRS)
    )

    def coords(width):
        svg = render_svg(
            build_dot(NODES, SOLID, DOTTED, positions=positions, spring=True,
                      draw_solid=False, dotted_penwidth=width),
            "neato",
            no_layout=True,
        )
        return re.findall(r'text-anchor="middle" x="([-\d.]+)" y="([-\d.]+)"', svg)

    assert coords(DOTTED_PENWIDTH_TOP) == coords(DOTTED_PENWIDTH)


# ------------------------------------------------------------ 시각 스타일
# test_visual_kinds.py 에서 옮겨왔다. **대상(group) 노드가 있는 그래프가
# 필요하다** — 위 그래프에는 group 이 없어 group_attrs 를 켜도 아무 일이 안 일어나
# 검사가 무력해진다. 그래서 그 파일의 데이터를 이름만 GROUP_ 접두로 바꿔 함께
# 옮겼다(같은 파일에 NODES 가 둘일 수 없다). 단언은 한 글자도 안 고쳤다.
GROUP_NODES = {
    "group_track": {"kind": "group", "name": "궤도"},
    "load_track_image": {
        "kind": "function", "name": "궤도 검측 이미지 불러오기",
        "inputs": [], "outputs": ["ImageData"],
    },
    "detect_track_crack": {
        "kind": "function", "name": "궤도 균열 검출",
        "inputs": ["ImageData"], "outputs": ["AnalysisResult"],
    },
    "generate_word": {
        "kind": "function", "name": "Word 보고서 생성",
        "inputs": ["AnalysisResult"], "outputs": ["DocumentData"],
    },
}
GROUP_SOLID = {
    ("load_track_image", "detect_track_crack"): "ImageData",
    ("detect_track_crack", "generate_word"): "AnalysisResult",
}
GROUP_DOTTED = {("detect_track_crack", "group_track"): ["about"]}
GROUP_PATH = [("load_track_image", "detect_track_crack"),
              ("detect_track_crack", "generate_word")]


@pytest.mark.skipif(shutil.which("neato") is None, reason="graphviz 가 없다")
def test_the_visual_style_never_moves_a_node():
    """도형과 색을 바꿔도 좌표와 캔버스가 그대로여야 함.

    노드를 눌러 좁히거나 등록 강조가 켜질 때 지도가 흔들리면 보던 자리를 잃음.
    좌표를 전부 고정하고 neato -n 으로 그려 구조적으로 보장하지만, 그 보장이
    깨지면 화면에서만 드러나므로 여기서 못을 박음.
    """
    positions = layout_positions(
        build_dot(GROUP_NODES, GROUP_SOLID, GROUP_DOTTED, spring=True,
                  graph_attrs=NEATO_FRESH_ATTRS)
    )

    def drawn(**kwargs):
        svg = render_svg(
            build_dot(GROUP_NODES, GROUP_SOLID, GROUP_DOTTED, positions=positions,
                      spring=True, node_attrs=NODE_ATTRS, graph_attrs=NEATO_ATTRS,
                      **kwargs),
            "neato", no_layout=True,
        )
        coords = {}
        for block in re.findall(r'<g id="node\d+" class="node">(.*?)</g>', svg, re.S):
            title = re.search(r"<title>([a-z_]+)</title>", block)
            pos = re.search(r'text-anchor="middle" x="([-\d.]+)" y="([-\d.]+)"', block)
            if title and pos:
                coords[title.group(1)] = (
                    round(float(pos.group(1)), 1), round(float(pos.group(2)), 1)
                )
        size = re.search(r'viewBox="([^"]+)"', svg)
        return coords, size.group(1)

    # 스타일은 고정하고 강조만 바꾼다. 프로덕션이 그렇게 부른다 — 한 화면 안의
    # 변형들은 전부 같은 group_attrs 로 그려지고, 달라지는 것은 강조뿐이다.
    base_coords, base_box = drawn(group_attrs=GROUP_ATTRS)
    assert base_coords, "노드 좌표를 하나도 못 읽었다 — 검사가 무력하다"

    for name, kwargs in (
        ("경로 강조", {"highlight": GROUP_PATH}),
        ("노드 강조", {"highlight_nodes": ["detect_track_crack"]}),
        ("등록 강조", {"mark_nodes": {"group_track"}}),
        ("점선 강조", {"mark_dotted": [("detect_track_crack", "group_track")]}),
    ):
        coords, box = drawn(group_attrs=GROUP_ATTRS, **kwargs)
        assert coords == base_coords, f"{name} 에서 노드가 움직였다"
        assert box == base_box, f"{name} 에서 캔버스가 달라졌다"


@pytest.mark.skipif(shutil.which("neato") is None, reason="graphviz 가 없다")
def test_the_top_and_bottom_styles_have_the_same_geometry():
    """상단과 하단은 색만 다르고 크기는 같아야 함.

    둘은 한 화면에 함께 뜨고 같은 좌표 파일을 씀. 도형이나 굵기가 갈리면
    노드 크기가 달라져 위아래가 미묘하게 어긋나 보임.

    실측으로 알아낸 것 : ellipse 는 box 보다 큼. group 스타일을 켜고 끄면
    캔버스가 커지면서 모든 노드가 통째로 5pt 씩 밀림(화면에는 평행이동이라
    안 보이지만, 위아래가 서로 다른 도형을 쓰면 진짜로 어긋남).
    """
    geometry = lambda attrs: [  # noqa: E731 — 색만 지운 속성 목록
        attr for attr in attrs if not attr.startswith(("color=", "fontcolor="))
    ]

    assert geometry(GROUP_ATTRS) == geometry(GROUP_ATTRS_TOP)
    assert GROUP_ATTRS != GROUP_ATTRS_TOP, "색은 달라야 한다 — 상단이 한 단계 옅다"


# ------------------------------------------------------------ 연기 감지
# test_build_dot.py 에서 옮겨왔다. 그 파일의 나머지(DOT 문법 · 색 · 강조)는
# 지웠지만 이것만 남긴다 — 온톨로지를 손보다 DOT 이 깨지면 시연이 백지가 되는데,
# 실제 데이터를 한 번 통과시키는 이것 하나면 잡힌다.
def test_graphviz_accepts_the_real_ontology():
    """실제 데이터로도 파싱되는지 봄. 고정 데이터만 쓰면 놓치는 게 있음.

    어느 recipe 든 상관없음. 보는 것은 "실제 데이터로 DOT 이 파싱되는가"
    하나뿐이라 첫 번째를 씀. 번호를 적어 두면 온톨로지가 바뀌어 번호가
    밀렸을 때 없는 recipe 를 가리키게 됨.
    """
    from demo.api.services.ontology_service import recipe_ids
    from ontology.graph import highlight_edges, recipe_nodes

    if not shutil.which("dot"):
        pytest.skip("graphviz 가 설치되어 있지 않다")

    sample = recipe_ids()[0]
    nodes, solid, dotted = domain_graph()
    svg = render_svg(
        build_dot(
            nodes,
            solid,
            dotted,
            highlight=highlight_edges(sample),
            highlight_nodes=recipe_nodes(sample),
        )
    )

    assert "<svg" in svg
    assert nodes["spoken_place"]["name"] in svg, "한글 라벨이 SVG 에 실리지 않았다."
