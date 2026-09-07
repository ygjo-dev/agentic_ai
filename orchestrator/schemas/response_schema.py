"""Static Workflow 의 LLM 응답 구조(JSON Schema)."""

SELECT = "SELECT"
CLARIFY = "CLARIFY"
NO_MATCH = "NO_MATCH"

# 발화에서 뽑은 값 중 **이름이 있는 것**. argument 와 달리 여럿이고, 배선표가
# 그 이름을 "@이름" 으로 적어 제 칸에 넣는다.
#
# **도구가 쓰는 말을 여기 적지 않는다.** 이동수단의 값이 도보 · 자전거 ·
# 승용차 · 대중교통 인 것은 사람이 쓰는 말이라서다. 그것이 WALK · BICYCLE ·
# CAR · TRANSIT 중 무엇이 되는지는 execution/wiring.yaml 의 options 가 안다 —
# 이 파일은 프롬프트에 실리는 자리라 도구 이름이 새면 안 되는 곳이다.
#
# key 는 배선표가 부르는 이름이고 값은 그 칸의 JSON schema 다.
SPOKEN_OPTIONS = {
    "travel_mode": {
        "type": ["string", "null"],
        "enum": ["도보", "자전거", "승용차", "대중교통", None],
    },
    "minutes": {
        "type": ["array", "null"],
        "items": {"type": "integer"},
    },
}

REQUIRED = [
    "reason",
    "argument",
    *SPOKEN_OPTIONS,
    "candidate_recipe_ids",
    "status",
    "recipe_id",
]


def recipe_selection_schema(reason_max_length: int) -> dict:
    """발화 해석 응답 구조(json).

    입력  reason 의 길이 상한. 모델마다 다르므로 models.yaml 에서 옴
    출력  provider 가 문법으로 강제하는 JSON schema
    규칙  properties 순서대로 생성됨. reason 을 맨 앞에 두어 무엇을 비교했는지
          먼저 쓰고 그다음에 고르게 함
          argument 는 발화에서 그대로 떼어 온 값이라 닫힌 목록이 아니고
          enum 이 없음. 무엇을 떼어 올지는 프롬프트가 말함
          SPOKEN_OPTIONS 는 argument 바로 뒤에 옴. 발화에서 값을 뽑는 칸끼리
          붙어 있어야 프롬프트의 「뽑는 법」 절과 차례가 같음
          말하지 않은 값은 null 임. 기본값을 여기서 넣지 않음 —
          무엇이 기본인가는 배선표가 아는 실행 쪽 값임
    제약  상한을 상수로 되돌리지 않는다.
          모델이 바뀌면 함께 바뀌는 값이라 한 모델만 표현하게 됨
          argument 를 장소 · 키워드 · 식별자 세 칸으로 나누지 않는다.
          칸을 나누면 프롬프트가 그만큼 길어짐
          SPOKEN_OPTIONS 의 enum 에 도구가 쓰는 말을 적지 않는다.
          이 schema 가 프롬프트에 실려 도구 이름이 새는 자리가 됨
    """
    return {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "maxLength": reason_max_length},
            "argument": {"type": ["string", "null"]},
            **{name: dict(field) for name, field in SPOKEN_OPTIONS.items()},
            "candidate_recipe_ids": {"type": "array", "items": {"type": "string"}},
            "status": {"type": "string", "enum": [SELECT, CLARIFY, NO_MATCH]},
            "recipe_id": {"type": ["string", "null"]},
        },
        "required": REQUIRED,
    }
