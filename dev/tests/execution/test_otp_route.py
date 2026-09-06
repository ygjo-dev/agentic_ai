"""경로 탐색(otp-router)이 지금 구조를 그대로 지나는가.

**두 지점을 받는 첫 노드다.** 지금까지 노드는 값을 한 줄기로 받았다 —
발화에서 오거나(@arg), 앞 단계에서 오거나($prev), 화면에서 오거나($context)
셋 중 하나였고 한 자리에 하나였다. 경로 탐색은 출발지와 도착지 둘을 받고
그 둘의 출처가 다르다. 그래서 「입력이 둘이면 무엇이 달라지는가」를 이
파일이 붙든다.

여기서 지키는 것은 여섯이다.

    권한      execute_service 의 refs 에 그 서버가 있어야 부를 수 있다
    관계      경로가 recipe 파일이 아니라 온톨로지 관계에서 나온다
    배선      노드가 그 서버 · 그 도구로 가고 live required 여섯을 다 채운다
    방향      출발지와 도착지가 뒤바뀌지 않는다
    실행 시각  부르는 순간의 날짜 · 시각이 들어간다. 고정값을 안 박는다
    답        길을 말로 요약하고 좌표 · polyline 을 안 흘린다

LLM 도 Gateway 도 부르지 않는다. 온톨로지 · 배선표 · 상수만 읽는다.
실제 호출은 사람이 dev/tools 로 누르고, 그 실측은 NOTES 에 있다.
"""

import datetime
import zoneinfo

from execution import execute_service, step_service
from ontology import graph
from vendor_to_be_deleted.asap import workflow_answer

# 「말한 장소 → 좌표 → 경로 탐색」 한 벌. 사슬로 찾는다 — 번호는 노드가 늘면 밀린다.
ROUTE_CHAIN = ["spoken_place", "geocode_place", "plan_trip"]

OTP_SERVER = "otp-router"

# live inputSchema 의 required 여섯 (2026-09-06 · Gateway /api/tools).
LIVE_REQUIRED = {"from_lat", "from_lon", "to_lat", "to_lon", "date", "time_kst"}

# 오송역 → 조치원역 실측 응답의 뼈대. dev/tools/probe_out/otp_plan_trip.json 과
# 같은 모양이고, 답 문구가 읽는 칸만 남겼다.
LIVE_ROUTE = {
    "ok": True,
    "itinerary_count": 1,
    "itineraries": [
        {
            "duration_sec": 1450,
            "numberOfTransfers": 0,
            "legs": [
                {"mode": "WALK", "geometry_polyline": "sko~EsrchWEIf@m@"},
                {"mode": "RAIL", "geometry_polyline": "qjo~EktchWbvBbeE"},
                {"mode": "WALK", "geometry_polyline": "qcn}EugwhWDlAv@ED"},
            ],
        }
    ],
}


def recipe_of(chain):
    """그 사슬을 가진 recipe id. 없으면 None."""
    for recipe_id in graph.recipe_ids():
        nodes = [entry["node_id"] for entry in graph.path_of(recipe_id)]
        if nodes == chain:
            return recipe_id
    return None


# ── 권한 ────────────────────────────────────────────────────────────


def test_the_otp_server_is_in_the_permission_scope():
    """빠뜨리면 배선이 맞아도 Gateway 가 거부함.

    실측 2026-09-06 — refs 에 없으면 HTTP 500 "MCP tool
    'otp-router/otp_health_check' is not applied for this user." 이고,
    "otp-router/*" 를 더하면 곧바로 200 {"ok": true} 다.
    """
    refs = execute_service.USER_CONTEXT["selected_mcp_tool_refs"]

    assert f"{OTP_SERVER}/*" in refs


def test_the_web_search_server_stayed_shut():
    """이번에 넓힌 것은 otp-router 하나뿐임.

    web-search 는 저쪽 권한이 안 열려 있어 부를 수 없다(NOTES 「아흔셋째」).
    한 서버를 열면서 옆의 것을 함께 열면 「무엇을 왜 열었나」를 못 되짚음.
    """
    refs = execute_service.USER_CONTEXT["selected_mcp_tool_refs"]

    assert not any(ref.startswith("web-search") for ref in refs)


