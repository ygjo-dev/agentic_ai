"""대상 : execution/workflow_materializer.py — 게시된 Recipe.execution 을 KRRI native call_mcp_workflow 로 만든다

요청 중에 실행이 지나는 자리다. 온톨로지를 안 읽는다. 블록이 없거나 알아볼 수 없으면
게시 오류로 터지고, 온톨로지로 계획을 다시 만들지 않는다.

부를 수 없는 요청은 문장이 아니라 판정(status)과 모자란 것(missing)으로 돌아온다.
사람에게 보일 문장은 workflow_answer 가 만든다.

여기 블록은 손으로 쓴 작은 것이다. 실제 recipe 에 게시된 블록은
test_published_execution.py 가, 만든 workflow 를 실행기에 넘기는 흐름은
test_legacy_vendor.py 가 본다.

LLM 도 Gateway 도 부르지 않는다.
"""

import copy
import datetime
import zoneinfo

import pytest
import yaml

import paths
from execution import workflow_materializer
from vendor_to_be_deleted.asap import workflow_answer

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

NOW = datetime.datetime(2026, 1, 1, 23, 59, tzinfo=zoneinfo.ZoneInfo("Asia/Seoul"))


def mutated(change):
    execution = copy.deepcopy(EXECUTION)
    change(execution)
    return execution


def native(argument, options=None, execution=EXECUTION):
    """블록 한 벌을 KRRI native workflow 로 채운 것."""
    return workflow_materializer.workflow_of(execution, {"argument": argument, **(options or {})}, NOW)


def published(monkeypatch, tmp_path, execution=EXECUTION, steps=("place_name", "geo", "cctv", "trip")):
    """손으로 쓴 블록을 게시된 recipe 파일 recipe_x 로 둠."""
    document = {"steps": [{"node": node} for node in steps], "execution": execution}
    (tmp_path / "recipe_x.yaml").write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    monkeypatch.setattr(paths, "RECIPES_DIR", tmp_path)


# ── 블록을 읽는다 ──────────────────────────────────────────────────


def test_a_block_in_the_shape_the_recipes_publish_passes():
    workflow_materializer.validate(copy.deepcopy(EXECUTION), "recipe_x")


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
    pytest.param(lambda e: e["workflow"][1].__setitem__("inputAdapter", "point_radius_to_bbox"), "모르는 칸", id="native_adapter_in_the_block"),
    pytest.param(_set_input(2, "to_lon", "$s1.location.0"), "모르는 꼴", id="native_reference_in_the_block"),
]


@pytest.mark.parametrize("change, fragment", UNTRUSTWORTHY_BLOCKS)
def test_a_block_that_cannot_be_trusted_raises(change, fragment):
    """native 표현(inputAdapter · "$s1.location.0")도 블록에 섞이면 터진다. Recipe.execution 은 semantic IR 이다."""
    with pytest.raises(workflow_materializer.PlanError, match=fragment):
        workflow_materializer.validate(mutated(change), "recipe_x")


def test_a_recipe_file_without_a_block_is_a_publication_error(monkeypatch, tmp_path):
    """블록이 없으면 게시가 빠진 것이다. 비워 두고 돌거나 판정으로 삼키거나 다른 원천으로 채우지 않는다."""
    (tmp_path / "recipe_900.yaml").write_text("steps:\n\n  - node: place_name\n", encoding="utf-8")
    monkeypatch.setattr(paths, "RECIPES_DIR", tmp_path)

    with pytest.raises(workflow_materializer.PlanError, match="블록이 없다"):
        workflow_materializer.load("recipe_900")
    with pytest.raises(workflow_materializer.PlanError, match="블록이 없다"):
        workflow_materializer.materialize("recipe_900", {"argument": "오송역"})


def test_an_id_with_no_recipe_file_is_not_an_accepted_recipe(monkeypatch, tmp_path):
    """파일이 없는 것은 게시 오류가 아니라 받아들인 recipe 가 아닌 것이다. 부를 것이 없다."""
    monkeypatch.setattr(paths, "RECIPES_DIR", tmp_path)

    assert workflow_materializer.load("recipe_900") is None
    materialized = workflow_materializer.materialize("recipe_900", {"argument": "오송역"}, SCREEN)
    assert materialized["status"] == workflow_materializer.NOT_ACCEPTED
    assert materialized["workflow"] is None


