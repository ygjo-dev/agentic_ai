"""대상 : 온톨로지의 tool 과 execution/wiring.yaml — 지금 적힌 실행 수단이 실제로 실행 가능한가

로더와 계획의 규칙은 test_step_service.py 가 본다. 여기서 보는 것은 **지금 파일에
적힌 것**이 온톨로지 · Gateway 스키마 · 실행 권한과 맞느냐다.

**개수를 박지 않는다.** recipe 가 몇 개인지 서버가 몇 개인지는 요구사항이
바뀌면 함께 바뀌는 값이라 빨간불이 아무것도 알려주지 않는다. 대신 전부를
훑어 「하나도 어긋난 것이 없다」를 본다.

**이 시험이 잡는 고장은 조용하다.** 없는 칸을 보내도 도구는 오류를 안 낸다 —
모르는 칸이라 버리고 인자 없이 부른 것처럼 답한다. 지도를 아무리 좁혀도
전국 결과가 오던 자리가 그것이었다(실측).

LLM 도 Gateway 도 부르지 않는다. 온톨로지 · wiring.yaml ·
dev/tools/probe_out/tools.json 만 읽는다.
"""

import json
from pathlib import Path

import pytest

import paths
from execution import execute_service, step_service
from ontology import graph, store

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "tools" / "probe_out" / "tools.json"

# 어댑터가 걸리면 중심 좌표 · 반경 대신 bbox 넷이 나간다. 걸린 벌은 스키마 대조에서
# 중심 · 반경을 빼고 bbox 넷을 넣어 맞댄다 — vendor 의 _point_radius_to_bbox_input 이
# 하는 그대로다.
BBOX_FIELDS = ("minLon", "minLat", "maxLon", "maxLat")
ADAPTER_CONSUMES = set(step_service.CENTER_KEYS) | {"radiusMeters", "radius"}


def _schemas():
    """도구 이름 -> (칸 이름 집합, required 집합)."""
    payload = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("tools") or []
    out = {}
    for tool in payload:
        if isinstance(tool, dict) and tool.get("name"):
            schema = tool.get("inputSchema") or {}
            out[tool["name"]] = (
                set((schema.get("properties") or {}).keys()),
                set(schema.get("required") or []),
            )
    return out


def _props(tool):
    return _schemas()[tool][0]


def _tool_nodes():
    """tool 이 있는 노드와 그 binding."""
    for node_id in graph.node_ids():
        binding = step_service.binding_of(node_id)
        if binding is not None:
            yield node_id, binding


def _rows():
    """(노드, 타입, 출처, 어미, 도구 이름, 보내는 칸 집합, 스키마 칸) 을 죽 편다."""
    schemas = _schemas()
    for node_id, binding in _tool_nodes():
        if binding["kind"] != step_service.MCP or binding["tool"] not in schemas:
            continue
        props, _required = schemas[binding["tool"]]
        for row in step_service.variants(node_id):
            fields = set(row["input"])
            if row["adapter"]:
                fields = (fields - ADAPTER_CONSUMES) | set(BBOX_FIELDS)
            yield node_id, row["type"], row["origin"], row["suffix"], binding["tool"], fields, props


# ── 표의 구조 ───────────────────────────────────────────────────────


def test_the_tools_and_the_remaining_wiring_agree():
    """tool 이 읽히고, 도구 · 명령 노드마다 답 첫 줄이 있고, legacy 경로가 쓰인다.

    plan 이 답 첫 줄을 HEADLINE[노드] 로 읽으므로 빠지면 그 경로 전체가 KeyError 로
    멈춘다. 안 쓰이는 legacy 줄은 다음 사람이 원천으로 읽는다.
    """
    assert step_service.check_bindings() == []


def test_every_tool_names_its_server_and_the_ontology_holds_no_address():
    """tool.id 는 논리 식별이다. 주소 · 포트 · 기계 이름은 배포마다 달라 endpoints.py 가 갖는다.

    온톨로지에 주소를 적으면 서비스를 다른 기계로 옮길 때 도메인을 고쳐야 한다.
    """
    ids = [binding["id"] for _node, binding in _tool_nodes()]
    assert ids, "tool 이 하나도 없다 — 이 검사가 무력하다"

    for tool_id in ids:
        server = tool_id.split("/", 1)[0]
        assert "://" not in tool_id and ":" not in server and "localhost" not in tool_id, tool_id

    raw = paths.ONTOLOGY_PATH.read_text(encoding="utf-8")
    for marker in ("http://", "https://", "localhost", "127.0.0.1", "host.docker.internal"):
        assert marker not in raw, marker


