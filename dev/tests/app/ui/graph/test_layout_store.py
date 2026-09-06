"""대상 : app/ui/graph/layout_store.py — 좌표 보관

노드 좌표 보관 검증.

좌표는 캐시일 뿐이다 — 없으면 다시 계산하면 된다. 그래서 어떤 입력에도
예외를 올리지 않아야 한다. 시연 중에 좌표 파일 때문에 화면이 죽는 것이
가장 나쁘다.
"""

import json

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
