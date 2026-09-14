"""대상 : execution/plan_service.py — 게시된 execution 블록을 읽어 ExecutionRequest 로 묶는다

요청 중에 실행이 지나는 자리다. 온톨로지를 안 읽는다. 블록이 없거나 알아볼 수 없으면
게시 오류로 터지고, 온톨로지로 계획을 다시 만들지 않는다.

ExecutionRequest 는 agentic_ai 의 공식 실행 출력이다. 옛 vendor 입력으로 바꾸는 것은
test_legacy_vendor.py 가 본다.

여기 블록은 손으로 쓴 작은 것이다. 실제 recipe 에 게시된 블록은
test_published_execution.py 가 본다.

LLM 도 Gateway 도 부르지 않는다.
"""

import copy
import json

import pytest

import paths
from execution import plan_service

POINT_FIELDS = {"lon": "location.0", "lat": "location.1"}

# 지금 recipe 들이 쓰는 꼴을 한 벌에 모았다. 발화 인자 · 이름 있는 값 · 상수 · 앞 단계 ·
# transform · 화면 값 · 부르는 순간 · 조건.
EXECUTION = {
    "spoken_needed": True,
    "context_needs": {
        "point": {"from": "context.selectedLocation", "fields": {"lon": "lon", "lat": "lat"}},
    },
    "workflow": [
        {
            "id": "s1",
            "node": "geo",
            "server_id": "srv",
            "tool": "t.geo",
            "input": {
                "query": {"from": "spoken.argument"},
                "railwayName": {"from": "spoken.argument", "if_endswith": "선"},
                "mode": {"from": "spoken.travel_mode", "default": "대중교통", "map": {"도보": "WALK", "대중교통": "TRANSIT"}},
            },
            "outputs": {"point": {"fields": POINT_FIELDS}},
        },
        {
            "id": "s2",
            "node": "cctv",
            "server_id": "srv",
            "tool": "t.cctv",
            "transform": {
                "id": "builtin/geo.pointRadiusToBbox",
                "node": "widen",
                "input": {"center": [{"from": "s1.point.lon"}, {"from": "s1.point.lat"}], "radiusMeters": {"value": 15000}},
            },
            "input": {"minLon": {"from": "transform.map_extent.minLon"}, "k": {"value": 3}},
        },
        {
            "id": "s3",
            "node": "trip",
            "server_id": "srv",
            "tool": "t.trip",
            "input": {
                "from_lon": {"from": "context.point.lon"},
                "to_lon": {"from": "s1.point.lon"},
                "date": {"from": "runtime.now.date"},
            },
        },
    ],
}

SCREEN = {"view": {"bbox": [[127.20, 36.55], [127.40, 36.70]]}, "selectedLocation": {"lon": 127.2974, "lat": 36.6199}}


def mutated(change):
    execution = copy.deepcopy(EXECUTION)
    change(execution)
    return execution


# ── 블록을 읽는다 ──────────────────────────────────────────────────


def test_a_block_in_the_shape_the_recipes_publish_passes():
    plan_service.validate(copy.deepcopy(EXECUTION), "recipe_x")


def _set_input(index, field, value):
    return lambda execution: execution["workflow"][index]["input"].__setitem__(field, value)


