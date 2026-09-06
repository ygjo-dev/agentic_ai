"""온톨로지 저장소와 맞닿는 유일한 파일.

지금은 `ontology.yaml` 을 읽고 쓴다. **저장소를 바꿀 때 고칠 곳을 이 경계에
모으는 것**이 이 파일의 존재 이유다 — `graph.py` · `registry.py` · `app/` 이
파일 형식을 모르게 두려는 것이다.

★ 한 파일만 고치면 된다고 보장하지는 않는다. `raw_bytes()` 처럼 파일이라는
것을 전제한 API 가 여기 남아 있고, `_init` 사본을 복사로 되돌리는 길도 그렇다.
저장소를 바꾸는 날 그 자리들은 함께 봐야 한다.

`paths` 외에 아무것도 import 하지 않는다. 저장소가 도메인을 알면 순환이 생기고,
교체할 때 무엇을 버리고 무엇을 남길지 다시 뒤져야 한다.

**recipe 와 menu 는 아직 여기 있지 않다.** `workflows/static/` 아래에서
`graph.py` 와 `registry.py` 가 각자 읽고 쓴다. 그것들을 여기로 모을지는
아직 정해지지 않았다.

캐시를 두지 않는다. 등록하면 파일이 바뀌고 그 다음 읽기가 새 내용을 봐야 한다.
"""

import shutil

import yaml

import paths


def read(path=None) -> dict:
    """ontology.yaml 원문. dict 로 돌려줌."""
    path = path or paths.ONTOLOGY_PATH
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def raw_bytes(path=None) -> bytes:
    """파일 원문 그대로.

    출력  파일 바이트. 내용 해시를 만드는 쪽이 씀
    제약  dict 로 읽어 다시 직렬화해 돌려주지 않는다.
          같은 내용이 다른 바이트가 될 수 있음(키 순서 · 따옴표 · 들여쓰기).
          캐시 키가 헛돌아 화면이 깜빡임
    """
    path = path or paths.ONTOLOGY_PATH
    return path.read_bytes()


def nodes(path=None) -> dict:
    """노드 dict.

    출력  {node_id: {name, description}}
    규칙  종류를 나누는 필드가 없음. 성격은 관계가 말하고 판정은 graph.py 가 함
    """
    return read(path)["nodes"]


def edges(path=None) -> list[dict]:
    """노드 사이의 관계. RDF 의 삼항 구조(주어 · 술어 · 목적어)를 그대로 씀.

    출력  [{"from": ..., "to": ..., "predicate": ...}, ...] 파일 순서 그대로.
          블록이 없으면 빈 목록 — 여기서 예외를 올리면 화면이 죽음
    제약  읽는 곳 없는 predicate 를 늘리지 않는다.
          지금 지원하는 것은 graph.SUPPORTED_PREDICATES 넷임. 새 관계는 그것을
          실제로 읽는 로직과 함께 더함. 읽는 곳이 없으면 파일만 무거워지고
          맞는지 틀린지 확인할 방법도 없음
          실행 순서(실선)를 여기 적지 않는다.
          그건 recipe 가 정함. 두 곳에 적으면 어긋났을 때 어느 쪽이 맞는지
          알 수 없음
    """
    return list(read(path).get("edges") or [])


# nodes 블록과 edges 블록의 경계. 노드는 이 앞에, edge 는 파일 끝에 붙는다.
EDGES_MARKER = "\nedges:"


def append_node(node_id: str, node: dict, path=None) -> None:
    """노드 한 덩어리를 nodes 블록 끝에 끼워 넣음.

    규칙  EDGES_MARKER 앞에 끼워 넣음. 마커가 없는 파일은 끝에 붙임.
          끝에 그냥 붙이면 새 노드가 edges 블록 뒤로 가 edge 목록의 일부로 읽힘
    제약  yaml.dump 로 다시 쓰지 않는다.
          파일 상단의 구조 원칙 주석과 손으로 맞춘 들여쓰기가 통째로 날아감
          중복 · 인터페이스 검사를 하지 않는다.
          도메인 규칙이라 registry.add_node() 가 맡음. 여기는 쓰기만 앎
    """
    path = path or paths.ONTOLOGY_PATH
    text = path.read_text(encoding="utf-8")
    block = node_block(node_id, node)

    head, marker, tail = text.partition(EDGES_MARKER)
    if marker:
        body = head.rstrip("\n") + "\n\n" + block + "\n\n" + marker.lstrip("\n") + tail
    else:
        # edges 블록이 아직 없는 파일. 끝에 붙인다.
        body = text.rstrip("\n") + "\n\n" + block + "\n"

    path.write_text(body, encoding="utf-8", newline="\n")


def append_edge(frm: str, to: str, predicate: str, path=None) -> None:
    """관계 한 줄을 edges 블록 끝에 이어 붙임.

    규칙  edges 가 파일 마지막이라 끝에 붙이면 됨. 블록이 없으면 만들어 붙임
    제약  한 줄 형식을 기존 항목과 다르게 적지 않는다.
          형식이 갈라지면 파일을 읽을 때 새로 등록된 것만 튀어 보임
    """
    path = path or paths.ONTOLOGY_PATH
    text = path.read_text(encoding="utf-8").rstrip("\n")
    line = edge_line(frm, to, predicate)

    if EDGES_MARKER in text:
        body = text + "\n" + line + "\n"
    else:
        body = text + "\n\n\nedges:\n\n" + line + "\n"

    path.write_text(body, encoding="utf-8", newline="\n")


def edge_line(frm: str, to: str, predicate: str) -> str:
    """edges 에 적을 한 줄. 기존 항목과 같은 형식."""
    return f"  - {{ from: {frm}, to: {to}, predicate: {predicate} }}"


def node_block(node_id: str, node: dict) -> str:
    """온톨로지에 적을 노드 한 덩어리.

    출력  기존 파일과 같은 들여쓰기의 여러 줄 문자열. name 과 description 뿐
    제약  무엇을 받고 내놓는지 여기 적지 않는다.
          노드가 아니라 관계에 적힘. hasInput / hasOutput edge 로 따로 붙음
    """
    return "\n".join([
        f"  {node_id}:",
        f"    name: {node['name']}",
        f"    description: {node['description']}",
    ])


def restore_from_init(path=None) -> None:
    """_init 사본으로 되돌림. 온톨로지만.

    규칙  recipe 와 menu 는 registry.reset_to_init() 이 이어서 되돌림
    제약  _init 사본 자체를 건드리지 않는다. 망가지면 되돌릴 곳이 없음
    """
    shutil.copy2(paths.INIT_ONTOLOGY_PATH, path or paths.ONTOLOGY_PATH)
