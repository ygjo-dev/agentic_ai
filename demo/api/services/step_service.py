"""recipe 의 노드 사슬을 vendor 실행기가 받는 steps 배열로 바꾼다. **우리 코드다.**

**온톨로지는 무엇을 어떤 순서로 하는지만 말한다.** 그 노드가 어느 도구인지,
input 을 어떻게 채우는지는 온톨로지에 없다 — 아래 STEP_OF 표가 갖는다.
온톨로지에 도구 이름을 적으면 노드가 특정 MCP 서버에 묶여, 같은 일을 하는
도구로 갈아끼울 때 도메인을 고쳐야 한다.

**배선은 여기서 끝난다.** 앞 단계 결과를 다음 input 에 어떻게 넣을지는
vendor/asap/generic_mcp_executor 의 _resolve_reference 가 안다 — 도구별이 아니라
필드 이름별이라 도구가 늘어도 재사용된다. 우리는 $prev.location 처럼 "앞
단계의 무엇" 이라고만 적는다.

발화에서 장소를 뽑는 것도 여기다. @place 를 채우는 값이라 같은 자리에 둔다.
"""

import re

from demo.api.services import ontology_service

SERVER_ID = "asap-mcp-core"

# road.getCctv 에 넘길 반경. vendor 의 point_radius_to_bbox 어댑터가 중심
# 좌표와 이 값으로 bbox 를 만든다 — 대상 도구의 required 에 bbox 넷이 있으면
# 저절로 걸린다.
#
# 어제 geocode bbox 에 ±0.15도를 더해 95건이 나왔고 그것이 대략 15km 다.
# 이 값으로는 오송역 83건이 나왔다(실측). 어댑터가 위도를 보정하기 때문에
# 세로가 ±0.1347도로 좁아진다 — ±0.15도로 네 변을 똑같이 넓히던 것과 다르다.
RADIUS_METERS = 15000

# 발화에서 온 값을 가리키는 표시. @place 하나뿐이다.
SPOKEN_PLACE = "@place"

# 앞 단계를 가리키는 표시. 실제 step id 로 바꿔서 vendor 에 넘긴다.
PREVIOUS_STEP = "$prev"

# 노드 -> step. **온톨로지 밖이다.**
#
#   server_id · tool  vendor 가 Gateway 에 보낼 것
#   input             그 도구가 받는 input. @place 와 $prev 를 쓸 수 있다
#   headline          그 노드에서 끝나는 경로의 답 첫 줄
#
# headline 은 마지막 노드의 것만 쓰인다. 도구 이름으로는 만들 수 없는 문장이라
# (road.getCctv -> "CCTV 를 조회했습니다") 노드가 들고 있어야 한다.
STEP_OF = {
    "geocode_place": {
        "server_id": SERVER_ID,
        "tool": "geo.geocode",
        "input": {"query": SPOKEN_PLACE},
        "headline": "{place} 좌표를 조회했습니다.",
    },
    "find_cctv": {
        "server_id": SERVER_ID,
        "tool": "road.getCctv",
        "input": {"location": f"{PREVIOUS_STEP}.location", "radiusMeters": RADIUS_METERS},
        "headline": "{place} CCTV 를 조회했습니다.",
    },
}

# 장소로 볼 어절의 끝 글자.
PLACE_SUFFIXES = "역시군구읍면동리"

# 한글 어절 하나가 통째로 장소인지 본다.
#
# **LLM 을 쓰지 않는다.** 인자 추출을 /resolve 에 얹으면 recipe 선택이 함께
# 흔들린다 — 지금 확인된 것이 그 선택이라 건드리지 않는다.
#
# 못 잡는 것 : "충북대 근처" · "청주 시내" 처럼 끝 글자가 다른 곳,
#              "오송역의" 처럼 조사가 붙은 어절, "서울에서 대전까지" 의 둘 중 하나.
# 잘못 잡는 것 : "알려주시" 같은 어절도 형태가 같다. 실제 발화에서는 드물다.
# 다음에 바꿀 것 : 발화 해석 LLM 이 recipe 를 고르면서 인자를 함께 내놓게 한다.
#                  그때 이 함수가 통째로 사라진다.
PLACE_PATTERN = re.compile(f"[가-힣]{{2,}}[{PLACE_SUFFIXES}]")