# 알아볼 수 없는 블록은 전부 터진다. 조용히 넘기면 없는 칸 · 빈 참조가 도구에 실려 나간다.
UNTRUSTWORTHY_BLOCKS = [
    pytest.param(lambda e: e.clear(), "spoken_needed", id="empty_block"),
    pytest.param(lambda e: e.__setitem__("workflow", {}), "workflow", id="workflow_not_a_list"),
    pytest.param(lambda e: e.__setitem__("steps", []), "모르는 칸", id="unknown_field"),
    pytest.param(lambda e: e["workflow"][1].__setitem__("id", "s1"), "겹친다", id="duplicate_step_id"),
    pytest.param(lambda e: e["workflow"][0].pop("node"), "node", id="no_node"),
    pytest.param(lambda e: e["workflow"][0].pop("tool"), "tool", id="no_tool"),
    pytest.param(lambda e: e["workflow"][0].pop("server_id"), "server_id", id="no_server"),
    pytest.param(_set_input(0, "query", "오송역"), "모르는 꼴", id="raw_value_in_input"),
    pytest.param(_set_input(0, "query", {"from": "s2.point.lon"}), "앞선 도구 단계", id="future_step"),
    pytest.param(_set_input(2, "to_lon", {"from": "s9.point.lon"}), "앞선 도구 단계", id="unknown_step"),
    pytest.param(_set_input(2, "to_lon", {"from": "s1.admin_code.code"}), "outputs", id="undeclared_output"),
    pytest.param(_set_input(2, "to_lon", {"from": "s1.point.x"}), "칸이 선언에 없다", id="undeclared_output_field"),
    pytest.param(lambda e: e["workflow"][1]["transform"].pop("node"), "transform", id="transform_shape"),
    pytest.param(lambda e: e["workflow"][1]["transform"].__setitem__("id", "builtin/geo.buffer"), "모르는 transform", id="unknown_transform"),
    pytest.param(_set_input(2, "x", {"from": "transform.map_extent.minLon"}), "transform 이 있는 단계", id="transform_without_transform"),
    pytest.param(_set_input(2, "from_lon", {"from": "context.map_extent.minLon"}), "선언 안 된 화면 값", id="undeclared_context"),
    pytest.param(_set_input(0, "query", {"from": "spoken.argument", "default": "x"}), "조건 하나", id="spoken_argument_with_default"),
    pytest.param(_set_input(0, "mode", {"from": "spoken.travel_mode"}), "default", id="named_value_without_default"),
    pytest.param(_set_input(2, "date", {"from": "runtime.now.datetime"}), "runtime.now", id="unknown_runtime"),
    pytest.param(lambda e: e.__setitem__("spoken_needed", False), "spoken_needed", id="spoken_needed_disagrees"),
    pytest.param(lambda e: e.__setitem__("unwired", ["cctv"]), "unwired", id="unwired_with_workflow"),
    pytest.param(lambda e: e["context_needs"]["point"].__setitem__("from", "screen.selectedLocation"), "context", id="context_not_from_context"),
]


@pytest.mark.parametrize("change, fragment", UNTRUSTWORTHY_BLOCKS)
def test_a_block_that_cannot_be_trusted_raises(change, fragment):
    with pytest.raises(plan_service.PlanError, match=fragment):
        plan_service.validate(mutated(change), "recipe_x")


def test_a_recipe_file_without_a_block_is_a_publication_error(monkeypatch, tmp_path):
    """블록이 없으면 게시가 빠진 것이다. 비워 두고 돌거나 다른 원천으로 채우지 않는다."""
    (tmp_path / "recipe_900.yaml").write_text("steps:\n\n  - node: place_name\n", encoding="utf-8")
    monkeypatch.setattr(paths, "RECIPES_DIR", tmp_path)

    with pytest.raises(plan_service.PlanError, match="블록이 없다"):
        plan_service.load("recipe_900")


def test_an_id_with_no_recipe_file_is_not_an_accepted_recipe(monkeypatch, tmp_path):
    """파일이 없는 것은 게시 오류가 아니라 받아들인 recipe 가 아닌 것이다. 부를 것이 없다."""
    monkeypatch.setattr(paths, "RECIPES_DIR", tmp_path)

    assert plan_service.load("recipe_900") is None


# ── ExecutionRequest ────────────────────────────────────────────────


def test_a_request_is_the_published_workflow_with_this_requests_spoken_values_and_context():
    """정적 계획은 그대로 두고 이번 요청의 값만 봉투로 붙인다.

    workflow 를 다시 적으면 게시된 계획과 실행 계층이 받는 계획이 두 모양이 된다. 발화 값과
    화면 문맥은 기호 안에 채우지 않고 따로 싣는다. 같은 입력이면 같은 한 벌이다.
    """
    request = plan_service.request("recipe_x", EXECUTION, "오송역", {"travel_mode": "도보", "minutes": None}, SCREEN)

    assert tuple(request) == ("recipe_id", "spoken", "context", "context_needs", "workflow")
    assert request["recipe_id"] == "recipe_x"
    assert request["spoken"] == {"argument": "오송역", "travel_mode": "도보", "minutes": None}
    assert request["context"] == SCREEN
    assert request["context_needs"] == EXECUTION["context_needs"]
    assert request["workflow"] == EXECUTION["workflow"]
    assert json.dumps(request, ensure_ascii=False) == json.dumps(
        plan_service.request("recipe_x", EXECUTION, "오송역", {"travel_mode": "도보", "minutes": None}, SCREEN),
        ensure_ascii=False,
    )


