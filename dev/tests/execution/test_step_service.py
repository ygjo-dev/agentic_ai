"""대상 : execution/step_service.py — recipe 를 실행 계획으로 바꾼다

배선표(wiring.yaml)를 읽어 노드마다 무엇을 부르고 input 을 어떻게 채울지 정한다.
여기서 보는 것은 그 규칙이지 배선표에 적힌 값이 맞느냐가 아니다 —
그것은 test_wiring_contract.py 가 본다.

input 에 들어가는 표시가 넷이고 값이 어디서 오는지가 그 넷을 가른다.

    @arg       발화에서 온 값
    $prev      앞 단계가 내놓은 값
    $context   화면이 함께 보낸 값. **여기서 안 채운다** — vendor 가 제자리에서 푼다
    $now       부르는 순간의 날짜 · 시각

LLM 도 Gateway 도 부르지 않는다. 온톨로지와 배선표만 읽는다.
"""

import datetime
import zoneinfo

import pytest

import paths
from execution import step_service
from ontology import graph

ARG = step_service.SPOKEN_VALUE

# 가짜 노드 사이에 흐르는 타입 하나. 온톨로지의 어느 타입도 아니다 —
# 배선 줄을 고르는 데만 쓰이므로 이름은 아무래도 좋다.
FAKE_TYPE = "가짜형식"


def recipe_of(chain):
    """그 사슬을 가진 recipe id. **번호를 박지 않으려고 찾아서 쓴다** —
    노드가 늘면 번호가 밀린다."""
    for recipe_id in graph.recipe_ids():
        nodes = [entry["node_id"] for entry in graph.path_of(recipe_id)]
        if nodes == list(chain):
            return recipe_id
    raise AssertionError(f"그런 사슬의 recipe 가 없다: {chain}")


