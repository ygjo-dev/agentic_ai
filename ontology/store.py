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
    """ontology.yaml 원문을 dict 로."""
    path = path or paths.ONTOLOGY_PATH
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def nodes(path=None) -> dict:
    """노드 dict. {node_id: {name, description, inputs, outputs, properties}}"""
    return read(path)["nodes"]


def interfaces(path=None) -> list[str]:
    """인터페이스 이름 목록.

    원문에서는 {이름: {description}} 형태의 dict 다. 이름만 순서대로 뽑는다.
    """
    return list(read(path)["interfaces"])


def append_node(node_id: str, node: dict, path=None) -> None:
    """노드 한 덩어리를 파일 끝에 이어 붙인다.

    **`yaml.dump` 로 다시 쓰지 않는다.** 파일 상단의 구조 원칙 주석과 손으로
    맞춘 들여쓰기가 통째로 날아가기 때문이다. `nodes:` 가 파일 마지막이라
    끝에 붙이면 된다.

    중복 · 인터페이스 · property key 검사는 하지 않는다. 그것은 도메인 규칙이라
    `registry.add_node()` 가 맡는다. 여기는 쓰기만 안다.
    """
    path = path or paths.ONTOLOGY_PATH
    path.write_text(
        path.read_text(encoding="utf-8").rstrip("\n")
        + "\n\n"
        + node_block(node_id, node)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def node_block(node_id: str, node: dict) -> str:
    """온톨로지에 적을 노드 한 덩어리. 기존 파일과 같은 들여쓰기."""
    lines = [
        f"  {node_id}:",
        f"    name: {node['name']}",
        f"    description: {node['description']}",
    ]

    for field in ("inputs", "outputs"):
        values = node[field]
        if values:
            lines.append(f"    {field}:")
            lines += [f"      - {value}" for value in values]
        else:
            lines.append(f"    {field}: []")

    properties = node.get("properties") or {}
    if properties:
        lines.append("    properties:")
        lines += [f"      {key}: {value}" for key, value in properties.items()]
    else:
        # 기존 노드와 관계가 없다는 뜻. 억지로 채우지 않는다.
        lines.append("    properties: {}")

    return "\n".join(lines)


def restore_from_init(path=None) -> None:
    """`_init` 사본으로 되돌린다. 온톨로지만이다.

    recipe 와 menu 는 `registry.reset_to_init()` 이 이어서 되돌린다 —
    그쪽은 아직 이 파일이 맡는 자산이 아니다.

    `_init` 사본 자체는 절대 건드리지 않는다. 그것이 망가지면 되돌릴 곳이 없다.
    """
    shutil.copy2(paths.INIT_ONTOLOGY_PATH, path or paths.ONTOLOGY_PATH)
