"""대상 : execution/wiring.yaml — 지금 배선표가 실제로 실행 가능한가

로더의 규칙은 test_step_service.py 가 본다. 여기서 보는 것은 **지금 파일에
적힌 것**이 온톨로지 · Gateway 스키마 · 실행 권한과 맞느냐다.

**개수를 박지 않는다.** recipe 가 몇 개인지 서버가 몇 개인지는 요구사항이
바뀌면 함께 바뀌는 값이라 빨간불이 아무것도 알려주지 않는다. 대신 전부를
훑어 「하나도 어긋난 것이 없다」를 본다.

**이 시험이 잡는 고장은 조용하다.** 없는 칸을 보내도 도구는 오류를 안 낸다 —
모르는 칸이라 버리고 인자 없이 부른 것처럼 답한다. 지도를 아무리 좁혀도
전국 결과가 오던 자리가 그것이었다(실측).

LLM 도 Gateway 도 부르지 않는다. wiring.yaml · 온톨로지 ·
dev/tools/probe_out/tools.json 만 읽는다.
"""

import json
from pathlib import Path

import pytest

from execution import execute_service, step_service
from ontology import graph

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "tools" / "probe_out" / "tools.json"

# 어댑터가 걸리면 중심 좌표 · 반경 대신 bbox 넷이 나간다. 걸리는 조건은
# check_inputs.sent_fields 와 같다 — STEP_OF 에 이름이 적혀 있고 중심 좌표가
# 있거나, 안 적혀 있어도 bbox 넷이 전부 required 라 vendor 가 저절로 거는 것.
# 걸린 줄은 스키마 대조에서 뺀다.
BBOX_FIELDS = ("minLon", "minLat", "maxLon", "maxLat")
CENTER_KEYS = set(step_service.CENTER_KEYS)
RADIUS_KEYS = {"radiusMeters", "radius"}


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


def _adapter_applies(wiring, fields, required):
    if wiring.get("adapter") == step_service.POINT_RADIUS_TO_BBOX and fields & CENTER_KEYS:
        return True
    return (
        set(BBOX_FIELDS).issubset(required)
        and bool(fields & CENTER_KEYS)
        and bool(fields & RADIUS_KEYS)
    )


def _rows():
    """(노드, 타입, 자리 이름, 도구 이름, 보내는 칸 집합, 스키마 칸) 을 죽 편다."""
    schemas = _schemas()
    for (node, kind), wiring in step_service.STEP_OF.items():
        tool = (step_service.TOOL_OF.get(node) or {}).get("tool")
        if not tool or tool not in schemas:
            continue
        props, required = schemas[tool]
        for variant in ("input", "input_first"):
            if variant not in wiring:
                continue
            fields = set(wiring[variant])
            if _adapter_applies(wiring, fields, required):
                continue  # 어댑터가 모양을 바꾼다. check_inputs 가 따로 본다
            yield node, kind, variant, tool, fields, props


# ── 표의 구조 ───────────────────────────────────────────────────────


def test_every_execution_means_is_either_a_tool_or_a_map_command():
    """실행 수단이 둘이고 한 줄이 둘 다이거나 아무것도 아니면 안 된다.

    plan 이 "command 가 있으면 지도 명령, 아니면 step" 으로만 가르므로 둘 다
    적힌 줄은 조용히 지도 명령이 되고 도구가 안 불린다.
    """
    문제 = []
    for node, row in step_service.TOOL_OF.items():
        is_tool = "server_id" in row and "tool" in row
        is_command = "command" in row
        if is_tool == is_command:
            문제.append(f"{node}: {sorted(row)}")
        if not row.get("headline"):
            문제.append(f"{node}: headline 이 없다")

    assert 문제 == [], "tool_of 줄이 어긋났다:\n  " + "\n  ".join(문제)


def test_every_wiring_row_names_a_node_the_ontology_knows():
    """배선이 없는 노드를 가리키면 그 줄은 영영 안 쓰인다.

    노드를 지우고 배선을 안 지운 자리가 그것이다.
    """
    nodes = set(graph.load_ontology()["nodes"])

    unknown = sorted(
        {node for node, _kind in step_service.STEP_OF if node not in nodes}
        | {node for node in step_service.TOOL_OF if node not in nodes}
    )

    assert unknown == [], f"온톨로지에 없는 노드의 배선이다: {unknown}"


def test_every_wiring_row_takes_a_type_that_node_actually_declares():
    """STEP_OF 의 키가 (노드, 받는 타입)이고 그 타입은 hasInput 과 1:1 이다.

    타입 이름을 잘못 적으면 wiring_at 이 그 줄을 영영 못 고르고, 그 노드는
    unwired 로 셈해져 실행이 통째로 막힌다.
    """
    어긋난_줄 = [
        f"{node} x {kind}"
        for node, kind in step_service.STEP_OF
        if kind not in graph.inputs_of(node)
    ]

    assert 어긋난_줄 == [], "hasInput 에 없는 타입을 키로 쓴 줄:\n  " + "\n  ".join(어긋난_줄)


# ── 지금 recipe 를 다 부를 수 있는가 ────────────────────────────────


def test_every_active_recipe_is_fully_wired():
    """하나라도 배선이 비면 그 recipe 는 골라도 실행이 안 된다.

    개수를 안 센다. 「전부 붙어 있다」가 요구사항이고 recipe 가 늘어도 그대로다.
    """
    붙지_않은_것 = {
        recipe_id: step_service.unwired(recipe_id)
        for recipe_id in graph.recipe_ids()
        if step_service.unwired(recipe_id)
    }

    assert 붙지_않은_것 == {}, f"배선이 빈 recipe 가 있다: {붙지_않은_것}"


