"""대상 : app/ui/graph_svg/layout.json — 그리는 노드마다 좌표가 있는가

**관문이다.** 온톨로지에 노드를 더하면 `layout.json` 에 좌표가 없어 그래프가
통째로 안 그려진다 — `neato -n` 이 `node ... has no position as required by the
-n flag` 로 거부한다. 등록 화면(POST /nodes)을 거치면 좌표가 붙지만 파일을 직접
고치면 안 붙는다. 2026-08-28 시연에서 그렇게 깨졌다 (NOTES.md 「마흔여섯째」).

좌표 파일은 gitignore 라 저장소에 안 들어간다. 그래서 「커밋에 좌표가 들어
있는가」로는 못 막고, 노드를 더한 사람의 장비에서 이 시험이 잡는다.

**형식 노드는 안 그린다.** 그리는 노드가 무엇인지는 screen_service 가 안다.
여기서 그 판단을 다시 하지 않는다.

graphviz 를 안 부른다. 파일과 온톨로지만 읽는다.
"""

from app.api.services.streamlit.screen_service import drawn_nodes
from app.ui.graph_svg import layout_store


def test_every_drawn_node_has_coordinates():
    """하나라도 없으면 그래프가 통째로 안 그려짐. 그 노드만 빠지는 것이 아님."""
    positions, missing = layout_store.resolve(drawn_nodes())

    assert missing == [], (
        f"좌표 없는 노드 {missing} — app/ui/graph_svg/layout_store.ensure_positions 를 "
        "한 번 돌리거나 화면에서 노드를 등록한다"
    )
    assert positions


def test_coordinates_for_undrawn_nodes_are_not_kept():
    """사라진 노드의 좌표가 남으면 새 노드의 자리를 잘못 잡음."""
    drawn = drawn_nodes()
    stored = layout_store.load()

    assert set(stored) <= set(drawn), sorted(set(stored) - set(drawn))
