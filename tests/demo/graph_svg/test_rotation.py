"""대상 : demo/graph_svg/layout_store.py — 최초 배치 회전

최초 배치 좌표 회전 검증.

힘 기반 배치는 그래프 모양에 따라 세로로 길게 나오기도 한다. 좌표를 파일로
들고 있으므로 축만 바꿔치면 가로로 눕는다.

**회전 다음에 늘리기(spread)가 온다.** 회전만 떼어 보려는 검사는 그 둘을
갈라야 하므로 spread 를 항등으로 바꿔 끼운다 — 안 그러면 늘어난 좌표가
회전 결과를 덮어 무엇을 재는지 알 수 없다.

**가장 중요한 것은 언제 눕히느냐다.** 최초 배치에서만 해야 한다. 증분 배치에
들어가는 핀 좌표는 이미 눕혀둔 값이라, 또 바꾸면 지도가 뒤집히고 기존 노드가
전부 움직인다 — 한 번은 통과하고 두 번째 등록에서 터지는 자리다.
"""

import shutil

import pytest

from demo.graph_svg import layout_store
from demo.graph_svg.dot import (
    GROUP_ATTRS,
    NODE_ATTRS,
    build_dot,
    wrap_node_labels,
)
from demo.graph_svg.graphviz import layout_positions
from demo.graph_svg.layout_store import NEATO_FRESH_ATTRS, ensure_positions

pytestmark = pytest.mark.skipif(
    shutil.which("neato") is None, reason="graphviz 가 설치되어 있지 않다"
)

GRAPH = {
    "version": "test",
    "interfaces": ["MediaData", "AnalysisResult", "DocumentData"],
    "nodes": {
        "load_cctv": {"name": "승강장 CCTV 불러오기", "description": "", "inputs": [],
                      "outputs": ["MediaData"], "properties": {"source": "cctv"}},
        "load_car": {"name": "검측차 이미지 불러오기", "description": "", "inputs": [],
                     "outputs": ["MediaData"], "properties": {"source": "cctv"}},
        "analyze": {"name": "승강장 혼잡도 분석", "description": "", "inputs": ["MediaData"],
                    "outputs": ["AnalysisResult"], "properties": {}},
        "generate_word": {"name": "Word 생성", "description": "", "inputs": ["AnalysisResult"],
                          "outputs": ["DocumentData"], "properties": {}},
    },
    "solid_edges": [
        {"from": "load_cctv", "to": "analyze", "interface": "MediaData"},
        {"from": "load_car", "to": "analyze", "interface": "MediaData"},
        {"from": "analyze", "to": "generate_word", "interface": "AnalysisResult"},
    ],
    "dotted_edges": [{"a": "load_cctv", "b": "load_car", "labels": ["source: cctv"]}],
}


@pytest.fixture
def no_spread(monkeypatch):
    """늘리기를 항등으로. 회전 분기만 보려는 검사에 씀."""
    monkeypatch.setattr(
        layout_store, "spread", lambda nodes, solid, dotted, positions: positions
    )


def graph_with_extra_node(node_id: str, feeder: str = "analyze") -> dict:
    """노드를 하나 더한 그래프. 등록을 흉내냄."""
    return {
        **GRAPH,
        "nodes": {
            **GRAPH["nodes"],
            node_id: {"name": f"새 노드 {node_id}", "description": "",
                      "inputs": ["AnalysisResult"], "outputs": [], "properties": {}},
        },
        "solid_edges": [
            *GRAPH["solid_edges"],
            {"from": feeder, "to": node_id, "interface": "AnalysisResult"},
        ],
    }


def domain(graph: dict) -> tuple[dict, dict, dict]:
    """fixture 를 ensure_positions 가 받는 도메인 형태로.

    예전에는 프로덕션의 to_build_dot_args 가 하던 일. 그리기가 서버로
    들어가면서 JSON 왕복이 사라져 어댑터도 없어졌고, 여기서는 fixture 를
    쓰기 좋게 펴는 용도로만 남음.
    """
    return (
        graph["nodes"],
        {(e["from"], e["to"]): e["interface"] for e in graph["solid_edges"]},
        {(e["a"], e["b"]): e["labels"] for e in graph["dotted_edges"]},
    )


@pytest.fixture
def store(tmp_path, monkeypatch):
    """저장소의 layout.json 을 안 건드림."""
    monkeypatch.setattr(layout_store, "LAYOUT_PATH", tmp_path / "layout.json")
    return tmp_path / "layout.json"


