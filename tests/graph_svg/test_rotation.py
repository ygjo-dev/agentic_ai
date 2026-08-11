"""대상 : demo/api/graph_svg/layout_store.py — 최초 배치 회전

최초 배치 좌표 회전 검증.

model=subset 은 교차가 적은 대신 세로로 길다(H/W 1.38). 좌표를 파일로 들고
있으므로 축만 바꿔치면 가로로 눕는다(0.65).

**가장 중요한 것은 언제 눕히느냐다.** 최초 배치에서만 해야 한다. 증분 배치에
들어가는 핀 좌표는 이미 눕혀둔 값이라, 또 바꾸면 지도가 뒤집히고 기존 노드가
전부 움직인다 — 한 번은 통과하고 두 번째 등록에서 터지는 자리다.
"""

import shutil

import pytest

from demo.api.graph_svg import layout_store
from demo.api.graph_svg.dot import build_dot
from demo.api.graph_svg.graphviz import layout_positions
from demo.api.graph_svg.layout_store import NEATO_FRESH_ATTRS, ensure_positions

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


def graph_with_extra_node(node_id: str, feeder: str = "analyze") -> dict:
    """노드를 하나 더한 그래프. 등록을 흉내낸다."""
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

    예전에는 프로덕션의 to_build_dot_args 가 하던 일이다. 그리기가 서버로
    들어가면서 JSON 왕복이 사라져 어댑터도 없어졌고, 여기서는 fixture 를
    쓰기 좋게 펴는 용도로만 남는다.
    """
    return (
        graph["nodes"],
        {(e["from"], e["to"]): e["interface"] for e in graph["solid_edges"]},
        {(e["a"], e["b"]): e["labels"] for e in graph["dotted_edges"]},
    )


@pytest.fixture
def store(tmp_path, monkeypatch):
    """저장소의 layout.json 을 건드리지 않는다."""
    monkeypatch.setattr(layout_store, "LAYOUT_PATH", tmp_path / "layout.json")
    return tmp_path / "layout.json"


def anchored(positions: dict, keys: list[str]) -> dict:
    """첫 노드를 원점으로 옮긴 상대 좌표.

    neato 는 배치를 캔버스에 맞춰 평행이동시킨다. 절대 좌표로 비교하면 그
    평행이동까지 "움직였다" 로 세는데, 화면에는 안 보이는 차이다(작업 2에서 확인).
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
    """교차 · 간격 · 겹침이 보존되는 근거다."""
    positions = {"a": (0.0, 0.0), "b": (30.0, 40.0)}
    flipped = layout_store.transpose(positions)

    def distance(p):
        (x0, y0), (x1, y1) = p["a"], p["b"]
        return ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5

    assert distance(positions) == distance(flipped)


# ------------------------------------------------------------ 최초 배치
def test_fresh_layout_is_transposed(store):
    """눕히지 않으면 세로로 길어 가로 패널을 못 채운다."""
    saved = ensure_positions(*domain(GRAPH))

    nodes, solid, dotted = domain(GRAPH)
    raw = layout_positions(
        build_dot(nodes, solid, dotted, positions={}, spring=True,
                  graph_attrs=NEATO_FRESH_ATTRS)
    )

    assert saved == layout_store.transpose(raw)
    assert saved != raw  # 정방형이면 같아질 수 있다 — 이 fixture 는 아니다


def test_fresh_layout_swaps_the_spans(store):
    """가로 폭과 세로 높이가 맞바뀐다.

    "가로로 눕는다" 를 직접 단언하지 않는다 — 그것은 그래프 모양에 달린 것이고
    코드의 성질이 아니다. 코드가 보장하는 것은 두 축이 바뀐다는 것뿐이다.
    """
    saved = ensure_positions(*domain(GRAPH))

    nodes, solid, dotted = domain(GRAPH)
    raw = layout_positions(
        build_dot(nodes, solid, dotted, positions={}, spring=True,
                  graph_attrs=NEATO_FRESH_ATTRS)
    )

    def spans(p):
        xs = [v[0] for v in p.values()]
        ys = [v[1] for v in p.values()]
        return round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3)

    assert spans(saved) == spans(raw)[::-1]


# ------------------------------------------------------------ 증분 배치 (핵심)
def test_incremental_layout_does_not_transpose(store):
    """증분에서 또 눕히면 지도가 뒤집히고 기존 노드가 전부 움직인다."""
    before = ensure_positions(*domain(GRAPH))

    after = ensure_positions(*domain(graph_with_extra_node("new_one")))

    assert worst_drift(before, after) < 0.51


def test_two_registrations_in_a_row_keep_the_map(store):
    """연달아 등록해도 지도가 그대로여야 한다.

    중간 상태도 함께 본다. 회전이 매번 걸리는 버그는 **홀수 번째에서만** 드러난다 —
    두 번 걸리면 서로 상쇄돼 처음과 같은 방향으로 돌아온다. 마지막만 비교하면
    그 상쇄 때문에 통과해 버린다(실측으로 확인했다).
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
    """좌표가 다 있으면 neato 를 부르지 않는다 — 부르면 회전이 또 걸릴 위험이 있다."""
    first = ensure_positions(*domain(GRAPH))

    assert ensure_positions(*domain(GRAPH)) == first
