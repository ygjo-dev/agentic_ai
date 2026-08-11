"""대상 : demo/api/main.py — POST /nodes · /nodes/reset

demo/api/main.py 의 /nodes · /nodes/reset 엔드포인트 검증.

등록은 실제 저장소 파일을 바꾼다. tests/node_registration 과 같은 방식으로
앞뒤에 reset_to_init() 을 걸어 되돌린다 — register_node 는 paths 전역을
직접 읽으므로 경로를 주입할 수 없다.

LLM 은 Stub 이다. 실제 Ollama 를 부르지 않는다.
"""

import json

import pytest
from fastapi.testclient import TestClient

import demo.api.main as backend_main
from conftest import REAL_ONTOLOGY_PATH, StubLLMClient, workspace_digest
from ontology.graph import dotted_edges, load_ontology, solid_edges
from ontology.registry import reset_to_init

FORM = {
    "name": "궤도 결함 이력 요약",
    "description": "궤도 점검 보고서에서 결함이 어떻게 이어져 왔는지 요약한다.",
    "inputs": ["DocumentData"],
    "outputs": ["AnalysisResult"],
}

# 시연의 주력 등록이다. 끊겨 있던 load_inspection_doc(실선 0개)이 이어지고
# 궤도 그룹에 점선이 붙는다 — subject 값을 글자 그대로 써야 그렇게 된다.
INFERRED = {
    "node_id": "analyze_crack_trend",
    "properties": {"subject": "궤도"},
    "reason": "궤도 균열 검출과 같은 대상을 다룬다.",
}


@pytest.fixture(autouse=True)
def clean_workspace(isolated_workspace):
    """등록이 건드리는 파일을 임시 디렉터리로 격리한 뒤 앞뒤로 원복한다.

    진짜 저장소에 쓰면 리허설로 만들어둔 시연 상태가 pytest 한 번에 날아간다.
    """
    reset_to_init()
    yield
    reset_to_init()


@pytest.fixture
def client():
    return TestClient(backend_main.app)


@pytest.fixture
def use_llm_client(monkeypatch):
    """demo.api.main 이 쓰는 OllamaClient 를 주어진 Stub 으로 교체한다."""

    def _use(response=INFERRED):
        llm_client = StubLLMClient(json.dumps(response))
        monkeypatch.setattr(backend_main, "OllamaClient", lambda: llm_client)
        return llm_client

    return _use


# ------------------------------------------------------------ 정상 등록
def test_register_returns_200(client, use_llm_client):
    use_llm_client()

    assert client.post("/nodes", json=FORM).status_code == 200


def test_register_body_has_contract_keys(client, use_llm_client):
    use_llm_client()

    body = client.post("/nodes", json=FORM).json()

    assert set(body) == {
        "node_id",
        "node",
        "properties",
        "reason",
        "recipe_ids",
        "paths",
        "new_solid_edges",
        "new_dotted_edges",
        "counts",
        "version",
    }


def test_registered_node_lands_in_the_ontology(client, use_llm_client):
    use_llm_client()

    body = client.post("/nodes", json=FORM).json()

    assert body["node_id"] == "analyze_crack_trend"
    assert "analyze_crack_trend" in load_ontology()["nodes"]


def test_paths_cover_every_new_recipe(client, use_llm_client):
    """화면이 새 recipe 의 경로를 그릴 수 있어야 한다."""
    use_llm_client()

    body = client.post("/nodes", json=FORM).json()

    assert set(body["paths"]) == set(body["recipe_ids"])
    for steps in body["paths"].values():
        assert steps
        for step in steps:
            assert set(step) == {"node_id", "name", "out_interface"}


# ------------------------------------------------------------ 증가분
def test_counts_match_the_actual_increase(client, use_llm_client):
    use_llm_client()
    before_nodes = len(load_ontology()["nodes"])

    body = client.post("/nodes", json=FORM).json()

    assert body["counts"]["nodes"] == [before_nodes, before_nodes + 1]
    assert body["counts"]["nodes"][1] == len(load_ontology()["nodes"])

    before_recipes, after_recipes = body["counts"]["recipes"]
    assert after_recipes - before_recipes == len(body["recipe_ids"])


