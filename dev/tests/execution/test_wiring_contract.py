"""대상 : 게시된 Recipe.execution — 지금 부르는 도구 · 칸이 실제로 실행 가능한가

compile 규칙은 agentic_ai 밖의 등록 저장소가 본다. 여기서 보는 것은 **지금 게시된 것**이
온톨로지 · Gateway 스키마 · 실행 권한과 맞느냐다.

**개수를 박지 않는다.** recipe 가 몇 개인지 서버가 몇 개인지는 요구사항이
바뀌면 함께 바뀌는 값이라 빨간불이 아무것도 알려주지 않는다. 대신 전부를
훑어 「하나도 어긋난 것이 없다」를 본다.

**이 시험이 잡는 고장은 조용하다.** 없는 칸을 보내도 도구는 오류를 안 낸다 —
모르는 칸이라 버리고 인자 없이 부른 것처럼 답한다. 지도를 아무리 좁혀도
전국 결과가 오던 자리가 그것이었다(실측).

LLM 도 Gateway 도 부르지 않는다. 온톨로지 · 게시된 recipe ·
dev/tools/probe_out/tools.json 만 읽는다.
"""

import json
from pathlib import Path

import pytest

import paths
from execution import workflow_execution, workflow_materializer
from ontology import ONTOLOGY

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "tools" / "probe_out" / "tools.json"

# 지도 범위를 평평한 네 칸으로 받는 도구의 칸 이름.
BBOX_FIELDS = ("minLon", "minLat", "maxLon", "maxLat")


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


def _tool_ids():
    """온톨로지 노드에 적힌 tool.id 전부."""
    return [tool["id"] for tool in (ONTOLOGY.tool_of(node_id) for node_id in ONTOLOGY.node_ids()) if tool]


def _published_steps():
    """(recipe id, 게시된 도구 단계) 를 죽 편다. 지도 명령은 도구 단계가 아님."""
    for recipe_id in ONTOLOGY.recipe_ids():
        for entry in workflow_materializer.load(recipe_id)["workflow"]:
            if "server_id" in entry:
                yield recipe_id, entry


def _rows():
    """(recipe, 노드, 도구 이름, 보내는 칸 집합, 스키마 칸) 을 죽 편다.

    transform 이 걸린 단계의 input 은 이미 transform 뒤의 칸(범위 네 칸)으로 게시돼 있다.
    """
    schemas = _schemas()
    for recipe_id, entry in _published_steps():
        if entry["tool"] not in schemas:
            continue
        yield recipe_id, entry["node"], entry["tool"], set(entry["input"]), schemas[entry["tool"]][0]


# ── 표의 구조 ───────────────────────────────────────────────────────


def test_no_wiring_table_stands_beside_the_ontology_and_the_published_plan():
    """실행 수단 · 응답 경로는 온톨로지에, 실행 계획은 게시된 recipe 에 있다. 노드별 표를 따로 두지 않는다.

    표가 파일이나 모듈에 되살아나면 같은 것의 원천이 둘이 되고, 어느 쪽이 이기는지 코드를
    읽어야 알게 된다. 노드마다 답 첫 줄을 적던 표도 실행 계획에 화면 문구를 섞던 자리라
    되살리지 않는다.
    """
    assert not (paths.REPO_ROOT / "execution" / "wiring.yaml").exists()
    assert not hasattr(paths, "WIRING_PATH")
    for module, name in [
        (workflow_materializer, "HEADLINE"),
        (workflow_materializer, "reload_wiring"),
    ]:
        assert not hasattr(module, name), name


def test_every_tool_names_its_server_and_the_ontology_holds_no_address():
    """tool.id 는 논리 식별이다. 주소 · 포트 · 기계 이름은 배포마다 달라 endpoints.py 가 갖는다.

    온톨로지에 주소를 적으면 서비스를 다른 기계로 옮길 때 도메인을 고쳐야 한다.
    """
    ids = _tool_ids()
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
    starts = ONTOLOGY.start_ids()
    assert starts, "시작점이 없으면 recipe 가 하나도 안 만들어진다"

    for node_id in starts:
        origin = ONTOLOGY.source_of(node_id).get("from")
        assert not ONTOLOGY.is_executable(node_id), node_id
        assert node_id not in ONTOLOGY.group_ids(), node_id
        assert origin == workflow_materializer.SPOKEN_ARGUMENT or origin.startswith(workflow_materializer.CONTEXT_SOURCE), origin


