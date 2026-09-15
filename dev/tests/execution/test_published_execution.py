"""대상 : 받아들인 recipe 파일에 게시된 execution — 요청 중에 실행이 읽는 원천

    온톨로지 + 사람이 받아들인 steps  ->  recipe_execution_builder.compile_execution  ->  recipe 파일의 execution

**온톨로지는 compile 의 원천이고 게시된 블록은 요청 중의 원천이다.** 온톨로지 · steps 를
고치고 다시 게시하지 않으면 여기서 빨개진다. 다시 적는 법은 둘이다.

    python -m registration.publish          작업본
    python -m registration.publish --init   _init 사본

**후보는 게시 대상이 아니다.** 후보는 파일이 아니고 사람이 받아들인 것만 execution 을 갖는다.

개수를 박지 않는다. 사슬로 recipe 를 찾는다 — 번호가 밀려도 그대로다.
LLM 도 Gateway 도 부르지 않는다.
"""

import datetime
import json

import pytest
import yaml

import paths
from execution import workflow_materializer
from ontology import graph, store
from registration import publish, recipe_execution_builder
from registration.registry import accepted_recipes, candidate_recipes
from workflows.static.menu.load import load_menu


def recipe_of(chain):
    """그 사슬을 가진 recipe id."""
    for recipe_id in graph.recipe_ids():
        if graph.recipe_nodes(recipe_id) == list(chain):
            return recipe_id
    raise AssertionError(f"그런 사슬의 recipe 가 없다: {chain}")


def recipe_files():
    files = sorted(paths.RECIPES_DIR.glob("recipe_*.yaml"))
    assert files, "recipe 파일이 없다 — 이 검사가 무력하다"
    return files


# ── 게시된 것이 지금 compile 한 것과 같은가 ──────────────────────────


@pytest.mark.parametrize("pair", ["work", "init"])
def test_every_accepted_recipe_file_is_exactly_what_publishing_writes_now(monkeypatch, pair):
    """게시된 블록 == 지금 온톨로지와 steps 로 다시 compile 한 블록. 글자까지 본다.

    낡은 블록이 남으면 온톨로지를 고친 것이 실행에 안 닿고, 아무도 모른 채 옛 도구 ·
    옛 칸으로 부른다. _init 짝도 본다 — 초기화가 그 사본을 작업본으로 복사한다.
    """
    if pair == "init":
        monkeypatch.setattr(paths, "ONTOLOGY_PATH", paths.INIT_ONTOLOGY_PATH)
        monkeypatch.setattr(paths, "RECIPES_DIR", paths.INIT_RECIPES_DIR)

    stale = [path.stem for path in recipe_files() if publish.published_text(path.read_text(encoding="utf-8")) != path.read_text(encoding="utf-8")]

    assert stale == [], f"다시 게시해야 할 recipe 가 있다 (python -m registration.publish{' --init' if pair == 'init' else ''}): {stale}"


def test_every_published_block_passes_the_runtime_check_and_equals_a_fresh_compile():
    """요청 중에 읽는 모양으로도 같다. 실행이 받아 주지 않는 블록은 게시된 것이 아니다."""
    for recipe_id in graph.recipe_ids():
        assert workflow_materializer.load(recipe_id) == recipe_execution_builder.compile_execution(graph.recipe_nodes(recipe_id)), recipe_id


# KRRI native workflow 에만 있는 표현과 옛 vendor 답 지시. Recipe.execution 에 보이면 IR 이 native 로 샌 것이다.
NATIVE_MARKERS = (
    '"$', "inputAdapter", "answer_instruction", "headline",
    workflow_materializer.POINT_RADIUS_TO_BBOX, workflow_materializer.WORKFLOW_ACTION,
)


def test_every_published_execution_stays_semantic_with_no_krri_native_form():
    """Recipe.execution 은 agentic_ai 안의 semantic IR 이다. native 표현은 요청 중에 materializer 가 적는다.

    "$s1.location.0" · inputAdapter 가 게시된 블록에 보이면 raw 참조와 어댑터 이름이 게시 계약으로
    새어 든 것이고, 실행기가 바뀌는 날 받아들인 recipe 를 전부 다시 게시해야 한다.
    """
    for recipe_id in graph.recipe_ids():
        text = json.dumps(workflow_materializer.load(recipe_id), ensure_ascii=False)

        assert [marker for marker in NATIVE_MARKERS if marker in text] == [], recipe_id


