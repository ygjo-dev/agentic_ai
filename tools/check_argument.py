"""발화에서 뽑은 인자가 도구에 실제로 통하는지 재는 도구.

    python tools/check_argument.py
    python tools/check_argument.py --runs 5 --model qwen3:32b
    python tools/check_argument.py --only 4,6

**재기만 한다. 아무것도 안 고친다.** 인자 추출을 어떻게 바꿀지는 사람이 정한다.

## 왜 이것을 재는가

`tools/check_resolve.py` 는 `recipe_id` 만 대조한다. recipe 가 맞으면 적중이다.
그런데 화면에서는 recipe 가 맞는데도 답이 0건으로 나온 적이 있다(2026-08-24 실측).

    철도 안전 문서 찾아줘       recipe_014 ✓  knowledge.query          0건
    국회의원 선거구 찾아줘      recipe_007 ✓  election.searchDistricts 0건
    청주시 인구 구성 알려줘     recipe_011    population.searchStatistics 0건

배선은 셋 다 `{"query": @arg}` 다. 그러니 recipe 가 맞아도 `@arg` 에 들어간 값이
도구에 안 통하면 답은 0건이다. **인자가 도구에 통하는지는 한 번도 안 쟀다.**
"축이 89/90 동일" 은 안정적이라는 뜻이지 맞다는 뜻이 아니다.

## 무엇을 재는가

    1  /resolve 를 발화마다 여러 번 불러 recipe 와 argument 를 받는다.
       check_resolve._call_resolve 를 그대로 쓴다 — 같은 경로여야 표를 믿을 수 있다
    2  그 recipe 의 첫 실행 노드 배선을 step_service.plan 에서 읽는다
    3  @arg 자리에 뽑힌 인자를 넣고 Gateway 를 직접 부른다
    4  건수를 적는다

표에는 그 회차의 축 셋(given · want · about)도 함께 찍는다. 어미만 바꾼
변주(VARIATIONS, 2026-08-25)에서 어미가 인자를 흔드는지 축을 흔드는지가
여기서 갈린다.

**첫 단계만 잰다.** `@arg` 를 쓰는 배선만 본다. `$prev` 만 쓰는 자리는 앞 단계가
있어야 부를 수 있으므로 이번 범위 밖이다 — 그런 자리는 표에 "$prev" 로 적고
안 부른다. 그래서 **여기 건수는 사슬 끝의 답이 아니다.** 3번 CCTV 는 첫 단계가
geo.geocode 라 여기서는 좌표 건수를 재고, CCTV 가 몇 건인지는 여기서 안 나온다.

## 사람이 골랐을 값을 함께 누른다

LLM 이 뽑은 값만 재면 0건이 나왔을 때 **인자 탓인지 데이터가 없는 것인지**
안 갈린다. 그래서 발화에서 사람이 뽑았을 값(HUMAN_ARGUMENT)을 손으로 정해
같이 부르고 건수를 나란히 적는다.

    인자 탓이면    LLM 이 뽑은 값은 0건, 사람이 고른 값은 데이터가 나온다
    데이터 탓이면  둘 다 0건

**사람이 고른 값은 추측이다.** 표에 "사람추측" 으로 표시한다. 정답이 아니라
비교 기준일 뿐이다.

## 이 파일이 안 하는 것

표를 옮겨 적지 않는다. 발화 목록은 check_resolve 에서, 배선은 step_service 에서,
user_context 는 execute_service 에서, Gateway 주소는 gateway_client 에서 그대로
가져온다. 여기에 베껴 적으면 저쪽을 고쳤을 때 이 도구가 세는 숫자를 믿을 수
없게 된다.

**테스트를 두지 않는다.** tools/ 는 재는 도구이고 제품 경로가 아니다.
"""

import argparse
import json
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from demo.api.services import gateway_client, step_service  # noqa: E402
from demo.api.services.execute_service import USER_CONTEXT  # noqa: E402
# check_resolve 의 밑줄 이름을 그대로 가져온다. 발화 목록과 /resolve 부르는
# 자리를 여기 베껴 적으면 "같은 경로" 가 아니게 되고, 그러면 이 표의 인자가
# check_resolve 표의 인자와 다른 것을 재게 된다. 같은 tools/ 안이라 밑줄을
# 넘는다.
from tools.check_resolve import (  # noqa: E402
    UTTERANCES,
    ServerDown,
    _call_resolve,
    _clip,
    _pad,
    _short,
    _width,
)