def anchored(positions: dict, keys: list[str]) -> dict:
    """첫 노드를 원점으로 옮긴 상대 좌표.

    neato 는 배치를 캔버스에 맞춰 평행이동시킴. 절대 좌표로 비교하면 그
    평행이동까지 "움직였다" 로 세는데, 화면에는 안 보이는 차이임(실측으로 확인).
    """
    ox, oy = positions[keys[0]]
    return {k: (positions[k][0] - ox, positions[k][1] - oy) for k in keys}


def worst_drift(before: dict, after: dict) -> float:
    keys = sorted(n for n in before if n in after)
    a, b = anchored(before, keys), anchored(after, keys)
    return max(max(abs(b[k][0] - a[k][0]), abs(b[k][1] - a[k][1])) for k in keys)


# ------------------------------------------------------------ 순수 함수
def test_transpose_swaps_x_and_y():
    assert layout_store.transpose({"a": (1.0, 2.0), "b": (3.5, 4.5)}) == {
        "a": (2.0, 1.0),
        "b": (4.5, 3.5),
    }


def test_transpose_twice_is_the_original():
    positions = {"a": (1.0, 2.0), "b": (3.5, 4.5)}

    assert layout_store.transpose(layout_store.transpose(positions)) == positions


def test_transpose_of_nothing_is_nothing():
    assert layout_store.transpose({}) == {}


def test_transpose_preserves_relative_distances():
    """교차 · 간격 · 겹침이 보존되는 근거."""
    positions = {"a": (0.0, 0.0), "b": (30.0, 40.0)}
    flipped = layout_store.transpose(positions)

    def distance(p):
        (x0, y0), (x1, y1) = p["a"], p["b"]
        return ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5

    assert distance(positions) == distance(flipped)


def test_only_a_tall_layout_is_tipped_over():
    """목적은 "회전한다" 가 아니라 "가로로 눕힌다" 임.

    조건 없이 눕히면 이미 가로로 긴 배치를 세로로 세워버림. 실제로 그랬음.
    온톨로지를 바꾸자 최초 배치가 H/W 0.83 으로 나왔는데 거기 또 회전을 걸어
    1.09 로 만들고 있었고, 패널 폭 사용이 49% 에서 37% 로 떨어졌음.
    """
    assert layout_store.is_tall({"a": (0.0, 0.0), "b": (10.0, 100.0)})
    assert not layout_store.is_tall({"a": (0.0, 0.0), "b": (100.0, 10.0)})

    # 정확히 정방형이면 눕혀도 얻는 것이 없다.
    assert not layout_store.is_tall({"a": (0.0, 0.0), "b": (50.0, 50.0)})

    # 눕힐 것이 없으면 0 으로 나누지도 않는다.
    assert not layout_store.is_tall({})
    assert not layout_store.is_tall({"a": (1.0, 2.0)})


# ------------------------------------------------------------ 최초 배치
def test_a_tall_fresh_layout_is_tipped_over(store, monkeypatch, no_spread):
    """배치가 세로로 길게 나오면 눕혀서 저장함.

    neato 가 어느 방향으로 놓을지는 그래프 모양에 달렸음. 그것에 기대면 검사가
    온톨로지를 바꿀 때마다 흔들리므로, 배치 결과를 고정해 분기만 봄.
    """
    tall = {"a": (0.0, 0.0), "b": (10.0, 300.0), "c": (20.0, 600.0)}
    monkeypatch.setattr(layout_store, "layout_positions", lambda dot: dict(tall))

    saved = ensure_positions(*domain(GRAPH))

    assert saved == layout_store.transpose(tall)
    assert not layout_store.is_tall(saved)


def test_a_wide_fresh_layout_is_left_alone(store, monkeypatch, no_spread):
    """이미 가로로 길면 그대로 둠. 눕히면 오히려 세로로 세워짐.

    실제로 그랬음. 온톨로지를 바꾸자 최초 배치가 H/W 0.83 으로 나왔는데 거기
    또 회전을 걸어 1.09 로 만들고 있었고, 패널 폭 사용이 49% 에서 37% 로 떨어졌음.
    """
    wide = {"a": (0.0, 0.0), "b": (300.0, 10.0), "c": (600.0, 20.0)}
    monkeypatch.setattr(layout_store, "layout_positions", lambda dot: dict(wide))

    saved = ensure_positions(*domain(GRAPH))

    assert saved == wide
    assert not layout_store.is_tall(saved)


