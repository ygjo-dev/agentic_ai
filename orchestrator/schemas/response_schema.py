"""
LLM for Static Workflow의 구조화된 Output Schema.
"""

SELECT = "SELECT"
CLARIFY = "CLARIFY"
NO_MATCH = "NO_MATCH"

REQUIRED = [
    "reason",
    "argument",
    "candidate_recipe_ids",
    "status",
    "recipe_id",
]


def recipe_selection_schema(reason_max_length: int) -> dict:
    """발화 해석 응답 구조(json).

    입력  reason 의 길이 상한. 모델마다 다르므로 models.yaml 에서 옴
    출력  Ollama 의 format 에 그대로 넣는 JSON schema
    규칙  상한은 Ollama 가 문법으로 강제하므로 모델이 못 넘음
          properties 순서대로 생성됨. reason 을 맨 앞에 두어 무엇을 비교했는지
          먼저 쓰고 그다음에 고르게 함
          argument 는 발화에서 그대로 떼어 온 값이라 닫힌 목록이 아니고
          enum 이 없음. 무엇을 떼어 올지는 프롬프트가 말함
    제약  상한을 상수로 되돌리지 않는다.
          모델이 바뀌면 함께 바뀌는 값이라 한 모델만 표현하게 됨
          argument 를 장소 · 키워드 · 식별자 세 칸으로 나누지 않는다.
          칸을 나누면 프롬프트가 그만큼 길어짐
    이력  2026-09-04 에 축 세 칸(given · want · about)을 뺐다. 축으로 온톨로지를
          조회해 검산하던 길을 통째로 걷었기 때문임. 까닭과 그때 잃은 여섯은
          NOTES.md 「아흔여섯째」에 있음
    """
    return {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "maxLength": reason_max_length},
            "argument": {"type": ["string", "null"]},
            "candidate_recipe_ids": {"type": "array", "items": {"type": "string"}},
            "status": {"type": "string", "enum": [SELECT, CLARIFY, NO_MATCH]},
            "recipe_id": {"type": ["string", "null"]},
        },
        "required": REQUIRED,
    }
