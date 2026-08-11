"""대상 : ontology/store.py — 온톨로지 저장소와 맞닿는 유일한 파일

지금은 `ontology.yaml` 을 읽고 쓴다. 나중에 그래프DB 로 바뀌면 여기만 교체하면
되고 `graph.py` · `registry.py` · `demo/` 는 그대로다.

여기서 지키는 것은 **파일 형식 보존**이다. `yaml.dump` 로 다시 쓰면 파일 상단의
구조 원칙 주석과 손으로 맞춘 들여쓰기가 통째로 날아간다. 사람이 읽는 문서이자
LLM 프롬프트의 재료라 그게 사라지면 되돌릴 방법이 없다.
"""

import ast
import pathlib

import pytest
import yaml

import paths
from ontology import store

NEW = {
    "name": "궤도 결함 이력 요약",
    "description": "궤도 점검 보고서에서 결함이 어떻게 이어져 왔는지 요약한다.",
    "inputs": ["DocumentData"],
    "outputs": ["AnalysisResult"],
    "properties": {"subject": "궤도"},
}


@pytest.fixture
def ontology_file(tmp_path):
    """실제 온톨로지를 복사해 임시 파일로 쓴다. 저장소를 건드리지 않는다."""
    path = tmp_path / "ontology.yaml"
    path.write_text(
        paths.ONTOLOGY_PATH.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
    )
    return path


def test_reading_gives_the_ontology_as_written(ontology_file):
    """읽기는 원문 그대로다. 캐시도 변형도 없다 — 등록 직후 읽으면 새 내용이 나와야 한다.

    interfaces 는 원문에서 {이름: {description}} 형태의 dict 인데, 접근자는
    이름만 순서대로 돌려준다. 그래프가 쓰는 것이 이름뿐이다.
    """
    raw = yaml.safe_load(ontology_file.read_text(encoding="utf-8"))

    assert store.read(ontology_file) == raw
    assert store.nodes(ontology_file) == raw["nodes"]
    assert store.interfaces(ontology_file) == list(raw["interfaces"])

    # 경로를 안 주면 실제 저장소를 본다. 프로덕션이 그렇게 부른다.
    assert store.read() == yaml.safe_load(
        paths.ONTOLOGY_PATH.read_text(encoding="utf-8")
    )

    # 저장소가 도메인을 알면 순환이 생기고, 교체할 때 뜯을 곳이 늘어난다.
    imported = set()
    for node in ast.walk(ast.parse(pathlib.Path(store.__file__).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported == {"shutil", "yaml", "paths"}, imported


def test_adding_a_node_preserves_the_existing_file(ontology_file):
    """상단 구조 원칙 주석 · 기존 본문 · 두 칸 들여쓰기가 전부 그대로여야 한다.

    yaml.dump 로 다시 쓰면 주석과 손으로 맞춘 들여쓰기가 통째로 날아가므로,
    nodes: 가 파일 마지막이라는 점을 이용해 텍스트를 이어 붙인다.
    """
    before = ontology_file.read_text(encoding="utf-8")
    head = before[: before.index("version:")]
    assert head.strip().startswith("#"), "fixture 에 주석이 없으면 이 검사가 무력하다"

    store.append_node("analyze_crack_trend", NEW, ontology_file)
    after = ontology_file.read_text(encoding="utf-8")

    assert after.startswith(head), "상단 주석이 사라졌다"
    assert after.startswith(before.rstrip("\n")), "기존 본문이 바뀌었다"
    assert after.count("#") == before.count("#")

    # 붙은 부분만 본다. 원문에는 절 사이에 빈 줄이 둘인 자리가 있어
    # 파일 전체에서 세 줄바꿈을 세면 원래 있던 것까지 잡힌다.
    appended = after[len(before.rstrip("\n")):]
    assert appended.startswith("\n\n  analyze_crack_trend:\n"), repr(appended[:24])

    # 덤프본과 다르다는 것을 직접 잰다 — 결과만 보면 통과하는 구현이 있다.
    assert after != yaml.safe_dump(
        store.read(ontology_file), allow_unicode=True, sort_keys=False
    )


def test_an_added_node_reads_back_unchanged(ontology_file):
    """왕복이 어긋나면 화면과 파일이 갈라진다.

    빈 리스트와 빈 dict 를 `[]` · `{}` 로 적는 것이 핵심이다. 생략하면
    None 으로 되읽혀 엣지 계산이 터진다. 불러오기 노드는 입력이 없고,
    범용 노드는 subject 가 없다.
    """
    before = store.nodes(ontology_file)

    store.append_node("analyze_crack_trend", NEW, ontology_file)
    store.append_node(
        "load_something", {**NEW, "inputs": [], "properties": {}}, ontology_file
    )

    nodes = store.nodes(ontology_file)
    assert nodes["analyze_crack_trend"] == NEW
    assert nodes["load_something"]["inputs"] == []
    assert nodes["load_something"]["properties"] == {}

    # 두 번 이어 붙여도 기존 노드가 그대로다.
    assert len(nodes) == len(before) + 2
    for node_id, node in before.items():
        assert nodes[node_id] == node, node_id


def test_restoring_brings_back_the_init_copy(ontology_file):
    """_init 사본은 절대 건드리지 않는다. 그것이 망가지면 되돌릴 곳이 없다."""
    init_before = paths.INIT_ONTOLOGY_PATH.read_bytes()
    store.append_node("analyze_crack_trend", NEW, ontology_file)

    store.restore_from_init(ontology_file)

    assert ontology_file.read_text(encoding="utf-8") == (
        paths.INIT_ONTOLOGY_PATH.read_text(encoding="utf-8")
    )
    assert "analyze_crack_trend" not in store.nodes(ontology_file)
    assert paths.INIT_ONTOLOGY_PATH.read_bytes() == init_before
