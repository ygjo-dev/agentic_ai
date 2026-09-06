"""대상 : app/ui/graph/ — 노드가 안 겹친다. **눈이 못 보는 것을 본다**

`test_layout_invariants.py` 옆에 나란히 두는 두 번째 안전줄이다.

    노드가 안 움직인다   좌표가 3pt 밀린 것은 화면을 봐도 모른다
    노드가 안 겹친다     한 쌍이 붙은 것은 48개 중에서 못 찾는다

2026-08-29 에 글씨를 16 -> 24 로 올리고 좌표를 0.64 배로 당겼다(하정목 박사님
피드백 ③). 둘은 서로를 밀어낸다 — 글씨를 키우면 노드가 커져 붙고, 좌표를
당기면 노드가 가까워져 붙는다. 다음에 어느 한쪽을 또 건드리는 사람이 있을 때
**어디까지 갈 수 있는지를 말해주는 것이 이 파일이다.**

겹침은 `neato -n -Tdot` 이 내주는 노드 상자로 잰다 — 프로덕션이 새 노드를
놓을 자리를 고를 때 쓰는 것과 **같은 함수**(graphviz.node_boxes)다. 그리는
그림에서 재지 않는 이유는 그 함수의 제약 절에 있다.

**여유 0 이 아니라 MIN_GAP 을 요구한다.** 0 으로 두면 이름 한 글자가 길어진
다음 등록에서 바로 붙는다. 여유가 있어야 시험이 미리 운다.
"""

import itertools
import shutil

import pytest

from app.api.services.streamlit.screen_service import domain_graph
from app.ui.graph.build import wrap_node_labels
from app.ui.graph.dot import GROUP_ATTRS, NODE_ATTRS, build_dot
from app.ui.graph import layout_store
from app.ui.graph.graphviz import node_boxes
from app.ui.graph.layout_store import (
    DRAW_SCALE,
    for_drawing,
    load,
)

pytestmark = pytest.mark.skipif(
    shutil.which("neato") is None, reason="graphviz 가 설치되어 있지 않다"
)

# 노드 사이에 남아야 하는 최소 빈 거리(pt). 0.64 배에서 실측 10.7pt 였다.
# 10 을 요구한다 — 지금 값이 아슬아슬하게 통과하는 것이 아니라 여유가 있다는
# 뜻이고, 배율을 0.63 으로 내리면 이 시험이 운다.
MIN_GAP = 8.0

def touching_pairs(boxes: dict, gap: float = MIN_GAP) -> list[tuple[str, str]]:
    """gap 만큼 떨어져 있지 않은 노드 쌍. 비어 있어야 한다."""
    pairs = []
    for (a, one), (b, other) in itertools.combinations(boxes.items(), 2):
        ax, ay, aw, ah = one
        bx, by, bw, bh = other
        if (
            abs(ax - bx) - (aw + bw) / 2 < gap
            and abs(ay - by) - (ah + bh) / 2 < gap
        ):
            pairs.append((a, b))
    return pairs


def drawn_dot(positions=None, nodes=None, solid=None, dotted=None):
    """배치를 재는 것과 같은 DOT. layout_store._drawn_boxes 를 그대로 흉내낸다.

    ★ **한 벌뿐이다.** 2026-09-06 까지는 상단 · 하단이 서로 다른 속성 벌로
    그려져 둘을 따로 쟀는데, 그림 만들기를 걷으면서 그 두 벌이 없어졌다 —
    좌표를 재는 스타일은 이제 하나다.
    """
    if nodes is None:
        nodes, solid, dotted = domain_graph()
    if positions is None:
        positions = load()
    return build_dot(
        wrap_node_labels(nodes),
        solid,
        dotted,
        positions=for_drawing(positions),
        spring=True,
        dotted_labels=False,
        node_attrs=NODE_ATTRS,
        group_attrs=GROUP_ATTRS,
    )


def test_no_two_nodes_touch():
    """실제 온톨로지 · 저장된 좌표 · 지금 글씨 크기에서 겹치는 쌍이 없어야 함."""
    boxes = node_boxes(drawn_dot())

    assert len(boxes) == len(domain_graph()[0])
    assert touching_pairs(boxes) == []


def registered(tmp_path, monkeypatch, extra: list[str]) -> tuple:
    """지금 지도에 노드를 차례로 등록해 본 결과.

    입력  tmp_path · monkeypatch · 새로 등록할 노드 이름들
    출력  (좌표, 노드, 실선, 점선)
    규칙  등록이 실제로 지나는 길(ensure_positions)을 그대로 탐. 진짜 좌표
          파일은 안 건드리고 tmp 로 옮겨 담아 「지금 지도에 하나 더」를 만듦
    """
    layout = tmp_path / "layout.json"
    monkeypatch.setattr(layout_store, "LAYOUT_PATH", layout)
    layout_store.save(load(), layout)

    nodes, solid, dotted = domain_graph()
    positions = None
    for name in extra:
        nodes = {**nodes, name: {"name": "구조물 균열 추세 분석"}}
        solid = list(solid) + [(solid[0][1], name)]
        positions = layout_store.ensure_positions(nodes, solid, dotted)
    return positions, nodes, solid, dotted


def test_registering_a_node_does_not_make_it_touch(tmp_path, monkeypatch):
    """새로 놓인 노드도 붙으면 안 됨. 등록이 시연의 핵심 장면임.

    ★ 등록이 실제로 지나는 길로 잼. 2026-09-06 까지는 그 길의 가운데 토막
    (build_dot + layout_positions)만 흉내 냈는데, 겹치면 새 노드만 밖으로
    미는 자리가 그 뒤에 생겨(layout_store.settled) 흉내가 등록을 대표하지
    못하게 됐음. 흉내로 재면 그 자리를 통째로 못 봄.
    """
    grown, nodes, solid, dotted = registered(tmp_path, monkeypatch, ["probe_new_node"])

    boxes = node_boxes(
        drawn_dot(positions=grown, nodes=nodes, solid=solid, dotted=dotted)
    )

    assert "probe_new_node" in boxes
    assert touching_pairs(boxes) == []


def test_the_registered_node_never_moves_the_old_ones(tmp_path, monkeypatch):
    """새 노드를 놓느라 기존 노드를 밀면 「지도가 리셋됐다」로 보임.

    ★ 겹침 제거(overlap)를 안 쓰는 까닭이 이것임 — 그것은 고정을 무시하고
    기존 노드를 388~710pt 씩 움직임(실측). 미는 것은 새 노드 하나뿐임.
    """
    before = load()

    grown, _, _, _ = registered(tmp_path, monkeypatch, ["probe_new_node"])

    assert all(grown[node_id] == tuple(point) for node_id, point in before.items())


def test_a_smaller_scale_would_make_nodes_touch():
    """음성 대조군. 이 시험이 실제로 겹침을 잡는지 본다.

    지금 배율이 겹침 직전이라는 뜻이기도 함 — 더 당기려면 글씨를 줄여야 함.
    """
    nodes, solid, dotted = domain_graph()
    tight = build_dot(
        wrap_node_labels(nodes), solid, dotted,
        positions=for_drawing(load(), DRAW_SCALE * 0.6),
        spring=True, dotted_labels=False, node_attrs=NODE_ATTRS,
        group_attrs=GROUP_ATTRS,
    )

    assert touching_pairs(node_boxes(tight)) != []
