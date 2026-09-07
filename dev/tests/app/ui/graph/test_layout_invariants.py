"""대상 : app/ui/graph/ — 배치 불변식. **눈이 못 보는 것을 본다**

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
`inputscale=72` · 핀이 있으면 `overlap` 금지.
**지우면 다시 알아낼 방법이 없다.**

원래 있던 곳 (전부 이 파일로 옮겼고 그 파일들은 지웠다) :
`test_neato_layout.py` · `test_bottom_flow.py` · `test_top_relations.py` ·
`test_build_dot.py`(연기 감지 하나).
**본문은 옮기기만 했다.** 실측으로 얻은 단언이라 손대면 무엇을 재던 것인지 잃는다.

★ **2026-09-06 에 재는 자를 SVG 에서 DOT 으로 갈았다.** 좌표를 SVG 의
`<text x= y=>` 에서 긁던 것을 `neato -n -Tdot` 이 그대로 적어 주는 pos 로
바꿨다 — 같은 엔진 · 같은 값이고 출력 형식만 다르다(graphviz.node_boxes 의
제약 절이 그것이다).

★ **같은 날 그리기 표시 아홉을 지웠다.** highlight · mark · dim · 화살표 ·
실선 끄기 · 점선 굵기 · 상단 스타일이 좌표를 안 바꾼다는 짝들이다. 그 인자가
build_dot 에서 통째로 사라져 **이제 구조로 불가능하다** — DOT 에는 강조라는
개념이 없다. 후보를 좁혀도 좌표가 같다는 것은 지금
`dev/tests/app/api/test_register_colours.py` 와
`dev/tests/app/ui/test_graph_library.py` 가 화면 쪽에서 지킨다.
"""

import shutil

import pytest

