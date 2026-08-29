"""대상 : demo/graph_svg/ · ontology/registry.py — 좌표의 _init 사본

**눈이 못 보는 것을 본다.** 초기화가 좌표를 안 되돌리면 화면은 멀쩡하다 —
첫 시연에서는 아무 일도 없고, **두 번째 시연에서 지도가 첫 배치가 아니다.**
그것이 리허설과 본 시연 사이에 벌어지면 무대 위에서 알게 된다.

좌표 파일이 둘이 된 이유는 `layout_store` 머리말에 있다. 여기서는 그 둘이
온톨로지 · recipe · menu 와 같은 규칙으로 도는지만 본다.

    작업본이 없으면   _init 에서 온다
    초기화하면        _init 으로 돌아간다
    _init 사본은      어느 경우에도 안 바뀐다
"""

import json
import pathlib

import pytest

from demo.graph_svg import layout_store

SAMPLE = {"n0": [10.0, 20.0], "n1": [30.0, 40.0]}
CHANGED = {"n0": [10.0, 20.0], "n1": [30.0, 40.0], "n2": [99.0, 99.0]}


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8", newline="\n")


@pytest.fixture
def layouts(monkeypatch, tmp_path):
    """작업본과 _init 사본을 임시 자리로 옮김. 진짜 파일은 안 건드림."""
    work = tmp_path / "layout.json"
    init = tmp_path / "_init" / "layout.json"
    write(init, SAMPLE)
    monkeypatch.setattr(layout_store, "LAYOUT_PATH", work)
    monkeypatch.setattr(layout_store, "INIT_LAYOUT_PATH", init)
    return work, init


def test_the_init_copy_is_tracked_and_the_working_one_is_not():
    """저장소에 실제로 있어야 함. 없으면 처음 켠 기계가 배치를 새로 잡음."""
    assert layout_store.INIT_LAYOUT_PATH.exists()
    assert layout_store.load(layout_store.INIT_LAYOUT_PATH)


def test_the_shipped_pair_holds_the_same_coordinates():
    """작업본과 _init 이 갈라져 있으면 화면과 커밋된 배치가 다른 것임."""
    if not layout_store.LAYOUT_PATH.exists():
        pytest.skip("작업본이 아직 없다 — 처음 켠 기계다")

    assert layout_store.load() == layout_store.load(layout_store.INIT_LAYOUT_PATH)


def test_reading_falls_back_to_the_init_copy(layouts):
    """작업본이 없어도 사람이 고른 배치가 나와야 함."""
    work, _ = layouts

    assert not work.exists()
    assert layout_store.load() == {"n0": (10.0, 20.0), "n1": (30.0, 40.0)}


def test_reading_does_not_create_the_working_copy(layouts):
    """읽기만 하는 함수가 파일을 만들지 않음. 복사는 ensure_positions 가 함."""
    work, _ = layouts

    layout_store.load()

    assert not work.exists()


def test_restoring_brings_the_init_copy_back(layouts):
    """등록으로 늘어난 좌표가 사라져야 함."""
    work, _ = layouts
    write(work, CHANGED)

    layout_store.restore_from_init()

    assert layout_store.load() == {"n0": (10.0, 20.0), "n1": (30.0, 40.0)}


def test_restoring_never_touches_the_init_copy(layouts):
    """망가지면 되돌릴 곳이 없음."""
    _, init = layouts
    before = init.read_bytes()

    layout_store.restore_from_init()
    layout_store.restore_from_init()  # 두 번 돌려도 같아야 한다

    assert init.read_bytes() == before


def test_restoring_without_an_init_copy_does_not_raise(monkeypatch, tmp_path):
    """좌표 파일 때문에 화면이 죽는 것이 가장 나쁨."""
    monkeypatch.setattr(layout_store, "LAYOUT_PATH", tmp_path / "layout.json")
    monkeypatch.setattr(layout_store, "INIT_LAYOUT_PATH", tmp_path / "없다.json")

    layout_store.restore_from_init()

    assert layout_store.load() == {}


def test_resetting_the_ontology_also_resets_the_coordinates(isolated_workspace):
    """★ 이번에 막은 구멍. 초기화가 좌표를 안 되돌리면 두 번째 시연이 다름.

    layouts 가 아니라 isolated_workspace 를 씀. reset_to_init() 은 온톨로지 ·
    menu · recipe 도 함께 갈아끼우므로 그쪽까지 격리해야 진짜 저장소가 안 바뀜.
    """
    from ontology.registry import reset_to_init

    before = layout_store.load()
    write(layout_store.LAYOUT_PATH, {**{k: list(v) for k, v in before.items()},
                                     "zz_added_node": [99.0, 99.0]})
    assert "zz_added_node" in layout_store.load()

    reset_to_init()

    assert "zz_added_node" not in layout_store.load()
    assert layout_store.load() == before


def test_the_core_does_not_import_the_demo_layer_at_module_level():
    """핵심이 시연 계층을 의존하면 demo/ 를 지울 때 import 가 깨짐."""
    import ontology.registry

    source = pathlib.Path(ontology.registry.__file__)
    head = source.read_text(encoding="utf-8").split("def ", 1)[0]

    assert "demo" not in head


def test_a_registration_leaves_the_init_copy_alone(layouts):
    """등록은 작업본만 바꿔야 함. 그래야 초기화로 되돌아옴."""
    work, init = layouts
    before = init.read_bytes()

    layout_store.save({"n0": (1.0, 2.0)})

    assert init.read_bytes() == before
    assert work.exists()
