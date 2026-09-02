"""도달 지역 · 음영 지역의 주민등록 인구를 센다. **찾아 둔 동 목록만 쓴다.**

점을 새로 뽑지 않는다. execution/reach_districts 와 execution/shadow_districts 가
이미 찾아 놓은 동 목록을 받아 그 동들의 인구만 더한다.

**동마다 부르지 않는다. 시군구마다 한 번 부른다.** `population.searchStatistics`
는 `code` 에 법정동 코드 **접두어**를 받는다. 시군구 다섯 자리를 주고
`level="emd"` 로 물으면 그 시군구의 읍면동이 한 번에 온다 (실측 : `41410`
군포시 -> 9건 · `41430` 의왕시 -> 11건). 의왕역 30분 겹에서 **동 마흔(도달 스물 ·
음영 스물)에 호출이 여섯**이다 — Gateway 창을 더 기다리지 않으려고 이 길을
골랐다 (NOTES.md 「여든셋째」 5절).

**이름으로는 못 묶는다** (실측). `query="군포시"` · `level="emd"` 가 0건이다.
query 는 읍면동 이름 칸과 맞춰 보므로 시군구 이름이 안 걸린다. `query="부곡동"`
은 8건이 오는데 부산 금정구 · 김해 · 안산 상록구 … 가 전국에서 함께 온다.

**65세 이상은 `population.getAgeProfile` 을 안 불러도 된다.** searchStatistics
가 동마다 `seniorPopulation` 을 함께 준다. 그 값이 getAgeProfile 의 5세 구간에서
65세 이상을 더한 것과 **같다** (실측 : 군포시 부곡동 41410103 이 양쪽 다 2694).
동마다 한 번을 더 부르면 호출이 갑절이 되고 값은 안 바뀐다.

**유소년도 같은 응답에 함께 온다. `metric` 을 바꿔 다시 부르지 않는다** (실측,
2026-09-02). 항목 하나가 `childrenPopulation` · `workingAgePopulation` ·
`seniorPopulation` 을 한꺼번에 들고 오고 **그 셋을 더하면 `totalPopulation` 과
글자 그대로 같다** (청주시 흥덕구 43113 : 37,163 + 211,864 + 43,598 = 292,625).
곧 셋이 인구를 겹치지 않고 나눠 가진다.

★ **`childrenPopulation` 은 0~14세다.** getAgeProfile 의 `0~4` · `5~9` ·
`10~14` 세 구간을 더한 것과 같다 (같은 구, 10,849 + 12,097 + 14,217 = 37,163).
같은 응답의 `youthPopulation`(청년)은 생산가능인구와 겹치므로 안 쓴다.

**보이는 동과 세는 동이 다르다.** 화면에는 열까지만 적고(workflow_answer 의
DISTRICTS_SHOWN) 인구는 **찾은 동 전부**를 더한다. 열만 더하면 「해당 지역」이
화면에 적힌 열 곳이라는 뜻이 되는데, 그 열은 점이 많이 걸린 차례로 자른 것이지
도달 지역의 전부가 아니다.

**우리가 찾은 동의 인구이지 도달 범위 안의 인구가 아니다.** 행정동 하나가
넓어 일부만 겹치는 곳이 많고, 격자가 빠뜨리는 동도 있다(reach_districts 의
모듈 주석). 화면 문구를 「해당 지역 인구」로 적는 까닭이 그것이다.
"""

import asyncio

from execution import reach_districts, step_service
from vendor_to_be_deleted.asap.workflow_answer import (
    DISTRICTS_KEY,
    SHADOW_DISTRICTS_KEY,
    SHADOW_KEY,
)

# 인구를 물을 노드. 배선표에서 server_id · tool 을 이 이름으로 찾는다.
#
# 노드 id 로 찾는 것은 도구 이름을 여기 적지 않기 위해서다. 배선을 고치면
# 여기가 따라 움직인다.
POPULATION_NODE = "search_population_statistics"

# 물을 행정구역 층과 한 번에 받을 최대 건수.
#
# 시군구 하나의 읍면동을 한 번에 다 받아야 한다. 잘리면 그 시군구의 뒤쪽
# 동이 조용히 안 세어진다 — 몇 곳을 세었는지는 결과의 COUNTED_KEY 에 남는다.
POPULATION_LEVEL = "emd"
POPULATION_LIMIT = 500