def test_every_start_node_is_a_semantic_type_with_a_known_source():
    """시작점은 source 가 있는 데이터 노드다. 실행 노드나 대상이 시작점이면 경로가 끊긴다.

    source.from 은 발화 인자 하나와 화면 문맥뿐이다. 모르는 출처는 실행 계획이
    값을 못 만든다.
    """
    starts = graph.start_ids()
    assert starts, "시작점이 없으면 recipe 가 하나도 안 만들어진다"

    for node_id in starts:
        origin = graph.source_of(node_id).get("from")
        assert not graph.is_executable(node_id), node_id
        assert node_id not in graph.group_ids(), node_id
        assert origin == step_service.SPOKEN_ARGUMENT or origin.startswith(step_service.CONTEXT_SOURCE), origin


# ── 지금 recipe 를 다 부를 수 있는가 ────────────────────────────────


def test_every_active_recipe_is_fully_wired():
    """하나라도 실행 수단이 비면 그 recipe 는 골라도 실행이 안 된다.

    개수를 안 센다. 「전부 붙어 있다」가 요구사항이고 recipe 가 늘어도 그대로다.
    """
    붙지_않은_것 = {
        recipe_id: step_service.unwired(recipe_id)
        for recipe_id in graph.recipe_ids()
        if step_service.unwired(recipe_id)
    }

    assert 붙지_않은_것 == {}, f"실행 수단이 빈 recipe 가 있다: {붙지_않은_것}"


def _permitted_servers():
    """refs 가 열어 준 서버. 「무엇을 왜 열었나」의 원천이다."""
    return {
        ref.split("/", 1)[0]
        for ref in execute_service.USER_CONTEXT["selected_mcp_tool_refs"]
    }


def _servers_recipes_call():
    """지금 recipe 가 실제로 지나는 서버.

    **tool 전체가 아니라 recipe 가 지나는 것만 본다.** 부를 수 없는 서버의
    tool 이 남아 있는 것은 권한이 열리면 되살릴 자리라는 뜻이지 지금 부른다는
    뜻이 아니다.
    """
    return {
        step["server_id"]
        for recipe_id in graph.recipe_ids()
        for step in step_service.plan(recipe_id, "오송역")["steps"]
    }


def test_every_server_a_recipe_calls_is_inside_the_permission_scope():
    """refs 에 없는 서버를 부르는 recipe 는 늘 실패한다.

    실측 — 없으면 HTTP 500 "MCP tool '<서버>/<도구>' is not applied for this
    user." 이고 refs 에 더하면 곧바로 200 이다. 노드를 더할 때 tool 만 적고
    권한을 잊는 것이 실제로 걸린 자리다.
    """
    쓰는_것 = _servers_recipes_call()

    assert 쓰는_것, "recipe 가 도구를 하나도 안 부른다 — 이 검사가 무력하다"
    assert 쓰는_것 <= _permitted_servers(), (
        f"권한 밖 서버를 부른다: {sorted(쓰는_것 - _permitted_servers())}"
    )


def test_the_permission_scope_holds_no_server_no_recipe_calls():
    """부를 것이 없는 서버를 미리 열지 않는다.

    지키는 것은 「몇 개를 넓혔나」가 아니라 「부르는 것만 열려 있나」다 —
    서버가 늘어도 그대로다.
    """
    허용 = _permitted_servers()

    assert 허용 <= _servers_recipes_call(), (
        f"부를 것이 없는데 열려 있다: {sorted(허용 - _servers_recipes_call())}"
    )


# ── 보내는 칸이 도구 스키마에 있는가 ────────────────────────────────


def test_every_field_the_tool_sends_exists_in_the_schema():
    """없는 칸은 버려진다. 조용히 전국을 뒤지는 길이 그것이다."""
    없는_칸 = [
        f"{node} × {kind} ({origin}{' …' + suffix if suffix else ''}) -> {tool} : {sorted(fields - props)}"
        for node, kind, origin, suffix, tool, fields, props in _rows()
        if fields - props
    ]
    assert 없는_칸 == [], "스키마에 없는 칸을 보내는 자리:\n  " + "\n  ".join(없는_칸)


