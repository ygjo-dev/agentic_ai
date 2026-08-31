"""발화에서 온 인자가 step 의 @arg 자리에 들어가는 것.

LLM 을 부르지 않는다. 경로와 배선을 가짜로 주고 치환 결과만 본다.

**배선 줄을 고르는 것이 타입이라 타입만은 있어야 한다.** 실제 노드를 쓰는
시험은 온톨로지의 타입을 그대로 읽고, 가짜 노드를 쓰는 시험은 handed 로
건네는 타입을 준다. 치환 규칙을 보는 시험이 노드 이름에 매이지 않게 하려는 것.

인자를 뽑는 자리가 둘이다. 발화 해석 LLM 의 argument 가 먼저이고, 그것이
없을 때만 정규식(place_in)이 돈다. 아래에서 둘 다 본다.
"""

import asyncio

import pytest

from demo.api.services import execute_service, step_service

ARG = step_service.SPOKEN_VALUE

# 가짜 노드 사이에 흐르는 타입 하나. 온톨로지의 어느 타입도 아니다 —
# 배선 줄을 고르는 데만 쓰이므로 이름은 아무래도 좋다.
FAKE_TYPE = "가짜형식"


def wire(monkeypatch, node_ids, rows=None, handed=None, tools=None):
    """가짜 경로를 plan 에 연결.

    node_ids  경로. **데이터 노드부터 적는다** — 첫 실행 노드의 배선 줄을
              고르는 것이 그 앞 칸이다
    rows      {(노드, 받는 타입): 배선}. STEP_OF 에 없는 자리를 얹을 때 씀
    handed    {노드: [건네는 타입, ...]}. 안 적은 노드는 온톨로지를 그대로 봄
    tools     {노드: {server_id, tool, headline}}. TOOL_OF 에 없는 노드용
    """
    monkeypatch.setattr(
        step_service.ontology_service,
        "path_of",
        lambda recipe_id: [{"node_id": node_id} for node_id in node_ids],
    )
    if handed:
        real = step_service.ontology_service.handed_types
        monkeypatch.setattr(
            step_service.ontology_service,
            "handed_types",
            lambda node_id: handed.get(node_id) or real(node_id),
        )
    for key, wiring in (rows or {}).items():
        monkeypatch.setitem(step_service.STEP_OF, key, wiring)
    for node_id, tool in (tools or {}).items():
        monkeypatch.setitem(step_service.TOOL_OF, node_id, tool)


def fake_tool(name):
    """가짜 노드의 TOOL_OF 한 줄."""
    return {
        "server_id": "asap-mcp-core",
        "tool": name,
        "headline": "{arg} 를 조회했습니다.",
    }


def collect(events):
    """async generator 가 낸 이벤트를 순서대로 모음."""

    async def pump():
        return [event async for event in events]

    return asyncio.run(pump())


def test_a_value_from_the_utterance_goes_into_the_arg_slot(monkeypatch):
    """@place 를 @arg 로 바꾼 뒤에도 장소 발화가 그대로 돌아야 함."""
    wire(monkeypatch, ["spoken_place", "geocode_place"])

    plan = step_service.plan("recipe_001", "오송역")

    assert plan["steps"][0]["input"]["query"] == "오송역"


def test_a_value_that_is_not_a_place_goes_into_the_same_slot(monkeypatch):
    """표시가 뜻하는 것은 "발화에서 온 값" 이지 "장소" 가 아님.

    키워드를 받는 도구도 같은 칸을 쓴다. 그것을 막으려고 이름을 바꿨음.
    """
    wire(
        monkeypatch,
        ["spoken_keyword", "search_documents"],
        rows={("search_documents", "keyword"): {"input": {"query": ARG}}},
    )

    plan = step_service.plan("recipe_014", "철도 안전")

    assert plan["steps"][0]["input"]["query"] == "철도 안전"


def test_document_search_sends_the_utterance_value_together_with_the_chunk_count(monkeypatch):
    """k 를 안 보내면 기본 4 조각이라 화면이 고를 두셋의 여지가 좁음.

    값 6 의 근거는 step_service 의 배선 주석과 NOTES.md 「서른한째」에 있음.
    여기서는 칸이 나가는 것만 봄 — k 를 다시 재서 고치면 값은 바뀔 수 있음.
    """
    wire(monkeypatch, ["spoken_keyword", "search_documents"])

    plan = step_service.plan("recipe_013", "철도 안전")

    assert plan["steps"][0]["input"]["query"] == "철도 안전"
    assert isinstance(plan["steps"][0]["input"]["k"], int)
    assert plan["steps"][0]["input"]["k"] >= 1


