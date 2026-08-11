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
    "kind": "function",
    "name": "궤도 결함 이력 요약",
    "description": "궤도 점검 보고서에서 결함이 어떻게 이어져 왔는지 요약한다.",
    "inputs": ["DocumentData"],
    "outputs": ["AnalysisResult"],
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
    assert store.edges(ontology_file) == list(raw["edges"])

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
    """상단 구조 원칙 주석 · 기존 본문 · edges 블록 · 들여쓰기가 그대로여야 한다.

    yaml.dump 로 다시 쓰면 주석과 손으로 맞춘 들여쓰기가 통째로 날아간다.

    **새 노드는 edges 앞에 끼워 넣는다.** 예전에는 nodes: 가 파일 마지막이라
    그냥 끝에 붙였는데, edges: 가 뒤에 생기면서 그 전제가 깨졌다 — 그대로 두면
    새 노드가 edge 목록의 일부로 읽힌다.
    """
    before = ontology_file.read_text(encoding="utf-8")
    head = before[: before.index("version:")]
    edges_block = before[before.index("\nedges:"):]
    assert head.strip().startswith("#"), "fixture 에 주석이 없으면 이 검사가 무력하다"

    store.append_node("analyze_crack_trend", NEW, ontology_file)
    after = ontology_file.read_text(encoding="utf-8")

    assert after.startswith(head), "상단 주석이 사라졌다"
    assert after.count("#") == before.count("#")
    assert after.endswith(edges_block), "edges 블록이 바뀌었다"

    # nodes 블록 안, edges 앞에 들어가야 한다.
    assert "\n  analyze_crack_trend:\n" in after
    assert after.index("analyze_crack_trend:") < after.index("\nedges:")

    # 기존 노드 본문은 한 글자도 안 바뀐다.
    assert before[: before.index("\nedges:")].rstrip("\n") in after

    # 덤프본과 다르다는 것을 직접 잰다 — 결과만 보면 통과하는 구현이 있다.
    assert after != yaml.safe_dump(
        store.read(ontology_file), allow_unicode=True, sort_keys=False
    )


def test_adding_an_edge_appends_one_line(ontology_file):
    """관계는 edges 끝에 한 줄로 붙는다. 형식이 기존 항목과 같아야 한다.

    노드를 쓴 뒤에 붙인다 — 순서가 바뀌면 아직 없는 노드를 가리키는 edge 가
    파일에 남는다.
    """
    before = store.edges(ontology_file)
    body_before = ontology_file.read_text(encoding="utf-8")

    store.append_node("analyze_crack_trend", NEW, ontology_file)
    store.append_edge("analyze_crack_trend", "group_track", "속함", ontology_file)

    after = store.edges(ontology_file)
    assert after[: len(before)] == before, "기존 관계가 바뀌었다"
    assert after[-1] == {
        "from": "analyze_crack_trend", "to": "group_track", "type": "속함"
    }

    text = ontology_file.read_text(encoding="utf-8")
    assert store.edge_line("analyze_crack_trend", "group_track", "속함") in text
    assert text.startswith(body_before[: body_before.index("version:")])


def test_an_added_node_reads_back_unchanged(ontology_file):
    """왕복이 어긋나면 화면과 파일이 갈라진다.

    빈 리스트를 `[]` 로 적는 것이 핵심이다. 생략하면 None 으로 되읽혀 엣지
    계산이 터진다. 불러오기 노드는 입력이 없다.

    group 은 반대다 — inputs / outputs 를 **아예 안 적는다.** 빈 리스트로 적으면
    "입력이 없는 기능" 으로 읽혀 recipe 시작점이 되어버린다.
    """
    before = store.nodes(ontology_file)

    store.append_node("analyze_crack_trend", NEW, ontology_file)
    store.append_node("load_something", {**NEW, "inputs": []}, ontology_file)
    store.append_node(
        "group_tunnel",
        {"kind": "group", "name": "터널", "description": "열차가 지나는 터널 구조물."},
        ontology_file,
    )

    nodes = store.nodes(ontology_file)
    assert nodes["analyze_crack_trend"] == NEW
    assert nodes["load_something"]["inputs"] == []
    assert nodes["group_tunnel"]["kind"] == "group"
    assert "inputs" not in nodes["group_tunnel"]
    assert "outputs" not in nodes["group_tunnel"]

    # 세 번 이어 붙여도 기존 노드가 그대로다.
    assert len(nodes) == len(before) + 3
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
