"""도달권 계산(r5-server)이 지금 구조를 그대로 지나는가.

**우리가 부르는 유일한 둘째 MCP 서버다.** 마흔은 asap-mcp-core 이고
web.search · web.fetch 는 권한이 없어 못 부른다. 그래서 「서버가 둘이면
무엇이 달라지는가」를 이 파일이 혼자 붙든다.

여기서 지키는 것은 넷이다.

    권한      execute_service 의 refs 에 그 서버가 있어야 부를 수 있다
    배선      노드가 그 서버 · 그 도구로 간다
    좌표 칸    앞 단계의 lon · lat 이 origin_lon · origin_lat 으로 들어간다
    실행값     분과 이동수단을 명시로 보낸다. 도구 기본값에 기대지 않는다
    오류 전달  권한이 없을 때의 Gateway 문구가 사용자에게 사유로 나간다

LLM 도 Gateway 도 부르지 않는다. 온톨로지 · 배선표 · 상수만 읽는다.
실제 호출은 사람이 dev/tools 로 누르고, 그 실측은 NOTES 에 있다.
"""

from execution import execute_service, step_service
from ontology import graph
from vendor_to_be_deleted.asap.workflow_answer import (
    NO_PERMISSION_REASON,
    NOT_APPLIED,
    compose_workflow_answer,
)

# 「말한 장소 → 좌표 → 도달권」 한 벌. 사슬로 찾는다 — 번호는 노드가 늘면 밀린다.
ISOCHRONE_CHAIN = ["spoken_place", "geocode_place", "compute_isochrone"]

R5_SERVER = "r5-server"

# 의왕역 실측 좌표. probe_out/geo.geocode.query-의왕역-2026-08-27.json 의 값이다.
UIWANG = (126.94821341201332, 37.32011340539614)


def recipe_of(chain):
    """그 사슬을 가진 recipe id. 없으면 None."""
    for recipe_id in graph.recipe_ids():
        nodes = [entry["node_id"] for entry in graph.path_of(recipe_id)]
        if nodes == chain:
            return recipe_id
    return None


# ── 권한 ────────────────────────────────────────────────────────────


def test_the_r5_server_is_in_the_permission_scope():
    """빠뜨리면 배선이 맞아도 Gateway 가 거부함.

    실측 2026-09-06 — refs 가 ["asap-mcp-core/*"] 뿐이면
    HTTP 500 "MCP tool 'r5-server/health_check' is not applied for this user."
    이고, "r5-server/*" 를 더하면 곧바로 200 이다.
    """
    refs = execute_service.USER_CONTEXT["selected_mcp_tool_refs"]

    assert f"{R5_SERVER}/*" in refs


def test_the_scope_was_widened_by_exactly_one_server():
    """부를 것이 없는 서버를 미리 열지 않음.

    Gateway 에는 넷이 있다 — asap-mcp-core · web-search · otp-router · r5-server.
    web-search 는 저쪽 권한이 따로 안 열려 있고 otp-router 는 부를 배선도
    recipe 도 아직 없다. 「무엇을 왜 열었나」가 refs 만 보고 읽혀야 함.
    """
    refs = execute_service.USER_CONTEXT["selected_mcp_tool_refs"]

    assert set(refs) == {"asap-mcp-core/*", f"{R5_SERVER}/*"}


