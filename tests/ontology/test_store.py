"""대상 : ontology/store.py

온톨로지 저장소와 맞닿는 유일한 파일. 지금은 ontology.yaml 을 읽고 쓴다.

여기서 지키는 것은 **파일 형식 보존**이다. `yaml.dump` 로 다시 쓰면 파일 상단의
구조 원칙 주석과 손으로 맞춘 들여쓰기가 통째로 날아간다. 사람이 읽는 문서이자
LLM 프롬프트의 재료라 그게 사라지면 되돌릴 방법이 없다.
"""

import pytest
import yaml

import paths
from ontology import store

NEW = {
    "name": "구조물 균열 진행 추세 분석",
    "description": "문서에서 구조물 균열 폭의 시간 변화를 분석한다.",
    "inputs": ["DocumentData"],
    "outputs": ["AnalysisResult"],
    "properties": {"target": "구조물"},
}


@pytest.fixture
def ontology_file(tmp_path):
    """실제 온톨로지를 복사해 임시 파일로 쓴다. 저장소를 건드리지 않는다."""
    path = tmp_path / "ontology.yaml"
    path.write_text(
        paths.ONTOLOGY_PATH.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
    )
    return path


# ------------------------------------------------------------ 읽기
def test_read_returns_the_file_contents(ontology_file):
    assert store.read(ontology_file) == yaml.safe_load(
        ontology_file.read_text(encoding="utf-8")
    )


def test_read_without_a_path_reads_the_repository(ontology_file):
    """인자를 안 주면 실제 온톨로지를 본다. 프로덕션이 그렇게 부른다."""
    assert store.read() == yaml.safe_load(
        paths.ONTOLOGY_PATH.read_text(encoding="utf-8")
    )


def test_nodes_are_the_nodes_section(ontology_file):
    assert store.nodes(ontology_file) == store.read(ontology_file)["nodes"]


def test_every_node_has_the_expected_fields(ontology_file):
    for node_id, node in store.nodes(ontology_file).items():
        assert set(node) >= {"name", "description", "inputs", "outputs"}, node_id
        assert isinstance(node["inputs"], list), node_id
        assert isinstance(node["outputs"], list), node_id


def test_interfaces_are_names_not_the_dict(ontology_file):
    """원문에서는 {이름: {description}} 이다. 이름만 순서대로 나와야 한다."""
    raw = store.read(ontology_file)["interfaces"]

    assert store.interfaces(ontology_file) == list(raw)
    assert all(isinstance(name, str) for name in store.interfaces(ontology_file))


# ------------------------------------------------------------ 쓰기 (핵심)
def test_header_comment_survives(ontology_file):
    """상단 주석에 구조 원칙과 property key 어휘가 적혀 있다.

    yaml.dump 로 다시 쓰면 여기가 통째로 사라진다. 그것을 막는 자리다.
    """
    before = ontology_file.read_text(encoding="utf-8")
    head = before[: before.index("version:")]
    assert head.strip().startswith("#"), "fixture 에 주석이 없으면 이 검사가 무력하다"

    store.append_node("analyze_crack_trend", NEW, ontology_file)

    assert ontology_file.read_text(encoding="utf-8").startswith(head)


def test_existing_text_is_untouched(ontology_file):
    """기존 내용은 한 글자도 안 바뀌고 뒤에 붙기만 해야 한다."""
    before = ontology_file.read_text(encoding="utf-8")

    store.append_node("analyze_crack_trend", NEW, ontology_file)

    after = ontology_file.read_text(encoding="utf-8")
    assert after.startswith(before.rstrip("\n"))


def test_existing_nodes_survive(ontology_file):
    before = store.nodes(ontology_file)

    store.append_node("analyze_crack_trend", NEW, ontology_file)

    after = store.nodes(ontology_file)
    assert len(after) == len(before) + 1
    for node_id, node in before.items():
        assert after[node_id] == node, node_id


def test_node_is_indented_under_nodes(ontology_file):
    """두 칸 들여쓰기가 아니면 nodes 아래로 안 들어간다."""
    store.append_node("analyze_crack_trend", NEW, ontology_file)

    assert "  analyze_crack_trend:\n" in ontology_file.read_text(encoding="utf-8")


def test_write_then_read_is_the_identity(ontology_file):
    """쓴 것이 그대로 되읽혀야 한다. 왕복이 어긋나면 화면과 파일이 갈라진다."""
    store.append_node("analyze_crack_trend", NEW, ontology_file)

    assert store.nodes(ontology_file)["analyze_crack_trend"] == NEW