# ── KRRI native workflow 로 채운다 ───────────────────────────────────


def test_only_the_argument_the_named_values_and_the_moment_are_filled():
    """앞 단계 결과와 화면 값은 참조로 적어 실행기가 푼다. 채우는 것은 셋뿐이다.

    서버 · 도구 이름은 게시된 그대로 나간다. 짧은 이름을 실행기가 정규화해 줄 것에 기대지 않는다.
    """
    built = native("오송역", {"travel_mode": "도보"})
    steps = built["workflow"]["steps"]

    assert built["workflow"]["action"] == workflow_materializer.WORKFLOW_ACTION == "call_mcp_workflow"
    assert [(step["id"], step["server_id"], step["tool"]) for step in steps] == [
        ("s1", "srv", "t.geo"), ("s2", "srv", "t.cctv"), ("s3", "srv", "t.trip"),
    ]
    assert steps[0]["input"] == {"query": "오송역", "mode": "WALK"}
    assert steps[2]["input"] == {
        "from_lon": "$context.selectedLocation.lon",
        "to_lon": "$s1.location.0",
        "date": "2026-01-01",
    }
    assert built["nodes"] == ["geo", "cctv", "trip"]


def test_the_same_type_from_two_producers_is_filled_from_each_producer():
    """화면에서 찍은 지점과 앞 단계가 찾은 지점은 같은 타입이다. 참조가 누가 내놓았는지로 갈린다."""
    sent = native("오송역")["workflow"]["steps"][2]["input"]

    assert sent["from_lon"].startswith("$context.")
    assert sent["to_lon"].startswith("$s1.")


def test_a_transform_becomes_an_explicit_input_adapter_and_its_outputs_are_not_sent():
    """transform 을 여기서 계산하지 않는다. 그 입력을 앞에 두고 inputAdapter 를 명시로 건다.

    transform 이 만드는 칸(minLon …)은 어댑터가 만들므로 안 보낸다. 상수 칸은 뒤에 붙는다.
    실행기의 자동 bbox 추론에 기대지 않는다.
    """
    step = native("오송역")["workflow"]["steps"][1]

    assert step["input"] == {"center": ["$s1.location.0", "$s1.location.1"], "radiusMeters": 15000, "k": 3}
    assert step["inputAdapter"] == workflow_materializer.POINT_RADIUS_TO_BBOX


@pytest.mark.parametrize("argument, sent", [("경부선", True), ("오송역", False), (None, False)])
def test_a_condition_is_decided_by_the_argument_when_the_call_is_made(argument, sent):
    step = native(argument)["workflow"]["steps"][0]

    assert ("railwayName" in step["input"]) is sent


def test_a_named_value_that_was_not_said_takes_the_default():
    for said in (None, {"travel_mode": None}, {"travel_mode": "비행기"}):
        assert native("오송역", said)["workflow"]["steps"][0]["input"]["mode"] == "TRANSIT"


def test_the_published_block_is_not_changed_by_materializing_it():
    """native 표현은 새 dict 에만 적는다. 블록이 바뀌면 다음 요청이 다른 계획을 받는다."""
    execution = copy.deepcopy(EXECUTION)

    built = native("오송역", {"travel_mode": "도보"}, execution)
    built["workflow"]["steps"][1]["input"]["center"].append("x")

    assert execution == EXECUTION


# ── 지금 부를 수 있는가 ─────────────────────────────────────────────
#
# 셋 다 게시된 execution 이 말한다. 못 부르면 다른 recipe 로 갈아타지 않고 판정만 돌려준다.


def test_a_ready_request_carries_the_whole_workflow_and_the_screen_context(monkeypatch, tmp_path):
    """발화 해석 결과를 통째로 받아도 argument 와 이름 있는 값만 읽는다."""
    published(monkeypatch, tmp_path)
    resolved = {"status": "SELECT", "recipe_id": "recipe_x", "argument": "오송역", "travel_mode": "도보", "reason": "…"}

    materialized = workflow_materializer.materialize("recipe_x", resolved, SCREEN, NOW)

    assert materialized["status"] == workflow_materializer.READY
    assert materialized["missing"] == []
    assert materialized["workflow"] == native("오송역", {"travel_mode": "도보"})["workflow"]
    assert materialized["context"] == SCREEN and materialized["context"] is not SCREEN


