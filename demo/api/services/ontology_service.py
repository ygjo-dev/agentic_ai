"""온톨로지를 읽어 API 응답 형태로 옮긴다.

**demo/ 안에서 온톨로지를 읽는 유일한 지점이다.** 다른 서비스는 여기를 거친다 —
그래프DB 로 바뀔 때 고칠 곳이 하나여야 하기 때문이다.

이름이 graph_service 였는데 graph_svg 와 "graph" 의 뜻이 달라 헷갈렸다.
여기의 graph 는 노드와 관계라는 **데이터**이고, graph_svg 의 graph 는 **그림**이다.
실제로 그 혼동 때문에 두 모듈이 비슷한 계층인 줄 알고 역방향 import 가 생겼었다.

색만은 graph_svg 에게 묻는다. 그리는 쪽이 팔레트의 주인이고, 화면은 그래프 SVG 와
같은 색으로 칩과 배지를 칠해야 한다 — 출처가 둘이면 조용히 어긋난다.

도메인 코드를 옮기거나 고치지 않는다 — 호출만 한다.
"""

import hashlib

import paths
from demo.graph_svg.dot import COLORS
from ontology import store
from ontology.graph import (
    ancestors,
    dotted_edges,
    group_ids,
    handed_over,
    inputs_of,
    is_executable,
    load_ontology,
    outputs_of,
    recipe_nodes,
    solid_edges,
    type_ids,
)


def ontology_version() -> str:
    """ontology.yaml + recipes/*.yaml 내용의 sha1.

    출력  16진 해시 문자열
    규칙  파일명도 해시에 넣음. 내용이 같은 recipe 가 다른 번호로 늘어나는
          경우를 내용만으로는 구분할 수 없음
    제약  mtime 으로 계산하지 않는다.
          reset_to_init 은 파일을 복사하므로 내용이 같아도 mtime 이 바뀜.
          프론트엔드 SVG 캐시가 헛돌고 그래프가 깜빡임
    """
    digest = hashlib.sha1()
    digest.update(store.raw_bytes())

    for recipe_path in sorted(paths.RECIPES_DIR.glob("*.yaml")):
        digest.update(recipe_path.name.encode("utf-8"))
        digest.update(recipe_path.read_bytes())

    return digest.hexdigest()


def recipe_ids() -> list[str]:
    """지금 있는 recipe id 전부. 번호 순."""
    return sorted(path.stem for path in paths.RECIPES_DIR.glob("recipe_*.yaml"))


def executable_in(recipe_id: str) -> list[str]:
    """recipe 안에서 실제로 부를 노드.

    입력  recipe id
    출력  실행 노드 id 목록. 경로 순서 그대로
    규칙  hasOutput 이 있으면 실행 노드. 데이터 노드(말한 장소)는 값을 준비할
          뿐 부를 것이 없어 빠짐
    """
    return [node_id for node_id in recipe_nodes(recipe_id) if is_executable(node_id)]


def handed_types(node_id: str) -> list[str]:
    """그 노드가 다음 자리에 건네는 타입. 상위 타입까지 편 것.

    입력  노드 id. 실행 노드일 수도 데이터 노드일 수도 있음
    출력  타입 id 목록. 앞에 오는 것이 먼저 건네는 것
    규칙  실행 노드는 hasOutput 이 말함. 적힌 순서 그대로임.
          장소 좌표 변환은 지점 좌표를 지도 범위보다 먼저 내놓음
          데이터 노드는 자기 자신을 건네므로 is-a 로 가리키는 상위 타입을 폄.
          말한 식별자는 행정구역 코드 · 선거구 코드 · 충전소 번호를 가리킴
          중복은 접고 순서는 유지함
    제약  받는 쪽이 무엇을 받는지 보지 않는다. 고르는 것은 부르는 쪽 일임
    """
    seen, handed = set(), []
    for out_id in handed_over(node_id):
        for type_id in (out_id, *ancestors(out_id)):
            if type_id not in seen:
                seen.add(type_id)
                handed.append(type_id)
    return handed


def path_of(recipe_id: str, nodes: dict | None = None) -> list[dict]:
    """recipe 한 벌의 실행 경로.

    입력  recipe id · 노드 전체(없으면 온톨로지에서 읽음)
    출력  [{node_id, name, out_type}, ...] 순서 그대로.
          없는 recipe 는 빈 리스트. recipe_nodes 가 그렇게 동작하므로 따름
    규칙  out_type 은 다음 노드로 흘러가는 것
            실행 노드   hasOutput 이 말함
            데이터 노드 자기 자신. 승강장 CCTV 영상은 무언가를 내놓는 것이
                        아니라 그 자체가 다음 단계로 건네짐
          경로의 마지막 노드도 값이 있지만 화면은 마지막 화살표를 안 그려
          쓰이지 않음
    """
    nodes = load_ontology()["nodes"] if nodes is None else nodes

    chain = []
    for node_id in recipe_nodes(recipe_id):
        node = nodes.get(node_id) or {}
        handed = outputs_of(node_id) or [node_id]
        chain.append(
            {
                "node_id": node_id,
                "name": node.get("name", node_id),
                "out_type": nodes.get(handed[0], {}).get("name", handed[0]),
            }
        )
    return chain


