"""backend/main.py 의 /graph 엔드포인트 검증.

가장 중요한 것은 JSON 왕복에서 정보가 새지 않는지다. 프론트엔드는 이 응답을
to_build_dot_args() 로 되돌려 그리므로, 되돌린 결과가 도메인 계산과 다르면
화면이 달라진다.
"""

import pytest
from fastapi.testclient import TestClient

import backend.main as backend_main
from frontend.components.graph_section import build_dot, to_build_dot_args
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


# ------------------------------------------------------------ 왕복 (핵심)
def test_solid_edges_survive_the_round_trip(payload):
    """JSON 은 튜플 key 를 못 담는다. 어댑터가 정확히 되돌려야 한다."""
    _, solid, _ = to_build_dot_args(payload)

    assert solid == solid_edges()


def test_dotted_edges_survive_the_round_trip(payload):
    _, _, dotted = to_build_dot_args(payload)

    assert dotted == dotted_edges()


def test_dot_is_identical_to_the_domain_computation(payload):
    """왕복한 인자로 그린 DOT 이 도메인에서 바로 그린 것과 한 글자도 다르지 않아야 한다.

    노드와 엣지가 나오는 순서가 Graphviz 레이아웃을 정한다. 순서가 흔들리면
    좌표가 바뀌어 화면이 깜빡인다 — 문자열 비교가 그것까지 잡는다.
    """
    nodes, solid, dotted = to_build_dot_args(payload)

    assert build_dot(nodes, solid, dotted) == build_dot(
        load_ontology()["nodes"], solid_edges(), dotted_edges()
    )


# ------------------------------------------------------------ version
def test_version_is_stable_while_the_ontology_is(client):
    """내용이 그대로면 값도 그대로여야 한다. 아니면 캐시가 헛돈다."""
    first = client.get("/graph").json()["version"]
    second = client.get("/graph").json()["version"]

    assert first == second