# ── 지금 recipe 를 다 부를 수 있는가 ────────────────────────────────


def test_every_active_recipe_is_fully_wired():
    """게시된 블록에 실행 수단이 빈 노드(unwired)가 있으면 그 recipe 는 골라도 실행이 안 된다.

    개수를 안 센다. 「전부 붙어 있다」가 요구사항이고 recipe 가 늘어도 그대로다.
    """
    붙지_않은_것 = {
        recipe_id: workflow_materializer.load(recipe_id).get("unwired")
        for recipe_id in ONTOLOGY.recipe_ids()
        if workflow_materializer.load(recipe_id).get("unwired")
    }

    assert 붙지_않은_것 == {}, f"실행 수단이 빈 recipe 가 있다: {붙지_않은_것}"


def _permitted_servers():
    """refs 가 열어 준 서버. 「무엇을 왜 열었나」의 원천이다."""
    return {
        ref.split("/", 1)[0]
        for ref in workflow_execution.USER_CONTEXT["selected_mcp_tool_refs"]
    }


def _servers_recipes_call():
    """지금 recipe 에 게시된 execution 이 실제로 부르는 서버.

    **tool 전체가 아니라 recipe 가 지나는 것만 본다.** 부를 수 없는 서버의
    tool 이 남아 있는 것은 권한이 열리면 되살릴 자리라는 뜻이지 지금 부른다는
    뜻이 아니다.
    """
    return {entry["server_id"] for _recipe_id, entry in _published_steps()}


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
        f"{recipe_id} × {node} -> {tool} : {sorted(fields - props)}"
        for recipe_id, node, tool, fields, props in _rows()
        if fields - props
    ]
    assert 없는_칸 == [], "스키마에 없는 칸을 보내는 자리:\n  " + "\n  ".join(없는_칸)


def test_the_check_actually_has_schemas_to_compare_against():
    """대조할 snapshot 이 없으면 위 시험이 조용히 아무것도 안 본다."""
    assert SCHEMA_PATH.exists(), f"도구 스키마 snapshot 이 없다: {SCHEMA_PATH}"
    assert list(_rows()), "대조된 자리가 하나도 없다"


def test_every_published_step_calls_a_tool_the_schema_snapshot_knows():
    """_rows 는 snapshot 에 없는 도구를 건너뛴다. 건너뛴 자리가 없어야 위 시험이 전부를 본 것이다."""
    schemas = _schemas()
    모르는_도구 = sorted({f"{recipe_id} -> {entry['tool']}" for recipe_id, entry in _published_steps() if entry["tool"] not in schemas})

    assert 모르는_도구 == [], f"스키마 snapshot 에 없는 도구를 부른다: {모르는_도구}"


def test_every_published_step_calls_the_tool_its_node_names_in_the_ontology():
    """게시된 server_id · tool 은 그 노드의 tool.id 그대로다. 다르면 다른 도구가 불린다."""
    어긋난_곳 = [
        f"{recipe_id} × {entry['node']}: {entry['server_id']}/{entry['tool']} ≠ {ONTOLOGY.tool_of(entry['node'])['id']}"
        for recipe_id, entry in _published_steps()
        if f"{entry['server_id']}/{entry['tool']}" != ONTOLOGY.tool_of(entry["node"])["id"]
    ]

    assert 어긋난_곳 == [], "\n  ".join(어긋난_곳)


def test_every_required_field_of_the_tool_is_always_sent():
    """required 칸이 빠지면 KRRI 실행기가 부르기 전에 그 단계를 실패로 멈춘다.

    조건(if_endswith · unless_endswith)이 붙은 칸은 인자에 따라 빠지므로 required 를 채운 것으로
    치지 않는다. transform 단계는 게시된 input 이 이미 inputAdapter 뒤의 칸이다.
    """
    schemas = _schemas()
    빠진_칸 = []
    for recipe_id, entry in _published_steps():
        always = {
            field for field, expression in entry["input"].items()
            if not (isinstance(expression, dict) and set(expression) & set(workflow_materializer._CONDITIONS))
        }
        missing = schemas[entry["tool"]][1] - always
        if missing:
            빠진_칸.append(f"{recipe_id} × {entry['node']} -> {entry['tool']} : {sorted(missing)}")

    assert 빠진_칸 == [], "required 칸을 늘 보내지 않는 자리:\n  " + "\n  ".join(빠진_칸)


