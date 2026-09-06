"""대상 : app/ui/graph/ · registration/registry.py — 좌표의 _init 사본

**눈이 못 보는 것을 본다.** 초기화가 좌표를 안 되돌리면 화면은 멀쩡하다 —
첫 시연에서는 아무 일도 없고, **두 번째 시연에서 지도가 첫 배치가 아니다.**
그것이 리허설과 본 시연 사이에 벌어지면 무대 위에서 알게 된다.

좌표 파일이 둘이 된 이유는 `layout_store` 머리말에 있다. 여기서는 그 둘이
온톨로지 · recipe · menu 와 같은 규칙으로 도는지만 본다.

    작업본이 없으면   _init 에서 온다
    초기화하면        _init 으로 돌아간다
    _init 사본은      어느 경우에도 안 바뀐다
"""

import ast
import json

import pytest

from app.ui.graph import layout_store

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
    from registration.registry import reset_to_init

    before = layout_store.load()
    write(layout_store.LAYOUT_PATH, {**{k: list(v) for k, v in before.items()},
                                     "zz_added_node": [99.0, 99.0]})
    assert "zz_added_node" in layout_store.load()

    reset_to_init()

    assert "zz_added_node" not in layout_store.load()
    assert layout_store.load() == before


# CLAUDE.md 「폴더가 말하는 여섯 갈래」에서 그대로 온다.
# 이름이 또 갈리면 아래 exists 확인이 먼저 빨간불이 된다 — 조용히 통과하지 않는다.
DOMAIN_DIRS = ("ontology", "registration", "orchestrator", "execution",
               "llm_engine", "workflows")
SERVICE_PACKAGES = ("app",)


def module_level_statements(tree):
    """함수 · 클래스 몸통 안으로는 안 들어간다. try · if 는 들어간다.

    함수 안의 늦은 import 는 순환을 푸는 흔한 손이라 여기서 안 본다.
    막으려는 것은 **모듈을 읽는 순간** 서비스 계층이 딸려 오는 것이다.
    """
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        stack.extend(c for c in ast.iter_child_nodes(node) if isinstance(c, ast.stmt))


def imported_roots(node):
    """import 문 하나가 부르는 최상위 패키지 이름들. import 문이 아니면 빈 것."""
    if isinstance(node, ast.Import):
        return [alias.name.split(".", 1)[0] for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0:
        return [(node.module or "").split(".", 1)[0]]
    return []


def test_the_domain_does_not_import_the_service_layer_at_module_level():
    """도메인이 서비스를 모듈 수준에서 부르면 서비스를 갈아 끼울 수 없다.

    낱말을 찾지 않고 **import 문을 판다.** 옛 몸통은 `ontology/registry.py`
    머리에 "demo" 라는 글자가 있는지만 봤는데, 계층 이름이 `app` 으로 갈리자
    그 assert 는 늘 참이 되어 아무것도 안 지키게 됐다 — 조용히 죽었다.
    여기서는 이름이 갈리면 아래 exists 확인이 먼저 깨지므로 그 일이 안 난다.
    """
    from paths import REPO_ROOT

    for name in DOMAIN_DIRS + SERVICE_PACKAGES:
        assert (REPO_ROOT / name).is_dir(), (
            f"{name}/ 이 없다. 계층 이름이 갈렸으면 이 시험의 목록부터 고친다"
        )

    offenders = []
    scanned = 0
    for folder in DOMAIN_DIRS:
        for path in sorted((REPO_ROOT / folder).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            scanned += 1
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in module_level_statements(tree):
                for root in imported_roots(node):
                    if root in SERVICE_PACKAGES:
                        rel = path.relative_to(REPO_ROOT)
                        offenders.append(f"{rel}:{node.lineno} -> {root}")

    assert scanned, "도메인에서 판 파일이 하나도 없다 — 경로가 어긋난 것이다"
    assert not offenders, "도메인이 서비스를 모듈 수준에서 부른다:\n" + "\n".join(offenders)


def test_a_registration_leaves_the_init_copy_alone(layouts):
    """등록은 작업본만 바꿔야 함. 그래야 초기화로 되돌아옴."""
    work, init = layouts
    before = init.read_bytes()

    layout_store.save({"n0": (1.0, 2.0)})

    assert init.read_bytes() == before
    assert work.exists()
