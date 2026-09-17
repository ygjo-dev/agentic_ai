"""표준 꼴 semantic 항목이 계약을 지키나. 지키면 이름 -> 값 한 벌로.

    [{name: place_name, value: 의왕역}, {name: travel_mode, value: 도보}]
      -> {place_name: "의왕역", travel_mode: "도보"}

**어긋난 값을 조용히 버리지 않는다.** 버리면 그 recipe 가 말하지 않은 기본값으로
조용히 돌아가고, 표에는 「안 말했다」로 보인다. 무엇이 어느 이름에서 어떻게
어긋났는지 적어 SemanticError 로 올린다.

**도구 값을 검사하지 않는다.** WALK 인지 availableOnly 인지 adm_cd 가 맞나는
게시된 execution 과 도구 스키마의 일이다. 여기서 보는 것은 사람이 말한 값의
모양뿐이다 — 이름을 아는가 · 갈래가 맞는가 · 0 이하가 아닌가 · 닫힌 선택지 안인가.

**닫힌 선택지는 지금 확실히 닫힌 것만이다.** 정당 이름 · 공약 분야 · 문서 힌트 ·
충전 가능 조건처럼 사람이 말하는 대로 들어오는 값은 자유 문자열로 둔다. 억지로
닫으면 멀쩡한 발화가 오류가 된다.
"""

from orchestrator import semantic_catalog


class SemanticError(ValueError):
    """발화에서 뽑은 semantic 값이 계약과 다르다."""


def validate(entries: list[dict]) -> dict:
    """표준 꼴 항목 목록 -> {이름: 값}.

    입력  semantic_normalizer.normalize 의 결과
    출력  {이름: 값}. 온 차례 그대로
    규칙  semantic_catalog 에 없는 이름이면 SemanticError.
          문맥 · 부르는 순간 · 앞 단계가 주는 값(document_names · admin_code …)도 여기서 걸림
          같은 이름이 두 번 오면 SemanticError. 어느 쪽이 맞는지 아무도 모름
          목록을 받는 이름은 빈 목록이 아닌 목록, 하나를 받는 이름은 목록이 아닌 값
          TEXT 는 빈 문자열이 아닌 문자열, INTEGER 는 정수, NUMBER 는 정수 · 실수
          (참거짓은 수가 아님)
          positive 인 이름은 0 보다 커야 함. 음수 시간 · 음수 반경 · 0 개는 뜻이 없음
          choices 가 있으면 그 안의 값이어야 함
    제약  값을 고치거나 채우지 않는다.
          기본값은 게시된 execution 이 갖는다. 여기서 넣으면 안 말한 값이 말한 값이 됨
          어긋난 항목을 버리지 않는다.
          도구 값 · 서버 · 칸 이름을 검사하지 않는다.
    """
    said = {}
    for index, entry in enumerate(entries or []):
        name = entry.get("name") if isinstance(entry, dict) else None
        value = entry.get("value") if isinstance(entry, dict) else entry
        at = f"semantic_inputs[{index}]"

        shape = semantic_catalog.CATALOG.get(name) if isinstance(name, str) else None
        if shape is None:
            raise SemanticError(f"{at}: 발화에서 뽑을 수 있는 값이 아니다: {name!r}")
        if name in said:
            raise SemanticError(f"{at}: 같은 이름이 두 번 왔다: {name}")

        _checked(at, name, shape, value)
        said[name] = value
    return said


def _checked(at: str, name: str, shape, value) -> None:
    """값 하나가 그 이름의 모양인가. 아니면 SemanticError."""
    if shape.many:
        if not isinstance(value, list):
            raise SemanticError(f"{at}: {name} 은 목록이다: {value!r}")
        if not value:
            raise SemanticError(f"{at}: {name} 이 빈 목록이다")
        if len(value) > shape.max_items:
            raise SemanticError(f"{at}: {name} 은 {shape.max_items} 칸까지다: {len(value)} 칸이 왔다")
        for item in value:
            _one(at, name, shape, item)
        return

    if isinstance(value, list):
        raise SemanticError(f"{at}: {name} 은 값 하나다. 여럿이 왔다: {value!r}")
    _one(at, name, shape, value)


def _one(at: str, name: str, shape, value) -> None:
    """목록의 한 칸 혹은 값 하나의 갈래 · 범위 · 선택지."""
    if shape.kind == semantic_catalog.TEXT:
        if not isinstance(value, str) or not value:
            raise SemanticError(f"{at}: {name} 은 빈 곳이 없는 문자열이다: {value!r}")
        if shape.choices and value not in shape.choices:
            raise SemanticError(
                f"{at}: {name} 은 {' · '.join(shape.choices)} 중 하나다: {value!r}"
            )
        return

    whole = shape.kind == semantic_catalog.INTEGER
    number = isinstance(value, int) if whole else isinstance(value, (int, float))
    if isinstance(value, bool) or not number:
        raise SemanticError(f"{at}: {name} 은 {'정수' if whole else '수'}다: {value!r}")
    if shape.positive and value <= 0:
        raise SemanticError(f"{at}: {name} 은 0 보다 커야 한다: {value!r}")