def test_publishing_leaves_the_human_accepted_part_as_it_was():
    """steps · example 은 사람의 판정이다. 게시는 파일 끝의 execution 칸만 붙인다.

    execution 칸을 떼면 사람이 쓴 원문이 글자 그대로 남아야 한다. yaml 로 통째로
    다시 쓰면 모양과 주석이 날아간다.
    """
    for path in recipe_files():
        text = path.read_text(encoding="utf-8")
        human = publish._without_execution(text).rstrip("\n")
        document = yaml.safe_load(text)

        assert text.startswith(human + "\n\nexecution:\n"), path.stem
        assert yaml.safe_load(human) == {key: value for key, value in document.items() if key != "execution"}, path.stem


def test_a_candidate_is_computed_not_published():
    """후보를 계산해도 recipe 파일은 늘지도 바뀌지도 않는다. 받아들이지 않은 후보는 execution 을 안 갖는다."""
    before = {path.name: path.read_bytes() for path in paths.RECIPES_DIR.glob("*.yaml")}

    candidates = candidate_recipes(store.nodes())
    accepted = {tuple(chain) for chain in accepted_recipes().values()}

    assert {path.name: path.read_bytes() for path in paths.RECIPES_DIR.glob("*.yaml")} == before
    assert [chain for chain in candidates if tuple(chain) not in accepted], "안 받아들인 후보가 없으면 이 검사가 무력하다"


def test_the_menu_the_llm_reads_carries_no_execution():
    """LLM 은 menu 만 보고 recipe 를 고른다. 게시된 실행 계획은 프롬프트에 안 실린다.

    실리면 LLM 이 도구 순서를 지어낼 재료를 얻고, menu 가 커져 컨텍스트 예산을 넘는다.
    """
    menu = load_menu()
    menu_ids = set((yaml.safe_load(menu).get("recipes") or {}))

    for marker in ("execution", "workflow", "server_id", "spoken_needed", "context_needs", "transform"):
        assert marker not in menu, marker
    assert menu_ids == set(graph.recipe_ids())


# ── 대표 자리 ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "chain, index, field, symbol",
    [
        # 발화 -> 도구
        (["place_name", "geocode_place"], 0, "query", {"from": "spoken.argument"}),
        # 화면 -> 도구
        (["map_extent", "find_cctv"], 0, "minLon", {"from": "context.map_extent.minLon"}),
        # 앞 도구 -> 다음 도구
        (["point", "find_admin_boundary_by_point", "get_age_profile"], 1, "code", {"from": "s1.admin_code.code"}),
        # 상수
        (["keyword", "search_documents"], 0, "k", {"value": 6}),
        # 이름 있는 값의 기본
        (["keyword", "search_admin_boundaries"], 0, "layer",
         {"from": "spoken.admin_level", "default": "시군구", "map": {"시도": "sido", "시군구": "sigungu", "읍면동": "emd"}}),
    ],
    ids=["spoken_to_tool", "context_to_tool", "previous_to_next", "literal", "named_default"],
)
def test_a_published_input_says_where_its_value_comes_from(chain, index, field, symbol):
    execution = workflow_materializer.load(recipe_of(chain))

    assert execution["workflow"][index]["input"][field] == symbol


CCTV_AROUND_A_PLACE = ["place_name", "geocode_place", "point_to_map_extent", "find_cctv"]


