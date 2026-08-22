"""
LLM for Static Workflow의 구조화된 Output Schema.
"""

SELECT = "SELECT"
CLARIFY = "CLARIFY"
NO_MATCH = "NO_MATCH"

REQUIRED = [
    "reason",
    "given",
    "want",
    "about",
    "argument",
    "candidate_recipe_ids",
    "status",
    "recipe_id",
]


def recipe_selection_schema(
    reason_max_length: int,
    given_choices: list[str],
    want_choices: list[str],
    about_choices: list[str],
) -> dict:
    """발화 해석 응답 구조(json).

    입력  reason 의 길이 상한. 모델마다 다르므로 models.yaml 에서 옴
          축 셋(given · want · about)의 선택지. 부르는 쪽이 온톨로지에서 뽑아 넘김
    출력  Ollama 의 format 에 그대로 넣는 JSON schema
    규칙  상한은 Ollama 가 문법으로 강제하므로 모델이 못 넘음
          properties 순서대로 생성됨. 축 셋을 recipe 보다 앞에 두어
          무엇을 찾는지 먼저 쓰고 그다음에 고르게 함
          축은 닫힌 목록(enum)이고 null 을 허용함. 발화에 근거가 없으면
          null 을 쓰고 그 축으로는 안 거름
          argument 는 축 셋 바로 뒤. 발화에서 그대로 떼어 온 값이라 닫힌
          목록이 아니고 enum 이 없음. 무엇을 떼어 올지는 given 이 말함
    제약  상한을 상수로 되돌리지 않는다.
          모델이 바뀌면 함께 바뀌는 값이라 한 모델만 표현하게 됨
          선택지를 이 파일에 박지 않는다.
          여기는 도메인을 모르는 자리임. 값은 ontology/shortlist.py 가 냄
          argument 를 장소 · 키워드 · 식별자 세 칸으로 나누지 않는다.
          given 이 이미 그 값이 무엇인지 말함. 칸을 나누면 given 과 어긋날
          수 있고 프롬프트도 그만큼 길어짐
    """
    return {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "maxLength": reason_max_length},
            "given": _axis(given_choices),
            "want": _axis(want_choices),
            "about": _axis(about_choices),
            "argument": {"type": ["string", "null"]},
            "candidate_recipe_ids": {"type": "array", "items": {"type": "string"}},
            "status": {"type": "string", "enum": [SELECT, CLARIFY, NO_MATCH]},
            "recipe_id": {"type": ["string", "null"]},
        },
        "required": REQUIRED,
    }


def _axis(choices: list[str]) -> dict:
    """축 한 칸의 스키마. 닫힌 목록에 null 을 더한 것."""
    return {"type": ["string", "null"], "enum": [*choices, None]}