def test_new_solid_edges_are_the_difference(client, use_llm_client):
    """등록 전후 차집합이어야 한다."""
    use_llm_client()
    before = set(solid_edges())

    body = client.post("/nodes", json=FORM).json()

    reported = {(e["from"], e["to"]) for e in body["new_solid_edges"]}
    assert reported == set(solid_edges()) - before


def test_new_dotted_edges_are_the_difference(client, use_llm_client):
    use_llm_client()
    before = set(dotted_edges())

    body = client.post("/nodes", json=FORM).json()

    reported = {(e["a"], e["b"]) for e in body["new_dotted_edges"]}
    assert reported == set(dotted_edges()) - before


# ------------------------------------------------------------ 잘못된 입력
def test_empty_name_is_422(client, use_llm_client):
    """이름이 비면 등록할 수 없다. 그래프에 이름 없는 노드가 남는다."""
    use_llm_client()

    assert client.post("/nodes", json={**FORM, "name": ""}).status_code == 422


def test_empty_description_is_422(client, use_llm_client):
    use_llm_client()

    assert client.post("/nodes", json={**FORM, "description": ""}).status_code == 422


def test_empty_outputs_is_422(client, use_llm_client):
    """출력이 없으면 어디로도 이어지지 않는다."""
    use_llm_client()

    assert client.post("/nodes", json={**FORM, "outputs": []}).status_code == 422


def test_empty_name_leaves_the_ontology_alone(client, use_llm_client):
    use_llm_client()
    before = len(load_ontology()["nodes"])

    client.post("/nodes", json={**FORM, "name": ""})

    assert len(load_ontology()["nodes"]) == before


def test_unknown_interface_is_422(client, use_llm_client):
    """온톨로지에 없는 인터페이스는 registry 가 막는다 (UnknownInterface)."""
    # 등록이 인터페이스 검사까지 가야 하므로 아직 없는 node_id 를 쓴다.
    use_llm_client({**INFERRED, "node_id": "analyze_unknown_thing"})

    response = client.post("/nodes", json={**FORM, "outputs": ["NoSuchData"]})

    assert response.status_code == 422
    assert "UnknownInterface" in response.json()["detail"]


def test_unknown_interface_leaves_the_ontology_alone(client, use_llm_client):
    use_llm_client({**INFERRED, "node_id": "analyze_unknown_thing"})
    before = len(load_ontology()["nodes"])

    client.post("/nodes", json={**FORM, "outputs": ["NoSuchData"]})

    assert len(load_ontology()["nodes"]) == before


def test_missing_required_field_is_422(client, use_llm_client):
    """name / description 은 필수다."""
    use_llm_client()

    assert client.post("/nodes", json={"inputs": [], "outputs": []}).status_code == 422


# ------------------------------------------------------------ 초기화
def test_reset_returns_ok(client, use_llm_client):
    use_llm_client()
    client.post("/nodes", json=FORM)

    body = client.post("/nodes/reset").json()

    assert body["ok"] is True
    assert body["version"]


def test_reset_undoes_a_registration(client, use_llm_client):
    use_llm_client()
    client.post("/nodes", json=FORM)

    client.post("/nodes/reset")

    assert "analyze_crack_trend" not in load_ontology()["nodes"]


# ------------------------------------------------------------ 격리
def test_registration_does_not_touch_the_real_repository(client, use_llm_client):
    """시연 상태를 만들어둔 뒤 pytest 를 돌려도 등록해둔 노드가 남아야 한다.

    격리가 풀리면(paths monkeypatch 를 빠뜨리면) 여기서 잡힌다.
    """
    before = workspace_digest()

    response = client.post("/nodes", json=FORM)
    assert response.status_code == 200

    assert workspace_digest() == before


def test_isolated_paths_point_outside_the_repository():
    """실제로 임시 디렉터리를 보고 있어야 한다."""
    import paths

    assert paths.ONTOLOGY_PATH != REAL_ONTOLOGY_PATH
    assert "ontology.yaml" == paths.ONTOLOGY_PATH.name


def test_version_changes_after_registration(client, use_llm_client):
    """온톨로지가 바뀌면 값이 바뀌어야 프론트엔드 SVG 캐시가 무효화된다."""
    use_llm_client()
    before = client.get("/graph").json()["version"]

    client.post("/nodes", json=FORM)

    assert client.get("/graph").json()["version"] != before
