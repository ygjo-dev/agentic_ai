"""
LLM for Static Workflow의 구조화된 Output Schema.
"""

SELECT = "SELECT"
CLARIFY = "CLARIFY"
NO_MATCH = "NO_MATCH"

REQUIRED = ["reason", "candidate_recipe_ids", "status", "recipe_id"]


def recipe_selection_schema(reason_max_length: int) -> dict:
    """발화 해석 응답 구조(json).

    입력  reason 의 길이 상한. 모델마다 다르므로 models.yaml 에서 옴
    출력  Ollama 의 format 에 그대로 넣는 JSON schema
    규칙  상한은 Ollama 가 문법으로 강제하므로 모델이 못 넘음
    제약  상한을 상수로 되돌리지 않는다.
          모델이 바뀌면 함께 바뀌는 값이라 한 모델만 표현하게 됨
    """
    return {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "maxLength": reason_max_length},
            "candidate_recipe_ids": {"type": "array", "items": {"type": "string"}},
            "status": {"type": "string", "enum": [SELECT, CLARIFY, NO_MATCH]},
            "recipe_id": {"type": ["string", "null"]},
        },
        "required": REQUIRED,
    }