def place_in(text: str) -> str | None:
    """발화에서 장소 하나.

    입력  사용자 발화
    출력  첫 번째로 걸린 어절. 없으면 None
    규칙  어절 전체가 걸려야 함. "보여줘" 처럼 일부만 맞는 것은 안 봄
          여러 개면 첫 번째. 발화가 "서울에서 대전까지" 인 recipe 는 아직 없음
    """
    for word in str(text or "").split():
        if PLACE_PATTERN.fullmatch(word):
            return word
    return None


def unwired(recipe_id: str) -> list[str]:
    """아직 도구가 안 붙은 노드.

    입력  recipe id
    출력  STEP_OF 에 없는 실행 노드 id 목록. 경로 순서. 전부 있으면 빈 목록
    규칙  실행 노드만 셈. 데이터 노드는 부를 것이 없어 세지 않음
          부르는 쪽(execute_service.run)이 비어 있지 않으면 도구를 하나도
          안 부름. 48개 중 온전히 도는 것은 001 과 025 둘뿐임
    """
    return [
        node_id
        for node_id in ontology_service.executable_in(recipe_id)
        if node_id not in STEP_OF
    ]


def plan(recipe_id: str, place: str) -> dict:
    """recipe 한 벌을 vendor 가 받는 실행 계획으로.

    입력  recipe id · 발화에서 뽑은 장소
    출력  steps  vendor 의 intent["steps"] 에 그대로 들어갈 배열
          nodes  steps 와 같은 길이. steps[i] 를 만든 노드 id
          headline  답의 첫 줄. 마지막 step 의 노드가 정함
    규칙  step id 는 s1 · s2 … 로 붙음. $prev 를 앞 step 의 id 로 바꿈
          STEP_OF 에 없는 노드는 step 을 만들지 않음. 데이터 노드
          (spoken_place)는 값을 준비할 뿐 부를 것이 없음
          실행 노드가 빠져 반쪽으로 도는 것은 부르기 전에 unwired 가 막음
    제약  첫 step 의 input 에 $prev 를 쓰지 않는다. 가리킬 앞 단계가 없음
    """
    steps: list[dict] = []
    nodes: list[str] = []
    headline = ""
    previous_id = None

    for entry in ontology_service.path_of(recipe_id):
        node_id = entry["node_id"]
        wiring = STEP_OF.get(node_id)
        if wiring is None:
            continue

        step_id = f"s{len(steps) + 1}"
        steps.append(
            {
                "id": step_id,
                "server_id": wiring["server_id"],
                "tool": wiring["tool"],
                "input": _filled(wiring["input"], place, previous_id),
            }
        )
        nodes.append(node_id)
        headline = wiring["headline"].format(place=place)
        previous_id = step_id

    return {"steps": steps, "nodes": nodes, "headline": headline}


def _filled(value, place: str, previous_id: str | None):
    """input 안의 @place 와 $prev 를 실제 값으로. 중첩된 것까지.

    입력  input 조각 · 장소 · 앞 step 의 id(없으면 None)
    출력  같은 모양에 표시만 바뀐 것
    규칙  "@place" 는 어절 전체가 표시일 때만 바꿈. 값의 타입이 바뀌므로
          문자열 안에 섞어 쓰지 않음
          "$prev" 로 시작하면 뒤의 경로는 그대로 두고 앞만 바꿈
    제약  앞 단계 없이 $prev 를 만나면 멈춘다. 조용히 넘기면 vendor 가
          해석 못 한 문자열을 그대로 Gateway 에 보냄
    """
    if isinstance(value, dict):
        return {key: _filled(item, place, previous_id) for key, item in value.items()}
    if isinstance(value, list):
        return [_filled(item, place, previous_id) for item in value]
    if value == SPOKEN_PLACE:
        return place
    if isinstance(value, str) and value.startswith(PREVIOUS_STEP):
        if previous_id is None:
            raise ValueError(f"첫 step 이 앞 단계를 가리킨다 : {value}")
        return f"${previous_id}{value[len(PREVIOUS_STEP):]}"
    return value
