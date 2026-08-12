"""대상 : demo/api/main.py — POST /nodes · /nodes/reset

demo/api/main.py 의 /nodes · /nodes/reset 엔드포인트 검증.

등록은 실제 저장소 파일을 바꾼다. tests/node_registration 과 같은 방식으로
앞뒤에 reset_to_init() 을 걸어 되돌린다 — register_node 는 paths 전역을
직접 읽으므로 경로를 주입할 수 없다.

LLM 은 Stub 이다. 실제 Ollama 를 부르지 않는다.
"""

import json

import pytest
import yaml
from fastapi.testclient import TestClient

import demo.api.main as backend_main
import paths
from conftest import REAL_ONTOLOGY_PATH, StubLLMClient, workspace_digest
from demo.api.services.ontology_service import drawn_nodes
from ontology.graph import dotted_edges, load_ontology, solid_edges
from ontology.registry import reset_to_init

# 받고 내놓는 것은 **타입 노드 id** 다. 이름이 아니다 — 예전에는 자유 문자열
# 이라 한 글자만 달라도 아무와도 안 이어졌다.
FORM = {
    "name": "승강장 위험 행동 검출",
    "description": "이미지에서 승강장 승객의 위험 행동을 검출한다.",
    "inputs": ["image"],
    "outputs": ["analysis"],
}

# 시연의 주력 등록이다. 프레임 추출 뒤에 붙어 승강장 경로가 통째로 하나 더
# 생기고, 승강장 그룹에 점선이 붙는다.
INFERRED = {
    "node_id": "detect_risky_behavior",
    "groups": ["group_platform"],
    "reason": "혼잡도 분석과 같은 대상에 관한 것이다.",
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
        "groups",
        "reason",
        "recipe_ids",
        "paths",
        "accepted",
        "pending",
        "new_solid_edges",
        "new_dotted_edges",
        "counts",
        "version",
    }


def test_registered_node_lands_in_the_ontology(client, use_llm_client):
    use_llm_client()

    body = client.post("/nodes", json=FORM).json()

    assert body["node_id"] == "detect_risky_behavior"
    assert "detect_risky_behavior" in load_ontology()["nodes"]

    # 노드에는 이름과 설명뿐이다. 받고 내놓는 것도, 무엇에 관한 것인지도 관계다.
    assert set(load_ontology()["nodes"]["detect_risky_behavior"]) == {
        "name", "description"
    }
    written = load_ontology()["edges"]
    for to, predicate in (
        ("image", "hasInput"), ("analysis", "hasOutput"), ("group_platform", "about")
    ):
        assert {
            "from": "detect_risky_behavior", "to": to, "predicate": predicate
        } in written


def test_paths_cover_every_new_recipe(client, use_llm_client):
    """화면이 새 recipe 의 경로를 그릴 수 있어야 한다."""
    use_llm_client()

    body = client.post("/nodes", json=FORM).json()

    assert set(body["paths"]) == set(body["recipe_ids"])
    for steps in body["paths"].values():
        assert steps
        for step in steps:
            assert set(step) == {"node_id", "name", "out_type"}


# ------------------------------------------------------------ 증가분
def test_counts_match_the_actual_increase(client, use_llm_client):
    use_llm_client()
    before_nodes = len(drawn_nodes())

    body = client.post("/nodes", json=FORM).json()

    # 세는 것은 **그리는 노드**다. 온톨로지 전부가 아니다 — 화면이 "노드 N개"
    # 라고 적어놓고 N개가 안 보이면 사람이 세어보고 어긋난 것을 발견한다.
    assert body["counts"]["nodes"] == [before_nodes, before_nodes + 1]
    assert body["counts"]["nodes"][1] == len(drawn_nodes())

    before_recipes, after_recipes = body["counts"]["recipes"]
    assert after_recipes - before_recipes == len(body["recipe_ids"])


def test_new_solid_edges_are_the_difference(client, use_llm_client):
    """등록 전후 차집합이어야 한다."""
    use_llm_client()
    before = set(solid_edges())

    body = client.post("/nodes", json=FORM).json()

    reported = {(e["from"], e["to"]) for e in body["new_solid_edges"]}
    assert reported == set(solid_edges()) - before
    assert reported, "새 실선이 하나도 없으면 이 검사가 무력하다"