def test_every_server_a_recipe_actually_calls_is_inside_the_permission_scope():
    """recipe 가 부르는 서버가 refs 에 없으면 그 recipe 는 늘 실패함.

    노드를 더할 때 배선만 적고 권한을 잊는 것이 이번에 실제로 걸린 자리다.
    서버를 하나 더 붙이는 사람이 여기서 빨간불을 본다.

    **배선 전체가 아니라 recipe 가 지나는 것만 본다.** web_search 는 배선이
    있는데 저쪽 권한이 안 열려 있고(NOTES 「아흔셋째」) 그래서 그것을 쓰던
    recipe 둘(007 · 051)을 지웠다. 배선을 남겨 둔 것은 권한이 열리면 되살릴
    자리라는 뜻이지 지금 부른다는 뜻이 아님.
    """
    refs = execute_service.USER_CONTEXT["selected_mcp_tool_refs"]
    허용 = {ref.split("/", 1)[0] for ref in refs}

    쓰는_것 = set()
    for recipe_id in graph.recipe_ids():
        for entry in graph.path_of(recipe_id):
            row = step_service.TOOL_OF.get(entry["node_id"], {})
            if "server_id" in row:
                쓰는_것.add(row["server_id"])

    assert 쓰는_것 <= 허용
    assert R5_SERVER in 쓰는_것


# ── 배선 ────────────────────────────────────────────────────────────


def test_the_isochrone_node_goes_to_the_r5_server():
    """도구 이름에 서버 접두어를 안 붙임. 서버는 제 칸에 따로 적음."""
    row = step_service.TOOL_OF["compute_isochrone"]

    assert row["server_id"] == R5_SERVER
    assert row["tool"] == "compute_isochrone"
    assert row["headline"]


def test_the_ontology_does_not_know_which_server_it_is():
    """노드에는 name 과 description 뿐. 도구도 서버도 배선의 일임."""
    node = graph.load_ontology()["nodes"]["compute_isochrone"]

    assert set(node) == {"name", "description"}
    assert R5_SERVER not in node["description"]
    assert "compute_isochrone" not in node["description"]


def test_it_takes_a_point_and_gives_back_a_reachable_area():
    """좌표를 받아 도달권을 내놓음. 그래서 좌표를 내는 노드 뒤에 설 수 있음."""
    assert graph.inputs_of("compute_isochrone") == ["point"]
    assert graph.outputs_of("compute_isochrone") == ["reachable_area"]
    assert graph.can_connect("geocode_place", "compute_isochrone")


def test_nothing_can_follow_a_reachable_area():
    """받는 노드가 없는 타입임. 경계 도형 · 통계와 같은 자리."""
    받는_이 = [nid for nid in graph.load_ontology()["nodes"]
              if "reachable_area" in graph.inputs_of(nid)]

    assert 받는_이 == []


# ── 좌표 칸 ──────────────────────────────────────────────────────────


def test_the_previous_coordinates_land_in_the_origin_fields():
    """칸 이름이 lon · lat 이 아니라 origin_lon · origin_lat 임.

    다른 지점 도구들은 lon · lat 을 받아 앵커 하나를 함께 쓰는데 이것만 다르다.
    베껴 쓰다 lon · lat 으로 보내면 도구가 required 가 없다고 거부함.
    """
    recipe_id = recipe_of(ISOCHRONE_CHAIN)
    plan = step_service.plan(recipe_id, "의왕역")

    좌표_단계 = plan["steps"][-1]

    assert plan["nodes"][-1] == "compute_isochrone"
    assert 좌표_단계["server_id"] == R5_SERVER
    assert 좌표_단계["input"] == {
        "origin_lon": "$s1.lon",
        "origin_lat": "$s1.lat",
        "max_minutes": 30,
        "mode": "TRANSIT",
    }


def test_the_place_from_the_utterance_reaches_the_geocode_step():
    """앞 단계가 발화 값을 받아야 좌표가 나옴. 사슬이 거기서 시작함."""
    recipe_id = recipe_of(ISOCHRONE_CHAIN)
    plan = step_service.plan(recipe_id, "의왕역")

    assert plan["steps"][0]["input"] == {"query": "의왕역"}
    assert "의왕역" in plan["headline"]