def _recorded_results(tool):
    """probe_out 에 남은 그 도구의 성공 응답 본문."""
    results = []
    for path in sorted(SCHEMA_PATH.parent.glob(f"{tool}.*.json")):
        body = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(body, dict) and {"status", "body"} <= set(body):
            body = body["body"] if body["status"] == 200 else None
        if isinstance(body, dict) and "error" not in body:
            results.append(body)
    return results


def _reaches(body, raw_path):
    """점으로 이은 dict 키 · 목록 번호 경로가 그 응답 안에 있는가. KRRI 실행기가 푸는 것과 같은 길."""
    current = body
    for segment in raw_path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit() and int(segment) < len(current):
            current = current[int(segment)]
        else:
            return False
    return True


def test_every_output_path_a_later_step_reads_exists_in_a_recorded_response():
    """outputs 의 경로가 실제 응답에 없으면 뒤 단계 참조가 null 로 풀린다. 오류가 아니라 빈 입력이 된다.

    기록된 응답 중 하나에라도 있으면 된다. 0건 응답에는 items.0 이 없다.
    """
    없는_경로 = []
    for recipe_id, entry in _published_steps():
        for type_id, reading in (entry.get("outputs") or {}).items():
            recorded = _recorded_results(entry["tool"])
            raw_paths = [reading["value"]] if "value" in reading else list(reading["fields"].values())
            없는_경로 += [
                f"{recipe_id} × {entry['node']} -> {type_id}: {raw_path} ({len(recorded)}개 응답)"
                for raw_path in raw_paths
                if not any(_reaches(body, raw_path) for body in recorded)
            ]

    assert 없는_경로 == [], "기록된 응답에 없는 출력 경로:\n  " + "\n  ".join(없는_경로)


def _published_inputs(node_id):
    """그 노드가 게시된 도구 단계로 나가는 input 전부."""
    return [entry["input"] for _recipe_id, entry in _published_steps() if entry["node"] == node_id]


@pytest.mark.parametrize(
    "node, tool",
    [
        ("get_railway_lines", "geo.getRailwayLines"),
        ("search_admin_boundaries", "adminBoundary.searchBoundaries"),
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
    inputs = _published_inputs(node)

    assert "bbox" in _props(tool)
    assert any("bbox" in fields for fields in inputs), f"{node} 가 범위를 받는 게시된 recipe 가 없다 — 이 검사가 무력하다"
    for fields in inputs:
        assert not set(BBOX_FIELDS) & set(fields), "좌표가 넷으로 흩어졌다"


def test_a_tool_without_a_bbox_field_gets_the_flat_four():
    """ev.searchStations 에는 bbox 라는 칸이 없다. 보내면 버려진다."""
    inputs = [fields for fields in _published_inputs("search_ev_stations") if set(BBOX_FIELDS) & set(fields)]

    assert "bbox" not in _props("ev.searchStations")
    assert inputs, "충전소를 범위로 찾는 게시된 recipe 가 없다 — 이 검사가 무력하다"
    for fields in inputs:
        assert set(BBOX_FIELDS) <= set(fields) and "bbox" not in fields


# ── 도구 이름이 발화 해석 프롬프트로 새지 않는가 ────────────────────


def _tool_names():
    names = set()
    for tool_id in _tool_ids():
        names.add(tool_id)
        names.add(tool_id.split("/", 1)[1])
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
    for node_id, node in ONTOLOGY.nodes().items():
        글 = " ".join(
            [node["name"], node["description"], str((node.get("source") or {}).get("description") or "")]
        )
        샌_곳 += [f"{node_id}: {이름}" for 이름 in 이름들 if 이름 in 글]

    menu = paths.MENU_YAML_PATH.read_text(encoding="utf-8")
    샌_곳 += [f"menu.yaml: {이름}" for 이름 in 이름들 if 이름 in menu]

    assert 샌_곳 == [], "발화 해석이 읽는 곳에 도구 이름이 샜다:\n  " + "\n  ".join(샌_곳)
