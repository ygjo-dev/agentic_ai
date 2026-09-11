"""대상 : execution/step_service.py — recipe 를 실행 계획으로 바꾼다

온톨로지 노드의 tool 을 읽어 노드마다 무엇을 부르고 input 을 어떻게 채울지 정한다.
여기서 보는 것은 그 규칙이지 온톨로지에 적힌 값이 도구와 맞느냐가 아니다 —
그것은 test_wiring_contract.py 가 본다.

한 자리에서 받는 값의 출처가 셋이고 그것이 input 의 모양을 가른다.

    source    경로의 시작 노드. 발화 인자 그대로 · "$context.…"
    step      앞 도구 단계. "$s1.…"
    adapter   앞 노드가 builtin 계산. 그 입력과 vendor 어댑터가 이 단계에 얹힌다

LLM 도 Gateway 도 부르지 않는다. 온톨로지와 배선표만 읽는다.
"""

import datetime
import zoneinfo

import pytest

import paths
from execution import step_service
from ontology import graph

PROBE_NOW = datetime.datetime(2026, 1, 1, 9, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Seoul"))


def recipe_of(chain):
    """그 사슬을 가진 recipe id. **번호를 박지 않으려고 찾아서 쓴다** —
    노드가 늘면 번호가 밀린다."""
    for recipe_id in graph.recipe_ids():
        nodes = [entry["node_id"] for entry in graph.path_of(recipe_id)]
        if nodes == list(chain):
            return recipe_id
    raise AssertionError(f"그런 사슬의 recipe 가 없다: {chain}")


def fake(monkeypatch, path, tools, inputs, outputs=None, sources=None, headlines=None):
    """가짜 온톨로지를 plan 에 연결.

    path      경로. 시작 노드부터 적는다
    tools     {노드: tool dict}
    inputs    {노드: [받는 타입, ...]}
    outputs   {노드: [내놓는 타입, ...]}. 안 적은 노드는 아무것도 안 내놓는다
    sources   {노드: source dict}
    headlines {노드: 답 첫 줄}. 안 적은 도구 노드는 "{arg} 를 조회했습니다."
    """
    outputs = outputs or {}
    sources = sources or {}
    known = set(path) | set(tools) | {t for ts in inputs.values() for t in ts}

    monkeypatch.setattr(graph, "path_of", lambda recipe_id: [{"node_id": node} for node in path])
    monkeypatch.setattr(graph, "tool_of", lambda node: tools.get(node))
    monkeypatch.setattr(graph, "inputs_of", lambda node: list(inputs.get(node, [])))
    monkeypatch.setattr(graph, "outputs_of", lambda node: list(outputs.get(node, [])))
    monkeypatch.setattr(graph, "source_of", lambda node: sources.get(node))
    monkeypatch.setattr(graph, "node_ids", lambda: sorted(known))
    monkeypatch.setattr(graph, "handed_types", lambda node: outputs.get(node) or [node])
    monkeypatch.setattr(graph, "is_executable", lambda node: bool(outputs.get(node)))
    for node in tools:
        monkeypatch.setitem(
            step_service.HEADLINE, node, (headlines or {}).get(node, "{arg} 를 조회했습니다.")
        )


SPOKEN = {"from": "spoken.argument"}


# ── 배선표에 남은 것을 읽는다 ───────────────────────────────────────
#
# **「계기판이 조용히 죽는다」가 세 번 났다.** 파일이 없거나 깨졌을 때 빈 표로
# 도는 대신 터지는지를 본다. 계기판이 표를 import 해서 곧장 읽으므로 빈 표는
# 멀쩡해 보이는 출력이 된다.


@pytest.fixture
def restore_tables():
    """가짜 파일을 물린 시험이 진짜 표를 두고 가지 않게.

    표는 모듈 하나에 하나뿐이고, 갈아 끼우지 않고 비웠다 채우는 방식이라
    시험이 얹은 것도 그대로 남음. monkeypatch 가 되돌리는 것은
    paths.WIRING_PATH 뿐임.
    """
    tables = [step_service.HEADLINE]
    saved = [dict(table) for table in tables]
    mtime = step_service._wiring_mtime
    yield
    for table, copy in zip(tables, saved):
        table.clear()
        table.update(copy)
    step_service._wiring_mtime = mtime


VALID_WIRING = (
    "headline:\n"
    "  n: 하나\n"
)

# 믿을 수 없는 배선 파일은 전부 터진다. **빈 표로 도는 길이 없어야 한다.**
UNTRUSTWORTHY_WIRING = [
    # 오타 난 절은 조용히 빈 표가 된다.
    pytest.param(VALID_WIRING + "headlines: {}\n", ValueError, "headlines", id="unknown_section"),
    # 절이 빠지면 답 첫 줄이 통째로 없다.
    pytest.param("{}\n", ValueError, "headline", id="missing_section"),
    # 응답 경로는 온톨로지의 tool.outputs · source.fields 가 갖는다. 표가 여기 되살아나면
    # 원천이 둘이 된다.
    pytest.param(
        VALID_WIRING + "previous_result_paths:\n  n:\n    point: location\n",
        ValueError, "previous_result_paths", id="response_paths_back_in_the_wiring",
    ),
    # 틀이 문자열이 아니면 답 첫 줄을 만드는 순간 터진다. 읽을 때 터지는 것이 낫다.
    pytest.param("headline:\n  n: 3\n", ValueError, "headline", id="non_string_headline"),
    pytest.param("headline: {\n  깨진다\n", Exception, None, id="broken_syntax"),
    # 파일이 아예 없는 경우. text 가 None 이면 파일을 안 만든다.
    pytest.param(None, FileNotFoundError, None, id="missing_file"),
]


@pytest.mark.parametrize("text, raised, fragment", UNTRUSTWORTHY_WIRING)
def test_a_wiring_file_that_cannot_be_trusted_raises(
    tmp_path, monkeypatch, restore_tables, text, raised, fragment
):
    """믿을 수 없는 배선 파일은 빈 표로 돌지 않고 터진다."""
    path = tmp_path / "wiring.yaml"
    if text is not None:
        path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(paths, "WIRING_PATH", path)

    with pytest.raises(raised, match=fragment):
        step_service._load_wiring()


def test_a_broken_file_does_not_empty_the_tables(tmp_path, monkeypatch, restore_tables):
    """터져도 반만 바뀐 표가 남지 않는다.

    표를 다 만든 뒤에 갈아 넣는다. 빈 표보다 반쪽 표가 나쁘다 — 계기판이
    멀쩡한 모양으로 틀린 수를 찍는다.
    """
    before = dict(step_service.HEADLINE)

    path = tmp_path / "wiring.yaml"
    path.write_text("headline: {깨진다\n", encoding="utf-8")
    monkeypatch.setattr(paths, "WIRING_PATH", path)

    with pytest.raises(Exception):
        step_service._load_wiring()

    assert step_service.HEADLINE == before


def test_reload_reads_again_when_mtime_changes(tmp_path, monkeypatch, restore_tables):
    """mtime 이 바뀌면 다시 읽는다. 안 바뀌면 안 읽는다.

    파일을 고치면 서버를 안 내리고 반영되어야 한다.
    """
    path = tmp_path / "wiring.yaml"
    path.write_text(VALID_WIRING, encoding="utf-8")
    monkeypatch.setattr(paths, "WIRING_PATH", path)
    monkeypatch.setattr(step_service, "_wiring_mtime", None)

    step_service.reload_wiring()
    assert step_service.HEADLINE["n"] == "하나"

    # 파일을 안 건드리면 다시 안 판다. 손으로 얹은 줄이 살아 있으면 안 판 것이다.
    step_service.HEADLINE["표시"] = "안 판다"
    step_service.reload_wiring()
    assert "표시" in step_service.HEADLINE

    stat = path.stat()
    path.write_text(VALID_WIRING.replace("하나", "둘"), encoding="utf-8")
    if path.stat().st_mtime_ns == stat.st_mtime_ns:  # 시계가 굵은 파일시스템
        import os

        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    step_service.reload_wiring()
    assert step_service.HEADLINE["n"] == "둘"
    assert "표시" not in step_service.HEADLINE


# ── 온톨로지의 tool 을 읽는다 ───────────────────────────────────────


@pytest.mark.parametrize(
    "tool_id, kind, fields",
    [
        ("asap-mcp-core/geo.geocode", step_service.MCP, {"server_id": "asap-mcp-core", "tool": "geo.geocode"}),
        ("builtin/geo.pointRadiusToBbox", step_service.BUILTIN, {"adapter": step_service.POINT_RADIUS_TO_BBOX}),
        ("frontend/digitalTwin.showFacility", step_service.COMMAND, {"command": "digitalTwin.showFacility"}),
    ],
    ids=["gateway", "builtin", "frontend"],
)
def test_the_namespace_of_the_tool_id_decides_how_it_runs(monkeypatch, tool_id, kind, fields):
    """도구 id 의 첫 칸이 실행 수단을 가른다. 예약 namespace 는 둘이다.

    서버 id 와 도구 이름을 따로 적지 않는다. Gateway 가 부르는 이름이
    "<server_id>/<도구>" 한 덩어리이고, 도구 이름에는 점이 들어 있다.
    """
    fake(monkeypatch, ["a", "n"], tools={"n": {"id": tool_id, "parameters": {}}}, inputs={})

    binding = step_service.binding_of("n")

    assert binding["kind"] == kind
    for key, value in fields.items():
        assert binding[key] == value


# 알아볼 수 없는 tool 은 전부 터진다. 조용히 넘기면 그 문자열이 도구에 실려 나가고
# 오류가 아니라 0건이 온다. 각 줄이 막는 실제 고장을 옆에 적었다.
UNTRUSTWORTHY_TOOLS = [
    # namespace 가 없으면 서버를 모른다.
    pytest.param({"id": "geo.geocode"}, "namespace", id="no_namespace"),
    # 모르는 builtin 은 걸 어댑터가 없다.
    pytest.param({"id": "builtin/geo.buffer"}, "builtin", id="unknown_builtin"),
    # parameter 오타는 칸이 소리 없이 사라진다.
    pytest.param({"id": "s/t", "parametres": {}}, "parametres", id="unknown_field"),
    # 받지 않는 타입을 가리키면 그 칸은 영영 안 채워진다.
    pytest.param({"id": "s/t", "parameters": {"code": "admin_code.code"}}, "hasInput", id="undeclared_type"),
    # 부르는 순간의 모르는 이름은 문자열 그대로 실려 나간다.
    pytest.param({"id": "s/t", "parameters": {"at": "runtime.now.datetime"}}, "runtime.now", id="unknown_runtime"),
    # 말하지 않은 발화가 갈 곳이 없다.
    pytest.param({"id": "s/t", "parameters": {"mode": {"from": "spoken.travel_mode"}}}, "default", id="no_default"),
    # default 를 사람 말로 적게 해 표에 두 가지 말이 섞이지 않게 한다.
    pytest.param(
        {"id": "s/t", "parameters": {"mode": {"from": "spoken.travel_mode", "default": "WALK", "map": {"도보": "WALK"}}}},
        "map", id="default_outside_map",
    ),
    # 발화 인자는 semantic 노드의 source 가 말한다. 두 길을 열지 않는다.
    pytest.param({"id": "s/t", "parameters": {"query": {"from": "spoken.argument"}}}, "spoken", id="argument_by_from"),
    # 조건은 하나만. 둘을 적으면 어느 쪽이 이기는지 안 갈린다.
    pytest.param(
        {"id": "s/t", "parameters": {"name": {"value": "place_name", "if_endswith": "선", "unless_endswith": "역"}}},
        "조건", id="two_conditions",
    ),
    # builtin 은 만드는 칸이 정해져 있다. 읽는 법을 적어도 아무도 안 읽는다.
    pytest.param({"id": "builtin/geo.pointRadiusToBbox", "outputs": {}}, "outputs", id="outputs_on_builtin"),
]


@pytest.mark.parametrize("tool, fragment", UNTRUSTWORTHY_TOOLS)
def test_a_tool_that_cannot_be_trusted_raises(monkeypatch, tool, fragment):
    """믿을 수 없는 tool 은 조용히 넘기지 않고 터진다."""
    fake(
        monkeypatch,
        ["place_name", "n"],
        tools={"n": tool},
        inputs={"n": ["place_name", "point"], "other": ["admin_code"]},
    )

    with pytest.raises(ValueError, match=fragment):
        step_service.binding_of("n")


def test_the_ontology_and_the_remaining_wiring_agree():
    """온톨로지의 tool · source 와 배선표에 남은 것이 서로를 가리킨다.

    headline 이 없으면 답 첫 줄에서 KeyError 가 나고, 받는 노드가 읽는 칸을 내놓는
    쪽이 안 적었으면 그 자리가 조용히 unwired 가 된다.
    """
    assert step_service.check_bindings() == []


# ── 어느 타입을 받는가 — binding_at ────────────────────────────────


def test_the_type_is_chosen_by_what_the_previous_node_hands_over():
    """앞 노드가 건네는 타입이 받는 칸을 고른다. 노드 이름만으로는 안 갈린다.

    같은 노드가 두 자리에 온다 — 전기차 충전소 검색은 키워드 뒤(keyword)에도
    오고 지점 주변 범위 변환 뒤(map_extent)에도 온다.
    """
    _, by_keyword = step_service.binding_at("search_ev_stations", "keyword")
    _, by_extent = step_service.binding_at("search_ev_stations", "point_to_map_extent")

    assert by_keyword == "keyword"
    assert by_extent == "map_extent"


def test_no_matching_type_is_none_not_an_error():
    """맞는 타입이 없으면 None. 여기서 터지면 unwired 가 셀 것이 없어진다."""
    assert step_service.binding_at("find_cctv", "keyword") is None


# ── 발화에서 온 값 ──────────────────────────────────────────────────


def test_a_value_from_the_utterance_goes_into_the_semantic_slot():
    plan = step_service.plan(recipe_of(["place_name", "geocode_place"]), "오송역")

    assert plan["steps"][0]["input"] == {"query": "오송역"}


def test_a_value_that_is_not_a_place_goes_into_its_own_slot_the_same_way():
    """발화 인자는 "장소" 를 뜻하지 않는다. 키워드를 받는 도구도 같은 길로 받는다.

    무엇으로 읽히는지는 시작 노드(키워드)가 말하고, 상수 칸(k)은 그대로 간다.
    """
    plan = step_service.plan(recipe_of(["keyword", "search_documents"]), "철도 안전")

    assert plan["steps"][0]["input"] == {"query": "철도 안전", "k": 6}


def test_a_field_for_a_type_not_handed_over_here_is_not_sent():
    """그 자리에서 건네받지 않은 타입의 칸은 안 보낸다. 목록 칸이면 통째로 뺀다.

    행정구역 조회는 키워드 뒤에서는 query 로, 지도 범위 뒤에서는 bbox 로 부른다.
    둘 다 보내면 도구가 두 조건을 함께 걸어 0건이 오거나, 빈 bbox 가 실려 나간다.
    """
    by_keyword = step_service.plan(recipe_of(["keyword", "search_admin_boundaries"]), "논산")
    by_extent = step_service.plan(recipe_of(["map_extent", "search_admin_boundaries"]), "")

    assert by_keyword["steps"][0]["input"] == {"query": "논산", "layer": "sigungu"}
    assert set(by_extent["steps"][0]["input"]) == {"bbox", "layer"}


# ── 값을 보고 칸을 고르는 조건 ──────────────────────────────────────
#
# 온톨로지에 값 판단이 들어온 유일한 자리다. 자가 좁은 것 자체가 요구사항이라
# 걸리는 값과 안 걸리는 값을 함께 본다.
#
# ★ 이 heuristic 을 언제 걷어낼지는 아직 정해지지 않았다.


# **보내는 칸 전체를 못 박는다.** 도구가 두 절을 AND 로 이으므로 railwayName 과
# stationName 을 함께 보내면 같은 값일 때 0건이 온다 — 한 칸만 나가야 한다.
@pytest.mark.parametrize(
    "argument, sent",
    [
        # "…선" 으로 끝나면 노선 이름. stationName 으로 보내면 0건이다.
        ("경부선", {"railwayName": "경부선"}),
        # 원래 하던 일. 깨지면 되던 발화가 0건이 된다.
        ("오송역", {"stationName": "오송역"}),
        # "청주" 는 railwayName 으로 0건이고 stationName 으로 9건이다(실측).
        # 자를 "…역" 으로 끝나는 것만으로 좁히지 않은 이유가 이것이다.
        ("청주", {"stationName": "청주"}),
        # 빈 값은 어떤 어미로도 안 끝난다. 두 칸 다 안 보내는 길은 여기 없다.
        ("", {"stationName": ""}),
    ],
    ids=["railway_line", "station", "neither", "empty"],
)
def test_the_value_decides_which_field_carries_the_argument(argument, sent):
    plan = step_service.plan(recipe_of(["place_name", "get_railway_lines"]), argument)

    assert plan["steps"][0]["input"] == sent


def test_a_condition_on_a_value_known_only_after_the_call_raises(monkeypatch):
    """앞 단계 결과는 vendor 가 나중에 푼다. 여기서 어미를 볼 수 없다.

    조용히 한쪽으로 보내면 절반의 발화가 늘 0건이 된다.
    """
    fake(
        monkeypatch,
        ["start", "first", "second"],
        tools={
            "first": {"id": "s/first", "parameters": {"q": "place_name"}, "outputs": {"place_name": {"value": "name"}}},
            "second": {"id": "s/second", "parameters": {"name": {"value": "place_name", "if_endswith": "선"}}},
        },
        inputs={"first": ["place_name"], "second": ["place_name"]},
        outputs={"first": ["place_name"], "start": ["place_name"]},
        sources={"start": SPOKEN},
    )

    with pytest.raises(ValueError, match="발화 인자"):
        step_service.plan("recipe_x", "경부선")


# ── 답 첫 줄 ────────────────────────────────────────────────────────


def test_the_arg_in_the_headline_is_substituted_too():
    """답 첫 줄에 그 값이 그대로 보임. 치환이 빠지면 화면에 {arg} 가 뜸."""
    plan = step_service.plan(
        recipe_of(["place_name", "geocode_place", "point_to_map_extent", "find_cctv"]), "오송역"
    )

    assert plan["headline"] == "오송역 CCTV 를 조회했습니다."


def test_the_argument_is_not_prefixed_when_it_is_already_in_the_preamble():
    """"전기차 충전소 데이터 검색해줘" 가 "전기차 충전소 전기차 충전소를 조회했습니다."

    틀이 "{arg} 전기차 충전소를 조회했습니다." 이고 인자도 "전기차 충전소" 라
    같은 말이 두 번 나갔음(실측).
    """
    assert step_service._headline("{arg} 전기차 충전소를 조회했습니다.", "전기차 충전소") == (
        "전기차 충전소를 조회했습니다."
    )


def test_a_non_overlapping_argument_is_still_prefixed():
    """겹침을 앞머리로만 봄. 인자가 문장 가운데 낱말과 같아도 안 뺌.

    포함(substring)으로 보면 "역" 이 "국회의원 지역구" 안에 걸려 멀쩡한 인자가
    빠짐. 인자가 붙는 자리는 앞이라 앞에서만 더듬거림.
    """
    plan = step_service.plan(recipe_of(["district_code", "get_election_district"]), "역")

    assert plan["headline"] == "역 국회의원 지역구를 조회했습니다."


# ── 앞 단계 응답 · 화면 값을 semantic 칸으로 읽는다 ──────────────────
#
# **칸이 raw 값의 어디 있는지는 내놓는 쪽이 적는다.** 앞 도구는 tool.outputs, 화면은
# semantic 노드의 source.fields 다. 계획은 그것을 dict 키 · 목록 번호로만 된 경로
# 참조로 적는다. 적힌 것이 없는 칸을 이름으로 짐작하지 않는다.
#
# 아래 raw 값은 dev/tools/probe_out/ 의 실측 응답에서 필요한 칸만 옮긴 것이다. 그
# 폴더는 .gitignore 라 시험이 읽지 않는다.

GEOCODE_FOUND = {
    "location": [127.3276666158151, 36.61995281117007],
    "bbox": [[127.3227, 36.615], [127.3327, 36.625]],
    "address": "충청북도 청주시 흥덕구 오송읍 봉산리 369-1",
}
SECTION_FOUND = {
    "sectionId": "e55869e8",
    "bbox": [[126.868587747, 36.619576682], [127.32811524, 37.554557989]],
}
# Gateway 는 못 찾은 것을 200 과 error 로 돌려준다. 읽을 칸이 하나도 없다.
NOT_FOUND = {"error": {"code": "NOT_FOUND", "message": "찾을 수 없습니다."}}
BOUNDARY_ONE = {"items": [{"code": "43113", "name": "청주시 흥덕구", "layerId": "sigungu"}], "count": 1}
BOUNDARY_NONE = {"items": [], "count": 0}
STATIONS_MANY = {
    "items": [
        {"id": "ev_station_MT064039", "stationId": "MT064039", "name": "일출랜드"},
        {"id": "ev_station_JE040085", "stationId": "JE040085", "name": "제주스누피가든"},
    ],
    "count": 2,
}
STATIONS_NONE = {"items": [], "count": 0}
SCREEN = {
    "view": {"bbox": [[127.20, 36.55], [127.40, 36.70]]},
    "selectedLocation": {"lon": 127.2974, "lat": 36.6199, "label": "관심 지점", "source": "map-right-click"},
}


def resolve(value, scope):
    """"$이름.경로" 를 dict 키와 목록 번호만으로 풂. 못 찾으면 None.

    vendor 의 참조 해석에는 이름으로 좌표를 찾는 특례가 있음. 여기에는 없음. 계획이
    그 특례 없이도 맞는 값을 가리키는지 보려는 것임.
    """
    if isinstance(value, dict):
        return {key: resolve(item, scope) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve(item, scope) for item in value]
    if not isinstance(value, str) or not value.startswith("$"):
        return value
    head, *keys = value[1:].split(".")
    current = scope.get(head)
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and key.isdigit() and int(key) < len(current):
            current = current[int(key)]
        else:
            return None
    return current


def step_input(chain, index, argument="오송역"):
    """그 사슬의 recipe 계획에서 index 번째 step 의 input."""
    return step_service.plan(recipe_of(chain), argument)["steps"][index]["input"]


GEOCODE_THEN_POINT = ["place_name", "geocode_place", "find_admin_boundary_by_point", "get_age_profile"]
GEOCODE_THEN_EXTENT = ["place_name", "geocode_place", "search_population_statistics"]
SECTION_THEN_EXTENT = ["place_name", "get_railway_section", "find_cctv"]
BOUNDARY_THEN_CODE = ["point", "find_admin_boundary_by_point", "get_age_profile"]
STATIONS_THEN_ID = ["keyword", "search_ev_stations", "get_ev_station"]
NO_EXTENT = {"minLon": None, "minLat": None, "maxLon": None, "maxLat": None}


@pytest.mark.parametrize(
    "chain, previous, expected",
    [
        # 장소 좌표 변환 -> 지점 좌표. location 이 [경도, 위도] 다.
        (GEOCODE_THEN_POINT, GEOCODE_FOUND, {"lon": 127.3276666158151, "lat": 36.61995281117007, "layer": "sigungu"}),
        (GEOCODE_THEN_POINT, NOT_FOUND, {"lon": None, "lat": None, "layer": "sigungu"}),
        # 장소 좌표 변환 -> 지도 범위. bbox 가 두 겹이다.
        (GEOCODE_THEN_EXTENT, GEOCODE_FOUND, {"bbox": [127.3227, 36.615, 127.3327, 36.625]}),
        # 철도 구간 형상 조회 -> 지도 범위.
        (SECTION_THEN_EXTENT, SECTION_FOUND,
         {"minLon": 126.868587747, "minLat": 36.619576682, "maxLon": 127.32811524, "maxLat": 37.554557989}),
        (SECTION_THEN_EXTENT, NOT_FOUND, NO_EXTENT),
        # 지점 행정구역 판별 -> 행정구역 코드. items 의 첫 칸이다.
        (BOUNDARY_THEN_CODE, BOUNDARY_ONE, {"level": "sigungu", "code": "43113"}),
        (BOUNDARY_THEN_CODE, BOUNDARY_NONE, {"level": None, "code": None}),
        # 전기차 충전소 검색 -> 충전소 번호. 첫 칸의 stationId 다. id 가 아니다.
        (STATIONS_THEN_ID, STATIONS_MANY, {"statId": "MT064039"}),
        (STATIONS_THEN_ID, STATIONS_NONE, {"statId": None}),
    ],
    ids=[
        "geocode_point", "geocode_not_found", "geocode_extent", "section_extent", "section_not_found",
        "boundary_one", "boundary_none", "stations_many", "stations_none",
    ],
)
def test_the_previous_response_is_read_by_the_path_its_producer_declares(chain, previous, expected):
    """앞 단계 응답에서 semantic 칸을 꺼내는 경로가 내놓는 노드의 tool.outputs 에서 온다.

    못 찾은 응답 · 빈 목록에서는 값이 None 이다. 다른 칸이나 다른 항목으로 채우지
    않는다. required 가 빈 채로는 vendor 가 부르기 전에 막는다.
    """
    sent = step_input(chain, 1)

    assert resolve(sent, {"s1": previous}) == expected


def test_a_semantic_field_becomes_an_explicit_path_not_its_own_name():
    """point.lon 은 $s1.lon 이 아니라 $s1.location.0 이다.

    칸 이름을 raw 경로로 쓰면 vendor 가 이름으로 좌표를 찾아 줄 때만 맞는다. 계획이
    그 특례에 기대지 않는다. 목록에서 고르는 칸은 고른 번호까지 경로에 적힌다.
    """
    assert step_input(GEOCODE_THEN_POINT, 1)["lon"] == "$s1.location.0"
    assert step_input(GEOCODE_THEN_EXTENT, 1)["bbox"][0] == "$s1.bbox.0.0"
    assert step_input(SECTION_THEN_EXTENT, 1)["maxLat"] == "$s1.bbox.1.1"
    assert step_input(BOUNDARY_THEN_CODE, 1) == {"level": "$s1.items.0.layerId", "code": "$s1.items.0.code"}
    assert step_input(STATIONS_THEN_ID, 1) == {"statId": "$s1.items.0.stationId"}


READER_CHAIN = ["place_name", "geo", "judge"]


def fake_reader(monkeypatch, outputs):
    """장소 이름 -> 좌표와 목록을 내놓는 도구(geo) -> 좌표 칸 둘을 읽는 도구(judge).

    outputs 는 geo 의 tool.outputs. None 이면 칸을 안 둔다.
    """
    geo = {"id": "s/geo", "parameters": {"query": "place_name"}}
    if outputs is not None:
        geo["outputs"] = outputs
    fake(
        monkeypatch,
        READER_CHAIN,
        tools={"geo": geo, "judge": {"id": "s/judge", "parameters": {"lon": "point.lon", "lat": "point.lat"}}},
        inputs={"geo": ["place_name"], "judge": ["point"]},
        outputs={"geo": ["point", "item_list"], "judge": ["item_detail"]},
        sources={"place_name": SPOKEN},
    )


# 알아볼 수 없는 읽는 법은 전부 터진다. 각 줄이 막는 고장을 옆에 적었다.
UNTRUSTWORTHY_OUTPUTS = [
    # 내놓지 않는 타입의 읽는 법은 누구도 안 읽는다. 거짓 선언이 남는다.
    pytest.param({"admin_code": {"value": "code"}}, "hasOutput", id="not_a_has_output"),
    # 값 하나인지 칸이 있는 값인지 안 갈린다.
    pytest.param({"point": {"value": "location", "fields": {"lon": "location.0"}}}, "value 와 fields", id="value_and_fields"),
    pytest.param({"point": {"list": "items", "pick": "first"}}, "value 와 fields", id="neither_value_nor_fields"),
    # 목록에서 무엇을 고를지 안 적으면 어느 항목의 칸인지 모른다.
    pytest.param({"point": {"list": "items", "fields": {"lon": "lon", "lat": "lat"}}}, "pick", id="list_without_pick"),
    pytest.param({"point": {"list": "items", "pick": "best", "fields": {"lon": "lon", "lat": "lat"}}}, "pick", id="unknown_pick"),
    # 따옴표 없이 적은 경로는 수가 된다.
    pytest.param({"point": {"fields": {"lon": 0.0, "lat": "location.1"}}}, "경로", id="number_as_path"),
]


@pytest.mark.parametrize("outputs, fragment", UNTRUSTWORTHY_OUTPUTS)
def test_an_output_reading_that_cannot_be_trusted_raises(monkeypatch, outputs, fragment):
    """믿을 수 없는 tool.outputs 는 조용히 넘기지 않고 터진다."""
    fake_reader(monkeypatch, outputs)

    with pytest.raises(ValueError, match=fragment):
        step_service.binding_of("geo")


UNTRUSTWORTHY_SOURCES = [
    # 발화 인자는 칸이 없는 값 하나다.
    pytest.param({"from": "spoken.argument", "fields": {"lon": "lon"}}, "화면 값에만", id="fields_on_the_utterance"),
    pytest.param({"from": "context.view.bbox", "fields": {"minLon": 0.0}}, "경로", id="number_as_path"),
    # 오타 난 fields 는 칸 없는 값으로 읽혀 그 source 의 자리가 소리 없이 unwired 가 된다.
    pytest.param({"from": "context.selectedLocation", "feilds": {"lon": "lon"}}, "feilds", id="unknown_field"),
]


@pytest.mark.parametrize("source, fragment", UNTRUSTWORTHY_SOURCES)
def test_a_source_reading_that_cannot_be_trusted_raises(monkeypatch, source, fragment):
    """믿을 수 없는 source.fields 는 조용히 넘기지 않고 터진다."""
    fake(monkeypatch, ["start", "n"], tools={}, inputs={}, sources={"start": source})

    with pytest.raises(ValueError, match=fragment):
        step_service._source_of("start")


@pytest.mark.parametrize(
    "outputs",
    [{"point": {"fields": {"lon": "location.0"}}}, None],
    ids=["one_field_missing", "no_reading_at_all"],
)
def test_a_field_the_producer_does_not_declare_is_not_guessed_from_its_name(monkeypatch, outputs):
    """point.lat 의 경로가 안 적혀 있으면 $s1.lat 으로 짐작하지 않는다. 그 자리는 unwired 다.

    칸 이름을 raw 경로로 쓰면 응답에 우연히 같은 이름이 있을 때만 맞고, 없으면 오류가
    아니라 빈 값이 조용히 실려 나간다. check_bindings 가 어느 짝에서 빠졌는지 적는다.
    """
    fake_reader(monkeypatch, outputs)

    assert step_service.unwired_in(READER_CHAIN) == ["judge"]
    assert step_service.plan("recipe_x", "오송역")["nodes"] == ["geo"]
    assert any("geo" in problem and "judge" in problem for problem in step_service.check_bindings())


def test_a_type_nobody_reads_needs_no_reading(monkeypatch):
    """geo 는 목록도 내놓지만 아무도 목록을 안 읽는다. 그 읽는 법까지 적으라고 하지 않는다."""
    fake_reader(monkeypatch, {"point": {"fields": {"lon": "location.0", "lat": "location.1"}}})

    assert step_service.check_bindings() == []
    assert step_service.unwired_in(READER_CHAIN) == []
    assert step_service.plan("recipe_x", "오송역")["steps"][1]["input"] == {
        "lon": "$s1.location.0",
        "lat": "$s1.location.1",
    }


# ── 화면이 함께 보낸 값 ─────────────────────────────────────────────
#
# **여기서 채우지 않는다.** 참조를 그대로 넘기고 vendor 가 제자리에서 푼다.


def test_starting_from_the_visible_extent_the_first_step_takes_the_context_bbox():
    """KRRI_ASAP 의 current-view-cctv 가 $context.view.bbox 네 칸을 넣는 자리다.

    화면의 bbox 는 [[minLon, minLat], [maxLon, maxLat]] 두 겹이다. 칸마다 그 안의 번호를
    지도 범위의 source.fields 가 적는다. minLon 은 $context.view.bbox.0.0 이다.
    """
    plan = step_service.plan(recipe_of(["map_extent", "find_cctv"]), "")
    sent = plan["steps"][0]["input"]

    assert plan["steps"][0]["tool"] == "road.getCctv"
    assert sent == {
        "minLon": "$context.view.bbox.0.0",
        "minLat": "$context.view.bbox.0.1",
        "maxLon": "$context.view.bbox.1.0",
        "maxLat": "$context.view.bbox.1.1",
    }
    assert resolve(sent, {"context": SCREEN}) == {"minLon": 127.20, "minLat": 36.55, "maxLon": 127.40, "maxLat": 36.70}


def test_the_picked_point_is_read_by_the_fields_its_source_declares():
    """찍은 점은 {lon, lat} 이다. 우클릭 전에는 null 이라 칸이 빈다.

    null 인 요청은 실행이 먼저 막는다(context_starts). 여기서 좌표를 채우지 않는다.
    """
    sent = step_input(["point", "find_admin_boundary_by_point"], 0, "")

    assert sent == {"lon": "$context.selectedLocation.lon", "lat": "$context.selectedLocation.lat", "layer": "sigungu"}
    assert resolve(sent, {"context": SCREEN}) == {"lon": 127.2974, "lat": 36.6199, "layer": "sigungu"}
    assert resolve(sent, {"context": {**SCREEN, "selectedLocation": None}}) == {"lon": None, "lat": None, "layer": "sigungu"}


def test_charging_stations_starting_from_the_visible_extent_also_take_the_flat_four():
    """ev.searchStations 에는 bbox 라는 칸이 없다 — 없는 칸이라 버려져서
    지도를 아무리 좁혀도 전국에서 상한 500건이 왔다(실측).
    CCTV 와 같은 꼴이어야 하고 키워드 칸은 안 나가야 한다."""
    plan = step_service.plan(
        recipe_of(["map_extent", "search_ev_stations", "get_ev_station"]), ""
    )

    assert plan["steps"][0]["tool"] == "ev.searchStations"
    assert plan["steps"][0]["input"] == {
        "minLon": "$context.view.bbox.0.0",
        "minLat": "$context.view.bbox.0.1",
        "maxLon": "$context.view.bbox.1.0",
        "maxLat": "$context.view.bbox.1.1",
    }


def test_a_tool_taking_a_bbox_array_takes_one_bbox_field_in_the_first_step_too():
    """같이 고치면 오히려 깨지는 자리다. geo.getRailwayLines 의 bbox 는
    진짜로 네 수짜리 배열 칸이다(inputSchema 실측)."""
    plan = step_service.plan(recipe_of(["map_extent", "get_railway_lines"]), "")

    assert plan["steps"][0]["tool"] == "geo.getRailwayLines"
    assert plan["steps"][0]["input"] == {
        "bbox": [
            "$context.view.bbox.0.0",
            "$context.view.bbox.0.1",
            "$context.view.bbox.1.0",
            "$context.view.bbox.1.1",
        ]
    }


def test_an_empty_context_field_does_not_count_that_start_data():
    """KRRI_ASAP 은 우클릭 전에 selectedLocation 을 null 로 보낸다. 빈 bbox 도 마찬가지."""
    full = {
        "view": {"bbox": [[127.20, 36.55], [127.40, 36.70]]},
        "selectedLocation": {"lon": 127.2974, "lat": 36.6199},
    }

    assert step_service.context_starts(full) == ["point", "map_extent"]
    assert step_service.context_starts({**full, "selectedLocation": None}) == ["map_extent"]
    assert step_service.context_starts({"view": {"bbox": []}}) == []
    assert step_service.context_starts({}) == []
    assert step_service.context_starts(None) == []


# ── builtin 계산 — 지점을 범위로 넓힌다 ─────────────────────────────


def test_the_point_is_widened_by_the_next_step_not_called_on_its_own():
    """builtin 노드는 step 이 안 된다. 그 입력과 어댑터가 바로 뒤 도구 단계에 얹힌다.

    vendor 는 builtin 계산을 따로 부를 수 없고, 반경 계산은 vendor 의
    point_radius_to_bbox 가 갖고 있다. 결과로 Gateway 에 나가는 bbox 넷은 옮기기
    전의 배선과 같다 — KRRI_ASAP 의 cctv-around-point 와 같은 꼴이다.

    중심은 지점 좌표의 lon · lat 두 칸을 목록으로 넘긴다. 통째로 넘기면 어댑터가
    화면의 {lon, lat} 과 geocode 의 location 배열을 짐작해 가려야 한다.
    """
    picked = step_service.plan(recipe_of(["point", "point_to_map_extent", "find_cctv"]), "")
    spoken = step_service.plan(
        recipe_of(["place_name", "geocode_place", "point_to_map_extent", "search_ev_stations", "get_ev_station"]),
        "오송역",
    )

    assert picked["nodes"] == ["find_cctv"]
    assert picked["steps"][0]["input"] == {
        "center": ["$context.selectedLocation.lon", "$context.selectedLocation.lat"],
        "radiusMeters": 15000,
    }
    assert picked["steps"][0]["inputAdapter"] == step_service.POINT_RADIUS_TO_BBOX

    assert spoken["nodes"] == ["geocode_place", "search_ev_stations", "get_ev_station"]
    assert spoken["steps"][1]["input"] == {"center": ["$s1.location.0", "$s1.location.1"], "radiusMeters": 15000}
    assert spoken["steps"][1]["inputAdapter"] == step_service.POINT_RADIUS_TO_BBOX
    assert spoken["steps"][2]["input"] == {"statId": "$s2.items.0.stationId"}

    # 어댑터가 받는 중심은 화면에서 왔든 장소에서 왔든 [경도, 위도] 다.
    assert resolve(picked["steps"][0]["input"], {"context": SCREEN})["center"] == [127.2974, 36.6199]
    assert resolve(spoken["steps"][1]["input"], {"s1": GEOCODE_FOUND})["center"] == GEOCODE_FOUND["location"]


def test_a_tool_that_takes_the_extent_in_another_shape_is_not_wired_behind_the_builtin():
    """어댑터가 만드는 것은 평평한 네 칸이다. bbox 배열 한 칸으로 받는 도구 뒤에는 못 잇는다.

    이어 두면 그 네 칸이 모르는 칸이라 버려지고 도구가 범위 없이 돈다 — 오류가 아니라
    전국 결과가 온다. 그래서 실행 수단이 없는 자리로 세어 부르지 않는다. 같은 도구도
    화면 범위 뒤에서는 bbox 배열로 잘 불린다.
    """
    behind_builtin = ["point", "point_to_map_extent", "search_admin_boundaries"]

    assert step_service.unwired_in(behind_builtin) == ["search_admin_boundaries"]
    assert step_service.unwired_in(["map_extent", "search_admin_boundaries"]) == []
    assert step_service.unwired_in(["point", "point_to_map_extent", "find_cctv"]) == []


def test_with_no_center_left_the_adapter_is_not_carried(monkeypatch):
    """걸 중심 좌표가 없는데 어댑터를 걸면 vendor 가 ValueError 를 올린다.

    값을 지어내는 것보다 안 보내는 것이 낫다. 앞 단계가 없으면 좌표 칸이 빠지고
    어댑터도 함께 빠진다.
    """
    fake(
        monkeypatch,
        ["start", "widen", "lonely"],
        tools={
            "widen": {"id": "builtin/geo.pointRadiusToBbox", "parameters": {"center": ["point.lon", "point.lat"], "radiusMeters": 15000}},
            "lonely": {"id": "s/lonely", "parameters": {"minLon": "map_extent.minLon"}},
        },
        inputs={"widen": ["point"], "lonely": ["map_extent"]},
        outputs={"start": ["point"], "widen": ["map_extent"], "lonely": ["item_list"]},
    )

    plan = step_service.plan("recipe_x", "오송역")

    assert plan["steps"][0]["input"] == {"radiusMeters": 15000}
    assert "inputAdapter" not in plan["steps"][0]


# ── 부르는 순간 ─────────────────────────────────────────────────────


ROUTE_CHAIN = ["place_name", "geocode_place", "plan_trip"]


def test_the_date_and_time_are_taken_when_the_call_is_made():
    """고정된 날짜를 박으면 그날이 지나는 순간 거짓이 됨.

    도구 설명이 KST 를 명시로 요구한다 — "서버 로케일이나 UTC 기준으로 넣으면
    자정 근처에서 하루가 어긋날 수 있다".
    """
    sent = step_service.plan(recipe_of(ROUTE_CHAIN), "조치원역")["steps"][-1]["input"]
    now = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Seoul"))

    assert sent["date"] == now.strftime("%Y-%m-%d")
    assert len(sent["time_kst"]) == 5 and sent["time_kst"][2] == ":"


def test_the_runtime_marker_is_resolved_before_the_vendor_sees_it():
    """부르는 순간은 vendor scope 에 없는 이름임. 우리가 값으로 바꿔 내보내야 함.

    안 바꾸면 vendor 의 _resolve_reference 가 None 을 돌려주고 required 가
    빈 채로 나감.
    """
    sent = step_service.plan(recipe_of(ROUTE_CHAIN), "조치원역")["steps"][-1]["input"]

    assert not any(str(value).startswith("runtime.") for value in sent.values())


def test_an_unknown_runtime_field_is_not_passed_through_silently():
    """모르는 이름을 그대로 두면 그 문자열이 도구에 실려 나감."""
    with pytest.raises(ValueError):
        step_service._now_field("runtime.now.datetime", PROBE_NOW)


def test_the_origin_comes_from_the_screen_and_the_destination_from_the_utterance():
    """뒤바뀌면 반대 방향 길이 나오고 도구는 아무 오류도 안 냄.

    출발지는 사람이 화면에서 찍은 자리이고 도착지는 말한 장소를 좌표로 바꾼 것이다.
    둘 다 「지점 좌표」라 타입으로는 안 갈리므로 이 시험이 그 자리를 지킴.
    도착은 앞 단계를 만든 노드(장소 좌표 변환)의 outputs 로 읽고, 출발은 화면 값의 칸을
    곧장 가리킴. 두 좌표를 서로 다르게 두고 풀어 봐야 섞였는지 보임.
    """
    plan = step_service.plan(recipe_of(ROUTE_CHAIN), "조치원역")
    sent = plan["steps"][-1]["input"]
    resolved = resolve(sent, {"context": SCREEN, "s1": GEOCODE_FOUND})

    assert plan["nodes"][-1] == "plan_trip"
    assert sent["from_lat"] == "$context.selectedLocation.lat"
    assert sent["from_lon"] == "$context.selectedLocation.lon"
    assert sent["to_lat"] == "$s1.location.1"
    assert sent["to_lon"] == "$s1.location.0"
    assert (resolved["from_lon"], resolved["from_lat"]) == (127.2974, 36.6199)
    assert (resolved["to_lon"], resolved["to_lat"]) == (127.3276666158151, 36.61995281117007)


# ── 발화에서 온 이름 있는 값 ────────────────────────────────────────


ISOCHRONE_CHAIN = ["place_name", "geocode_place", "compute_isochrone"]


def isochrone_input(options=None):
    return step_service.plan(recipe_of(ISOCHRONE_CHAIN), "의왕역", options)["steps"][-1]["input"]


def test_the_previous_coordinates_are_split_into_the_origin_fields():
    """칸 이름이 lon · lat 이 아니라 origin_lon · origin_lat 인 자리.

    분과 이동수단도 명시로 보낸다 — 도구 기본값(30 · WALK)에 기대면 무엇으로
    계산한 답인지가 온톨로지에 안 남고, 그 값이 바뀌어도 우리 쪽에 신호가 없다.
    """
    assert isochrone_input() == {
        "origin_lon": "$s1.location.0",
        "origin_lat": "$s1.location.1",
        "cutoffs_minutes": [30],
        "mode": "TRANSIT",
    }


def test_the_spoken_mode_and_minutes_reach_the_tool():
    """사람이 말한 이동수단과 시간이 실제 호출 인자가 되는 자리.

    사람은 「도보」라고 말하고 도구는 WALK 를 받는다. 그 대응이 tool 에 있어야
    발화 해석 프롬프트에 도구가 쓰는 말이 안 샌다.
    """
    sent = isochrone_input({"travel_mode": "도보", "minutes": [20]})

    assert sent["mode"] == "WALK"
    assert sent["cutoffs_minutes"] == [20]


def test_several_spoken_minutes_go_into_one_field():
    """겹을 여러 개 말해도 칸이 갈라지지 않는 자리.

    cutoffs_minutes 는 목록을 받으므로 한 겹과 여러 겹이 같은 칸으로 간다.
    한 겹을 max_minutes 로 보내던 것과 답이 같다(2026-09-08 실측).
    """
    assert isochrone_input({"minutes": [15, 30, 60]})["cutoffs_minutes"] == [15, 30, 60]


def test_a_value_the_tool_does_not_know_falls_back_to_the_default():
    """응답 schema 의 enum 이 이미 막지만 그것이 유일한 자물쇠면 provider 를
    갈 때 조용히 샌다. 모르는 말은 기본값으로 간다.
    """
    assert isochrone_input({"travel_mode": "비행기"})["mode"] == "TRANSIT"


AGE_CHAIN = ["place_name", "geocode_place", "find_admin_boundary_by_point", "get_age_profile"]


def age_inputs(options=None):
    return [step["input"] for step in step_service.plan(recipe_of(AGE_CHAIN), "충청북도", options)["steps"]]


def test_the_spoken_administrative_level_becomes_the_layer_of_the_lookup():
    """층위를 앞 단계에 물어보는 자리. 응답의 몇째 칸을 세지 않는다.

    layer 를 안 보내면 시도 · 시군구 · 읍면동 세 칸이 함께 오고, 그때 뒤
    단계가 몇째를 쓸지 골라야 했다. 그 셈이 시군구에 박혀 있어 「충청북도
    연령대별 인구」가 청주시 상당구를 답했다.
    """
    said = age_inputs({"admin_level": "시도"})
    assert said[1]["layer"] == "sido"
    assert said[2] == {"level": "$s2.items.0.layerId", "code": "$s2.items.0.code"}


def test_the_level_the_utterance_did_not_say_stays_at_the_district():
    """층위를 안 말한 발화가 여태 나오던 값 그대로 가는지."""
    assert age_inputs()[1]["layer"] == "sigungu"


# ── 지도 명령 — 부를 도구가 없는 노드 ───────────────────────────────


def test_a_node_without_a_gateway_tool_becomes_a_map_command_not_a_step():
    """tool 이 「노드 -> 서버 · 도구」가 아니라 「노드 -> 실행 수단」이다.

    frontend 노드는 지도 명령이 되고 vendor 에 넘길 step 이 안 된다.
    vendor 에 빈 steps 를 넘기면 실패로 보므로 step 이 되어서도 안 된다.
    """
    binding = step_service.binding_of("show_facility")
    plan = step_service.plan(recipe_of(["place_name", "show_facility"]), "오송 테스트트랙")

    assert binding["kind"] == step_service.COMMAND
    assert plan["steps"] == []
    assert plan["command_nodes"] == ["show_facility"]
    assert plan["commands"][0]["op"] == binding["command"]
    assert plan["commands"][0]["args"]["facilityName"] == "오송 테스트트랙"
    assert plan["headline"]


def test_a_map_command_node_is_not_counted_as_unwired():
    """도구가 없는 것과 실행 수단이 없는 것은 다름. tool 이 있으면 붙은 것임."""
    assert step_service.unwired(recipe_of(["place_name", "show_facility"])) == []


# ── 이 recipe 를 지금 부를 수 있는가 ────────────────────────────────


def test_a_recipe_that_reads_only_the_context_does_not_need_an_argument():
    """"지금 보이는 곳 CCTV 보여줘" 에는 뽑을 말이 없다. 조회할 곳은 문맥이 말했다.

    판정 근거는 실행 계획이다 — 그 recipe 의 계획에 발화 인자가 남는지를 본다.
    recipe id 로 가르지 않는다.
    """
    assert not step_service.spoken_needed(recipe_of(["point", "point_to_map_extent", "find_cctv"]))
    assert not step_service.spoken_needed(
        recipe_of(["map_extent", "search_ev_stations", "get_ev_station"])
    )
    assert step_service.spoken_needed(
        recipe_of(["place_name", "geocode_place", "point_to_map_extent", "find_cctv"])
    )


def test_a_recipe_that_mixes_the_context_and_the_utterance_still_needs_the_argument():
    """경로 탐색은 출발지를 문맥에서, 도착지를 발화에서 받는다.

    ★ 문맥이 있다고 인자 없이 부르면 도착지가 빈 채로 도구가 나간다.
    """
    route = recipe_of(ROUTE_CHAIN)

    assert step_service.context_needs(route) == {"point"}
    assert step_service.spoken_needed(route)


def test_context_needs_looks_past_the_first_step():
    """경로의 첫 칸은 장소 이름이라 「첫 칸이 화면 데이터인가」로는 못 센다.

    세는 것은 계획이 실제로 읽는 문맥이다. 지점 좌표는 화면에서도 오고 장소 좌표
    변환에서도 오므로, 타입만 보고 세면 말한 장소 경로가 찍은 지점을 요구하게 된다.
    """
    spoken_only = recipe_of(["place_name", "geocode_place", "point_to_map_extent", "find_cctv"])

    assert step_service.context_needs(spoken_only) == set()
    assert step_service.context_needs(recipe_of(["map_extent", "find_cctv"])) == {"map_extent"}
    assert step_service.context_needs(
        recipe_of(["point", "point_to_map_extent", "find_cctv"])
    ) == {"point"}


def test_unwired_names_the_executable_nodes_with_no_tool(monkeypatch):
    """실행 수단이 없는 실행 노드를 경로 순서로 셈. 시작 노드는 안 셈.

    부르는 쪽(execute_service.run)이 비어 있지 않으면 도구를 하나도 안 부른다.
    """
    fake(
        monkeypatch,
        ["start", "없는노드"],
        tools={},
        inputs={"없는노드": ["start"]},
        outputs={"없는노드": ["item_list"]},
    )

    assert step_service.unwired("recipe_x") == ["없는노드"]
