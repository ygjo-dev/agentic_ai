"""대상 : ontology/registry.py — infer_node()

infer_node() 검증. LLM 이 노드 id 와 properties 를 판단한다.

Stub 으로 검증한다. 실제 호출은 CPU 추론이라 30~60초 걸린다.

LLM 이 하는 일은 "기존 key 중에서 고르기" 가 아니다. 새 노드가 기존 노드 중
무엇과 관계있는지 먼저 판단하고, 그 관계를 점선으로 드러내려면 관계된 노드와
같은 key: value 를 가져야 하므로 그렇게 쓴다. 관계가 없으면 비운다.
"""

import json

import pytest

import paths
from conftest import StubLLMClient
from ontology.registry import NODE_REGISTRATION_SCHEMA, InvalidInference, infer_node

FORM = {
    "name": "구조물 균열 진행 추세 분석",
    "description": "문서에서 구조물 균열 폭의 시간 변화를 분석한다.",
    "inputs": ["DocumentData"],
    "outputs": ["AnalysisResult"],
}

GOOD = {
    "node_id": "analyze_crack_trend",
    "properties": {"target": "구조물"},
    "reason": "구조물 균열 분석과 같은 대상을 다룬다.",
}


def stub(response: dict | str):
    return StubLLMClient(response if isinstance(response, str) else json.dumps(response))


# ------------------------------------------------------------ 프롬프트
def test_prompt_carries_existing_nodes_with_properties():
    """어느 노드와 관계있는지 판단하려면 기존 properties 를 봐야 한다."""
    client = stub(GOOD)

    infer_node(FORM, llm_client=client)

    sent = client.prompts[0]
    assert "detect_structure_crack" in sent
    assert "target: 구조물" in sent or "구조물" in sent
    assert "generate_word" in sent


def test_prompt_carries_the_form_input():
    client = stub(GOOD)

    infer_node(FORM, llm_client=client)

    sent = client.prompts[0]
    assert FORM["name"] in sent
    assert FORM["description"] in sent
    assert "DocumentData" in sent


def test_prompt_lists_the_allowed_property_keys():
    """새 key 를 만들면 점선 조회가 갈라진다. 프롬프트로도 알린다."""
    client = stub(GOOD)

    infer_node(FORM, llm_client=client)

    sent = client.prompts[0]
    for key in ("source", "site", "target", "output_kind", "format"):
        assert key in sent, key


# ------------------------------------------------------------ 정상 응답
def test_returns_node_id_and_properties():
    result = infer_node(FORM, llm_client=stub(GOOD))

    assert result["node_id"] == "analyze_crack_trend"
    assert result["properties"] == {"target": "구조물"}
    assert result["reason"]


def test_empty_properties_is_accepted():
    """관계가 없으면 비운다. 억지로 끼워 맞추는 것보다 낫다."""
    result = infer_node(FORM, llm_client=stub({**GOOD, "properties": {}}))

    assert result["properties"] == {}


def test_new_value_on_a_known_key_is_accepted():
    """막는 것은 key 뿐이다. 값은 새로워도 된다."""
    result = infer_node(FORM, llm_client=stub({**GOOD, "properties": {"target": "터널"}}))

    assert result["properties"] == {"target": "터널"}


# ------------------------------------------------------------ 거부
@pytest.mark.parametrize(
    "node_id",
    ["Analyze-Crack", "분석노드", "analyze crack", "1analyze", "analyzeCrackTrend", ""],
)
def test_malformed_node_id_is_rejected(node_id):
    with pytest.raises(InvalidInference):
        infer_node(FORM, llm_client=stub({**GOOD, "node_id": node_id}))


def test_unknown_property_key_is_rejected():
    with pytest.raises(InvalidInference):
        infer_node(
            FORM, llm_client=stub({**GOOD, "properties": {"modality": "document"}})
        )


def test_duplicate_node_id_is_rejected():
    """이미 있는 id 를 주면 온톨로지가 덮어써진다."""
    with pytest.raises(InvalidInference):
        infer_node(FORM, llm_client=stub({**GOOD, "node_id": "analyze_congestion"}))


def test_properties_must_be_an_object():
    with pytest.raises(InvalidInference):
        infer_node(FORM, llm_client=stub({**GOOD, "properties": ["target"]}))


# ------------------------------------------------------------ 깨진 응답
def test_non_json_response_raises():
    with pytest.raises(Exception) as error_info:
        infer_node(FORM, llm_client=stub("이건 JSON 이 아니다"))

    assert "이건 JSON 이 아니다" in str(error_info.value)


def test_missing_key_raises():
    with pytest.raises(Exception):
        infer_node(FORM, llm_client=stub({"node_id": "x"}))


# ------------------------------------------------------------ 스키마
def test_schema_declares_the_three_fields():
    assert set(NODE_REGISTRATION_SCHEMA["required"]) == {
        "node_id",
        "properties",
        "reason",
    }
    assert NODE_REGISTRATION_SCHEMA["type"] == "object"


def test_prompt_file_exists_and_has_placeholders():
    text = paths.NODE_REGISTRATION_PROMPT_PATH.read_text(encoding="utf-8")

    assert "{existing_nodes}" in text
    assert "{new_node}" in text
    assert "{property_keys}" in text