# 응답에서 읽을 칸.
ITEMS_KEY = "items"
ITEM_CODE_KEY = "code"
ITEM_TOTAL_KEY = "totalPopulation"
ITEM_SENIOR_KEY = "seniorPopulation"

# 유소년(0~14세)이 담겨 오는 칸. **같은 응답에 이미 들어 있다.**
#
# 교통약자를 세려고 얹었다. 호출이 한 건도 안 는다 — metric 을 바꿔 다시
# 부르는 길로 가지 않은 까닭이 그것이다 (위 모듈 주석).
ITEM_CHILDREN_KEY = "childrenPopulation"
REFERENCE_DATE_KEY = "referenceDate"

# 시군구 응답 하나를 보관에 담는 모양. 발화 하나가 sampled 노드 둘에 걸쳐 씀.
ROWS_KEY = "rows"
ANSWER_DATE_KEY = "date"

# 결과에 인구를 담는 칸. workflow_answer 가 이 이름으로 읽는다.
POPULATION_KEY = "population"
TOTAL_KEY = "total"
SENIOR_KEY = "senior"
CHILDREN_KEY = "children"
COUNTED_KEY = "counted"
FOUND_KEY = "found"
DATE_KEY = "reference_date"


async def attach(item: dict, user_context: dict, sent: int, cache: dict) -> tuple:
    """trace 항목 하나에 그 동들의 인구를 얹음. (항목, 창에 보낸 수).

    입력  reach_districts · shadow_districts 가 낸 항목 · 권한 ·
          이 창에 이미 보낸 건수 · 발화 하나가 이어 쓰는 시군구 응답 보관
    출력  같은 항목. 인구를 얹었으면 동 목록 옆에 POPULATION_KEY 가 붙음
    규칙  동 목록이 놓인 자리 옆에 얹음. 도달 지역은 result 바로 밑이고
          음영 지역은 result 의 음영 칸 밑임
          못 세면 아무것도 안 얹음. 답이 인구 줄을 통째로 안 냄
    제약  항목을 새로 만들지 않는다.
          부르는 쪽이 이미 id 를 붙여 두었고 그 자리에서 이어 쓴다
    """
    found = holder(item.get("result"))
    if found is None:
        return item, sent

    target, districts = found
    counted, sent = await totals(districts, user_context, sent, cache)
    if counted:
        target[POPULATION_KEY] = counted
    return item, sent


def holder(result) -> tuple | None:
    """(인구를 얹을 dict, 그 안의 동 목록). 그런 응답이 아니면 None.

    규칙  음영 지역을 먼저 봄. 두 칸 이름이 같아 도달 지역으로 먼저 보면
          음영 지역의 바깥 칸에 인구가 얹힘
    """
    if not isinstance(result, dict):
        return None

    shadow = result.get(SHADOW_KEY)
    if isinstance(shadow, dict) and isinstance(shadow.get(SHADOW_DISTRICTS_KEY), list):
        return shadow, shadow[SHADOW_DISTRICTS_KEY]

    districts = result.get(DISTRICTS_KEY)
    if isinstance(districts, list):
        return result, districts
    return None