def test_empty_lists_round_trip(ontology_file):
    """불러오기 노드는 입력이 없다. `[]` 로 적어야 빈 리스트로 되읽힌다."""
    store.append_node(
        "load_something", {**NEW, "inputs": [], "properties": {}}, ontology_file
    )

    node = store.nodes(ontology_file)["load_something"]
    assert node["inputs"] == []
    assert node["properties"] == {}


def test_two_appends_in_a_row_stay_valid(ontology_file):
    """한 번은 되고 두 번째에서 형식이 깨지는 일이 없어야 한다."""
    store.append_node("a_node", NEW, ontology_file)
    store.append_node("b_node", {**NEW, "properties": {}}, ontology_file)

    nodes = store.nodes(ontology_file)
    assert "a_node" in nodes and "b_node" in nodes


def test_blank_lines_do_not_pile_up(ontology_file):
    """노드 사이는 빈 줄 하나다.

    붙이기 전에 끝 개행을 정리하지 않으면 등록할 때마다 빈 줄이 하나씩 더
    끼어든다. yaml 은 계속 파싱되므로 파일을 열어보기 전까지 아무도 모른다 —
    그래서 파일 끝만 보지 않고 **노드 사이**를 잰다.
    """
    for node_id in ("a_node", "b_node"):
        before = ontology_file.read_text(encoding="utf-8")

        store.append_node(node_id, NEW, ontology_file)

        # 붙은 부분만 본다. 원문에는 절(節) 사이에 빈 줄이 둘인 자리가 있어
        # 파일 전체에서 세 줄바꿈을 세면 원래 있던 것까지 잡힌다.
        appended = ontology_file.read_text(encoding="utf-8")[len(before.rstrip("\n")):]
        assert appended.startswith(f"\n\n  {node_id}:\n"), repr(appended[:20])

    text = ontology_file.read_text(encoding="utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_appending_does_not_use_yaml_dump(ontology_file):
    """yaml.dump 는 주석을 지우고 따옴표 · 들여쓰기를 제 방식대로 바꾼다.

    결과만 보면 통과하는 구현이 있을 수 있으므로, 덤프본과 **다르다**는 것을
    직접 잰다.
    """
    store.append_node("analyze_crack_trend", NEW, ontology_file)
    text = ontology_file.read_text(encoding="utf-8")

    dumped = yaml.safe_dump(
        store.read(ontology_file), allow_unicode=True, sort_keys=False
    )
    assert text != dumped
    assert "#" in text, "주석이 사라졌다 — 덤프로 다시 쓴 것이다"


# ------------------------------------------------------------ 블록 형식
def test_node_block_shape():
    """파일에 적히는 모양. 들여쓰기가 어긋나면 yaml 이 깨진다."""
    block = store.node_block("x_node", NEW)

    assert block.splitlines()[0] == "  x_node:"
    assert "    name: 구조물 균열 진행 추세 분석" in block
    assert "    inputs:" in block
    assert "      - DocumentData" in block
    assert "    properties:" in block
    assert "      target: 구조물" in block


def test_node_block_writes_empty_collections_inline():
    block = store.node_block("x_node", {**NEW, "inputs": [], "properties": {}})

    assert "    inputs: []" in block
    assert "    properties: {}" in block


# ------------------------------------------------------------ 되돌리기
def test_restore_brings_back_the_init_copy(ontology_file):
    store.append_node("analyze_crack_trend", NEW, ontology_file)
    assert "analyze_crack_trend" in store.nodes(ontology_file)

    store.restore_from_init(ontology_file)

    assert ontology_file.read_text(encoding="utf-8") == paths.INIT_ONTOLOGY_PATH.read_text(
        encoding="utf-8"
    )
    assert "analyze_crack_trend" not in store.nodes(ontology_file)


def test_restore_does_not_touch_the_init_copy(ontology_file):
    """_init 이 망가지면 되돌릴 곳이 없다."""
    before = paths.INIT_ONTOLOGY_PATH.read_bytes()

    store.restore_from_init(ontology_file)

    assert paths.INIT_ONTOLOGY_PATH.read_bytes() == before


# ------------------------------------------------------------ 계층
def test_store_only_imports_paths():
    """저장소가 도메인을 알면 순환이 생기고, 교체할 때 뜯을 곳이 늘어난다."""
    import ast
    import pathlib

    source = pathlib.Path(store.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])

    assert imported == {"shutil", "yaml", "paths"}, imported
