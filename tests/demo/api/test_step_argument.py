"""발화에서 온 인자가 step 의 @arg 자리에 들어가는 것.

LLM 을 부르지 않는다. 온톨로지도 안 읽는다 — 경로와 배선을 가짜로 주고
치환 결과만 본다. 실제 노드 이름이 바뀌어도 흔들리지 않게 하려는 것.

인자를 뽑는 자리가 둘이다. 발화 해석 LLM 의 argument 가 먼저이고, 그것이
없을 때만 정규식(place_in)이 돈다. 아래에서 둘 다 본다.
"""

import asyncio

import pytest

from demo.api.services import execute_service, step_service

ARG = step_service.SPOKEN_VALUE


def wire(monkeypatch, node_ids, **extra):
    """가짜 경로를 plan 에 연결. STEP_OF 에 없는 노드는 extra 로 얹음."""
    monkeypatch.setattr(
        step_service.ontology_service,
        "path_of",
        lambda recipe_id: [{"node_id": node_id} for node_id in node_ids],
    )
    for node_id, wiring in extra.items():
        monkeypatch.setitem(step_service.STEP_OF, node_id, wiring)


def collect(events):
    """async generator 가 낸 이벤트를 순서대로 모음."""

    async def pump():
        return [event async for event in events]

    return asyncio.run(pump())


def test_발화에서_온_값이_arg_자리에_들어간다(monkeypatch):
    """@place 를 @arg 로 바꾼 뒤에도 장소 발화가 그대로 돌아야 함."""
    wire(monkeypatch, ["geocode_place"])

    plan = step_service.plan("recipe_001", "오송역")

    assert plan["steps"][0]["input"]["query"] == "오송역"


def test_장소가_아닌_값도_같은_자리에_들어간다(monkeypatch):
    """표시가 뜻하는 것은 "발화에서 온 값" 이지 "장소" 가 아님.

    키워드를 받는 도구도 같은 칸을 쓴다. 그것을 막으려고 이름을 바꿨음.
    """
    wire(monkeypatch, ["search_documents"], search_documents={
        "server_id": "asap-mcp-core",
        "tool": "doc.search",
        "input": {"query": ARG},
        "headline": "{arg} 문서를 조회했습니다.",
    })

    plan = step_service.plan("recipe_014", "철도 안전")

    assert plan["steps"][0]["input"]["query"] == "철도 안전"


def test_중첩된_input_안까지_바뀐다(monkeypatch):
    """도구에 따라 input 이 한 겹이 아님. dict 안에도 list 안에도 있을 수 있음."""
    wire(monkeypatch, ["nested"], nested={
        "server_id": "asap-mcp-core",
        "tool": "x.nested",
        "input": {
            "filter": {"name": ARG, "limit": 10},
            "names": [ARG, "고정값"],
        },
        "headline": "{arg} 를 조회했습니다.",
    })

    plan = step_service.plan("recipe_x", "오송역")

    assert plan["steps"][0]["input"] == {
        "filter": {"name": "오송역", "limit": 10},
        "names": ["오송역", "고정값"],
    }


def test_arg_와_prev_가_섞여도_각각_제_값이_된다(monkeypatch):
    """둘은 다른 것을 가리킴. @arg 는 발화, $prev 는 앞 step 의 결과."""
    wire(monkeypatch, ["mixed_first", "mixed_second"],
         mixed_first={
             "server_id": "asap-mcp-core",
             "tool": "x.first",
             "input": {"query": ARG},
             "headline": "{arg} 첫 단계.",
         },
         mixed_second={
             "server_id": "asap-mcp-core",
             "tool": "x.second",
             "input": {"name": ARG, "location": "$prev.location", "radius": 15000},
             "headline": "{arg} 두 번째 단계.",
         })

    plan = step_service.plan("recipe_x", "오송역")

    assert plan["steps"][1]["input"] == {
        "name": "오송역",
        "location": "$s1.location",
        "radius": 15000,
    }


def test_headline_의_arg_도_바뀐다(monkeypatch):
    """답 첫 줄에 그 값이 그대로 보임. 치환이 빠지면 화면에 {arg} 가 뜸."""
    wire(monkeypatch, ["geocode_place", "find_cctv"])

    plan = step_service.plan("recipe_025", "오송역")

    assert plan["headline"] == "오송역 CCTV 를 조회했습니다."


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
        lambda text, llm_client, reason_max_length: answer,
    )