def test_substitution_reaches_inside_a_nested_input(monkeypatch):
    """도구에 따라 input 이 한 겹이 아님. dict 안에도 list 안에도 있을 수 있음."""
    wire(
        monkeypatch,
        ["start", "nested"],
        rows={("nested", FAKE_TYPE): {"input": {
            "filter": {"name": ARG, "limit": 10},
            "names": [ARG, "고정값"],
        }}},
        handed={"start": [FAKE_TYPE]},
        tools={"nested": fake_tool("x.nested")},
    )

    plan = step_service.plan("recipe_x", "오송역")

    assert plan["steps"][0]["input"] == {
        "filter": {"name": "오송역", "limit": 10},
        "names": ["오송역", "고정값"],
    }


def test_arg_and_prev_mixed_each_become_their_own_value(monkeypatch):
    """둘은 다른 것을 가리킴. @arg 는 발화, $prev 는 앞 step 의 결과."""
    wire(
        monkeypatch,
        ["start", "mixed_first", "mixed_second"],
        rows={
            ("mixed_first", FAKE_TYPE): {"input": {"query": ARG}},
            ("mixed_second", FAKE_TYPE): {"input": {
                "name": ARG, "location": "$prev.location", "radius": 15000,
            }},
        },
        handed={"start": [FAKE_TYPE], "mixed_first": [FAKE_TYPE]},
        tools={
            "mixed_first": fake_tool("x.first"),
            "mixed_second": fake_tool("x.second"),
        },
    )

    plan = step_service.plan("recipe_x", "오송역")

    assert plan["steps"][1]["input"] == {
        "name": "오송역",
        "location": "$s1.location",
        "radius": 15000,
    }


# ── 값을 보고 칸을 고르는 줄 ────────────────────────────────────────
#
# 배선표에 값 판단이 들어온 유일한 자리다. 자가 좁은 것 자체가 요구사항이라
# 걸리는 값과 안 걸리는 값을 함께 본다.


def test_a_railway_line_name_goes_to_railwayName(monkeypatch):
    """"…선" 으로 끝나면 노선 이름임. stationName 으로 보내면 0건임."""
    wire(monkeypatch, ["spoken_place", "get_railway_lines"])

    plan = step_service.plan("recipe_003", "경부선")

    assert plan["steps"][0]["input"] == {"railwayName": "경부선"}


def test_a_station_name_stays_on_stationName(monkeypatch):
    """이 줄이 원래 하던 일임. 깨지면 되던 발화가 0건이 됨."""
    wire(monkeypatch, ["spoken_place", "get_railway_lines"])

    plan = step_service.plan("recipe_003", "오송역")

    assert plan["steps"][0]["input"] == {"stationName": "오송역"}


def test_a_value_that_is_neither_is_not_moved(monkeypatch):
    """"청주" 는 railwayName 으로 0건이고 stationName 으로 9건임(실측).

    자를 "…역" 으로 끝나는 것만으로 좁히지 않은 이유가 이것임.
    """
    wire(monkeypatch, ["spoken_place", "get_railway_lines"])

    plan = step_service.plan("recipe_003", "청주")

    assert plan["steps"][0]["input"] == {"stationName": "청주"}


def test_an_empty_argument_leaves_the_field_unchanged(monkeypatch):
    """빈 값은 어떤 어미로도 안 끝남. 두 칸 다 안 보내는 길은 여기 없음."""
    wire(monkeypatch, ["spoken_place", "get_railway_lines"])

    plan = step_service.plan("recipe_003", "")

    assert list(plan["steps"][0]["input"]) == ["stationName"]


def test_only_one_field_is_sent(monkeypatch):
    """저쪽이 두 절을 AND 로 이어서 둘 다 보내면 같은 값일 때 0건임."""
    wire(monkeypatch, ["spoken_place", "get_railway_lines"])

    for argument in ("경부선", "오송역"):
        sent = step_service.plan("recipe_003", argument)["steps"][0]["input"]
        assert len(sent) == 1


def test_the_railway_section_geometry_is_not_split(monkeypatch):
    """그 도구는 sectionName 한 칸뿐임. arg_field 를 안 적었으니 안 움직여야 함."""
    wire(monkeypatch, ["spoken_place", "get_railway_section"])

    plan = step_service.plan("recipe_002", "경부선")

    assert plan["steps"][0]["input"] == {"sectionName": "경부선"}


def test_a_wiring_line_without_arg_field_is_unchanged(monkeypatch):
    """지금 그 칸을 적은 줄이 하나뿐임. 나머지 서른다섯 줄이 안 흔들려야 함."""
    wire(monkeypatch, ["spoken_place", "geocode_place"])

    plan = step_service.plan("recipe_001", "경부선")

    assert plan["steps"][0]["input"] == {"query": "경부선"}