def test_the_radius_widening_stays_a_declared_transform_of_the_cctv_call_not_a_call_of_its_own():
    """장소 -> 좌표 -> 지점 주변 범위 -> CCTV. 사람이 받아들인 경로는 넷이고 부르는 도구는 둘이다.

    지점 주변 범위 변환은 builtin 이라 따로 부르는 도구가 아니다. 가짜 MCP 단계로 늘리지
    않고 CCTV 단계의 transform 으로 선언한다. 좌표 변환이 내놓은 지점이 transform 의
    입력이고 transform 이 만드는 범위가 CCTV 의 칸이다. 게시된 블록에는 transform id 로 남고,
    KRRI native workflow 에서는 명시한 inputAdapter 가 된다. 실행기의 자동 bbox 추론에 기대지 않는다.
    """
    recipe_id = recipe_of(CCTV_AROUND_A_PLACE)
    execution = workflow_materializer.load(recipe_id)
    geocode, cctv = execution["workflow"]

    assert graph.recipe_nodes(recipe_id) == CCTV_AROUND_A_PLACE
    assert (geocode["node"], cctv["node"]) == ("geocode_place", "find_cctv")
    assert geocode["outputs"] == {"point": {"fields": {"lon": "location.0", "lat": "location.1"}}}
    assert cctv["transform"] == {
        "id": "builtin/geo.pointRadiusToBbox",
        "node": "point_to_map_extent",
        "input": {"center": [{"from": "s1.point.lon"}, {"from": "s1.point.lat"}], "radiusMeters": {"value": 15000}},
    }
    assert cctv["input"] == {field: {"from": f"transform.map_extent.{field}"} for field in ("minLon", "minLat", "maxLon", "maxLat")}

    materialized = workflow_materializer.materialize(recipe_id, {"argument": "오송역"})
    assert materialized["status"] == workflow_materializer.READY
    assert materialized["workflow"] == {
        "action": "call_mcp_workflow",
        "steps": [
            {"id": "s1", "server_id": "asap-mcp-core", "tool": "geo.geocode", "input": {"query": "오송역"}},
            {
                "id": "s2",
                "server_id": "asap-mcp-core",
                "tool": "road.getCctv",
                "input": {"center": ["$s1.location.0", "$s1.location.1"], "radiusMeters": 15000},
                "inputAdapter": workflow_materializer.POINT_RADIUS_TO_BBOX,
            },
        ],
    }
    assert materialized["nodes"] == ["geocode_place", "find_cctv"]
    assert materialized["commands"] == []


ROUTE = ["place_name", "geocode_place", "plan_trip"]


def test_the_origin_point_and_the_destination_point_keep_their_own_producers():
    """경로 탐색의 두 좌표는 둘 다 「지점 좌표」다. 누가 내놓았는지로만 갈린다.

    출발은 화면이 찍은 지점(context_needs 의 point), 도착은 좌표 변환 단계 s1 이 찾은
    지점이다. 타입만 보고 아무 지점이나 이으면 반대 방향 길이 나오고 도구는 오류를 안 낸다.

    raw 경로(location.0)는 내놓는 쪽 s1 의 outputs 에만 있고 받는 쪽은 semantic 칸만 가리킨다.
    native 참조("$s1.location.0")는 materializer 가 두 선언을 이어 적을 때만 나온다.
    부르는 순간은 실제 날짜 · 시각 글자로 나간다.
    """
    execution = workflow_materializer.load(recipe_of(ROUTE))
    trip = execution["workflow"][-1]["input"]

    assert execution["context_needs"] == {
        "point": {"from": "context.selectedLocation", "fields": {"lon": "lon", "lat": "lat"}}
    }
    assert (trip["from_lon"], trip["from_lat"]) == ({"from": "context.point.lon"}, {"from": "context.point.lat"})
    assert (trip["to_lon"], trip["to_lat"]) == ({"from": "s1.point.lon"}, {"from": "s1.point.lat"})

    assert execution["workflow"][0]["outputs"] == {"point": {"fields": {"lon": "location.0", "lat": "location.1"}}}
    assert "outputs" not in execution["workflow"][-1]
    assert "location" not in json.dumps(trip)

    now = datetime.datetime(2026, 1, 1, 23, 59, tzinfo=workflow_materializer.RUNTIME_ZONE)
    picked = {"selectedLocation": {"lon": 127.29, "lat": 36.61}}
    materialized = workflow_materializer.materialize(recipe_of(ROUTE), {"argument": "조치원역"}, picked, now)

    assert materialized["status"] == workflow_materializer.READY
    assert materialized["workflow"]["steps"][-1] == {
        "id": "s2",
        "server_id": "otp-router",
        "tool": "otp_plan_trip",
        "input": {
            "from_lat": "$context.selectedLocation.lat",
            "from_lon": "$context.selectedLocation.lon",
            "to_lat": "$s1.location.1",
            "to_lon": "$s1.location.0",
            "date": "2026-01-01",
            "time_kst": "23:59",
        },
    }
    assert materialized["context"] == picked

    unpicked = workflow_materializer.materialize(recipe_of(ROUTE), {"argument": "조치원역"}, {"selectedLocation": None})
    assert (unpicked["status"], unpicked["missing"]) == (workflow_materializer.MISSING_CONTEXT, ["point"])