# 어미만 바꾼 변주 (2026-08-25 더함). 낱말은 같고 말투만 다르다.
# 2026-08-25 화면 실측에서 "…데이터 검색해줘" 는 SELECT 인데 "…데이터 줘" 는
# CLARIFY 로 갈렸다. 어미가 축(given)을 흔드는지 인자를 흔드는지를 가르려고
# 잰다.
#
# **check_resolve.UTTERANCES 의 아홉은 한 글자도 안 건드린다** — 스물일곱
# 항목의 기록이 그 아홉으로 재어져 있다. 번호만 이어 붙인다.
# 기대 recipe 는 빈 집합으로 둔다. 이 도구는 기대값을 안 읽고, 무엇이
# 정답인지는 표를 보고 사람이 정한다.
VARIATIONS = [
    (10, "전기차 충전소 데이터 줘", set(), True),  # 7번의 어미 변주
    (11, "전기차 충전소 알려줘",    set(), True),  # 7번의 어미 변주
    (12, "철도 안전 문서 보여줘",   set(), True),  # 8번의 어미 변주
    (13, "청주시 인구 알려줘",      set(), True),  # 4번의 어미 변주
]

ALL_UTTERANCES = UTTERANCES + VARIATIONS

# 사람이 발화에서 뽑았을 값. **추측이다.** LLM 이 뽑은 값과 견주는 기준일 뿐이고
# 정답이 아니다. 표에 "사람추측" 으로 표시된다.
#
# 고른 근거는 하나다 — 도구가 받는 것이 무엇인지 보고 그 발화에서 그 자리에
# 넣을 낱말을 골랐다. 장소를 받는 도구에는 장소를, 키워드를 받는 도구에는
# 찾을 것의 이름을 넣었다. "인구 구성" 이나 "국회의원 선거구" 처럼 발화를
# 통째로 옮긴 것은 넣지 않았다.
HUMAN_ARGUMENT = {
    1: "오송역",
    2: "오송역",
    3: "오송역",
    4: "청주시",
    5: "오송역",
    6: "선거구",
    7: "전기차 충전소",
    8: "철도 안전",
    9: "충북 제1선거구",
    10: "전기차 충전소",
    11: "전기차 충전소",
    12: "철도 안전",
    13: "청주시",
}

# 확장 표(check_resolve 10~31, 2026-08-26 「서른두째」)의 사람추측 값.
# **위의 HUMAN_ARGUMENT 와 마찬가지로 추측이지 정답이 아니다.**
#
# 번호가 아니라 발화 문장이 key 다 — check_resolve 가 10~31 을 늘리면서
# 이 파일의 VARIATIONS(10~13)와 번호가 겹치게 됐다. 번호로 걸면 확장 표
# 10번(오송역이 어느 동인지)에 변주 10번의 값(전기차 충전소)이 들어간다.
# 위의 HUMAN_ARGUMENT 는 기록이 걸려 있어 한 글자도 안 바꾸고(2026-08-27
# 무인 실행 규칙), 여기서 발화로 먼저 걸고 없으면 번호로 떨어진다.
#
# 고른 근거는 HUMAN_ARGUMENT 와 같다 — 도구가 받는 것을 보고 그 발화에서
# 그 자리에 넣을 낱말을 골랐다. 발화를 통째로 옮긴 것은 넣지 않았다.
#
#   19  "인구 많은 시군구 순위 보여줘" 는 일부러 뺐다. 도구의 query 는
#       "행정구역명 또는 코드 검색어" 인데 이 발화에는 행정구역 이름이 없다.
#       사람도 뽑을 값이 없는 자리다 — 값을 지어 넣으면 "사람 값이면 몇 건"
#       이라는 비교가 거짓이 된다. 없으면 사람추측 줄이 안 찍힌다
HUMAN_ARGUMENT_BY_UTTERANCE = {
    "오송역이 어느 동인지 알려줘": "오송역",
    "오송역 행정경계 보여줘": "오송역",
    "청주시 행정경계 보여줘": "청주시",
    "오송역 국회의원 누구야": "오송역",
    "오송역 국회의원 공약 보여줘": "오송역",
    "청주 선거구 찾아줘": "청주",
    "교통 공약 많은 선거구 검색해줘": "교통",
    "청주 국회의원 공약 검색해줘": "청주",
    "오송역 일대 인구 얼마야": "오송역",
    "대전역 연령대별 인구 알려줘": "대전역",
    "경부선 선형 데이터 줘": "경부선",
    "오송역 지나는 노선 알려줘": "오송역",
    "경부선 주변 CCTV 보여줘": "경부선",
    "오송역 근처 충전소 자세히 알려줘": "오송역",
    "문서에서 철도안전법 관련 내용 찾아줘": "철도안전법",
    "문서에서 철도 안전 교육 내용 찾아줘": "철도 안전 교육",
    "철도안전법 내용 찾아줘": "철도안전법",
    "경부선 노선 보여줘": "경부선",
    "청주시 인구 알려줘": "청주시",
    "오송역 선거구 알려줘": "오송역",
    "청주 국회의원 선거구 검색해줘": "청주",
}