def test_a_field_that_is_not_arg_does_not_get_renamed(monkeypatch):
    """옮기는 것은 발화 값이 든 칸 하나뿐임."""
    wire(
        monkeypatch,
        ["start", "narrow"],
        rows={
            ("narrow", FAKE_TYPE): {
                "input": {"stationName": ARG, "limit": 5},
                "arg_field": (step_service.RAILWAY_LINE_SUFFIX, "railwayName"),
            }
        },
        handed={"start": [FAKE_TYPE], "narrow": []},
        tools={"narrow": fake_tool("geo.getRailwayLines")},
    )

    plan = step_service.plan("recipe_003", "경부선")

    assert plan["steps"][0]["input"] == {"railwayName": "경부선", "limit": 5}


def test_the_arg_in_the_headline_is_substituted_too(monkeypatch):
    """답 첫 줄에 그 값이 그대로 보임. 치환이 빠지면 화면에 {arg} 가 뜸."""
    wire(monkeypatch, ["spoken_place", "geocode_place", "find_cctv"])

    plan = step_service.plan("recipe_025", "오송역")

    assert plan["headline"] == "오송역 CCTV 를 조회했습니다."


def test_the_argument_is_not_prefixed_when_it_is_already_in_the_preamble(monkeypatch):
    """"전기차 충전소 데이터 검색해줘" 가 "전기차 충전소 전기차 충전소를 조회했습니다."

    틀이 "{arg} 전기차 충전소를 조회했습니다." 이고 인자도 "전기차 충전소" 라
    같은 말이 두 번 나갔음 (2026-08-25 화면 실측).
    """
    wire(monkeypatch, ["spoken_keyword", "search_ev_stations"])

    plan = step_service.plan("recipe_012", "전기차 충전소")

    assert plan["headline"] == "전기차 충전소를 조회했습니다."


def test_a_non_overlapping_argument_is_still_prefixed(monkeypatch):
    """겹침을 앞머리로만 봄. 인자가 문장 가운데 낱말과 같아도 안 뺌.

    포함(substring)으로 보면 "역" 이 "국회의원 지역구" 안에 걸려 멀쩡한 인자가
    빠짐. 인자가 붙는 자리는 앞이라 앞에서만 더듬거림.
    """
    wire(monkeypatch, ["spoken_identifier", "get_election_district"])

    plan = step_service.plan("recipe_015", "역")

    assert plan["headline"] == "역 국회의원 지역구를 조회했습니다."


# ── 인자를 어디서 받는가 ────────────────────────────────────────────


@pytest.fixture
def no_execution(monkeypatch):
    """run 을 가로챔. vendor 실행기와 Gateway 를 안 부름. 받은 인자만 남김."""
    seen = {}

    async def fake_run(recipe_id, argument, text="", context=None):
        seen["recipe_id"], seen["argument"] = recipe_id, argument
        yield {"type": "result", "answer": "", "commands": []}

    monkeypatch.setattr(execute_service, "run", fake_run)
    return seen


def resolved(monkeypatch, **result):
    """resolve 결과를 가짜로 줌. LLM 도 온톨로지도 안 부름."""
    answer = {"status": "SELECT", "recipe_id": "recipe_001", **result}
    monkeypatch.setattr(
        execute_service.resolve_service,
        "resolve",
        lambda text, llm_client, reason_max_length, context=None: answer,
    )


def test_the_argument_the_LLM_gave_is_used_first(monkeypatch, no_execution):
    """정규식이 못 잡는 발화도 이것으로 돎. "충북대" 는 끝 글자가 안 맞음."""
    resolved(monkeypatch, given="spoken_place", argument="충북대")

    collect(execute_service.chat("충북대 근처 CCTV 보여줘", None, 200))

    assert no_execution["argument"] == "충북대"


def test_place_in_runs_instead_when_argument_is_absent(monkeypatch, no_execution):
    """대비책. LLM 이 인자를 빠뜨려도 장소 발화만은 여전히 돌아야 함."""
    resolved(monkeypatch, given="spoken_place", argument=None)

    collect(execute_service.chat("오송역 위치 보여줘", None, 200))

    assert no_execution["argument"] == "오송역"


@pytest.mark.parametrize(
    "given, fragment",
    [
        ("spoken_place", "장소를 함께"),
        ("spoken_keyword", "찾을 것을 함께"),
        ("spoken_identifier", "이름이나 코드를 함께"),
        (None, "장소를 함께"),
    ],
    ids=["place", "keyword", "identifier", "given_없음"],
)
def test_with_neither_the_guidance_matching_given_goes_out(
    monkeypatch, no_execution, given, fragment
):
    """장소 문구 하나로 두면 "선거구 찾아줘" 에 장소를 대라고 답하게 됨.

    given 이 없거나 모르는 값이면 예전 문구 그대로다.
    """
    resolved(monkeypatch, given=given, argument=None)

    events = collect(execute_service.chat("찾아줘", None, 200))

    assert fragment in events[-1]["answer"]
    assert not no_execution, "인자가 없는데 도구를 불렀다"