def test_every_server_a_recipe_calls_is_inside_the_permission_scope():
    """refs 에 없는 서버를 부르는 recipe 는 늘 실패한다.

    실측 — 없으면 HTTP 500 "MCP tool '<서버>/<도구>' is not applied for this
    user." 이고 refs 에 더하면 곧바로 200 이다. 노드를 더할 때 배선만 적고
    권한을 잊는 것이 실제로 걸린 자리다.

    **배선 전체가 아니라 recipe 가 지나는 것만 본다.** 부를 수 없는 서버의
    배선이 남아 있는 것은 권한이 열리면 되살릴 자리라는 뜻이지 지금 부른다는
    뜻이 아니다.
    """
    허용 = {
        ref.split("/", 1)[0]
        for ref in execute_service.USER_CONTEXT["selected_mcp_tool_refs"]
    }

    쓰는_것 = set()
    for recipe_id in graph.recipe_ids():
        for entry in graph.path_of(recipe_id):
            row = step_service.TOOL_OF.get(entry["node_id"], {})
            if "server_id" in row:
                쓰는_것.add(row["server_id"])

    assert 쓰는_것, "recipe 가 도구를 하나도 안 부른다 — 이 검사가 무력하다"
    assert 쓰는_것 <= 허용, f"권한 밖 서버를 부른다: {sorted(쓰는_것 - 허용)}"


def test_the_permission_scope_holds_no_server_no_recipe_calls():
    """부를 것이 없는 서버를 미리 열지 않는다.

    「무엇을 왜 열었나」가 refs 만 보고 읽혀야 한다. 지키는 것은 「몇 개를
    넓혔나」가 아니라 「부르는 것만 열려 있나」다 — 서버가 늘어도 그대로다.
    """
    허용 = {
        ref.split("/", 1)[0]
        for ref in execute_service.USER_CONTEXT["selected_mcp_tool_refs"]
    }

    쓰는_것 = {
        row["server_id"]
        for recipe_id in graph.recipe_ids()
        for entry in graph.path_of(recipe_id)
        for row in [step_service.TOOL_OF.get(entry["node_id"], {})]
        if "server_id" in row
    }

    assert 허용 <= 쓰는_것, f"부를 것이 없는데 열려 있다: {sorted(허용 - 쓰는_것)}"


# ── 보내는 칸이 도구 스키마에 있는가 ────────────────────────────────


def test_every_field_the_wiring_sends_exists_in_the_schema():
    """없는 칸은 버려진다. 조용히 전국을 뒤지는 길이 그것이다."""
    없는_칸 = [
        f"{node} × {kind} ({variant}) -> {tool} : {sorted(fields - props)}"
        for node, kind, variant, tool, fields, props in _rows()
        if fields - props
    ]
    assert 없는_칸 == [], "스키마에 없는 칸을 보내는 줄:\n  " + "\n  ".join(없는_칸)


def test_the_check_actually_has_schemas_to_compare_against():
    """대조할 snapshot 이 없으면 위 시험이 조용히 아무것도 안 본다.

    dev/tools/check_inputs.py 가 쓰는 것과 같은 파일이라 계기판과 시험이 같은
    근거를 본다.
    """
    assert SCHEMA_PATH.exists(), f"도구 스키마 snapshot 이 없다: {SCHEMA_PATH}"
    assert list(_rows()), "대조된 배선 줄이 하나도 없다"


# 지도 범위를 받는 두 모양. **wiring.yaml 의 anchor 가 원천이고 여기는 기대값이다.**
BBOX_FROM_PREVIOUS = [
    "$prev.minLon",
    "$prev.minLat",
    "$prev.maxLon",
    "$prev.maxLat",
]
BBOX_FROM_CONTEXT = [
    "$context.view.minLon",
    "$context.view.minLat",
    "$context.view.maxLon",
    "$context.view.maxLat",
]


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
    """
    wiring = step_service.STEP_OF[(node, "map_extent")]

    assert "bbox" in _props(tool)
    assert wiring["input_first"] == {"bbox": BBOX_FROM_CONTEXT}
    assert wiring["input"] == {"bbox": BBOX_FROM_PREVIOUS}


def test_a_tool_without_a_bbox_field_gets_the_flat_four():
    """ev.searchStations 에는 bbox 라는 칸이 없다. 보내면 버려진다."""
    wiring = step_service.STEP_OF[("search_ev_stations", "map_extent")]

    assert "bbox" not in _props("ev.searchStations")
    assert wiring["input_first"] == dict(zip(BBOX_FIELDS, BBOX_FROM_CONTEXT))


# ── 온톨로지에 도구 이름이 새지 않는가 ─────────────────────────────


def test_the_ontology_never_names_a_server_or_a_tool():
    """**노드가 특정 MCP 서버에 묶이면 도구를 갈아끼울 때 도메인을 고쳐야 한다.**

    menu 가 온톨로지 문장에서 만들어지므로 도구 이름이 새면 발화 해석
    프롬프트까지 그대로 실린다. 노드마다 따로 보지 않고 전부 훑는다 —
    서버가 늘어도 이 시험은 그대로다.
    """
    이름들 = set()
    for row in step_service.TOOL_OF.values():
        for key in ("server_id", "tool", "command"):
            if row.get(key):
                이름들.add(row[key])

    assert 이름들, "배선표가 비었다 — 이 검사가 무력하다"

    샌_곳 = []
    for node_id, node in graph.load_ontology()["nodes"].items():
        글 = f"{node['name']} {node['description']}"
        샌_곳 += [f"{node_id}: {이름}" for 이름 in 이름들 if 이름 in 글]

    assert 샌_곳 == [], "온톨로지에 도구 이름이 샜다:\n  " + "\n  ".join(샌_곳)