# 도구와 데이터가 살아 있는지만 보는 값. **사람이 말할 값이 아니다.**
#
# 사람이 골랐을 값도 0건이면 그것만으로는 "데이터가 없다" 가 안 나온다.
# 그 값이 안 통한 것일 수도 있기 때문이다. 그래서 통하는 것이 확인된 값을
# 하나 더 눌러 도구와 데이터가 살아 있는지를 가른다.
#
#   6  "청주"  election.searchDistricts 가 찾는 것은 선거구 이름이다
#              ("충북 청주서원"). 발화의 "국회의원" · "선거구" 는 이름의 일부가
#              아니라 종류의 이름이라 어떤 낱말도 안 걸린다 (2026-08-24 실측)
#   8  ""      knowledge.query 는 빈 질의에도 [] 다. 문서가 하나도 없다
#              (2026-08-24 실측). MEMORY 의 gitignore 런타임 데이터 누락과 같은 줄기
ALIVE_ARGUMENT = {
    6: "청주",
    8: "",
}

# plan 에 넣어 @arg 자리를 찾는 표시. 어느 발화에서도 안 나올 값이어야 한다.
PROBE = "@@ARG@@"

# 첫 단계가 @arg 를 안 쓸 때 인자 칸에 적는 것.
NO_SPOKEN = "$prev 만 씀"

# 건수를 어디서 읽을지. 앞의 것부터 본다.
#
# 도구마다 응답 모양이 다르다. population.searchStatistics 와
# election.searchDistricts 는 count · totalMatches 를 함께 내고, 그것이 없는
# 도구는 목록 길이를 센다. 여기 없는 모양이면 "?" 로 적고 지어내지 않는다.
#
# 목록도 건수도 없는 dict 는 단건 응답이다. 그것을 "1" 로만 적으면 세어 나온 1
# 과 안 갈려서 표시를 따로 둔다.
SINGLE = "1(단건)"
COUNT_KEYS = ("count", "totalMatches", "total")
LIST_KEYS = ("items", "features", "results", "documents", "rows", "data", "hits")

GATEWAY_TIMEOUT = 120

# 표 칸 폭.
UTTERANCE_WIDTH = 26
RECIPE_WIDTH = 8
TOOL_WIDTH = 30
PICKER_WIDTH = 10
ARGUMENT_WIDTH = 22
COUNT_WIDTH = 8
RUNS_WIDTH = 6

LLM_PICKER = "LLM"
HUMAN_PICKER = "사람추측"
ALIVE_PICKER = "확인용"

# status 칸 폭. CLARIFY 가 폭 7이다.
STATUS_WIDTH = 9


# ── 배선 읽기 ────────────────────────────────────────────────────────


