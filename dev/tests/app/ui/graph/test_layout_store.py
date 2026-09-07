"""대상 : app/ui/graph/layout_store.py — 좌표 보관

노드 좌표 보관 검증.

좌표는 캐시일 뿐이다 — 없으면 다시 계산하면 된다. 그래서 어떤 입력에도
예외를 올리지 않아야 한다. 시연 중에 좌표 파일 때문에 화면이 죽는 것이
가장 나쁘다.

앞쪽은 임시 파일로 규칙만 본다. 맨 끝의 두 시험만 **진짜 좌표 파일과 진짜
온톨로지**를 본다 — 같은 `resolve` 를 쓰지만 잡는 것이 다르다(그쪽 절의
머리말에 있다).

graphviz 를 안 부른다. 파일과 온톨로지만 읽는다.
"""

import json

from app.api.services.streamlit.screen_service import drawn_nodes
from app.ui.graph import layout_store

POSITIONS = {
    "load_cctv_platform": (86.2, 209.91),
    "analyze_congestion": (83.957, 145.39),
}


def nodes_of(*node_ids):
    """resolve 가 받는 노드 dict. 이름만 있으면 됨."""
    return {node_id: {"name": node_id} for node_id in node_ids}


# ------------------------------------------------------------ 왕복
def test_save_then_load_is_identity(tmp_path):
    path = tmp_path / "layout.json"

    layout_store.save(POSITIONS, path=path)

    assert layout_store.load(path=path) == POSITIONS


def test_saved_file_is_utf8_json(tmp_path):
    path = tmp_path / "layout.json"

    layout_store.save(POSITIONS, path=path)

    assert set(json.loads(path.read_text(encoding="utf-8"))) == set(POSITIONS)


# ------------------------------------------------------------ 망가진 입력
def test_missing_file_is_empty_not_an_error(tmp_path):
    assert layout_store.load(path=tmp_path / "없다.json") == {}


def test_broken_json_is_empty_not_an_error(tmp_path):
    path = tmp_path / "layout.json"
    path.write_text("{망가짐", encoding="utf-8")

    assert layout_store.load(path=path) == {}


def test_wrong_shape_is_empty_not_an_error(tmp_path):
    path = tmp_path / "layout.json"
    path.write_text('["리스트다"]', encoding="utf-8")

    assert layout_store.load(path=path) == {}


def test_one_bad_entry_does_not_lose_the_rest(tmp_path):
    path = tmp_path / "layout.json"
    path.write_text('{"a": [1, 2], "b": "이상함"}', encoding="utf-8")

    assert layout_store.load(path=path) == {"a": (1.0, 2.0)}


def test_atomic_write_leaves_no_temp_file(tmp_path):
    path = tmp_path / "layout.json"

    layout_store.save(POSITIONS, path=path)

    assert [p.name for p in tmp_path.iterdir()] == ["layout.json"]


# ------------------------------------------------------------ resolve
def test_resolve_returns_stored_positions(tmp_path):
    path = tmp_path / "layout.json"
    layout_store.save(POSITIONS, path=path)

    positions, missing = layout_store.resolve(nodes_of(*POSITIONS), path=path)

    assert positions == POSITIONS
    assert missing == []


def test_resolve_drops_nodes_that_are_gone(tmp_path):
    """초기화하거나 노드가 사라지면 남은 좌표가 새 노드 자리를 잘못 잡음."""
    path = tmp_path / "layout.json"
    layout_store.save(POSITIONS, path=path)

    positions, _ = layout_store.resolve(nodes_of("analyze_congestion"), path=path)

    assert set(positions) == {"analyze_congestion"}


def test_resolve_reports_nodes_without_coordinates(tmp_path):
    path = tmp_path / "layout.json"
    layout_store.save(POSITIONS, path=path)

    _, missing = layout_store.resolve(
        nodes_of("analyze_congestion", "generate_word", "generate_ppt"), path=path
    )

    assert missing == ["generate_word", "generate_ppt"]


def test_resolve_on_a_fresh_install_reports_everything_missing(tmp_path):
    positions, missing = layout_store.resolve(
        nodes_of("a", "b"), path=tmp_path / "없다.json"
    )

    assert positions == {}
    assert missing == ["a", "b"]


# ------------------------------------------------------------ 진짜 데이터 관문
#
# **온톨로지에 노드를 더하면 여기서 걸린다.** `layout.json` 에 좌표가 없으면
# 그래프가 통째로 안 그려진다 — `neato -n` 이 `node ... has no position as
# required by the -n flag` 로 거부한다. 등록 화면(POST /nodes)을 거치면 좌표가
# 붙지만 파일을 직접 고치면 안 붙는다. 2026-08-28 시연에서 그렇게 깨졌다
# (NOTES.md 「마흔여섯째」).
#
# 좌표 파일은 gitignore 라 저장소에 안 들어간다. 그래서 「커밋에 좌표가 들어
# 있는가」로는 못 막고, 노드를 더한 사람의 장비에서 이 두 시험이 잡는다.
#
# **형식 노드는 안 그린다.** 그리는 노드가 무엇인지는 screen_service 가 안다.
# 여기서 그 판단을 다시 하지 않는다.


def test_every_drawn_node_has_coordinates():
    """하나라도 없으면 그래프가 통째로 안 그려짐. 그 노드만 빠지는 것이 아님."""
    positions, missing = layout_store.resolve(drawn_nodes())

    assert missing == [], (
        f"좌표 없는 노드 {missing} — app/ui/graph/layout_store.ensure_positions 를 "
        "한 번 돌리거나 화면에서 노드를 등록한다"
    )
    assert positions


def test_coordinates_for_undrawn_nodes_are_not_kept():
    """사라진 노드의 좌표가 남으면 새 노드의 자리를 잘못 잡음."""
    drawn = drawn_nodes()
    stored = layout_store.load()

    assert set(stored) <= set(drawn), sorted(set(stored) - set(drawn))
