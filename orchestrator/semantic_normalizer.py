"""LLM 이 뽑은 semantic 값을 표준 꼴로. **판정은 안 한다.**

    {place_name: " 의왕역 ", travel_time_cutoffs_min: [15, 30, 60]}
      -> [{name: place_name, value: 의왕역}, {name: travel_time_cutoffs_min, value: [15, 30, 60]}]

응답 schema 가 이름마다 갈래를 알고 있어 수는 수로, 목록은 목록으로 온다. 여기서
하는 일은 모델이 남긴 앞뒤 공백을 지우고 「안 말한 것」을 빼는 것, 그리고 문법이
없는 자리(시험 stub · 다른 provider)에서 온 문자열 수를 되돌리는 것뿐이다.

**LLM 을 다시 부르지 않고, 도구를 모른다.** 「도보」를 WALK 로 바꾸지 않고,
「청주시」를 행정코드로 찾지 않고, 「내일」을 날짜로 셈하지 않는다. 그것은
각각 게시된 execution 의 map · 도구 · 부르는 순간의 일이다.

**틀린 값을 여기서 버리지 않는다.** 수로 못 읽히는 값은 문자열 그대로 두고
넘긴다 — semantic_validator 가 무엇이 어긋났는지 말한다. 여기서 조용히
지우면 「안 말한 것」과 「잘못 뽑힌 것」이 한 모양이 된다.

**빈 값은 틀린 값이 아니라 안 말한 것이다.** 빈 문자열 · 빈 목록 · null 은 그
이름을 통째로 뺀다. 남겨 두면 실행에서 「말했는데 빈 값」과 「안 말함」이 같은
자리로 가는데, 뒤엣것만 게시된 default 로 가야 한다.
"""

import re

from orchestrator import semantic_catalog

# 수로 읽을 글자. 자리수 구분 쉼표를 안 지운다 — "15,30,60" 이 153060 이 된다.
_NUMBER = re.compile(r"[+-]?(?:[0-9]+\.[0-9]+|[0-9]+)$")

def normalize(raw) -> list[dict]:
    """raw semantic_inputs -> 표준 꼴 항목 목록.

    입력  LLM 응답의 semantic_inputs. 말한 이름만 key 로 있는 성긴 object. 없으면 None
    출력  [{name, value}] 온 차례 그대로. value 는 값 하나이거나 목록
    규칙  이름 · 문자열 값의 앞뒤 공백을 지움
          빈 문자열 · 빈 목록 · null 은 안 말한 것이라 그 이름을 뺌.
          목록 안의 빈 칸도 같게 빼고, 그래서 목록이 비면 이름을 뺌
          이름이 수를 받는 것이면 "15" -> 15, "7.7" -> 7.7. 못 읽히면 글자 그대로 둠
          목록의 차례를 바꾸거나 중복을 지우지 않음. 말한 차례가 뜻임
          값의 모양(목록인가 · 갈래가 맞나)을 여기서 고치지 않음. 그것은 validator 가 말함
          모르는 이름도 그대로 실어 보냄. 무엇이 왔는지 validator 가 말해야 함
          object 가 아닌 것이 오면 항목 하나로 싸서 넘김. 삼키지 않음
    제약  LLM 을 다시 부르지 않는다.
          도구 값 · 행정코드 · 상대 날짜로 바꾸지 않는다.
          틀린 값을 지우지 않는다.
    """
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return [{"name": None, "value": raw}]

    entries = []
    for name, value in raw.items():
        if isinstance(name, str):
            name = name.strip()
        value = _cleaned(value, semantic_catalog.CATALOG.get(name))
        if value is None:
            continue
        entries.append({"name": name, "value": value})
    return entries


def _cleaned(value, shape):
    """값 하나를 다듬음. 말한 것이 아니면 None.

    입력  값 하나 혹은 값의 목록 · 그 이름의 모양(모르는 이름이면 None)
    출력  다듬은 값. 안 말한 것이면 None
    규칙  목록이면 칸마다 같은 일을 하고 빈 칸을 뺌. 다 빠지면 None
          문자열이면 앞뒤 공백을 지우고, 비면 None
          수를 받는 이름의 문자열만 수로 돌림. 문법이 없는 자리에서 온 값의 보루임
    """
    if isinstance(value, list):
        kept = [item for item in (_cleaned(item, shape) for item in value) if item is not None]
        return kept or None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        if shape is not None and shape.kind in semantic_catalog.NUMERIC_KINDS:
            return _number(value, shape.kind)
    return None if value is None or value == {} else value


def _number(text: str, kind: str):
    """수로 읽히면 수로, 아니면 글자 그대로. 여기서 터지지 않는다."""
    if not _NUMBER.match(text):
        return text
    if kind == semantic_catalog.INTEGER:
        return int(text) if text.lstrip("+-").isdigit() else float(text)
    number = float(text)
    return int(number) if number.is_integer() else number