def _first_step(recipe_id: str) -> dict | None:
    """그 recipe 의 첫 실행 단계. @arg 자리를 PROBE 로 표시한 채.

    입력  recipe id
    출력  step_service.plan 이 만든 첫 step. 부를 것이 없으면 None
    규칙  plan 을 그대로 부름. 배선을 여기서 다시 읽지 않음 — 실행이 지나는
          것과 같은 자리를 봐야 표를 믿을 수 있음
          인자 자리에 PROBE 를 넣어 두면 @arg 를 쓰는지 아닌지가 값으로 드러남
    """
    try:
        steps = step_service.plan(recipe_id, PROBE)["steps"]
    except Exception:  # noqa: BLE001 — 표에 남기고 계속 간다.
        return None
    return steps[0] if steps else None


def _spoken_fields(tool_input: dict) -> list[str]:
    """input 에서 발화에서 온 값이 들어간 칸 이름.

    입력  PROBE 를 넣어 만든 step 의 input
    출력  값이 PROBE 인 칸 이름 목록. 없으면 빈 목록
    규칙  한 겹만 봄. 지금 배선의 @arg 는 전부 한 겹임
    """
    return [key for key, value in tool_input.items() if value == PROBE]


def _with_argument(tool_input: dict, argument: str) -> dict:
    """PROBE 를 실제 인자로 바꾼 input."""
    return {
        key: (argument if value == PROBE else value)
        for key, value in tool_input.items()
    }


# ── Gateway 호출 ─────────────────────────────────────────────────────


def _count(body) -> str:
    """응답에서 건수 하나.

    입력  Gateway 가 돌려준 본문
    출력  건수 문자열. 어디서 읽을지 모르면 "?"
    규칙  COUNT_KEYS 를 먼저 봄. 없으면 LIST_KEYS 의 목록 길이를 셈
          **모르면 지어내지 않는다.** "?" 로 적고 사람이 본문을 보게 함
    """
    if isinstance(body, list):
        return str(len(body))
    if not isinstance(body, dict):
        return "?"
    for key in COUNT_KEYS:
        value = body.get(key)
        if isinstance(value, int):
            return str(value)
    for key in LIST_KEYS:
        value = body.get(key)
        if isinstance(value, list):
            return str(len(value))
    # 목록도 건수도 없는 dict 는 단건 응답이다. geo.geocode 가 그렇다 —
    # {location, bbox, address} 하나를 낸다. 0 으로 적으면 못 찾은 것처럼 보인다.
    return SINGLE if body else "0"