def test_a_fresh_layout_never_ends_up_tall(store):
    """실제 neato 배치로도 결과가 세로로 길지 않아야 함.

    위 두 검사는 배치를 고정해 분기만 봤음. 여기서는 진짜 배치를 태움.
    분기 조건과 실제 좌표가 어긋나면 여기서 잡힘.
    """
    saved = ensure_positions(*domain(GRAPH))

    assert saved
    assert not layout_store.is_tall(saved)


def test_the_rotation_does_not_invent_coordinates(store, no_spread):
    """회전은 축을 맞바꿀 뿐임. 두 폭이 그대로이거나 맞바뀐 것이어야 함.

    늘리기를 빼고 봄. 늘리기는 일부러 폭을 바꾸는 단계라 함께 보면 이 성질을
    잴 수가 없음.
    """
    saved = ensure_positions(*domain(GRAPH))

    nodes, solid, dotted = domain(GRAPH)
    raw = layout_positions(
        build_dot(wrap_node_labels(nodes), solid, dotted, positions={}, spring=True,
                  graph_attrs=NEATO_FRESH_ATTRS, dotted_labels=False,
                  node_attrs=NODE_ATTRS, group_attrs=GROUP_ATTRS)
    )

    def spans(p):
        xs = [v[0] for v in p.values()]
        ys = [v[1] for v in p.values()]
        return round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3)

    assert sorted(spans(saved)) == sorted(spans(raw))


def test_spreading_widens_the_layout(store):
    """늘리기가 실제로 가로를 벌려야 함. 안 걸리면 화면 폭을 못 씀."""
    nodes, solid, dotted = domain(GRAPH)
    before = layout_positions(
        build_dot(wrap_node_labels(nodes), solid, dotted, positions={}, spring=True,
                  graph_attrs=NEATO_FRESH_ATTRS, dotted_labels=False,
                  node_attrs=NODE_ATTRS, group_attrs=GROUP_ATTRS)
    )

    after = layout_store.spread(nodes, solid, dotted, before)

    def ratio(p):
        xs = [v[0] for v in p.values()]
        ys = [v[1] for v in p.values()]
        return (max(ys) - min(ys)) / (max(xs) - min(xs))

    assert ratio(after) < ratio(before)


# ------------------------------------------------------------ 증분 배치 (핵심)
def test_incremental_layout_does_not_transpose(store):
    """증분에서 또 눕히면 지도가 뒤집히고 기존 노드가 전부 움직임."""
    before = ensure_positions(*domain(GRAPH))

    after = ensure_positions(*domain(graph_with_extra_node("new_one")))

    assert worst_drift(before, after) < 0.51


def test_two_registrations_in_a_row_keep_the_map(store):
    """연달아 등록해도 지도가 그대로여야 함.

    중간 상태도 함께 봄. 회전이 매번 걸리는 버그는 홀수 번째에서만 드러남.
    두 번 걸리면 서로 상쇄돼 처음과 같은 방향으로 돌아옴. 마지막만 비교하면
    그 상쇄 때문에 통과해 버림(실측으로 확인했음).
    """
    first = ensure_positions(*domain(GRAPH))

    second = ensure_positions(*domain(graph_with_extra_node("new_one")))
    assert worst_drift(first, second) < 0.51, "1회 등록에서 이미 틀어졌다"

    third = ensure_positions(
        *domain({
            **graph_with_extra_node("new_one"),
            "nodes": {
                **graph_with_extra_node("new_one")["nodes"],
                "new_two": {"name": "새 노드 둘", "description": "",
                            "inputs": ["AnalysisResult"], "outputs": [], "properties": {}},
            },
            "solid_edges": [
                *graph_with_extra_node("new_one")["solid_edges"],
                {"from": "analyze", "to": "new_two", "interface": "AnalysisResult"},
            ],
        })
    )

    assert worst_drift(first, third) < 0.51


def test_nothing_missing_means_no_layout_run(store):
    """좌표가 다 있으면 neato 를 부르지 않음. 부르면 회전이 또 걸릴 위험이 있음."""
    first = ensure_positions(*domain(GRAPH))

    assert ensure_positions(*domain(GRAPH)) == first