@pytest.mark.parametrize("argument", [None, ""])
def test_a_recipe_that_uses_the_spoken_argument_is_not_materialized_without_one(monkeypatch, tmp_path, argument):
    """**LLM 이 인자를 안 냈으면 발화를 다시 훑지 않는다.** 무엇을 더 말해야 하는지는 시작 노드가 말한다.

    화면 문맥도 없지만 인자가 먼저다. 인자가 없는 요청에 지점을 찍어 달라고 하면 찍어도 못 부른다.
    """
    published(monkeypatch, tmp_path)

    materialized = workflow_materializer.materialize("recipe_x", {"argument": argument}, None)

    assert materialized["status"] == workflow_materializer.MISSING_ARGUMENT
    assert materialized["missing"] == ["place_name"]
    assert materialized["workflow"] is None


def test_a_recipe_that_uses_no_spoken_argument_is_materialized_without_one(monkeypatch, tmp_path):
    """"지금 보이는 곳 CCTV" 에는 뽑을 말이 없고 조회할 곳은 이미 문맥이 말했다."""
    screen_only = {
        "spoken_needed": False,
        "context_needs": {"point": {"from": "context.selectedLocation", "fields": {"lon": "lon"}}},
        "workflow": [{"id": "s1", "node": "near", "server_id": "srv", "tool": "t.near", "input": {"lon": {"from": "context.point.lon"}}}],
    }
    published(monkeypatch, tmp_path, screen_only, steps=("point", "near"))

    materialized = workflow_materializer.materialize("recipe_x", {"argument": None}, SCREEN, NOW)

    assert materialized["status"] == workflow_materializer.READY
    assert materialized["workflow"]["steps"][0]["input"] == {"lon": "$context.selectedLocation.lon"}


def test_a_recipe_with_an_unwired_node_is_not_materialized(monkeypatch, tmp_path):
    """부르는 것만 부르면 반쪽 결과를 온전한 답인 것처럼 내놓게 된다."""
    published(monkeypatch, tmp_path, {"spoken_needed": False, "unwired": ["cctv"], "context_needs": {}, "workflow": []})

    materialized = workflow_materializer.materialize("recipe_x", {"argument": "오송역"}, SCREEN)

    assert (materialized["status"], materialized["missing"]) == (workflow_materializer.UNWIRED, ["cctv"])


def test_a_recipe_needing_the_screen_context_is_not_materialized_without_it(monkeypatch, tmp_path):
    """**고른 것을 바꾸지 않고 실행만 멈춘다.** 없는 좌표로 부르면 전국이 나오거나 도구가 거부한다."""
    published(monkeypatch, tmp_path)

    for screen in (None, {**SCREEN, "selectedLocation": None}):
        materialized = workflow_materializer.materialize("recipe_x", {"argument": "오송역"}, screen)
        assert (materialized["status"], materialized["missing"]) == (workflow_materializer.MISSING_CONTEXT, ["point"])


def test_a_block_with_nothing_to_call_is_not_materialized(monkeypatch, tmp_path):
    published(monkeypatch, tmp_path, {"spoken_needed": False, "context_needs": {}, "workflow": []})

    assert workflow_materializer.materialize("recipe_x", {"argument": "오송역"})["status"] == workflow_materializer.NOTHING_TO_CALL


def test_the_statuses_the_answer_words_are_named_as_the_materializer_names_them():
    """이름이 갈리면 판정은 맞는데 답이 「부를 도구가 없습니다」 로 떨어진다."""
    for name in ("MISSING_ARGUMENT", "UNWIRED", "MISSING_CONTEXT"):
        assert getattr(workflow_answer, name) == getattr(workflow_materializer, name)


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

    assert workflow_materializer.absent_context(both, SCREEN) == []
    assert workflow_materializer.absent_context(both, {**SCREEN, "selectedLocation": None}) == ["point"]
    assert workflow_materializer.absent_context(both, {"view": {"bbox": []}}) == ["point", "map_extent"]
    assert workflow_materializer.absent_context(both, None) == ["point", "map_extent"]