def _execute(step: dict, argument: str) -> tuple:
    """Gateway 에 도구 하나를 직접 부름.

    입력  첫 실행 단계 · @arg 자리에 넣을 인자
    출력  (건수 문자열, 본문). 실패하면 ("오류", 사유 문자열)
    규칙  본문 모양은 vendor/asap/mcp_client.execute_tool 과 같음.
          **user_context 를 반드시 넣는다** — 빠뜨리면 요청마다 새 guest 가
          만들어지고 adminBoundary 셋 말고는 전부 거부됨(execute_service 주석)
          그 값을 여기 베껴 적지 않고 execute_service.USER_CONTEXT 를 씀
    제약  실패해도 멈추지 않는다. 아홉 발화를 끝까지 재는 것이 목적임
    """
    payload = {
        "tool": step["tool"],
        "input": _with_argument(step["input"], argument),
        "server_id": step["server_id"],
        "user_context": dict(USER_CONTEXT),
    }
    try:
        response = requests.post(
            f"{gateway_client.base_url()}/api/tools/execute",
            json=payload,
            timeout=GATEWAY_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001
        return "오류", f"{type(exc).__name__}: {exc}"

    if response.status_code >= 400:
        return "오류", f"HTTP {response.status_code} {response.text[:200]}"

    try:
        body = response.json()
    except ValueError:
        return "?", response.text[:200]
    return _count(body), body


# ── 측정 ────────────────────────────────────────────────────────────


def _measure(entries, runs: int, model: str | None) -> list[dict]:
    """발화마다 인자를 뽑고 그 인자로 도구를 부름.

    입력  발화 목록 · /resolve 반복 횟수 · 모델 이름
    출력  발화당 한 줄짜리 dict 목록. 표와 본문 덤프가 같은 것을 읽음
    규칙  /resolve 는 runs 회. 나온 (recipe, 인자) 조합을 다 셈 —
          흔들리면 흔들린 대로 적음
          Gateway 는 **조합마다 한 번씩만** 부름. 같은 인자를 세 번 부르면
          같은 답이 세 번 오고 표만 길어짐
          사람이 골랐을 값은 조합과 상관없이 recipe 마다 한 번 부름
    제약  후보가 여럿이면(CLARIFY) 번호가 작은 것 하나를 씀. 화면은 그때
          되묻지 실행하지 않으므로 그 줄은 "만약 이것을 골랐다면" 이라는 뜻임.
          status 칸을 함께 봐야 함
    """
    rows = []
    for number, utterance, _expected, _default in entries:
        sys.stdout.write(f"  {number} ")
        sys.stdout.flush()

        picked, errors = {}, 0
        for _ in range(runs):
            try:
                # _call_resolve 는 다섯을 돌려준다. LLM 단독 칸을 더한 뒤
                # (4dd552a) 여기 언팩이 넷이라 매 호출이 ValueError 로 떨어져
                # 전부 "!" 가 됐다. 뒤에 무엇이 더 붙어도 안 깨지게 받는다.
                found, status, axes, *_rest = _call_resolve(utterance, model)
                recipe_id = sorted(found)[0] if found else None
                given_want_about = axes[:3]  # (given, want, about, argument)
                argument = axes[3]
                key = (recipe_id, argument, status, given_want_about)
                picked[key] = picked.get(key, 0) + 1
                sys.stdout.write(".")
            except ServerDown:
                sys.stdout.write("\n")
                raise
            except Exception:  # noqa: BLE001
                errors += 1
                sys.stdout.write("!")
            sys.stdout.flush()

        calls = []
        seen_recipes = set()
        for (recipe_id, argument, status, given_want_about), count in sorted(
            picked.items(), key=lambda item: -item[1]
        ):
            step = _first_step(recipe_id) if recipe_id else None
            call = _one_call(LLM_PICKER, recipe_id, status, step, argument, count)
            call["axes"] = " · ".join(given_want_about)
            calls.append(call)
            seen_recipes.add(recipe_id)

        # 사람이 골랐을 값과 확인용 값. LLM 이 고른 recipe 위에서 인자만 갈아
        # 끼운다 — recipe 까지 바꾸면 무엇 때문에 건수가 달라졌는지 안 갈린다.
        # 발화 key 가 번호 key 보다 먼저다. 근거는 HUMAN_ARGUMENT_BY_UTTERANCE 옆에.
        extras = [(
            HUMAN_PICKER,
            HUMAN_ARGUMENT_BY_UTTERANCE.get(utterance, HUMAN_ARGUMENT.get(number)),
        )]
        if number in ALIVE_ARGUMENT:
            extras.append((ALIVE_PICKER, ALIVE_ARGUMENT[number]))
        for recipe_id in sorted(rid for rid in seen_recipes if rid):
            step = _first_step(recipe_id)
            if step is None:
                continue
            for picker, argument in extras:
                if argument is None:
                    continue
                if _spoken_fields(step["input"]):
                    sys.stdout.write("+")
                    sys.stdout.flush()
                calls.append(_one_call(picker, recipe_id, "-", step, argument, None))

        sys.stdout.write("\n")
        sys.stdout.flush()
        rows.append(
            {"number": number, "utterance": utterance, "calls": calls, "errors": errors}
        )
    return rows


def _one_call(picker, recipe_id, status, step, argument, count) -> dict:
    """한 줄. 부를 수 있으면 부르고, 아니면 왜 안 불렀는지 적음.

    규칙  @arg 를 쓰는 배선만 부름. 첫 단계가 $prev 만 쓰면 안 부르고
          그 사실을 적음 — 앞 단계가 있어야 부를 수 있고 이번 범위 밖임
    """
    row = {
        "picker": picker,
        "recipe_id": recipe_id,
        "status": status,
        "argument": argument,
        "runs": count,
        "tool": "-",
        "fields": [],
        "hits": "-",
        "body": None,
        # LLM 줄만 /resolve 가 쓴 축 셋(given · want · about)으로 채워진다.
        # 사람추측 · 확인용 줄은 축이 없다 — 인자만 갈아 끼운 호출이다.
        "axes": "-",
    }
    if step is None:
        # 배선이 안 붙은 노드가 있으면 execute_service.run 이 하나도 안 부른다.
        # recipe 는 맞았는데 화면에 아무것도 안 나오는 자리라 이름을 적는다.
        missing = step_service.unwired(recipe_id) if recipe_id else []
        row["hits"] = f"배선 없음 {'·'.join(missing)}" if missing else "부를 것 없음"
        return row

    row["tool"] = step["tool"]
    row["fields"] = _spoken_fields(step["input"])
    if not row["fields"]:
        row["hits"] = NO_SPOKEN
        return row

    row["hits"], row["body"] = _execute(step, argument)
    return row


# ── 표 ──────────────────────────────────────────────────────────────


def _print_table(rows) -> None:
    print()
    print(
        "  "
        + _pad("#", 3)
        + _pad("발화", UTTERANCE_WIDTH + 2)
        + _pad("recipe", RECIPE_WIDTH)
        + _pad("status", STATUS_WIDTH)
        + _pad("첫 도구", TOOL_WIDTH)
        + _pad("뽑은 이", PICKER_WIDTH)
        + _pad("인자", ARGUMENT_WIDTH)
        + _pad("건수", COUNT_WIDTH)
        + _pad("횟수", RUNS_WIDTH)
        + "given · want · about"
    )

    for row in rows:
        # 옛 아홉과 변주가 표에서 갈려 보여야 한다. 변주의 첫 줄 앞에 금을 긋는다.
        # 번호만 보면 안 된다 — 확장 표(check_resolve 10~31)와 변주(10~13)의
        # 번호가 겹쳐서, 번호로 그으면 확장 표 10번 앞에도 금이 생긴다.
        if (
            VARIATIONS
            and row["number"] == VARIATIONS[0][0]
            and row["utterance"] == VARIATIONS[0][1]
        ):
            print("  ── 변주 · 어미만 다름 (2026-08-25 더함) " + "─" * 40)
        head = (
            "  "
            + _pad(str(row["number"]), 3)
            + _pad(_clip(row["utterance"], UTTERANCE_WIDTH), UTTERANCE_WIDTH + 2)
        )
        if not row["calls"]:
            print(head.rstrip())
            continue
        for index, call in enumerate(row["calls"]):
            prefix = head if index == 0 else " " * _width(head)
            recipe = (
                _short({call["recipe_id"]})[1:-1] if call["recipe_id"] else "-"
            )
            runs = f"{call['runs']}회" if call["runs"] is not None else "-"
            print(
                prefix
                + _pad(recipe, RECIPE_WIDTH)
                # CLARIFY 줄의 건수는 "만약 이것을 골랐다면" 이다. 화면은
                # 되묻지 실행하지 않는다. status 없이 읽으면 그것이 안 보인다.
                + _pad(str(call["status"]), STATUS_WIDTH)
                + _pad(_clip(call["tool"], TOOL_WIDTH - 2), TOOL_WIDTH)
                + _pad(call["picker"], PICKER_WIDTH)
                + _pad(_clip(str(call["argument"]), ARGUMENT_WIDTH - 2), ARGUMENT_WIDTH)
                + _pad(str(call["hits"]), max(COUNT_WIDTH, _width(str(call["hits"])) + 2))
                + _pad(runs, RUNS_WIDTH)
                + call["axes"]
            )
        if row["errors"]:
            print(" " * _width(head) + f"/resolve 오류 {row['errors']}회")


def _as_number(hits) -> int | None:
    """건수 칸을 수로. 못 읽으면 None (오류 · "?" · 안 부른 자리)."""
    text = str(hits)
    if text == SINGLE:
        return 1
    return int(text) if text.isdigit() else None


def _print_verdict(rows) -> None:
    """0건이 인자 탓인지 데이터 탓인지 발화마다 한 줄로.

    규칙  **억지로 결론 내지 않는다.** 못 가른 것은 못 갈랐다고 적는다
            LLM 값이 1건 이상          가를 것이 없음
            LLM 0 · 사람 값 1건 이상   ★ 인자 탓
            둘 다 0 · 확인용 1건 이상  ★ 발화에 통하는 낱말이 없음.
                                       도구도 데이터도 살아 있는데 발화의 어떤
                                       낱말도 데이터의 이름과 안 겹친다
            둘 다 0 · 확인용도 0       데이터 탓
            둘 다 0 · 확인용 없음      안 갈림. **여기서 "데이터가 없다" 를
                                       말하지 않는다** — 고른 값 둘이 다 안
                                       통한 것일 수도 있음
    """
    print()
    print("  0건이 무엇 탓인가")
    print()
    for row in rows:
        picked = {
            name: [c for c in row["calls"] if c["picker"] == name]
            for name in (LLM_PICKER, HUMAN_PICKER, ALIVE_PICKER)
        }
        llm, human, alive = (picked[name] for name in (LLM_PICKER, HUMAN_PICKER, ALIVE_PICKER))
        if not llm:
            continue

        def _best(calls):
            """그 값들이 낸 최대 건수. 하나라도 못 읽으면 None.

            규칙  SINGLE 은 1 로 셈. 단건 응답도 나온 것은 나온 것임
            """
            numbers = [_as_number(c["hits"]) for c in calls]
            if not numbers or any(n is None for n in numbers):
                return None
            return max(numbers)

        if any(str(c["hits"]).startswith(("배선 없음", "부를 것 없음")) for c in llm):
            verdict = "안 잼 (" + str(llm[0]["hits"]) + " — 실행 자체가 안 됨)"
        elif any(c["hits"] == NO_SPOKEN for c in llm):
            verdict = "안 잼 (첫 단계가 @arg 를 안 씀)"
        else:
            llm_max, human_max, alive_max = _best(llm), _best(human), _best(alive)
            if llm_max is None:
                verdict = "안 갈림 (건수를 못 읽거나 오류)"
            elif llm_max > 0:
                verdict = f"LLM 값으로 {llm_max}건 나옴 — 가를 것 없음"
            elif human_max is None:
                verdict = "안 갈림 (사람 값을 못 쟀다)"
            elif human_max > 0:
                verdict = f"★ 인자 탓 (사람 값이면 {human_max}건)"
            elif alive_max is None:
                verdict = "안 갈림 (둘 다 0건. 데이터가 없다고는 아직 못 말한다)"
            elif alive_max > 0:
                verdict = f"★ 발화에 통하는 낱말이 없음 (확인용 값이면 {alive_max}건)"
            else:
                verdict = "데이터 탓 (확인용 값도 0건)"

        print(
            "  "
            + _pad(str(row["number"]), 3)
            + _pad(_clip(row["utterance"], UTTERANCE_WIDTH), UTTERANCE_WIDTH + 2)
            + verdict
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="발화에서 뽑은 인자가 도구에 통하는지 잰다. 고치지 않는다."
    )
    parser.add_argument("--runs", type=int, default=3, help="발화마다 /resolve 몇 번 (기본 3)")
    parser.add_argument("--only", default="", help="잴 발화 번호. 예: 4,6")
    parser.add_argument("--model", default="", help="쓸 모델. 예: qwen3:32b (기본: 서버 기본 모델)")
    parser.add_argument("--dump", default="", help="Gateway 응답 본문을 적을 파일")
    args = parser.parse_args()

    if args.only:
        wanted = [int(part) for part in args.only.replace(" ", "").split(",") if part]
        entries = [entry for entry in ALL_UTTERANCES if entry[0] in wanted]
        missing = sorted(set(wanted) - {entry[0] for entry in entries})
        if missing:
            print(f"목록에 없는 번호 : {missing}")
            return 2
    else:
        entries = [entry for entry in ALL_UTTERANCES if entry[3]]

    print(
        f"발화 {len(entries)}개 × {args.runs}회 · 모델 {args.model or '서버 기본'}"
        f" · Gateway {gateway_client.base_url()}"
    )
    print("첫 실행 단계만 잰다. 사슬 끝의 답이 아니다.")
    print()

    rows, note, status = [], "", 0
    try:
        rows = _measure(entries, args.runs, args.model)
    except ServerDown:
        note, status = "uvicorn 을 먼저 실행하세요", 1
    except KeyboardInterrupt:
        note = "(중단됨 — 여기까지의 결과)"

    if rows:
        _print_table(rows)
        _print_verdict(rows)
    if args.dump and rows:
        Path(args.dump).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print()
        print(f"  응답 본문 : {args.dump}")
    if note:
        print()
        print(note)
    return status


if __name__ == "__main__":
    sys.exit(main())
