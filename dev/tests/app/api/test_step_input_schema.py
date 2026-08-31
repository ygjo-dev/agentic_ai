"""배선이 보내는 칸이 도구 스키마에 있는 칸인가.

**이 시험이 잡는 고장은 조용하다.** 없는 칸을 보내도 도구는 오류를 안 낸다 —
모르는 칸이라 버리고 인자 없이 부른 것처럼 답한다. 2026-08-30 에
`("search_ev_stations", "map_extent")` 의 첫 자리가 그랬다. `{"bbox": …}` 를
보냈는데 ev.searchStations 에는 bbox 라는 칸이 없어서(minLon · minLat ·
maxLon · maxLat 평평한 넷이다) 지도를 아무리 좁혀도 전국 92,821건에서
상한 500건이 왔다. NOTES.md 「예순째」.

LLM 도 서버도 안 부른다. STEP_OF 와 tools/probe_out/tools.json 만 읽는다.
그 snapshot 은 tools/check_inputs.py 가 쓰는 것과 같은 파일이라 계기판과
시험이 같은 근거를 본다.
"""

import json
from pathlib import Path

import pytest

from app.api.services import step_service

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "tools" / "probe_out" / "tools.json"

# 어댑터가 걸리면 중심 좌표 · 반경 대신 bbox 넷이 나간다. 걸리는 조건은
# check_inputs.sent_fields 와 같다 — STEP_OF 에 이름이 적혀 있고 중심 좌표가
# 있거나, 안 적혀 있어도 bbox 넷이 전부 required 라 vendor 가 저절로 거는 것
# (_should_auto_apply_point_radius_to_bbox). 걸린 줄은 스키마 대조에서 뺀다.
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
    """(노드, 타입, 자리 이름, 도구 이름, 보내는 칸 집합) 을 죽 편다."""
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


def test_every_field_the_wiring_sends_exists_in_the_schema():
    """없는 칸은 버려진다. 조용히 전국을 뒤지는 길이 그것이다."""
    없는_칸 = [
        f"{node} × {kind} ({variant}) -> {tool} : {sorted(fields - props)}"
        for node, kind, variant, tool, fields, props in _rows()
        if fields - props
    ]
    assert 없는_칸 == [], "스키마에 없는 칸을 보내는 줄:\n  " + "\n  ".join(없는_칸)


def test_ev_stations_send_the_flat_four_in_the_first_slot_too():
    """2026-08-30 의 그 줄. ev.searchStations 에 bbox 라는 칸은 없다."""
    wiring = step_service.STEP_OF[("search_ev_stations", "map_extent")]

    assert wiring["input_first"] == {
        "minLon": "$context.view.minLon",
        "minLat": "$context.view.minLat",
        "maxLon": "$context.view.maxLon",
        "maxLat": "$context.view.maxLat",
    }
    assert "bbox" not in _props("ev.searchStations")


def test_the_previous_step_slot_for_ev_stations_is_unchanged():
    """「오송역 근처 충전소」가 도는 길이다. 첫 자리를 고치면서 안 건드렸다."""
    wiring = step_service.STEP_OF[("search_ev_stations", "map_extent")]

    assert wiring["input"] == {
        "center": f"{step_service.PREVIOUS_STEP}.location",
        "radiusMeters": step_service.RADIUS_METERS,
    }
    assert wiring["adapter"] == step_service.POINT_RADIUS_TO_BBOX


# 이 넷은 스키마가 **진짜로** bbox 배열을 받는다. ev 를 고치면서 같이 고치면
# 오히려 깨진다 — 2026-08-30 에 확인하고 안 고쳤다. 그 확인을 여기 박아 둔다.
@pytest.mark.parametrize(
    "node, tool",
    [
        ("get_railway_lines", "geo.getRailwayLines"),
        ("search_admin_boundaries", "adminBoundary.searchBoundaries"),
        ("get_vworld_boundaries", "vworld.getAdministrativeBoundaries"),
        ("search_population_statistics", "population.searchStatistics"),
    ],
)
def test_the_four_taking_a_bbox_array_still_send_one_bbox_field(node, tool):
    wiring = step_service.STEP_OF[(node, "map_extent")]

    assert "bbox" in _props(tool)
    assert wiring["input_first"] == {"bbox": step_service.BBOX_FROM_CONTEXT}
    assert wiring["input"] == {"bbox": step_service.BBOX_FROM_PREVIOUS}


def test_the_visible_extent_four_are_ordered_minLon_minLat_maxLon_maxLat():
    """평평한 넷으로 풀어 적을 때 이 순서를 믿는다."""
    assert step_service.BBOX_FROM_CONTEXT == [
        "$context.view.minLon",
        "$context.view.minLat",
        "$context.view.maxLon",
        "$context.view.maxLat",
    ]