def test_the_check_actually_has_schemas_to_compare_against():
    """대조할 snapshot 이 없으면 위 시험이 조용히 아무것도 안 본다.

    dev/tools/check_inputs.py 가 쓰는 것과 같은 파일이라 계기판과 시험이 같은
    근거를 본다.
    """
    assert SCHEMA_PATH.exists(), f"도구 스키마 snapshot 이 없다: {SCHEMA_PATH}"
    assert list(_rows()), "대조된 자리가 하나도 없다"


# 지도 범위를 받는 두 모양. **실행 계획이 원천이고 여기는 기대값이다.**
BBOX_FROM_PREVIOUS = [
    "$s1.minLon",
    "$s1.minLat",
    "$s1.maxLon",
    "$s1.maxLat",
]
BBOX_FROM_CONTEXT = [
    "$context.view.minLon",
    "$context.view.minLat",
    "$context.view.maxLon",
    "$context.view.maxLat",
]


def _by_origin(node_id, type_id):
    return {row["origin"]: row for row in step_service.variants(node_id) if row["type"] == type_id and not row["suffix"]}


@pytest.mark.parametrize(
    "node, tool",
    [
        ("get_railway_lines", "geo.getRailwayLines"),
        ("search_admin_boundaries", "adminBoundary.searchBoundaries"),
        ("get_vworld_boundaries", "vworld.getAdministrativeBoundaries"),
        ("search_population_statistics", "population.searchStatistics"),
    ],
)
def test_a_tool_whose_schema_really_takes_a_bbox_array_gets_one_field(node, tool):
    """평평한 넷으로 풀면 오히려 깨지는 자리다. 스키마에 bbox 칸이 실재한다.

    ev.searchStations 를 고치면서 같이 고치면 안 되는 것을 확인하고 안 고쳤다.
    그 확인을 여기 박아 둔다.

    줄 전체를 못 박지 않는다. 같은 자리에 bbox 말고 다른 칸이 함께 갈 수 있고
    (행정구역 조회의 layer 가 그것이다) 그것은 이 시험이 보는 것이 아니다.
    보는 것은 **좌표가 한 칸으로 가느냐 넷으로 흩어지느냐** 하나다.
    """
    rows = _by_origin(node, "map_extent")

    assert "bbox" in _props(tool)
    assert rows[step_service.SOURCE]["input"]["bbox"] == BBOX_FROM_CONTEXT
    assert rows[step_service.STEP]["input"]["bbox"] == BBOX_FROM_PREVIOUS
    for row in rows.values():
        assert not set(BBOX_FIELDS) & set(row["input"]), "좌표가 넷으로 흩어졌다"


def test_a_tool_without_a_bbox_field_gets_the_flat_four():
    """ev.searchStations 에는 bbox 라는 칸이 없다. 보내면 버려진다."""
    rows = _by_origin("search_ev_stations", "map_extent")

    assert "bbox" not in _props("ev.searchStations")
    assert rows[step_service.SOURCE]["input"] == dict(zip(BBOX_FIELDS, BBOX_FROM_CONTEXT))


# ── 도구 이름이 발화 해석 프롬프트로 새지 않는가 ────────────────────


def _tool_names():
    names = set()
    for _node, binding in _tool_nodes():
        names.add(binding["id"])
        names.add(binding.get("tool") or binding.get("command") or binding["id"].split("/", 1)[1])
    return names


def test_no_server_or_tool_name_leaks_into_what_the_llm_reads():
    """**도구 이름은 tool 칸에만 있다.** name · description · source.description 과 menu 에는 없다.

    menu 문장이 온톨로지 문장에서 만들어지고 menu.yaml 원문이 발화 해석 프롬프트에
    그대로 실린다. 도구 이름이 새면 LLM 이 도구 순서를 지어낼 재료를 얻는다.
    노드마다 따로 보지 않고 전부 훑는다 — 서버가 늘어도 이 시험은 그대로다.
    """
    이름들 = _tool_names()
    assert 이름들, "tool 이 비었다 — 이 검사가 무력하다"

    샌_곳 = []
    for node_id, node in store.nodes().items():
        글 = " ".join(
            [node["name"], node["description"], str((node.get("source") or {}).get("description") or "")]
        )
        샌_곳 += [f"{node_id}: {이름}" for 이름 in 이름들 if 이름 in 글]

    menu = paths.MENU_YAML_PATH.read_text(encoding="utf-8")
    샌_곳 += [f"menu.yaml: {이름}" for 이름 in 이름들 if 이름 in menu]

    assert 샌_곳 == [], "발화 해석이 읽는 곳에 도구 이름이 샜다:\n  " + "\n  ".join(샌_곳)