def test_the_minutes_and_the_mode_are_sent_and_never_left_to_the_tool():
    """도구 기본값에 기대지 않음. 무엇으로 계산한 답인지가 배선에 적혀 있어야 함.

    required 는 좌표 둘뿐이라 안 보내도 돌긴 한다. 그러면 저쪽 서버의
    기본값(30분 · WALK)으로 도는데, 그 값은 우리가 모르는 새 바뀔 수 있고
    바뀌어도 우리 쪽에는 아무 신호가 없다.
    ★ mode 가 도구 기본값(WALK)과 다르므로 안 보내면 답이 실제로 달라짐.
    """
    보낸_것 = step_service.plan(recipe_of(ISOCHRONE_CHAIN), "의왕역")["steps"][-1]["input"]

    assert set(보낸_것) == {"origin_lon", "origin_lat", "max_minutes", "mode"}
    assert 보낸_것["max_minutes"] == 30
    assert 보낸_것["mode"] == "TRANSIT"


# ── 오류 전달 ────────────────────────────────────────────────────────


def test_a_gateway_permission_refusal_comes_out_as_a_reason_not_a_crash():
    """권한이 없는 것은 잠깐 터진 것과 다름. 사용자가 알아야 할 사실임.

    refs 에서 r5 를 빼면 Gateway 가 이 문구를 돌려준다(실측 2026-09-06).
    """
    거부 = (f"MCP tool '{R5_SERVER}/compute_isochrone' {NOT_APPLIED}.")
    trace = [{
        "id": "s2",
        "tool": "compute_isochrone",
        "status": "error",
        "error": "s2 단계 도구 호출 실패",
        "error_detail": 거부,
    }]

    answer = compose_workflow_answer({"answer_instruction": "도달권을 계산했습니다."}, trace)

    assert NO_PERMISSION_REASON in answer
    assert NOT_APPLIED not in answer


# ── 답 문구 ──────────────────────────────────────────────────────────


def test_the_answer_says_how_far_and_never_carries_the_shape():
    """도형은 지도가 그림. 말로 낼 것은 어떻게 · 몇 분 · 얼마나 넓은가임.

    features 를 문자열에 담으면 raw JSON 이 화면에 샌다 — geojson 이 새던
    자리와 같음. 아래 응답 모양은 2026-09-06 의왕역 실측이다.
    """
    trace = [{
        "id": "s2",
        "tool": "compute_isochrone",
        "status": "success",
        "input": {"origin_lon": UIWANG[0], "origin_lat": UIWANG[1]},
        "result": {
            "status": "success",
            "origin": {"lon": UIWANG[0], "lat": UIWANG[1]},
            "max_minutes": 30,
            "cutoffs_minutes": [30],
            "mode": "WALK",
            "smoothing": "kde",
            "reachable_cell_count": 140,
            "elapsed_ms": 259,
            "feature_collections": {
                "polygons": {"type": "FeatureCollection", "features": [
                    {"type": "Feature",
                     "geometry": {"type": "MultiPolygon", "coordinates": [[[[126.943, 37.307]]]]},
                     "properties": {"cutoff_min": 30}}]},
                "lines": {"type": "FeatureCollection", "features": []},
            },
        },
    }]

    answer = compose_workflow_answer({"answer_instruction": "의왕역 도달권을 계산했습니다."}, trace)

    assert "걸어서" in answer
    assert "30분" in answer
    assert "140" in answer
    assert "MultiPolygon" not in answer
    assert "coordinates" not in answer
    assert "126.943" not in answer


def test_an_unknown_mode_drops_the_word_instead_of_leaking_english():
    """모르는 값이 오면 수단을 빼고 나머지만 냄. 영어를 그대로 안 내보냄."""
    trace = [{
        "id": "s1",
        "tool": "compute_isochrone",
        "status": "success",
        "input": {},
        "result": {
            "mode": "SCOOTER",
            "max_minutes": 15,
            "reachable_cell_count": 7,
            "feature_collections": {"polygons": {"type": "FeatureCollection", "features": []}},
        },
    }]

    answer = compose_workflow_answer({"answer_instruction": "도달권을 계산했습니다."}, trace)

    assert "SCOOTER" not in answer
    assert "15분" in answer