from app.api.services.streamlit.screen_service import domain_graph
from app.ui.graph.dot import NODE_ATTRS, build_dot
from app.ui.graph.graphviz import layout_positions, node_boxes
from app.ui.graph import layout_store
from app.ui.graph.layout_store import (
    NEATO_ATTRS,
    NEATO_FRESH_ATTRS,
    NEATO_SPREAD_ATTRS,
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


def fresh_positions(nodes=NODES, solid=SOLID, dotted=DOTTED):
    """핀 없는 최초 배치. 겹침 제거를 쓸 수 있는 유일한 경우."""
    return layout_positions(
        build_dot(nodes, solid, dotted, spring=True, graph_attrs=NEATO_FRESH_ATTRS)
    )


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


def drawn_centres(positions, **kwargs) -> dict[str, tuple[float, float]]:
    """그 좌표로 그렸을 때 노드가 실제로 놓이는 자리. -n 이라 재계산이 없음."""
    boxes = node_boxes(
        build_dot(
            NODES, SOLID, DOTTED,
            positions=positions, spring=True, node_attrs=NODE_ATTRS, **kwargs,
        )
    )
    return {node_id: (x, y) for node_id, (x, y, _, _) in boxes.items()}


def test_positions_actually_pin_the_layout():
    """좌표를 넘기면 그 좌표대로 놓여야 함.

    판별력 확인 : 서로 다른 좌표를 주면 결과도 달라야 함. positions 를
    무시하는 구현(부르는 쪽이 positions= 를 빠뜨림)이면 두 결과가 같아져
    여기서 잡힘.

    노드 하나만 옮김. 전부 같은 만큼 옮기면 캔버스 정규화가 흡수해 버려
    화면상 차이가 없음. 그러면 이 테스트가 아무것도 판별하지 못함.
    """
    positions = fresh_positions()
    one = sorted(positions)[0]
    moved = {**positions, one: (positions[one][0] + 120, positions[one][1] + 60)}

    base = drawn_centres(positions, dotted_labels=False)
    assert len(base) == len(NODES), "노드 좌표를 못 읽었다 — 검사가 무력하다"
    assert drawn_centres(moved, dotted_labels=False) != base


def test_reviving_dotted_labels_never_moves_a_node():
    """3A 에서 숨긴 라벨을 되살려도 노드가 밀리면 안 됨.

    **지금도 살아 있는 인자다.** 배치는 라벨을 끈 채로 재고
    (layout_store 가 dotted_labels=False 로 부른다), 켜면 상자가 커질 수 있다.
    """
    positions = fresh_positions()

    off = drawn_centres(positions, dotted_labels=False)
    assert len(off) == len(NODES), "노드 좌표를 못 읽었다 — 검사가 무력하다"
    assert drawn_centres(positions, dotted_labels=True) == off


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
    """최초와 증분이 다른 모델이면 새 노드가 다른 규칙으로 놓여 어색해짐.

    모델 이름을 박지 않음. 예전에는 둘 다 model=subset 이었고 지금은 둘 다
    기본값임 — 지켜야 하는 것은 어느 모델이냐가 아니라 둘이 같다는 것임.
    """
    models = [
        {attr for attr in attrs if attr.startswith(("model=", "mode="))}
        for attrs in (NEATO_ATTRS, NEATO_FRESH_ATTRS)
    ]

    assert models[0] == models[1]


def test_overlap_removal_is_not_used_when_pinning():
    """overlap 은 고정(!)을 무시하고 재배치함. 핀이 있으면 쓰면 안 됨.

    실측으로 388~710pt 씩 움직였음. 이 테스트는 그 설정이 되살아나는 것을 막음.
    겹침 제거를 쓰는 설정이 둘로 늘었으므로(최초 voronoi · 늘리기 prism)
    핀을 쓰는 증분 설정에만 없으면 됨.
    """
    assert "overlap" not in " ".join(NEATO_ATTRS)
    assert "overlap=voronoi" in " ".join(NEATO_FRESH_ATTRS)
    assert "overlap=prism" in " ".join(NEATO_SPREAD_ATTRS)


def test_spreading_never_pins():
    """늘리기는 겹침 제거를 쓰므로 좌표를 못박으면 안 됨.

    못박으면 겹침 제거가 그것을 무시하고 재배치함 — 핀이 있는데 overlap 을
    쓰는 바로 그 잘못된 설정이 됨. 시작 위치로만 넘겨야 함.
    """
    emitted = []
    original = layout_store.layout_positions

    def spy(dot):
        emitted.append(dot)
        return original(dot)

    layout_store.layout_positions = spy
    try:
        layout_store.spread(NODES, SOLID, DOTTED, fresh_positions())
    finally:
        layout_store.layout_positions = original

    assert emitted
    assert "pos=" in emitted[0]
    assert '!"' not in emitted[0]


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

    **겹침 제거를 쓰게 된 뒤에도 이 짝의 뜻은 안 바뀌었음.** 겹침 제거는
    좌표를 못박지 않는 자리(최초 배치 · 늘리기)에서만 씀. 못박은 자리에
    되살아나는 것을 막는 것이 이 짝의 일이고, 그 자리는 증분 배치 하나뿐임.
    """
    before, after = dense_after_adding(BARE_FRESH_ATTRS)

    assert worst_drift(before, after) > 1.0


# ------------------------------------------------------------ 연기 감지
def test_graphviz_accepts_the_real_ontology():
    """실제 데이터로도 파싱되는지 봄. 고정 데이터만 쓰면 놓치는 게 있음.

    온톨로지를 손보다 DOT 이 깨지면 좌표를 못 받아 화면이 백지가 되는데,
    실제 데이터를 한 번 통과시키는 이것 하나면 잡힌다.
    """
    if not shutil.which("neato"):
        pytest.skip("graphviz 가 설치되어 있지 않다")

    nodes, solid, dotted = domain_graph()
    boxes = node_boxes(
        build_dot(nodes, solid, dotted, positions=fresh_real_positions(), spring=True)
    )

    assert set(boxes) == set(nodes), "실제 온톨로지의 노드 좌표를 다 못 받았다"
    assert all(width > 0 and height > 0 for _, _, width, height in boxes.values())


def fresh_real_positions():
    """실제 온톨로지의 최초 배치. 한글 라벨이 여기서 Graphviz 를 지난다."""
    nodes, solid, dotted = domain_graph()
    return layout_positions(
        build_dot(nodes, solid, dotted, spring=True, graph_attrs=NEATO_FRESH_ATTRS)
    )