def test_new_dotted_edges_are_the_difference(client, use_llm_client):
    use_llm_client()
    before = set(dotted_edges())

    body = client.post("/nodes", json=FORM).json()

    reported = {(e["a"], e["b"]) for e in body["new_dotted_edges"]}
    assert reported == set(dotted_edges()) - before


# ------------------------------------------------------------ 검토 관문
def test_pending_paths_come_back_with_display_steps(client, use_llm_client):
    """검토 대상은 chain(승인 요청용)과 steps(화면용)를 함께 담는다.

    steps 의 about 은 대상 노드의 **이름**이다 — 화면이 어느 노드에서 대상이
    어긋나는지 보여줄 근거다. id 는 사람이 읽을 것이 아니다.
    """
    use_llm_client()

    body = client.post("/nodes", json=FORM).json()

    assert body["pending"], "검토 대상이 없으면 이 검사가 무력하다"
    for entry in body["pending"]:
        assert set(entry) == {"chain", "steps"}
        assert [step["node_id"] for step in entry["steps"]] == entry["chain"]
        for step in entry["steps"]:
            assert set(step) == {"node_id", "name", "about"}

    # recipe_ids 는 자동 승격분만이다. 검토 대상은 아직 recipe 가 아니다.
    assert set(body["recipe_ids"]) == set(body["accepted"]["recipe_ids"])
    assert body["counts"]["recipes"][1] - body["counts"]["recipes"][0] == len(
        body["recipe_ids"]
    )


def test_approving_a_subset_promotes_only_that_subset(client, use_llm_client):
    """고른 경로만 recipe 파일이 되고 counts 가 승인 후 값으로 갱신된다."""
    use_llm_client()
    registered = client.post("/nodes", json=FORM).json()
    pending = [entry["chain"] for entry in registered["pending"]]
    assert len(pending) >= 2, "후보가 둘은 있어야 '일부만 승인' 을 검사할 수 있다"
    before_recipes = registered["counts"]["recipes"][1]

    response = client.post("/nodes/approve", json={"chains": [pending[0]]})

    assert response.status_code == 200
    body = response.json()
    assert len(body["recipe_ids"]) == 1
    assert set(body["paths"]) == set(body["recipe_ids"])
    assert body["counts"]["recipes"] == [before_recipes, before_recipes + 1]
    assert body["version"] != registered["version"]

    # 승인된 경로가 실제 파일이 됐고, 안 고른 것은 파일이 없다.
    written = {
        tuple(step["node"] for step in yaml.safe_load(p.read_text(encoding="utf-8"))["steps"])
        for p in paths.RECIPES_DIR.glob("recipe_*.yaml")
    }
    assert tuple(pending[0]) in written
    assert tuple(pending[1]) not in written


def test_an_unproposed_chain_is_422(client, use_llm_client):
    """제안에 없던 경로는 거부된다. 아무 경로나 승인되면 관문이 뚫린다."""
    use_llm_client()
    client.post("/nodes", json=FORM)

    response = client.post(
        "/nodes/approve",
        json={"chains": [["platform_cctv_video", "extract_frames"]]},
    )

    assert response.status_code == 422
    assert "UnproposedChain" in response.json()["detail"]


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


def test_unknown_type_is_422(client, use_llm_client):
    """온톨로지에 없는 타입은 registry 가 막는다 (UnknownType)."""
    # 등록이 타입 검사까지 가야 하므로 아직 없는 node_id 를 쓴다.
    use_llm_client({**INFERRED, "node_id": "analyze_unknown_thing"})

    response = client.post("/nodes", json={**FORM, "outputs": ["NoSuchData"]})

    assert response.status_code == 422
    assert "UnknownType" in response.json()["detail"]


def test_several_subjects_all_come_back(client, use_llm_client):
    """대상을 여럿 고르면 전부 돌아온다. 하나만 오면 화면에서 점선이 빠진다."""
    use_llm_client({**INFERRED, "groups": ["group_platform", "group_cctv"]})

    body = client.post("/nodes", json=FORM).json()

    assert body["groups"] == ["group_platform", "group_cctv"]
    assert len(body["new_dotted_edges"]) == 2


def test_unknown_type_leaves_the_ontology_alone(client, use_llm_client):
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

    assert "detect_risky_behavior" not in load_ontology()["nodes"]


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
