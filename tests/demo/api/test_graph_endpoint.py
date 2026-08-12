"""대상 : demo/api/main.py — GET /graph

demo/api/main.py 의 /graph 엔드포인트 검증.

가장 중요한 것은 응답이 도메인 계산과 어긋나지 않는지다. 그리기는 이제 서버
안에서 도메인 dict 를 그대로 쓰고(ontology_service.domain_graph), 이 응답은 화면이
받는 것이다. 둘이 갈라지면 사람이 보는 그래프와 서버가 아는 그래프가 달라진다.

UI 를 import 하지 않는다. API 테스트가 화면을 끌어오면 화면을 갈아끼울 때
API 테스트가 함께 깨진다.
"""

import pytest
from fastapi.testclient import TestClient

import demo.api.main as backend_main
from demo.graph_svg.dot import build_dot
from demo.api.services.ontology_service import domain_graph
from demo.api.services.ontology_service import drawn_nodes
from ontology.graph import dotted_edges, load_ontology, solid_edges, type_ids


@pytest.fixture
def client():
    return TestClient(backend_main.app)


@pytest.fixture
def payload(client):
    response = client.get("/graph")
    assert response.status_code == 200
    return response.json()


# ------------------------------------------------------------ 형태
def test_graph_returns_200(client):
    assert client.get("/graph").status_code == 200


def test_graph_has_contract_keys(payload):
    assert set(payload) == {
        "version",
        "colors",
        "types",
        "nodes",
        "solid_edges",
        "dotted_edges",
    }


def test_types_carry_both_the_id_and_the_name(payload):
    """등록 폼이 고르는 것은 **id** 이고 사람이 읽는 것은 이름이다.

    예전에는 인터페이스 이름(자유 문자열)을 골랐다. 한 글자만 달라도 아무와도
    안 이어지는데 화면에서는 등록이 성공한 것처럼 보였다. 지금은 실재하는
    노드 id 를 고르므로 그럴 수가 없다.
    """
    assert [entry["id"] for entry in payload["types"]] == type_ids()

    nodes = load_ontology()["nodes"]
    for entry in payload["types"]:
        assert set(entry) == {"id", "name"}
        assert entry["name"] == nodes[entry["id"]]["name"]
        assert entry["id"] in nodes, entry


def test_only_the_drawn_nodes_are_sent(payload):
    """**온톨로지 전부를 보내지 않는다.** 그리는 것만 보낸다.

    형식 노드(영상 · 이미지 · 문서 · 분석결과)는 recipe 에 안 나와 실선이 없고
    about 도 안 붙어 점선도 없다. 보내면 아무 선도 없는 점이 다섯 개 떠 있게
    되고, 사람은 그것이 무슨 뜻인지 물어보게 된다.

    조용히 깨지는 자리다 — 화면은 정상으로 보이고 설명만 안 될 뿐이다.
    """
    all_nodes = load_ontology()["nodes"]

    assert set(payload["nodes"]) == set(drawn_nodes())
    assert set(payload["nodes"]) < set(all_nodes), "전부 보내고 있다"

    # 빠진 것은 형식 노드다. 그리고 그것들은 실제로 온톨로지에 있다.
    dropped = set(all_nodes) - set(payload["nodes"])
    assert dropped == set(type_ids()), dropped

    # 그리는 노드는 전부 어느 선엔가 닿아 있어야 한다.
    touched = {nid for pair in solid_edges() for nid in pair}
    touched |= {nid for pair in dotted_edges() for nid in pair}
    assert set(payload["nodes"]) <= touched

    # 그룹은 그린다. 점선의 끝이라 빠지면 점선이 허공에 뜬다.
    assert {"group_platform", "group_track", "group_cctv"} <= set(payload["nodes"])

    # 받고 내놓는 것은 관계에서 뽑아 넣는다. 노드에는 안 적혀 있다.
    assert payload["nodes"]["extract_frames"]["inputs"] == ["video"]
    assert payload["nodes"]["extract_frames"]["executable"] is True
    assert payload["nodes"]["platform_cctv_video"]["executable"] is False
    assert payload["nodes"]["group_track"]["kind"] == "group"
    assert payload["nodes"]["extract_frames"]["kind"] == "function"


def test_solid_edge_count_matches(payload):
    assert len(payload["solid_edges"]) == len(solid_edges())


def test_stages_are_gone(payload):
    """열 정렬을 그만두고 neato 배치로 갔다. 응답에 stages 가 없어야 한다."""
    assert "stages" not in payload


# ------------------------------------------------------------ 도메인과의 일치 (핵심)
def test_solid_edges_match_the_domain(payload):
    """JSON 은 튜플 key 를 못 담아 리스트로 편다. 펴는 과정에서 새면 안 된다."""
    flattened = [(edge["from"], edge["to"]) for edge in payload["solid_edges"]]

    assert flattened == solid_edges()

    # 라벨이 없다. 무엇이 오가는지는 경로 안에 노드로 들어 있다 —
    # 라벨로 또 적으면 같은 것을 두 번 말하는 셈이다.
    for edge in payload["solid_edges"]:
        assert set(edge) == {"from", "to"}, edge


def test_dotted_edges_match_the_domain(payload):
    flattened = {
        (edge["a"], edge["b"]): edge["labels"] for edge in payload["dotted_edges"]
    }

    assert flattened == dotted_edges()


def test_payload_keeps_the_domain_order(payload):
    """순서까지 같아야 한다.

    노드와 엣지가 나오는 순서가 Graphviz 레이아웃을 정한다. 순서가 흔들리면
    좌표가 바뀌어 화면이 깜빡인다. dict 비교는 순서를 안 보므로 따로 본다.
    """
    assert list(payload["nodes"]) == list(drawn_nodes())
    assert [(e["from"], e["to"]) for e in payload["solid_edges"]] == list(solid_edges())
    assert [(e["a"], e["b"]) for e in payload["dotted_edges"]] == list(dotted_edges())


def test_drawing_uses_the_same_graph_as_the_response():
    """그리기가 받는 도메인 dict 와 도메인 계산이 한 글자도 다르지 않아야 한다.

    그리기는 domain_graph() 로 바로 받는다(어댑터가 사라졌다). 그 경로가
    /graph 응답과 갈라지면 화면과 서버가 다른 그래프를 말하게 된다.
    """
    nodes, solid, dotted = domain_graph()

    assert build_dot(nodes, solid, dotted) == build_dot(
        drawn_nodes(), solid_edges(), dotted_edges()
    )

    # 그림에도 형식 노드가 없어야 한다. 위 단언은 양쪽이 같이 틀려도 통과한다.
    dot = build_dot(nodes, solid, dotted)
    for type_id in type_ids():
        assert f'"{type_id}"' not in dot, type_id


# ------------------------------------------------------------ version
def test_version_is_stable_while_the_ontology_is(client):
    """내용이 그대로면 값도 그대로여야 한다. 아니면 캐시가 헛돈다."""
    first = client.get("/graph").json()["version"]
    second = client.get("/graph").json()["version"]

    assert first == second