# ── 관계 ────────────────────────────────────────────────────────────


def test_the_path_comes_out_of_the_relations_not_the_recipe_file():
    """recipe 파일이 없어도 관계만으로 같은 사슬이 나와야 함.

    hasOutput 지점 좌표(장소 좌표 변환) 와 hasInput 지점 좌표(경로 탐색) 가
    이어 주는 것이지 recipe YAML 이 이어 주는 것이 아님. 관계에 없는 경로를
    recipe 로만 적으면 등록으로 만든 것과 초기 것이 갈림.
    """
    from registration import registry

    사슬들 = registry.all_recipes(graph.load_ontology()["nodes"])

    assert ROUTE_CHAIN in 사슬들


def test_it_takes_a_point_and_gives_back_a_route():
    """받는 것과 내놓는 것이 관계에 적혀 있어야 경로가 생성됨."""
    assert "point" in graph.inputs_of("plan_trip")
    assert "travel_route" in graph.outputs_of("plan_trip")


def test_nothing_can_follow_a_route():
    """이동 경로를 받는 노드가 없음. 경로가 여기서 끝나야 함.

    도달권과 같은 자리다. 받는 노드가 생기면 「경로 뒤에 무엇을 더 하는가」를
    사람이 정한 뒤여야 함.
    """
    받는_것 = [
        node_id
        for node_id in graph.load_ontology()["nodes"]
        if "travel_route" in graph.inputs_of(node_id)
    ]

    assert 받는_것 == []


# ── 배선 ────────────────────────────────────────────────────────────


def test_the_route_node_goes_to_the_otp_server():
    """노드가 어느 서버 · 어느 도구인지는 배선만 앎."""
    row = step_service.TOOL_OF["plan_trip"]

    assert row["server_id"] == OTP_SERVER
    assert row["tool"] == "otp_plan_trip"


def test_the_ontology_does_not_know_which_server_it_is():
    """도구 이름이 온톨로지에 새면 노드가 특정 서버에 묶임."""
    node = graph.load_ontology()["nodes"]["plan_trip"]

    assert "otp" not in str(node).lower()
    assert OTP_SERVER not in str(node)


def test_every_live_required_field_is_sent():
    """하나라도 빠지면 도구가 거부함.

    실측 2026-09-06 — date · time_kst 를 빼고 부르면 HTTP 500
    "2 validation errors for otp_plan_tripArguments ... Field required" 다.
    """
    보낸_것 = step_service.plan(recipe_of(ROUTE_CHAIN), "조치원역")["steps"][-1]["input"]

    assert LIVE_REQUIRED <= set(보낸_것)


def test_the_optional_fields_are_left_to_the_tool():
    """재보지 않은 값을 배선에 새로 들이지 않음.

    arrive_by(기본 false) · num_itineraries(기본 3)는 도구가 기본값을 가진다.
    도달권의 분 · 이동수단과 달리 우리가 고를 근거를 아직 안 쟀음.
    """
    보낸_것 = step_service.plan(recipe_of(ROUTE_CHAIN), "조치원역")["steps"][-1]["input"]

    assert set(보낸_것) == LIVE_REQUIRED


# ── 방향 ────────────────────────────────────────────────────────────


def test_the_origin_comes_from_the_screen_and_the_destination_from_the_utterance():
    """뒤바뀌면 반대 방향 길이 나오고 도구는 아무 오류도 안 냄.

    출발지는 사람이 화면에서 찍은 자리($context)이고 도착지는 말한 장소를
    좌표로 바꾼 것($prev)이다. 둘 다 「지점 좌표」라 타입으로는 안 갈리므로
    이 시험이 그 자리를 지킴.
    """
    plan = step_service.plan(recipe_of(ROUTE_CHAIN), "조치원역")
    보낸_것 = plan["steps"][-1]["input"]

    assert plan["nodes"][-1] == "plan_trip"
    assert 보낸_것["from_lat"] == "$context.selectedLocation.lat"
    assert 보낸_것["from_lon"] == "$context.selectedLocation.lon"
    assert 보낸_것["to_lat"] == "$s1.lat"
    assert 보낸_것["to_lon"] == "$s1.lon"