# ── 앞 단계가 없을 때 ───────────────────────────────────────────────
#
# 같은 노드가 두 자리에 쓰인다. search_ev_stations 는 말한 키워드 뒤(recipe 012 ·
# 013)에도 오고 geocode 뒤(recipe 035 · 036)에도 온다.
#
# 예전에는 배선이 노드당 한 줄이라 $prev 를 쓰는 칸이 첫 step 에 놓였고,
# recipe 012 · 013 이 발화에서 온 값을 버리고 전국을 검색했다. 이제 그 자리는
# 키워드 줄이 걸린다 — 아래 첫 시험이 그것이다.
#
# 그래도 $prev 칸이 첫 step 에 놓이는 자리가 생길 수 있어 "빼고 부른다" 규칙은
# 남는다. 아래 넷이 그 규칙을 가짜 배선으로 본다.
#
# 첫 자리에서 키워드 줄이 걸리는지는 여기서 안 본다. demo/ 테스트를 늘리지
# 않는 규칙(CLAUDE.md)이라 tools/check_wiring.py 의 A 가 그것을 센다.


def test_with_no_previous_step_the_prev_field_is_dropped_from_the_call(monkeypatch):
    """멈추지 않고 그 칸만 빠져야 함.

    값을 지어내는 것보다 안 보내는 것이 낫다는 규칙이다. 그 칸이 required 면
    도구가 거부하고 그것은 배선이 틀린 것이다.
    """
    wire(
        monkeypatch,
        ["start", "lonely"],
        rows={("lonely", FAKE_TYPE): {
            "input": {"center": "$prev.location", "radiusMeters": 15000},
            "adapter": step_service.POINT_RADIUS_TO_BBOX,
        }},
        handed={"start": [FAKE_TYPE]},
        tools={"lonely": fake_tool("x.lonely")},
    )

    plan = step_service.plan("recipe_x", "오송역")

    assert plan["steps"][0]["input"] == {"radiusMeters": 15000}
    assert "center" not in plan["steps"][0]["input"]


def test_with_no_previous_step_the_inputAdapter_is_not_carried_either(monkeypatch):
    """걸 중심 좌표가 사라졌음. 그대로 걸면 vendor 어댑터가 ValueError 를 올림.

    _point_radius_to_bbox_input 이 center/location 을 못 찾으면 예외다.
    배선에 adapter 가 적혀 있어도 실을 수 없는 자리가 있다.
    """
    wire(
        monkeypatch,
        ["start", "lonely"],
        rows={("lonely", FAKE_TYPE): {
            "input": {"center": "$prev.location", "radiusMeters": 15000},
            "adapter": step_service.POINT_RADIUS_TO_BBOX,
        }},
        handed={"start": [FAKE_TYPE]},
        tools={"lonely": fake_tool("x.lonely")},
    )

    plan = step_service.plan("recipe_x", "오송역")

    assert "inputAdapter" not in plan["steps"][0]


def test_with_a_previous_step_the_inputAdapter_is_carried_verbatim(monkeypatch):
    """빼는 것은 앞 단계가 없을 때뿐임. geocode 뒤에서는 예전 그대로여야 함."""
    wire(monkeypatch, ["spoken_place", "geocode_place", "search_ev_stations"])

    plan = step_service.plan("recipe_035", "오송역")

    assert plan["steps"][1]["input"]["center"] == "$s1.location"
    assert plan["steps"][1]["inputAdapter"] == step_service.POINT_RADIUS_TO_BBOX


def test_only_the_prev_field_is_dropped(monkeypatch):
    """@arg 와 상수는 그대로 남아야 함. 통째로 비우는 것이 아님."""
    wire(
        monkeypatch,
        ["start", "lonely"],
        rows={("lonely", FAKE_TYPE): {
            "input": {"query": ARG, "location": "$prev.location", "limit": 50},
        }},
        handed={"start": [FAKE_TYPE]},
        tools={"lonely": fake_tool("x.lonely")},
    )

    plan = step_service.plan("recipe_x", "오송역")

    assert plan["steps"][0]["input"] == {"query": "오송역", "limit": 50}


def test_a_prev_inside_a_list_is_dropped_too(monkeypatch):
    """중첩된 자리도 같은 규칙. dict 만 보고 list 를 빠뜨리면 참조가 새어 나감."""
    wire(
        monkeypatch,
        ["start", "nested_prev"],
        rows={("nested_prev", FAKE_TYPE): {
            "input": {"names": [ARG, "$prev.name", "고정값"]},
        }},
        handed={"start": [FAKE_TYPE]},
        tools={"nested_prev": fake_tool("x.nested")},
    )

    plan = step_service.plan("recipe_x", "오송역")

    assert plan["steps"][0]["input"]["names"] == ["오송역", "고정값"]