def test_the_request_keeps_every_symbol_the_published_plan_declares():
    """앞 단계 참조 · 내놓는 쪽 경로 · transform · 부르는 순간 · 조건이 기호 그대로 남는다.

    누가 내놓았는지(s1.point.lon)는 받는 쪽에, raw 경로(location.0)는 내놓는 단계의
    outputs 에만 있다. 여기서 풀면 경로를 정하는 쪽이 실행 계층으로 넘어간다.
    """
    request = plan_service.request("recipe_x", EXECUTION, "경부선", None, SCREEN)
    geo, cctv, trip = request["workflow"]

    assert trip["input"]["to_lon"] == {"from": "s1.point.lon"}
    assert trip["input"]["from_lon"] == {"from": "context.point.lon"}
    assert geo["outputs"] == {"point": {"fields": POINT_FIELDS}}
    assert "location.0" not in json.dumps([cctv["input"], trip["input"]])
    assert cctv["transform"]["id"] == "builtin/geo.pointRadiusToBbox"
    assert trip["input"]["date"] == {"from": "runtime.now.date"}
    assert geo["input"]["railwayName"] == {"from": "spoken.argument", "if_endswith": "선"}


def test_the_request_does_not_change_the_published_block():
    """요청마다 같은 블록을 읽는다. 봉투를 고치다 블록이 바뀌면 다음 요청이 다른 계획을 받는다."""
    execution = copy.deepcopy(EXECUTION)

    request = plan_service.request("recipe_x", execution, "오송역", None, SCREEN)
    request["workflow"][1]["transform"]["input"]["center"].append("x")

    assert execution == EXECUTION


@pytest.mark.parametrize(
    "change, fragment",
    [
        pytest.param(lambda r: r["workflow"][1].__setitem__("inputAdapter", "point_radius_to_bbox"), "모르는 칸", id="vendor_adapter_name"),
        pytest.param(lambda r: r["workflow"][2]["input"].__setitem__("to_lon", "$s1.location.0"), "모르는 꼴", id="vendor_raw_reference"),
        pytest.param(lambda r: r.__setitem__("answer_instruction", "…"), "칸은", id="vendor_answer_field"),
        pytest.param(lambda r: r["spoken"].pop("argument"), "argument", id="no_spoken_argument"),
    ],
)
def test_a_request_in_the_legacy_vendor_shape_is_not_a_request(change, fragment):
    """옛 vendor 표현은 계약이 아니다. 섞이면 계약 검사에서 터진다."""
    request = plan_service.request("recipe_x", EXECUTION, "오송역", None, SCREEN)
    change(request)

    with pytest.raises(plan_service.PlanError, match=fragment):
        plan_service.validate_request(request)


def test_a_missing_screen_value_is_named_in_the_published_order():
    """KRRI_ASAP 은 우클릭 전에 selectedLocation 을 null 로 보낸다. 빈 bbox 도 마찬가지."""
    both = {
        "spoken_needed": False,
        "context_needs": {
            "point": {"from": "context.selectedLocation", "fields": {"lon": "lon"}},
            "map_extent": {"from": "context.view.bbox", "fields": {"minLon": "0.0"}},
        },
        "workflow": [],
    }

    assert plan_service.absent_context(both, SCREEN) == []
    assert plan_service.absent_context(both, {**SCREEN, "selectedLocation": None}) == ["point"]
    assert plan_service.absent_context(both, {"view": {"bbox": []}}) == ["point", "map_extent"]
    assert plan_service.absent_context(both, None) == ["point", "map_extent"]