async def totals(districts: list, user_context: dict, sent: int, cache: dict) -> tuple:
    """찾아 둔 동들의 주민등록 인구를 한 벌로. (인구 dict 또는 None, 창에 보낸 수).

    입력  reach_districts.districts_in_order 가 낸 목록 · Gateway 에 보낼 권한 ·
          이 창에 이미 보낸 건수 · 발화 하나 안에서 이어 쓰는 시군구 응답 보관
    출력  {total, senior, children, counted, found, reference_date}.
          한 곳도 못 세면 None
    규칙  시군구마다 한 번만 부름. 같은 시군구가 보관에 있으면 안 부름
          보관을 발화 하나가 sampled 노드 둘에 걸쳐 함께 씀. 도달 지역과 음영
          지역이 같은 시군구를 많이 나눠 가짐
          CHUNK 건마다 창이 빌 때까지 쉼. 점 뽑기와 같은 셈을 이어 씀
          코드가 없는 동은 못 셈. 이름만으로는 인구 데이터에서 못 찾음
          찾은 동 전부를 더함. 화면에 열만 보이는 것과 다름
          한 곳도 못 세면 None. 0명이라고 적으면 잰 것처럼 보임
    제약  동마다 부르지 않는다.
          시군구 접두어 한 번에 그 읍면동이 전부 온다. 동마다 부르면 호출이
          여섯에서 마흔으로 는다
          65세 이상을 따로 부르지 않는다.
          searchStatistics 의 seniorPopulation 이 getAgeProfile 의 65세 이상
          합과 같다 (실측)
          유소년도 따로 부르지 않는다.
          같은 응답이 childrenPopulation 을 함께 준다. metric 을 바꿔 다시
          부르면 호출이 갑절이 되고 값은 안 바뀐다 (실측)
    """
    tool = step_service.TOOL_OF.get(POPULATION_NODE)
    if not tool or not isinstance(districts, list):
        return None, sent

    pairs = wanted(districts)
    if not pairs:
        return None, sent

    for sigungu_code in dict.fromkeys(code for code, _ in pairs):
        if sigungu_code in cache:
            continue
        if sent >= reach_districts.CHUNK:
            await asyncio.sleep(reach_districts.WINDOW_WAIT_S)
            sent = 0
        result, waited = await reach_districts.ask(
            tool,
            {"code": sigungu_code, "level": POPULATION_LEVEL, "limit": POPULATION_LIMIT},
            user_context,
        )
        sent = 1 if waited else sent + 1
        cache[sigungu_code] = _read(result)

    total = senior = children = counted = 0
    for sigungu_code, emd_code in pairs:
        row = cache.get(sigungu_code, _empty())[ROWS_KEY].get(emd_code)
        if row is None:
            continue
        counted += 1
        total += row[0]
        senior += row[1]
        children += row[2]

    if not counted:
        return None, sent

    return {
        TOTAL_KEY: total,
        SENIOR_KEY: senior,
        CHILDREN_KEY: children,
        COUNTED_KEY: counted,
        FOUND_KEY: len(districts),
        DATE_KEY: _reference_date(cache),
    }, sent


def wanted(districts: list) -> list:
    """셀 수 있는 동의 (시군구 코드, 읍면동 코드) 짝들. 없으면 빈 목록.

    규칙  두 코드가 다 문자열이고 비어 있지 않은 항목만 셈
          같은 동이 두 번 들면 한 번만 셈. 목록은 이미 동마다 한 줄이지만
          두 번 더하면 인구가 갑절이 됨
          받은 차례를 지킴. 어느 시군구를 먼저 부를지가 그 차례임
    """
    pairs = []
    for entry in districts:
        if not isinstance(entry, dict):
            continue
        sigungu_code = entry.get(reach_districts.SIGUNGU_CODE_KEY)
        emd_code = entry.get(reach_districts.EMD_CODE_KEY)
        if not isinstance(sigungu_code, str) or not sigungu_code:
            continue
        if not isinstance(emd_code, str) or not emd_code:
            continue
        pair = (sigungu_code, emd_code)
        if pair not in pairs:
            pairs.append(pair)
    return pairs


def _read(result) -> dict:
    """시군구 응답 하나를 보관 한 칸으로. 못 읽으면 빈 칸.

    출력  {rows: {읍면동 코드: (총인구, 65세 이상, 유소년)}, date: 기준일}
    규칙  세 수가 다 정수인 항목만 담음. bool 은 수로 안 봄
          기준일을 함께 담아 둠. 화면이 언제 기준인지 말해야 함
    """
    if not isinstance(result, dict):
        return _empty()
    items = result.get(ITEMS_KEY)
    if not isinstance(items, list):
        return _empty()

    rows: dict = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        code = item.get(ITEM_CODE_KEY)
        total = _number(item.get(ITEM_TOTAL_KEY))
        senior = _number(item.get(ITEM_SENIOR_KEY))
        children = _number(item.get(ITEM_CHILDREN_KEY))
        if not isinstance(code, str) or not code:
            continue
        if total is None or senior is None or children is None:
            continue
        rows[code] = (total, senior, children)
    date = result.get(REFERENCE_DATE_KEY)
    return {ROWS_KEY: rows, ANSWER_DATE_KEY: date if isinstance(date, str) else ""}


def _reference_date(cache: dict) -> str:
    """받은 응답들이 말하는 기준일. 없으면 "".

    규칙  먼저 걸리는 것 하나만 씀. 한 데이터셋이라 응답마다 같은 값임
    """
    for held in cache.values():
        date = held.get(ANSWER_DATE_KEY)
        if isinstance(date, str) and date:
            return date
    return ""


def _empty() -> dict:
    """못 읽은 시군구의 보관 한 칸."""
    return {ROWS_KEY: {}, ANSWER_DATE_KEY: ""}


def _number(value):
    """정수 값. 수가 아니면 None. bool 은 수로 안 봄."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)