def test_the_place_from_the_utterance_reaches_the_geocode_step():
    """앞 단계가 발화 값을 받아야 도착지 좌표가 나옴."""
    plan = step_service.plan(recipe_of(ROUTE_CHAIN), "조치원역")

    assert plan["steps"][0]["input"] == {"query": "조치원역"}
    assert "조치원역" in plan["headline"]


def test_a_recipe_that_reads_the_screen_midway_is_still_guarded():
    """찍은 지점이 안 왔으면 후보에서 빠져야 함.

    경로의 첫 칸은 말한 장소라 「첫 칸이 화면 데이터인가」로는 못 거른다.
    거르는 것은 배선이 실제로 읽는 문맥이고 context_needs 가 그것을 셈.
    안 걸러지면 출발지가 빈 채로 도구를 불러 required 오류가 남.
    """
    assert step_service.context_needs(recipe_of(ROUTE_CHAIN)) == {"picked_point"}


# ── 실행 시각 ────────────────────────────────────────────────────────


def test_the_date_and_time_are_taken_when_the_call_is_made():
    """고정된 날짜를 배선에 박으면 그날이 지나는 순간 거짓이 됨.

    도구 설명이 KST 를 명시로 요구한다 — "서버 로케일이나 UTC 기준으로 넣으면
    자정 근처에서 하루가 어긋날 수 있다".
    """
    보낸_것 = step_service.plan(recipe_of(ROUTE_CHAIN), "조치원역")["steps"][-1]["input"]
    지금 = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Seoul"))

    assert 보낸_것["date"] == 지금.strftime("%Y-%m-%d")
    assert len(보낸_것["time_kst"]) == 5 and 보낸_것["time_kst"][2] == ":"


def test_the_runtime_marker_is_resolved_before_the_vendor_sees_it():
    """$now 는 저쪽 scope 에 없는 이름임. 우리가 값으로 바꿔 내보내야 함.

    안 바꾸면 vendor 의 _resolve_reference 가 None 을 돌려주고 required 가
    빈 채로 나감.
    """
    보낸_것 = step_service.plan(recipe_of(ROUTE_CHAIN), "조치원역")["steps"][-1]["input"]

    assert not any(str(값).startswith("$now") for 값 in 보낸_것.values())


def test_an_unknown_runtime_field_is_not_passed_through_silently():
    """모르는 이름을 그대로 두면 그 문자열이 도구에 실려 나감."""
    지금 = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Seoul"))

    try:
        step_service._now_field("$now.datetime", 지금)
    except ValueError:
        return
    raise AssertionError("모르는 $now 이름에서 터져야 함")


# ── 답 ──────────────────────────────────────────────────────────────


def test_the_answer_says_how_long_and_never_carries_the_shape():
    """길은 지도가 그림. 말로 낼 것은 시간 · 갈아타기 · 무엇을 타는가 셋임.

    polyline 을 문자열에 담으면 raw JSON 이 화면에 샌다. 도달권의
    「도형을 문자열에 담지 않는다」와 같은 자리다.
    """
    한마디 = workflow_answer.summarize({}, LIVE_ROUTE)

    assert "24분 걸림" in 한마디
    assert "갈아타지 않음" in 한마디
    assert "도보 → 열차 → 도보" in 한마디
    assert "sko~E" not in 한마디
    assert "polyline" not in 한마디


def test_an_unknown_mode_drops_the_word_instead_of_leaking_english():
    """모르는 이동 수단이 오면 그 구간을 뺌. 답에 영어를 안 섞음."""
    응답 = {
        "itineraries": [
            {"duration_sec": 600, "numberOfTransfers": 0,
             "legs": [{"mode": "FUNICULAR"}, {"mode": "WALK"}]}
        ]
    }

    한마디 = workflow_answer.summarize({}, 응답)

    assert "FUNICULAR" not in 한마디
    assert "도보" in 한마디


def test_a_response_without_legs_is_not_read_as_a_route():
    """itineraries 라는 이름만 보고 경로로 읽으면 딴 도구의 답을 잘못 요약함."""
    assert workflow_answer._route_line({"itineraries": [{"duration_sec": 60}]}) == ""
    assert workflow_answer._route_line({"itineraries": []}) == ""
