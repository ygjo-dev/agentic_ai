"""대상 : execution/plan_service.py — 게시된 execution 블록을 읽어 vendor 계획으로 채운다

요청 중에 실행이 지나는 자리다. 온톨로지를 안 읽는다. 블록이 없거나 알아볼 수 없으면
게시 오류로 터지고, 온톨로지로 계획을 다시 만들지 않는다.

여기 블록은 손으로 쓴 작은 것이다. 실제 recipe 에 게시된 블록은
test_published_execution.py 가 본다.

LLM 도 Gateway 도 부르지 않는다.
"""

import copy
import datetime
import zoneinfo

import pytest

import paths
from execution import plan_service

NOW = datetime.datetime(2026, 1, 1, 23, 59, tzinfo=zoneinfo.ZoneInfo("Asia/Seoul"))

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


@pytest.fixture
def headlines(monkeypatch):
    for node in ("geo", "cctv", "trip"):
        monkeypatch.setitem(plan_service.HEADLINE, node, "{arg} 를 조회했습니다.")


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


# ── 채운다 ──────────────────────────────────────────────────────────


def test_only_the_argument_the_named_values_and_the_moment_are_filled(headlines):
    """앞 단계 결과와 화면 값은 참조로 적어 vendor 가 푼다. 여기서 채우는 것은 셋뿐이다."""
    plan = plan_service.bind(EXECUTION, "오송역", {"travel_mode": "도보"}, NOW)

    assert plan["steps"][0]["input"] == {"query": "오송역", "mode": "WALK"}
    assert plan["steps"][2]["input"] == {
        "from_lon": "$context.selectedLocation.lon",
        "to_lon": "$s1.location.0",
        "date": "2026-01-01",
    }
    assert plan["nodes"] == ["geo", "cctv", "trip"]
    assert plan["headline"] == "오송역 를 조회했습니다."


def test_the_same_type_from_two_producers_is_filled_from_each_producer(headlines):
    """화면에서 찍은 지점과 앞 단계가 찾은 지점은 같은 타입이다. 참조가 누가 내놓았는지로 갈린다."""
    sent = plan_service.bind(EXECUTION, "오송역", None, NOW)["steps"][2]["input"]

    assert sent["from_lon"].startswith("$context.")
    assert sent["to_lon"].startswith("$s1.")


def test_a_transform_becomes_the_vendor_input_adapter_and_its_outputs_are_not_sent(headlines):
    """transform 은 여기서 계산하지 않는다. 그 입력을 앞에 두고 vendor 어댑터 이름을 건다.

    transform 이 만드는 칸(minLon …)은 어댑터가 만들므로 안 보낸다. 상수 칸은 뒤에 붙는다.
    """
    step = plan_service.bind(EXECUTION, "오송역", None, NOW)["steps"][1]

    assert step["input"] == {"center": ["$s1.location.0", "$s1.location.1"], "radiusMeters": 15000, "k": 3}
    assert step["inputAdapter"] == plan_service.POINT_RADIUS_TO_BBOX


@pytest.mark.parametrize("argument, sent", [("경부선", True), ("오송역", False), (None, False)])
def test_a_condition_is_decided_by_the_argument_when_the_call_is_made(headlines, argument, sent):
    step = plan_service.bind(EXECUTION, argument, None, NOW)["steps"][0]

    assert ("railwayName" in step["input"]) is sent


def test_a_named_value_that_was_not_said_takes_the_default(headlines):
    for said in (None, {"travel_mode": None}, {"travel_mode": "비행기"}):
        assert plan_service.bind(EXECUTION, "오송역", said, NOW)["steps"][0]["input"]["mode"] == "TRANSIT"


def test_the_published_block_is_not_changed_by_filling_it(headlines):
    """요청마다 같은 블록을 읽는다. 채우다 블록이 바뀌면 다음 요청이 다른 계획을 받는다."""
    execution = copy.deepcopy(EXECUTION)

    plan = plan_service.bind(execution, "오송역", {"travel_mode": "도보"}, NOW)
    plan["steps"][1]["input"]["center"].append("x")

    assert execution == EXECUTION


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
    full = {"view": {"bbox": [[127.20, 36.55], [127.40, 36.70]]}, "selectedLocation": {"lon": 127.2974, "lat": 36.6199}}

    assert plan_service.absent_context(both, full) == []
    assert plan_service.absent_context(both, {**full, "selectedLocation": None}) == ["point"]
    assert plan_service.absent_context(both, {"view": {"bbox": []}}) == ["point", "map_extent"]
    assert plan_service.absent_context(both, None) == ["point", "map_extent"]


# ── 답 첫 줄 ────────────────────────────────────────────────────────


def test_the_argument_is_not_prefixed_when_it_is_already_in_the_preamble():
    """"전기차 충전소 데이터 검색해줘" 가 "전기차 충전소 전기차 충전소를 조회했습니다."

    틀이 "{arg} 전기차 충전소를 조회했습니다." 이고 인자도 "전기차 충전소" 라
    같은 말이 두 번 나갔음(실측).
    """
    assert plan_service._headline("{arg} 전기차 충전소를 조회했습니다.", "전기차 충전소") == (
        "전기차 충전소를 조회했습니다."
    )


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
    saved = dict(plan_service.HEADLINE)
    mtime = plan_service._wiring_mtime
    yield
    plan_service.HEADLINE.clear()
    plan_service.HEADLINE.update(saved)
    plan_service._wiring_mtime = mtime


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
        plan_service._load_wiring()


def test_a_broken_file_does_not_empty_the_tables(tmp_path, monkeypatch, restore_tables):
    """터져도 반만 바뀐 표가 남지 않는다.

    표를 다 만든 뒤에 갈아 넣는다. 빈 표보다 반쪽 표가 나쁘다 — 계기판이
    멀쩡한 모양으로 틀린 수를 찍는다.
    """
    before = dict(plan_service.HEADLINE)

    path = tmp_path / "wiring.yaml"
    path.write_text("headline: {깨진다\n", encoding="utf-8")
    monkeypatch.setattr(paths, "WIRING_PATH", path)

    with pytest.raises(Exception):
        plan_service._load_wiring()

    assert plan_service.HEADLINE == before


def test_reload_reads_again_when_mtime_changes(tmp_path, monkeypatch, restore_tables):
    """mtime 이 바뀌면 다시 읽는다. 안 바뀌면 안 읽는다.

    파일을 고치면 서버를 안 내리고 반영되어야 한다.
    """
    path = tmp_path / "wiring.yaml"
    path.write_text(VALID_WIRING, encoding="utf-8")
    monkeypatch.setattr(paths, "WIRING_PATH", path)
    monkeypatch.setattr(plan_service, "_wiring_mtime", None)

    plan_service.reload_wiring()
    assert plan_service.HEADLINE["n"] == "하나"

    # 파일을 안 건드리면 다시 안 판다. 손으로 얹은 줄이 살아 있으면 안 판 것이다.
    plan_service.HEADLINE["표시"] = "안 판다"
    plan_service.reload_wiring()
    assert "표시" in plan_service.HEADLINE

    stat = path.stat()
    path.write_text(VALID_WIRING.replace("하나", "둘"), encoding="utf-8")
    if path.stat().st_mtime_ns == stat.st_mtime_ns:  # 시계가 굵은 파일시스템
        import os

        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    plan_service.reload_wiring()
    assert plan_service.HEADLINE["n"] == "둘"
    assert "표시" not in plan_service.HEADLINE
