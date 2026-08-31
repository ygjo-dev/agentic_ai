"""대상 : ontology/store.py — 온톨로지 저장소와 맞닿는 유일한 파일

지금은 `ontology.yaml` 을 읽고 쓴다. 나중에 그래프DB 로 바뀌면 여기만 교체하면
되고 `graph.py` · `registry.py` · `app/` 는 그대로다.

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

# 노드에는 name 과 description 뿐이다. 무엇을 받고 내놓는지도, 무엇에 관한
# 것인지도 관계라서 edges 에 적힌다.
NEW = {
    "name": "궤도 결함 이력 요약",
    "description": "궤도 점검 보고서에서 결함이 어떻게 이어져 왔는지 요약한다.",
}


@pytest.fixture
def ontology_file(tmp_path):
    """실제 온톨로지를 복사해 임시 파일로 씀. 저장소를 안 건드림."""
    path = tmp_path / "ontology.yaml"
    path.write_text(
        paths.ONTOLOGY_PATH.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
    )
    return path


def test_reading_gives_the_ontology_as_written(ontology_file):
    """읽기는 원문 그대로. 캐시도 변형도 없음. 등록 직후 읽으면 새 내용이 나와야 함.

    여기에 캐시를 두면 안 됨. 저장소는 쓰는 쪽이라 "방금 쓴 것이 다음
    읽기에 보인다" 를 어기면 등록이 조용히 어긋남. 읽기 전용 계산의 캐시는
    graph.py 가 파일 내용을 키로 따로 들고 있음.
    """
    raw = yaml.safe_load(ontology_file.read_text(encoding="utf-8"))

    assert store.read(ontology_file) == raw
    assert store.nodes(ontology_file) == raw["nodes"]
    assert store.edges(ontology_file) == list(raw["edges"])
    assert store.raw_bytes(ontology_file) == ontology_file.read_bytes()

    # 쓴 직후 읽으면 바로 보인다.
    store.append_node("probe_node", NEW, ontology_file)
    assert "probe_node" in store.nodes(ontology_file)

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
    """상단 구조 원칙 주석 · 기존 본문 · edges 블록 · 들여쓰기가 그대로여야 함.

    yaml.dump 로 다시 쓰면 주석과 손으로 맞춘 들여쓰기가 통째로 날아감.

    새 노드는 edges 앞에 끼워 넣음. 예전에는 nodes: 가 파일 마지막이라
    그냥 끝에 붙였는데, edges: 가 뒤에 생기면서 그 전제가 깨졌음. 그대로 두면
    새 노드가 edge 목록의 일부로 읽힘.
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
    """관계는 edges 끝에 한 줄로 붙음. 형식이 기존 항목과 같아야 함.

    노드를 쓴 뒤에 붙임. 순서가 바뀌면 아직 없는 노드를 가리키는 edge 가
    파일에 남음.
    """
    before = store.edges(ontology_file)
    body_before = ontology_file.read_text(encoding="utf-8")

    # 관계 이름을 박아두지 않는다. 어휘가 바뀌면(속함 -> about) 여기가 깨지는데,
    # 이 검사가 지키려는 것은 "한 줄이 같은 형식으로 붙는다" 이지 이름이 아니다.
    relation = before[0]["predicate"]

    store.append_node("analyze_crack_trend", NEW, ontology_file)
    store.append_edge("analyze_crack_trend", "group_track", relation, ontology_file)

    after = store.edges(ontology_file)
    assert after[: len(before)] == before, "기존 관계가 바뀌었다"
    assert after[-1] == {
        "from": "analyze_crack_trend", "to": "group_track", "predicate": relation
    }

    text = ontology_file.read_text(encoding="utf-8")
    assert store.edge_line("analyze_crack_trend", "group_track", relation) in text
    assert text.startswith(body_before[: body_before.index("version:")])


def test_an_added_node_reads_back_unchanged(ontology_file):
    """왕복이 어긋나면 화면과 파일이 갈라짐.

    어떤 노드든 같은 모양으로 적힘. 종류에 따라 필드가 갈리지 않으므로
    "이건 group 이니 inputs 를 빼야 한다" 같은 분기가 아예 없음. 예전에는
    그 분기를 빠뜨리면 대상 노드가 "입력이 없는 기능" 으로 읽혀 recipe
    시작점이 되어버렸음.
    """
    before = store.nodes(ontology_file)

    store.append_node("analyze_crack_trend", NEW, ontology_file)
    store.append_node(
        "group_tunnel",
        {"name": "터널", "description": "열차가 지나는 터널 구조물."},
        ontology_file,
    )

    nodes = store.nodes(ontology_file)
    assert nodes["analyze_crack_trend"] == NEW
    assert set(nodes["group_tunnel"]) == {"name", "description"}

    # 기존 노드와 모양이 같다. 새로 적힌 것만 튀어 보이면 안 된다.
    for node in nodes.values():
        assert set(node) == {"name", "description"}

    # 두 번 이어 붙여도 기존 노드가 그대로다.
    assert len(nodes) == len(before) + 2
    for node_id, node in before.items():
        assert nodes[node_id] == node, node_id


def test_restoring_brings_back_the_init_copy(ontology_file):
    """_init 사본은 절대 안 건드림. 그것이 망가지면 되돌릴 곳이 없음."""
    init_before = paths.INIT_ONTOLOGY_PATH.read_bytes()
    store.append_node("analyze_crack_trend", NEW, ontology_file)

    store.restore_from_init(ontology_file)

    assert ontology_file.read_text(encoding="utf-8") == (
        paths.INIT_ONTOLOGY_PATH.read_text(encoding="utf-8")
    )
    assert "analyze_crack_trend" not in store.nodes(ontology_file)
    assert paths.INIT_ONTOLOGY_PATH.read_bytes() == init_before
