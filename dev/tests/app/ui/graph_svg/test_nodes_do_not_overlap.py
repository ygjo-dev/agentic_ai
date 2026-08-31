"""대상 : app/ui/graph_svg/ — 노드가 안 겹친다. **눈이 못 보는 것을 본다**

`test_layout_invariants.py` 옆에 나란히 두는 두 번째 안전줄이다.

    노드가 안 움직인다   좌표가 3pt 밀린 것은 화면을 봐도 모른다
    노드가 안 겹친다     한 쌍이 붙은 것은 48개 중에서 못 찾는다

2026-08-29 에 글씨를 16 -> 24 로 올리고 좌표를 0.64 배로 당겼다(하정목 박사님
피드백 ③). 둘은 서로를 밀어낸다 — 글씨를 키우면 노드가 커져 붙고, 좌표를
당기면 노드가 가까워져 붙는다. 다음에 어느 한쪽을 또 건드리는 사람이 있을 때
**어디까지 갈 수 있는지를 말해주는 것이 이 파일이다.**

겹침은 `neato -n -Tdot` 이 내주는 노드 상자로 잰다. SVG 로 재지 않는 이유 :
`style="rounded,filled"` 라 노드가 <path> 로 나오고 거기서 사각형을 되찾으려면
경로 문자열을 파싱해야 한다. 같은 DOT · 같은 엔진이고 출력 형식만 다르다.

**여유 0 이 아니라 MIN_GAP 을 요구한다.** 0 으로 두면 이름 한 글자가 길어진
다음 등록에서 바로 붙는다. 여유가 있어야 시험이 미리 운다.
"""

import itertools
import re
import shutil

import pytest

from app.api.services.ontology_service import domain_graph
from app.ui.graph_svg.build import wrap_node_labels
from app.ui.graph_svg.dot import (
    GROUP_ATTRS,
    GROUP_ATTRS_TOP,
    NODE_ATTRS,
    NODE_ATTRS_TOP,
    build_dot,
)
from app.ui.graph_svg.graphviz import _run_graphviz, layout_positions
from app.ui.graph_svg.layout_store import (
    DRAW_SCALE,
    NEATO_ATTRS,
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

# 엣지에도 pos(스플라인)가 붙는다. 노드만 골라내려면 엣지 문장을 먼저 지운다.
_EDGE_STATEMENT = re.compile(r'"?[\w]+"?\s*->\s*"?[\w]+"?\s*\[[^\]]*\];')
_NODE_STATEMENT = re.compile(r'"?([A-Za-z_]\w*)"?\s*\[([^\]]*)\]\s*;')
_POS_ATTR = re.compile(r'pos="([-\d.e+]+),([-\d.e+]+)')
_WIDTH_ATTR = re.compile(r'width="?([\d.]+)')
_HEIGHT_ATTR = re.compile(r'height="?([\d.]+)')


def node_boxes(dot: str) -> dict[str, tuple[float, float, float, float]]:
    """그려질 노드 사각형. {node_id: (중심x, 중심y, 폭, 높이)} 단위 pt."""
    out = _run_graphviz(dot, "neato", ["-n", "-Tdot"])
    flat = _EDGE_STATEMENT.sub(" ", re.sub(r"\s+", " ", out))

    boxes = {}
    for match in _NODE_STATEMENT.finditer(flat):
        body = match.group(2)
        pos = _POS_ATTR.search(body)
        width = _WIDTH_ATTR.search(body)
        height = _HEIGHT_ATTR.search(body)
        if pos and width and height:
            boxes[match.group(1)] = (
                float(pos.group(1)),
                float(pos.group(2)),
                float(width.group(1)) * 72,   # 인치로 나온다
                float(height.group(1)) * 72,
            )
    return boxes


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


def drawn_dot(top: bool = False, positions=None, nodes=None, solid=None, dotted=None):
    """화면에 나가는 것과 같은 DOT. build.py 의 두 갈래를 그대로 흉내낸다."""
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
        draw_solid=not top,
        node_attrs=NODE_ATTRS_TOP if top else NODE_ATTRS,
        group_attrs=GROUP_ATTRS_TOP if top else GROUP_ATTRS,
    )


@pytest.mark.parametrize("top", [False, True], ids=["하단", "상단"])
def test_no_two_nodes_touch(top):
    """실제 온톨로지 · 저장된 좌표 · 지금 글씨 크기에서 겹치는 쌍이 없어야 함."""
    boxes = node_boxes(drawn_dot(top=top))

    assert len(boxes) == len(domain_graph()[0])
    assert touching_pairs(boxes) == []


def test_registering_a_node_does_not_make_it_touch():
    """새로 놓인 노드도 붙으면 안 됨. 등록이 시연의 핵심 장면임."""
    nodes, solid, dotted = domain_graph()
    stored = load()

    nodes = {**nodes, "probe_new_node": {"name": "구조물 균열 추세 분석"}}
    solid = list(solid) + [(solid[0][1], "probe_new_node")]
    # 증분 배치는 저장된 좌표계에서 돈다. 배율은 그린 뒤에 곱한다.
    grown = layout_positions(
        build_dot(nodes, solid, dotted, positions=stored, spring=True,
                  graph_attrs=NEATO_ATTRS)
    )

    boxes = node_boxes(
        drawn_dot(positions=grown, nodes=nodes, solid=solid, dotted=dotted)
    )

    assert "probe_new_node" in boxes
    assert touching_pairs(boxes) == []


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