def paths_for(ids, nodes: dict | None = None) -> dict[str, list[dict]]:
    """recipe id 여럿의 경로를 한 번에. 중복은 접고 순서는 유지함."""
    nodes = load_ontology()["nodes"] if nodes is None else nodes
    return {recipe_id: path_of(recipe_id, nodes) for recipe_id in dict.fromkeys(ids)}


def drawn_nodes() -> dict:
    """화면에 그리는 노드. 온톨로지 전부가 아님.

    출력  {node_id: {name, description, kind}}
    규칙  그리는 것은 셋
            실행할 수 있는 경로   실선에 나오는 노드
            무엇에 관한 것인가    그룹과 점선에 나오는 노드
            실행할 수 있는 노드   전부
          kind 를 여기서 만들어 붙임. 온톨로지에는 종류가 안 적혀 있고,
          그리는 쪽은 그룹을 다르게 칠해야 함
    제약  실행할 수 있는 노드를 실선 조건에 맡기지 않는다.
          등록한 노드의 경로가 전부 버려질 수 있음. 대상이 어긋나는 경로는
          등록되지 않으므로(crosses_groups) 그런 노드는 어느 recipe 에도
          안 들어감. 빼면 그 노드가 화면에서 사라지고, 새 점선이 좌표 없는
          노드를 가리켜 neato -n 이 그림을 통째로 거부함
          (실측 : "node ... has no position as required by the -n flag").
          등록 직후에 그 노드를 보여주는 것이 등록 장면 자체임
          형식 노드(영상 · 이미지 · 문서 · 분석결과)를 그리지 않는다.
          실행하지 않고, recipe 에 나오지 않아 실선이 없고, about 도 안 붙어
          점선도 없음. 그리면 아무 선도 없는 점 다섯 개가 떠 있게 되고 사람은
          그것이 무슨 뜻인지 물어보게 됨. 형식 계층은 경로를 만들 때 쓰는
          것이지 사람이 볼 것이 아님
          kind 를 파일에 되돌려 적지 않는다.
          화면에만 필요한 구분이라 파일에 적으면 관계와 어긋날 수 있는 자리가
          하나 늘어남
    """
    nodes = load_ontology()["nodes"]
    groups = set(group_ids())
    in_paths = {node_id for pair in solid_edges() for node_id in pair}
    in_dotted = {node_id for pair in dotted_edges() for node_id in pair}

    return {
        node_id: {**node, "kind": "group" if node_id in groups else "function"}
        for node_id, node in nodes.items()
        if node_id in groups
        or node_id in in_paths
        or node_id in in_dotted
        or is_executable(node_id)
    }


def domain_graph() -> tuple[dict, dict, dict]:
    """그리기가 쓰는 도메인 형태 그대로.

    출력  (nodes, solid, dotted). solid / dotted 는 튜플 키 dict
    규칙  온톨로지를 읽는 곳은 이 모듈 하나. graph_svg 는 여기서 받아 쓰기만 함
    이력  JSON 은 튜플 키를 못 담아 graph_payload 는 리스트로 펴지만, 서버
          안에서 그릴 때는 펼 이유가 없음. 예전에는 프론트엔드가 받아서 다시
          튜플로 되돌렸음(to_build_dot_args). 그 왕복이 사라졌음
    """
    return drawn_nodes(), solid_edges(), dotted_edges()


def graph_payload() -> dict:
    """그래프 한 벌 전체. 프론트엔드가 그리는 데 필요한 것만 담음.

    출력  version · colors · types · nodes · solid_edges · dotted_edges
    제약  엣지를 객체(dict)로 담지 않는다.
          JSON 이 튜플 키를 못 담기도 하지만 그보다 순서가 중요함. 노드와
          엣지가 나오는 순서가 Graphviz 레이아웃을 정하므로 왕복에서 순서가
          흔들리면 좌표가 바뀜
    """
    all_nodes = load_ontology()["nodes"]

    return {
        "version": ontology_version(),
        # 색은 graph_svg 가 정한다. UI 가 자기 팔레트를 따로 들면 두 곳이
        # 조용히 어긋나고, 그때 사람은 화면을 보고 코드를 의심한다.
        "colors": dict(COLORS),
        # 등록 폼의 입출력 선택지. **이름이 아니라 id 를 고르게 한다** —
        # 예전에는 인터페이스 이름(자유 문자열)이라 한 글자만 달라도 아무와도
        # 안 이어졌다. 이름은 사람이 읽으라고 같이 보낸다.
        "types": [
            {"id": type_id, "name": all_nodes[type_id]["name"]}
            for type_id in type_ids()
        ],
        # 그리는 노드만 담는다. 무엇을 받고 내놓는지는 관계에서 뽑아 넣는다 —
        # 노드에는 안 적혀 있고, 화면은 칩에 그것을 보여준다.
        "nodes": {
            node_id: {
                "kind": node["kind"],
                "name": node["name"],
                "description": node["description"],
                "inputs": inputs_of(node_id),
                "outputs": outputs_of(node_id),
                "executable": is_executable(node_id),
            }
            for node_id, node in drawn_nodes().items()
        },
        # 실선에는 라벨이 없다. 무엇이 오가는지는 경로 안에 노드로 들어 있다.
        "solid_edges": [{"from": frm, "to": to} for frm, to in solid_edges()],
        "dotted_edges": [
            {"a": a, "b": b, "labels": labels}
            for (a, b), labels in dotted_edges().items()
        ],
    }