def wire(monkeypatch, node_ids, rows=None, handed=None, tools=None):
    """가짜 경로를 plan 에 연결.

    node_ids  경로. **데이터 노드부터 적는다** — 첫 실행 노드의 배선 줄을
              고르는 것이 그 앞 칸이다
    rows      {(노드, 받는 타입): 배선}. STEP_OF 에 없는 자리를 얹을 때 씀
    handed    {노드: [건네는 타입, ...]}. 안 적은 노드는 온톨로지를 그대로 봄
    tools     {노드: {server_id, tool, headline}}. TOOL_OF 에 없는 노드용
    """
    monkeypatch.setattr(
        step_service.graph,
        "path_of",
        lambda recipe_id: [{"node_id": node_id} for node_id in node_ids],
    )
    if handed:
        real = step_service.graph.handed_types
        monkeypatch.setattr(
            step_service.graph,
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


# ── 배선표를 읽는다 ─────────────────────────────────────────────────
#
# **「계기판이 조용히 죽는다」가 세 번 났다.** 파일이 없거나 깨졌을 때 빈 표로
# 도는 대신 터지는지를 본다. 계기판이 TOOL_OF · STEP_OF 를 import 해서 곧장
# 읽으므로 빈 표는 「배선 0줄」이라는 멀쩡해 보이는 출력이 된다.


@pytest.fixture
def restore_tables():
    """가짜 파일을 물린 시험이 진짜 표를 두고 가지 않게.

    표는 모듈 하나에 하나뿐이고, 갈아 끼우지 않고 비웠다 채우는 방식이라
    시험이 얹은 것도 그대로 남음. monkeypatch 가 되돌리는 것은
    paths.WIRING_PATH 뿐임.
    """
    tool_of = dict(step_service.TOOL_OF)
    step_of = dict(step_service.STEP_OF)
    mtime = step_service._wiring_mtime
    yield
    step_service.TOOL_OF.clear()
    step_service.TOOL_OF.update(tool_of)
    step_service.STEP_OF.clear()
    step_service.STEP_OF.update(step_of)
    step_service._wiring_mtime = mtime


def test_arg_field_is_a_pair_not_a_list():
    """arg_field 는 짝이다.

    YAML 은 목록으로만 적을 수 있어 로더가 튜플로 바꾼다. 목록으로 남으면
    _by_argument 는 그대로 돌지만 짝으로 푸는 자리가 조용히 어긋난다.
    """
    wiring = step_service.STEP_OF[("get_railway_lines", "place_name")]
    assert wiring["arg_field"] == (step_service.RAILWAY_LINE_SUFFIX, "railwayName")
    assert isinstance(wiring["arg_field"], tuple)


def test_names_in_yaml_become_values_from_code():
    """<이름> 이 코드의 값으로 바뀐다.

    값의 원천은 코드에 남겼다. POINT_RADIUS_TO_BBOX 는 vendor 어댑터의 이름이라
    YAML 에 값을 옮기면 원천이 둘이 된다.
    """
    wiring = step_service.STEP_OF[("search_ev_stations", "map_extent")]
    assert wiring["input"]["radiusMeters"] == step_service.RADIUS_METERS
    assert wiring["adapter"] == step_service.POINT_RADIUS_TO_BBOX


def test_unknown_name_raises(tmp_path, monkeypatch, restore_tables):
    """모르는 이름은 조용히 안 넘어간다.

    그대로 두면 "<RADIUS_METRES>" 라는 문자열이 도구에 실려 나가고, 0건이
    오지 오류가 오지 않는다.
    """
    path = tmp_path / "wiring.yaml"
    path.write_text(
        "tool_of: {}\n"
        "step_of:\n"
        "  find_cctv:\n"
        "    point:\n"
        '      input: {radiusMeters: "<RADIUS_METRES>"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "WIRING_PATH", path)

    with pytest.raises(ValueError, match="RADIUS_METRES"):
        step_service._load_wiring()


def test_unknown_wiring_field_raises(tmp_path, monkeypatch, restore_tables):
    """모르는 칸 이름도 터진다.

    input_frist 같은 오타가 넘어가면 화면 문맥에서 시작하는 자리가 소리 없이
    사라진다.
    """
    path = tmp_path / "wiring.yaml"
    path.write_text(
        "tool_of: {}\n"
        "step_of:\n"
        "  find_cctv:\n"
        "    point:\n"
        "      input: {lon: 1}\n"
        "      input_frist: {lon: 2}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "WIRING_PATH", path)

    with pytest.raises(ValueError, match="input_frist"):
        step_service._load_wiring()


def test_missing_file_raises(tmp_path, monkeypatch, restore_tables):
    """파일이 없으면 빈 표로 돌지 않고 터진다."""
    monkeypatch.setattr(paths, "WIRING_PATH", tmp_path / "없다.yaml")

    with pytest.raises(FileNotFoundError):
        step_service._load_wiring()


def test_broken_yaml_raises(tmp_path, monkeypatch, restore_tables):
    """문법이 깨져도 터진다."""
    path = tmp_path / "wiring.yaml"
    path.write_text("tool_of: {\n  깨진다\n", encoding="utf-8")
    monkeypatch.setattr(paths, "WIRING_PATH", path)

    with pytest.raises(Exception):
        step_service._load_wiring()


def test_unknown_section_raises(tmp_path, monkeypatch, restore_tables):
    """모르는 절도 터진다. 오타 난 절은 조용히 빈 표가 된다."""
    path = tmp_path / "wiring.yaml"
    path.write_text("tool_of: {}\nstep_of: {}\ntool_off: {}\n", encoding="utf-8")
    monkeypatch.setattr(paths, "WIRING_PATH", path)

    with pytest.raises(ValueError, match="tool_off"):
        step_service._load_wiring()


def test_a_broken_file_does_not_empty_the_tables(tmp_path, monkeypatch, restore_tables):
    """터져도 반만 바뀐 표가 남지 않는다.

    두 표를 다 만든 뒤에 갈아 넣는다. 빈 표보다 반쪽 표가 나쁘다 — 계기판이
    「배선 3줄」처럼 멀쩡한 모양으로 틀린 수를 찍는다.
    """
    before_tool = dict(step_service.TOOL_OF)
    before_step = dict(step_service.STEP_OF)

    path = tmp_path / "wiring.yaml"
    path.write_text("tool_of: {}\nstep_of: {깨진다\n", encoding="utf-8")
    monkeypatch.setattr(paths, "WIRING_PATH", path)

    with pytest.raises(Exception):
        step_service._load_wiring()

    assert step_service.TOOL_OF == before_tool
    assert step_service.STEP_OF == before_step


def test_reload_reads_again_when_mtime_changes(tmp_path, monkeypatch, restore_tables):
    """mtime 이 바뀌면 다시 읽는다. 안 바뀌면 안 읽는다.

    등록 화면이 wiring.yaml 을 쓰면 서버를 안 내리고 반영되어야 한다.
    """
    path = tmp_path / "wiring.yaml"
    path.write_text(
        "tool_of:\n"
        "  n:\n"
        "    server_id: s\n"
        "    tool: t\n"
        "    headline: 하나\n"
        "step_of:\n"
        "  n:\n"
        "    k:\n"
        "      input: {query: '@arg'}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "WIRING_PATH", path)
    monkeypatch.setattr(step_service, "_wiring_mtime", None)

    step_service.reload_wiring()
    assert step_service.TOOL_OF["n"]["headline"] == "하나"

    # 파일을 안 건드리면 다시 안 판다. 손으로 얹은 줄이 살아 있으면 안 판 것이다.
    step_service.TOOL_OF["표시"] = "안 판다"
    step_service.reload_wiring()
    assert "표시" in step_service.TOOL_OF

    stat = path.stat()
    path.write_text(
        "tool_of:\n"
        "  n:\n"
        "    server_id: s\n"
        "    tool: t\n"
        "    headline: 둘\n"
        "step_of:\n"
        "  n:\n"
        "    k:\n"
        "      input: {query: '@arg'}\n",
        encoding="utf-8",
    )
    if path.stat().st_mtime_ns == stat.st_mtime_ns:  # 시계가 굵은 파일시스템
        import os

        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    step_service.reload_wiring()
    assert step_service.TOOL_OF["n"]["headline"] == "둘"
    assert "표시" not in step_service.TOOL_OF


# ── 어느 줄을 쓰는가 — wiring_at · input_of ─────────────────────────


def test_the_wiring_row_is_chosen_by_what_the_previous_node_hands_over():
    """앞 노드가 건네는 타입이 줄을 고른다. 노드 이름만으로는 안 갈린다.

    같은 노드가 두 자리에 온다 — 전기차 충전소 검색은 말한 키워드 뒤(keyword)
    에도 오고 장소 좌표 변환 뒤(map_extent)에도 온다.
    """
    by_keyword = step_service.wiring_at("search_ev_stations", "spoken_keyword")
    by_point = step_service.wiring_at("search_ev_stations", "geocode_place")

    assert by_keyword is not None and by_point is not None
    assert by_keyword is not by_point, "받는 타입이 다른데 같은 줄을 골랐다"


def test_no_matching_row_is_none_not_an_error():
    """맞는 줄이 없으면 None. 여기서 터지면 unwired 가 셀 것이 없어진다."""
    assert step_service.wiring_at("find_cctv", "spoken_keyword") is None


def test_input_first_is_used_only_in_the_first_slot():
    """첫 MCP 실행에서만 input_first 를 쓴다. 뒤에서는 input 그대로.

    같은 타입을 앞 단계에서 받을 수도 화면 문맥에서 받을 수도 있는 자리를
    위한 것이다.
    """
    wiring = step_service.STEP_OF[("search_ev_stations", "map_extent")]

    assert "input_first" in wiring, "이 줄이 두 벌을 가져야 이 시험이 뜻이 있다"
    assert step_service.input_of(wiring, first=True) == wiring["input_first"]
    assert step_service.input_of(wiring, first=False) == wiring["input"]


def test_a_row_without_input_first_uses_input_in_both_slots():
    """한 벌뿐인 줄은 자리와 상관없이 같은 것을 쓴다."""
    wiring = {"input": {"query": ARG}}

    assert step_service.input_of(wiring, first=True) == {"query": ARG}
    assert step_service.input_of(wiring, first=False) == {"query": ARG}


# ── @arg — 발화에서 온 값 ───────────────────────────────────────────


def test_a_value_from_the_utterance_goes_into_the_arg_slot(monkeypatch):
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


# ── 값을 보고 칸을 고르는 줄 (arg_field) ────────────────────────────
#
# 배선표에 값 판단이 들어온 유일한 자리다. 자가 좁은 것 자체가 요구사항이라
# 걸리는 값과 안 걸리는 값을 함께 본다.
#
# ★ 이 heuristic 을 언제 걷어낼지는 아직 정해지지 않았다.


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
    """도구가 두 절을 AND 로 이어서 둘 다 보내면 같은 값일 때 0건임."""
    wire(monkeypatch, ["spoken_place", "get_railway_lines"])

    for argument in ("경부선", "오송역"):
        sent = step_service.plan("recipe_003", argument)["steps"][0]["input"]
        assert len(sent) == 1


def test_a_wiring_line_without_arg_field_is_unchanged(monkeypatch):
    """그 칸을 적은 줄은 하나뿐임. 나머지 줄이 안 흔들려야 함."""
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


# ── 답 첫 줄 ────────────────────────────────────────────────────────


def test_the_arg_in_the_headline_is_substituted_too(monkeypatch):
    """답 첫 줄에 그 값이 그대로 보임. 치환이 빠지면 화면에 {arg} 가 뜸."""
    wire(monkeypatch, ["spoken_place", "geocode_place", "find_cctv"])

    plan = step_service.plan("recipe_025", "오송역")

    assert plan["headline"] == "오송역 CCTV 를 조회했습니다."


def test_the_argument_is_not_prefixed_when_it_is_already_in_the_preamble(monkeypatch):
    """"전기차 충전소 데이터 검색해줘" 가 "전기차 충전소 전기차 충전소를 조회했습니다."

    틀이 "{arg} 전기차 충전소를 조회했습니다." 이고 인자도 "전기차 충전소" 라
    같은 말이 두 번 나갔음(실측).
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


# ── $prev — 앞 단계가 없을 때 ───────────────────────────────────────
#
# 같은 노드가 두 자리에 쓰이므로 $prev 칸이 첫 step 에 놓이는 자리가 생길 수
# 있다. 그때 "빼고 부른다" 는 사람이 정한 규칙이고 아래 넷이 그것을 본다.


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


# ── $context — 화면이 함께 보낸 값 ──────────────────────────────────
#
# **여기서 채우지 않는다.** 표시를 그대로 넘기고 vendor 가 제자리에서 푼다.


def test_starting_from_the_visible_extent_the_first_step_takes_the_context_bbox():
    """KRRI_ASAP 의 current-view-cctv 가 $context.view.bbox 네 칸을 넣는 자리다."""
    plan = step_service.plan(recipe_of(["visible_extent", "find_cctv"]), "")

    assert plan["steps"][0]["tool"] == "road.getCctv"
    assert plan["steps"][0]["input"] == {
        "minLon": "$context.view.minLon",
        "minLat": "$context.view.minLat",
        "maxLon": "$context.view.maxLon",
        "maxLat": "$context.view.maxLat",
    }


def test_charging_stations_starting_from_the_visible_extent_also_take_the_flat_four():
    """ev.searchStations 에는 bbox 라는 칸이 없다 — 없는 칸이라 버려져서
    지도를 아무리 좁혀도 전국에서 상한 500건이 왔다(실측).
    CCTV 줄과 같은 꼴이어야 한다."""
    plan = step_service.plan(
        recipe_of(["visible_extent", "search_ev_stations", "get_ev_station"]), ""
    )

    assert plan["steps"][0]["tool"] == "ev.searchStations"
    assert plan["steps"][0]["input"] == {
        "minLon": "$context.view.minLon",
        "minLat": "$context.view.minLat",
        "maxLon": "$context.view.maxLon",
        "maxLat": "$context.view.maxLat",
    }


def test_a_tool_taking_a_bbox_array_takes_one_bbox_field_in_the_first_step_too():
    """같이 고치면 오히려 깨지는 자리다. geo.getRailwayLines 의 bbox 는
    진짜로 네 수짜리 배열 칸이다(inputSchema 실측)."""
    plan = step_service.plan(recipe_of(["visible_extent", "get_railway_lines"]), "")

    assert plan["steps"][0]["tool"] == "geo.getRailwayLines"
    assert plan["steps"][0]["input"] == {
        "bbox": [
            "$context.view.minLon",
            "$context.view.minLat",
            "$context.view.maxLon",
            "$context.view.maxLat",
        ]
    }


def test_starting_from_the_picked_point_the_first_step_takes_the_selected_location():
    """KRRI_ASAP 의 cctv-around-point 와 같은 꼴이다. 중심 좌표와 반경을 준다."""
    plan = step_service.plan(recipe_of(["picked_point", "find_cctv"]), "")

    assert plan["steps"][0]["input"] == {
        "location": "$context.selectedLocation",
        "radiusMeters": step_service.RADIUS_METERS,
    }


def test_a_slot_with_a_previous_step_still_points_at_the_previous_step():
    """input_first 를 더해도 두 번째 칸부터는 한 글자도 안 달라져야 한다."""
    plan = step_service.plan(
        recipe_of(["spoken_place", "geocode_place", "find_cctv"]), "오송역"
    )

    assert plan["steps"][0]["input"] == {"query": "오송역"}
    assert plan["steps"][1]["input"] == {
        "location": "$s1.location",
        "radiusMeters": step_service.RADIUS_METERS,
    }


def test_an_empty_context_field_does_not_count_that_start_data():
    """KRRI_ASAP 은 우클릭 전에 selectedLocation 을 null 로 보낸다. 빈 bbox 도 마찬가지."""
    full = {
        "view": {"bbox": [[127.20, 36.55], [127.40, 36.70]]},
        "selectedLocation": {"lon": 127.2974, "lat": 36.6199},
    }

    assert step_service.context_starts(full) == ["picked_point", "visible_extent"]
    assert step_service.context_starts({**full, "selectedLocation": None}) == [
        "visible_extent"
    ]
    assert step_service.context_starts({"view": {"bbox": []}}) == []
    assert step_service.context_starts({}) == []
    assert step_service.context_starts(None) == []


# ── $now — 부르는 순간 ──────────────────────────────────────────────


def test_the_date_and_time_are_taken_when_the_call_is_made():
    """고정된 날짜를 배선에 박으면 그날이 지나는 순간 거짓이 됨.

    도구 설명이 KST 를 명시로 요구한다 — "서버 로케일이나 UTC 기준으로 넣으면
    자정 근처에서 하루가 어긋날 수 있다".
    """
    sent = step_service.plan(
        recipe_of(["spoken_place", "geocode_place", "plan_trip"]), "조치원역"
    )["steps"][-1]["input"]
    now = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Seoul"))

    assert sent["date"] == now.strftime("%Y-%m-%d")
    assert len(sent["time_kst"]) == 5 and sent["time_kst"][2] == ":"


def test_the_runtime_marker_is_resolved_before_the_vendor_sees_it():
    """$now 는 vendor scope 에 없는 이름임. 우리가 값으로 바꿔 내보내야 함.

    안 바꾸면 vendor 의 _resolve_reference 가 None 을 돌려주고 required 가
    빈 채로 나감.
    """
    sent = step_service.plan(
        recipe_of(["spoken_place", "geocode_place", "plan_trip"]), "조치원역"
    )["steps"][-1]["input"]

    assert not any(str(value).startswith("$now") for value in sent.values())


def test_an_unknown_runtime_field_is_not_passed_through_silently():
    """모르는 이름을 그대로 두면 그 문자열이 도구에 실려 나감."""
    now = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Seoul"))

    with pytest.raises(ValueError):
        step_service._now_field("$now.datetime", now)


# ── 비자명한 배선 의미 — 대표로 둘 ──────────────────────────────────
#
# 값의 출처가 코드만 보고 안 읽히는 자리만 남긴다. 도구 이름 · 서버 · 답 문구는
# test_wiring_contract.py 가 generic 하게 본다.


def test_the_previous_coordinates_are_split_into_the_origin_fields():
    """칸 이름이 lon · lat 이 아니라 origin_lon · origin_lat 인 자리.

    다른 지점 도구들은 lon · lat 을 받아 앵커 하나를 함께 쓰는데 이것만 다르다.
    베껴 쓰다 lon · lat 으로 보내면 도구가 required 가 없다고 거부함.
    분과 이동수단도 명시로 보낸다 — 도구 기본값(30 · WALK)에 기대면 무엇으로
    계산한 답인지가 배선에 안 남고, 그 값이 바뀌어도 우리 쪽에 신호가 없다.
    """
    sent = step_service.plan(
        recipe_of(["spoken_place", "geocode_place", "compute_isochrone"]), "의왕역"
    )["steps"][-1]["input"]

    assert sent == {
        "origin_lon": "$s1.lon",
        "origin_lat": "$s1.lat",
        "max_minutes": 30,
        "mode": "TRANSIT",
    }


def test_the_origin_comes_from_the_screen_and_the_destination_from_the_utterance():
    """뒤바뀌면 반대 방향 길이 나오고 도구는 아무 오류도 안 냄.

    출발지는 사람이 화면에서 찍은 자리($context)이고 도착지는 말한 장소를
    좌표로 바꾼 것($prev)이다. 둘 다 「지점 좌표」라 타입으로는 안 갈리므로
    이 시험이 그 자리를 지킴.
    """
    plan = step_service.plan(
        recipe_of(["spoken_place", "geocode_place", "plan_trip"]), "조치원역"
    )
    sent = plan["steps"][-1]["input"]

    assert plan["nodes"][-1] == "plan_trip"
    assert sent["from_lat"] == "$context.selectedLocation.lat"
    assert sent["from_lon"] == "$context.selectedLocation.lon"
    assert sent["to_lat"] == "$s1.lat"
    assert sent["to_lon"] == "$s1.lon"


# ── 지도 명령 — 부를 도구가 없는 노드 ───────────────────────────────


def test_a_node_without_a_tool_becomes_a_map_command_not_a_step():
    """TOOL_OF 가 「노드 -> 서버 · 도구」가 아니라 「노드 -> 실행 수단」이다.

    온톨로지는 그것을 모른다. 거기 적힌 것은 「장소 이름을 받아 시설물 화면을
    내놓는다」 뿐이고, 무엇으로 수행하는지는 배선표가 안다.
    vendor 에 빈 steps 를 넘기면 실패로 보므로 step 이 되어서도 안 된다.
    """
    row = step_service.TOOL_OF["show_facility"]
    plan = step_service.plan(
        recipe_of(["spoken_place", "show_facility"]), "오송 테스트트랙"
    )

    assert "tool" not in row and "server_id" not in row
    assert plan["steps"] == []
    assert plan["command_nodes"] == ["show_facility"]
    assert plan["commands"][0]["op"] == row["command"]
    assert plan["commands"][0]["args"]["facilityName"] == "오송 테스트트랙"
    assert plan["headline"]


def test_a_map_command_node_is_not_counted_as_unwired():
    """도구가 없는 것과 배선이 없는 것은 다름. STEP_OF 에 줄이 있으면 붙은 것임."""
    assert step_service.unwired(recipe_of(["spoken_place", "show_facility"])) == []


# ── 이 recipe 를 지금 부를 수 있는가 ────────────────────────────────


def test_a_recipe_that_reads_only_the_context_does_not_need_an_argument():
    """"지금 보이는 곳 CCTV 보여줘" 에는 뽑을 말이 없다. 조회할 곳은 문맥이 말했다.

    판정 근거는 배선이다 — 그 recipe 의 계획에 @arg 가 남는지를 본다.
    recipe id 로 가르지 않는다.
    """
    assert not step_service.spoken_needed(recipe_of(["picked_point", "find_cctv"]))
    assert not step_service.spoken_needed(
        recipe_of(["visible_extent", "search_ev_stations", "get_ev_station"])
    )
    assert step_service.spoken_needed(
        recipe_of(["spoken_place", "geocode_place", "find_cctv"])
    )


def test_a_recipe_that_mixes_the_context_and_the_utterance_still_needs_the_argument():
    """경로 탐색은 출발지를 문맥에서, 도착지를 발화에서 받는다.

    ★ 문맥이 있다고 인자 없이 부르면 도착지가 빈 채로 도구가 나간다.
    """
    route = recipe_of(["spoken_place", "geocode_place", "plan_trip"])

    assert step_service.context_needs(route) == {"picked_point"}
    assert step_service.spoken_needed(route)


def test_context_needs_looks_past_the_first_step():
    """경로의 첫 칸은 말한 장소라 「첫 칸이 화면 데이터인가」로는 못 센다.

    세는 것은 배선이 실제로 읽는 문맥이다. 안 세면 출발지가 빈 채로 도구를
    불러 required 오류가 난다.
    """
    spoken_only = recipe_of(["spoken_place", "geocode_place", "find_cctv"])

    assert step_service.context_needs(spoken_only) == set()
    assert step_service.context_needs(
        recipe_of(["visible_extent", "find_cctv"])
    ) == {"visible_extent"}


def test_unwired_names_the_executable_nodes_with_no_wiring_row(monkeypatch):
    """배선이 없는 실행 노드를 경로 순서로 셈. 데이터 노드는 안 셈.

    부르는 쪽(execute_service.run)이 비어 있지 않으면 도구를 하나도 안 부른다.
    """
    wire(
        monkeypatch,
        ["start", "없는노드"],
        handed={"start": [FAKE_TYPE]},
    )
    monkeypatch.setattr(
        step_service.graph, "executable_in", lambda recipe_id: ["없는노드"]
    )

    assert step_service.unwired("recipe_x") == ["없는노드"]
