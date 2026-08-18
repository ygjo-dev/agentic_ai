"""온톨로지 저장소와 맞닿는 유일한 파일.

지금은 `ontology.yaml` 을 읽고 쓴다. 나중에 그래프DB(Neo4j 등)로 바뀌면
**여기만 교체**하면 되고 `graph.py` · `registry.py` · `demo/` 는 그대로다.
그 지점을 만드는 것이 이 파일의 존재 이유다.

`paths` 외에 아무것도 import 하지 않는다. 저장소가 도메인을 알면 순환이 생기고,
교체할 때 무엇을 버리고 무엇을 남길지 다시 뒤져야 한다.

**recipe 와 menu 는 아직 여기 있지 않다.** `workflows/static/` 아래에서
`graph.py` 와 `registry.py` 가 각자 읽고 쓴다. 그쪽이 그래프DB 로 갈지 아직
정해지지 않아 이번에는 손대지 않았다 — 갈 때가 되면 그때 이 파일로 모은다.

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
    이력  저장소가 그래프DB 로 바뀌면 파일이 없으므로 여기서 스냅샷을
          직렬화해 돌려주면 됨. 부르는 쪽은 그대로임
    """
    path = path or paths.ONTOLOGY_PATH
    return path.read_bytes()


def nodes(path=None) -> dict:
    """노드 dict.

    출력  {node_id: {name, description}}
    규칙  종류를 나누는 필드가 없음. 노드는 그저 존재할 뿐이고 성격은
          관계가 말함
            hasOutput 이 있음      실행할 수 있는 노드
            about 의 대상으로 등장  대상(그룹) 노드
          판정은 graph.py 가 함
    """
    return read(path)["nodes"]


def edges(path=None) -> list[dict]:
    """노드 사이의 관계.

    출력  [{"from": ..., "to": ..., "predicate": ...}, ...] 파일 순서 그대로.
          edges 블록이 없어도 빈 리스트. 관계가 하나도 없는 온톨로지가
          이상한 것은 아니고, 여기서 예외를 올리면 화면이 죽음
    규칙  RDF 의 삼항 구조(주어 · 술어 · 목적어)를 그대로 씀
    제약  predicate 를 늘리지 않는다.
          is-a · about · hasInput · hasOutput 넷뿐. 읽는 곳이 없는 관계는
          파일만 무겁게 하고 맞는지 틀린지 확인할 방법도 없음
          실행 순서(실선)를 여기 적지 않는다.
          그건 recipe 가 정함. 두 곳에 적으면 진실의 원천이 둘이 되고
          어긋났을 때 어느 쪽이 맞는지 알 수 없음
    """
    return list(read(path).get("edges") or [])


# nodes 블록과 edges 블록의 경계. 노드는 이 앞에, edge 는 파일 끝에 붙는다.
EDGES_MARKER = "\nedges:"


def append_node(node_id: str, node: dict, path=None) -> None:
    """노드 한 덩어리를 nodes 블록 끝에 끼워 넣음.

    입력  노드 id · 노드 dict · 온톨로지 경로(없으면 기본)
    규칙  EDGES_MARKER 앞에 끼워 넣음. 마커가 없는 파일은 끝에 붙임
    제약  yaml.dump 로 다시 쓰지 않는다.
          파일 상단의 구조 원칙 주석과 손으로 맞춘 들여쓰기가 통째로 날아감
          중복 · 인터페이스 검사를 하지 않는다.
          도메인 규칙이라 registry.add_node() 가 맡음. 여기는 쓰기만 앎
    이력  예전에는 nodes: 가 파일 마지막이라 그냥 끝에 붙였음. edges: 가 뒤에
          생기면서 그 전제가 깨졌음. 그대로 두면 새 노드가 edges 블록 뒤에
          붙어 노드가 아니라 edge 목록의 일부로 읽힘
    """
    path = path or paths.ONTOLOGY_PATH
    text = path.read_text(encoding="utf-8")
    block = node_block(node_id, node)

    head, marker, tail = text.partition(EDGES_MARKER)
    if marker:
        body = head.rstrip("\n") + "\n\n" + block + "\n\n" + marker.lstrip("\n") + tail
    else:
        # edges 블록이 아직 없는 파일. 예전처럼 끝에 붙인다.
        body = text.rstrip("\n") + "\n\n" + block + "\n"

    path.write_text(body, encoding="utf-8", newline="\n")


def append_edge(frm: str, to: str, predicate: str, path=None) -> None:
    """관계 한 줄을 edges 블록 끝에 이어 붙임.

    입력  from · to · predicate · 온톨로지 경로(없으면 기본)
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

    출력  기존 파일과 같은 들여쓰기의 여러 줄 문자열
    규칙  name 과 description 뿐
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

    규칙  recipe 와 menu 는 registry.reset_to_init() 이 이어서 되돌림.
          그쪽은 아직 이 파일이 맡는 자산이 아님
    제약  _init 사본 자체를 건드리지 않는다. 망가지면 되돌릴 곳이 없음
    """
    shutil.copy2(paths.INIT_ONTOLOGY_PATH, path or paths.ONTOLOGY_PATH)
