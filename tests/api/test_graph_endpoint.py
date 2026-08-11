"""대상 : demo/api/main.py — GET /graph

demo/api/main.py 의 /graph 엔드포인트 검증.

가장 중요한 것은 응답이 도메인 계산과 어긋나지 않는지다. 그리기는 이제 서버
안에서 도메인 dict 를 그대로 쓰고(graph_service.domain_graph), 이 응답은 화면이
받는 것이다. 둘이 갈라지면 사람이 보는 그래프와 서버가 아는 그래프가 달라진다.

UI 를 import 하지 않는다. API 테스트가 화면을 끌어오면 화면을 갈아끼울 때
API 테스트가 함께 깨진다.
"""

import pytest
from fastapi.testclient import TestClient

import demo.api.main as backend_main
from demo.api.graph_svg.dot import build_dot
from demo.api.services.graph_service import domain_graph
from ontology.graph import dotted_edges, load_ontology, solid_edges


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
        "interfaces",
        "nodes",
        "solid_edges",
        "dotted_edges",
    }


def test_interfaces_are_names(payload):
    """온톨로지의 interfaces 는 dict 지만 API 는 이름 목록을 준다."""
    assert payload["interfaces"] == list(load_ontology()["interfaces"])


def test_nodes_match_the_ontology(payload):
    assert set(payload["nodes"]) == set(load_ontology()["nodes"])


def test_solid_edge_count_matches(payload):
    assert len(payload["solid_edges"]) == len(solid_edges())


def test_stages_are_gone(payload):
    """열 정렬을 그만두고 neato 배치로 갔다. 응답에 stages 가 없어야 한다."""
    assert "stages" not in payload


# ------------------------------------------------------------ 도메인과의 일치 (핵심)
def test_solid_edges_match_the_domain(payload):
    """JSON 은 튜플 key 를 못 담아 리스트로 편다. 펴는 과정에서 새면 안 된다."""
    flattened = {
        (edge["from"], edge["to"]): edge["interface"]
        for edge in payload["solid_edges"]
    }

    assert flattened == solid_edges()


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
    assert list(payload["nodes"]) == list(load_ontology()["nodes"])
    assert [(e["from"], e["to"]) for e in payload["solid_edges"]] == list(solid_edges())
    assert [(e["a"], e["b"]) for e in payload["dotted_edges"]] == list(dotted_edges())


def test_drawing_uses_the_same_graph_as_the_response():
    """그리기가 받는 도메인 dict 와 도메인 계산이 한 글자도 다르지 않아야 한다.

    그리기는 domain_graph() 로 바로 받는다(어댑터가 사라졌다). 그 경로가
    /graph 응답과 갈라지면 화면과 서버가 다른 그래프를 말하게 된다.
    """
    nodes, solid, dotted = domain_graph()

    assert build_dot(nodes, solid, dotted) == build_dot(
        load_ontology()["nodes"], solid_edges(), dotted_edges()
    )


# ------------------------------------------------------------ version
def test_version_is_stable_while_the_ontology_is(client):
    """내용이 그대로면 값도 그대로여야 한다. 아니면 캐시가 헛돈다."""
    first = client.get("/graph").json()["version"]
    second = client.get("/graph").json()["version"]

    assert first == second
