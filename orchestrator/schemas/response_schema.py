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


def _axis(choices: list[str]) -> dict:
    """축 한 칸의 스키마. 닫힌 목록에 null 을 더한 것."""
    return {"type": ["string", "null"], "enum": [*choices, None]}


# ── 좁히기 길(두 번 부르기)의 스키마 둘 — ★ 아무도 안 부른다 ────────
#
# 좁히기 자체는 2026-09-01 에 걷었다(태그 `had-narrow-path`). 그때 스키마 둘만
# 남았고 지울지는 다음 사람이 정하기로 했다 (NOTES.md 「열린 과제」).
#
# ★ 2026-09-04 에 축 한 벌(선택지 · 조회 · 검산)을 걷으면서 위의
# recipe_selection_schema 에서 축 세 칸이 빠졌다. **아래 둘은 축을 그대로
# 갖고 있다** — 이제 위와 아래가 같은 축을 말하지 않는다. 되살릴 때 맞대야 한다.

# 1차 응답의 key. 축 셋과 인자만 받던 자리다.
REQUIRED_AXES = ["reason", "given", "want", "about", "argument"]

# 2차 응답의 key. 축은 이미 받았으므로 recipe 관련 셋과 reason 뿐.
REQUIRED_PICK = ["reason", "candidate_recipe_ids", "status", "recipe_id"]


def axis_selection_schema(
    reason_max_length: int,
    given_choices: list[str],
    want_choices: list[str],
    about_choices: list[str],
) -> dict:
    """1차 응답 구조. 축 셋과 인자만 받는다. recipe 는 안 받는다.

    입력  recipe_selection_schema 와 같음
    출력  Ollama 의 format 에 그대로 넣는 JSON schema
    규칙  칸의 뜻과 순서는 recipe_selection_schema 의 앞 다섯 칸과 같음.
          축을 재는 자(check_resolve 의 축 표)가 두 길을 같은 눈으로 보게
          하려는 것임
    """
    return {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "maxLength": reason_max_length},
            "given": _axis(given_choices),
            "want": _axis(want_choices),
            "about": _axis(about_choices),
            "argument": {"type": ["string", "null"]},
        },
        "required": REQUIRED_AXES,
    }


def recipe_pick_schema(reason_max_length: int, candidate_ids: list[str]) -> dict:
    """2차 응답 구조. 좁힌 후보 가운데 고른다.

    입력  reason 길이 상한 · 온톨로지가 좁힌 후보 id 목록
    출력  Ollama 의 format 에 그대로 넣는 JSON schema
    규칙  recipe_id 와 candidate_recipe_ids 의 항목이 후보의 닫힌 목록(enum)임.
          후보 밖의 id 를 문법으로 못 쓰게 함 — 좁히기의 뜻이 그것임
          "여기 없다" 는 status = NO_MATCH 로 말함. 그때 부르는 쪽이 지금 길로
          빠져나감 (resolve_service 의 폴백 나)
    """
    return {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "maxLength": reason_max_length},
            "candidate_recipe_ids": {
                "type": "array",
                "items": {"type": "string", "enum": list(candidate_ids)},
            },
            "status": {"type": "string", "enum": [SELECT, CLARIFY, NO_MATCH]},
            "recipe_id": {"type": ["string", "null"], "enum": [*candidate_ids, None]},
        },
        "required": REQUIRED_PICK,
    }