def test_LLM_이_준_argument_를_먼저_쓴다(monkeypatch, no_execution):
    """정규식이 못 잡는 발화도 이것으로 돎. "충북대" 는 끝 글자가 안 맞음."""
    resolved(monkeypatch, given="spoken_place", argument="충북대")

    collect(execute_service.chat("충북대 근처 CCTV 보여줘", None, 200))

    assert no_execution["argument"] == "충북대"


def test_argument_가_없으면_place_in_이_대신_돈다(monkeypatch, no_execution):
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
def test_둘_다_없으면_given_에_맞는_안내가_나간다(
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
# 같은 노드가 두 자리에 쓰인다. search_ev_stations 는 keyword 뒤(recipe 012 ·
# 013)에도 오고 geocode 뒤(recipe 035 · 036)에도 온다. 배선은 한 벌뿐이라
# $prev 를 쓰는 칸이 첫 step 에 놓이는 일이 생긴다.
#
# 예전에는 그때 ValueError 로 멈춰 recipe 012 · 013 이 도구를 하나도 못 불렀다.
# 지금은 그 칸을 빼고 부른다 — 아래가 그 규칙이다.


def test_앞_단계가_없으면_prev_칸을_빼고_부른다(monkeypatch):
    """멈추지 않고 그 칸만 빠져야 함.

    ev.searchStations 의 bbox 넷은 전부 optional 이라 없어도 도구가 돌고
    전국을 검색한다. 좌표를 지어내는 것보다 안 보내는 것이 낫다.
    """
    wire(monkeypatch, ["search_ev_stations"])

    plan = step_service.plan("recipe_012", "충전소")

    assert plan["steps"][0]["input"] == {"radiusMeters": step_service.RADIUS_METERS}
    assert "center" not in plan["steps"][0]["input"]


def test_앞_단계가_없으면_inputAdapter_도_안_싣는다(monkeypatch):
    """걸 중심 좌표가 사라졌음. 그대로 걸면 vendor 어댑터가 ValueError 를 올림.

    _point_radius_to_bbox_input 이 center/location 을 못 찾으면 예외다.
    배선에 adapter 가 적혀 있어도 실을 수 없는 자리가 있다.
    """
    wire(monkeypatch, ["search_ev_stations"])

    plan = step_service.plan("recipe_012", "충전소")

    assert "inputAdapter" not in plan["steps"][0]


def test_앞_단계가_있으면_inputAdapter_를_그대로_싣는다(monkeypatch):
    """빼는 것은 앞 단계가 없을 때뿐임. geocode 뒤에서는 예전 그대로여야 함."""
    wire(monkeypatch, ["geocode_place", "search_ev_stations"])

    plan = step_service.plan("recipe_035", "오송역")

    assert plan["steps"][1]["input"]["center"] == "$s1.location"
    assert plan["steps"][1]["inputAdapter"] == step_service.POINT_RADIUS_TO_BBOX


def test_빠지는_것은_prev_칸_하나뿐이다(monkeypatch):
    """@arg 와 상수는 그대로 남아야 함. 통째로 비우는 것이 아님."""
    wire(monkeypatch, ["lonely"], lonely={
        "server_id": "asap-mcp-core",
        "tool": "x.lonely",
        "input": {"query": ARG, "location": "$prev.location", "limit": 50},
        "headline": "{arg} 를 조회했습니다.",
    })

    plan = step_service.plan("recipe_x", "오송역")

    assert plan["steps"][0]["input"] == {"query": "오송역", "limit": 50}


def test_list_안의_prev_도_빠진다(monkeypatch):
    """중첩된 자리도 같은 규칙. dict 만 보고 list 를 빠뜨리면 참조가 새어 나감."""
    wire(monkeypatch, ["nested_prev"], nested_prev={
        "server_id": "asap-mcp-core",
        "tool": "x.nested",
        "input": {"names": [ARG, "$prev.name", "고정값"]},
        "headline": "{arg} 를 조회했습니다.",
    })

    plan = step_service.plan("recipe_x", "오송역")

    assert plan["steps"][0]["input"]["names"] == ["오송역", "고정값"]
