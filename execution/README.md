# execution — 발화 하나가 KRRI_ASAP 요청이 되기까지

예시: recipe_036 (장소 주변 CCTV)

> **수원역 근처 CCTV 띄워줘**
>
> 공식 평가 v1 case 14

## 1. agentic_ai `POST /chat/stream` 입력

`app/api/schemas/requests.py` `ChatRequest`

```json
{
  "text": "수원역 근처 CCTV 띄워줘",
  "context": {}
}
```

## 2. Resolve 결과

`orchestrator/resolve_service.py` `resolve`. 값은 공식 평가 run `20260922-163007-test_suite_v1` case 14 의 기록입니다.

```json
{
  "reason": "…",
  "candidate_recipe_ids": ["recipe_036"],
  "status": "SELECT",
  "recipe_id": "recipe_036",
  "argument": "수원역",
  "travel_mode": null,
  "minutes": null,
  "admin_level": null,
  "paths": { "recipe_036": ["…"] }
}
```

## 3. Accepted Recipe.execution

`KRRI_Ontology_Registry/recipes/recipe_036.yaml`

```yaml
execution:
  spoken_needed: true
  context_needs: {}
  workflow:
    - id: s1
      node: geocode_place
      server_id: asap-mcp-core
      tool: geo.geocode
      input:
        query: {from: spoken.argument}
      outputs:
        point: {fields: {lon: location.0, lat: location.1}}

    - id: s2
      node: find_cctv
      server_id: asap-mcp-core
      tool: road.getCctv
      transform:
        id: builtin/geo.pointRadiusToBbox
        node: point_to_map_extent
        input:
          center: [{from: s1.point.lon}, {from: s1.point.lat}]
          radiusMeters: {value: 15000}
      input:
        minLon: {from: transform.map_extent.minLon}
        minLat: {from: transform.map_extent.minLat}
        maxLon: {from: transform.map_extent.maxLon}
        maxLat: {from: transform.map_extent.maxLat}
```

## 4. `workflow_materializer.materialize()` 결과

`execution/workflow_materializer.py` `materialize` → `bind_input`

```json
{
  "status": "READY",
  "recipe_id": "recipe_036",
  "missing": [],
  "workflow": {
    "action": "call_mcp_workflow",
    "steps": [
      {
        "id": "s1",
        "server_id": "asap-mcp-core",
        "tool": "geo.geocode",
        "input": { "query": "수원역" }
      },
      {
        "id": "s2",
        "server_id": "asap-mcp-core",
        "tool": "road.getCctv",
        "input": {
          "center": ["$s1.location.0", "$s1.location.1"],
          "radiusMeters": 15000
        },
        "inputAdapter": "point_radius_to_bbox"
      }
    ]
  },
  "nodes": ["geocode_place", "find_cctv"],
  "commands": [],
  "command_nodes": [],
  "context": {}
}
```

| 3 의 표현 | 4 의 값 |
| --- | --- |
| `{from: spoken.argument}` | `"수원역"` |
| `{value: 15000}` | `15000` |
| `{from: s1.point.lon}` · `{from: s1.point.lat}` | `"$s1.location.0"` · `"$s1.location.1"` |
| `{from: transform.map_extent.*}` | (칸 없음) |
| `transform.id: builtin/geo.pointRadiusToBbox` | `"inputAdapter": "point_radius_to_bbox"` |

## 5. KRRI_ASAP `POST /workflow/execute/stream` request body

`execution/workflow_execution.py` `run` → `execution/krri_executor_client.py` `stream_workflow`

```json
{
  "workflow": {
    "action": "call_mcp_workflow",
    "steps": [
      {
        "id": "s1",
        "server_id": "asap-mcp-core",
        "tool": "geo.geocode",
        "input": { "query": "수원역" }
      },
      {
        "id": "s2",
        "server_id": "asap-mcp-core",
        "tool": "road.getCctv",
        "input": {
          "center": ["$s1.location.0", "$s1.location.1"],
          "radiusMeters": 15000
        },
        "inputAdapter": "point_radius_to_bbox"
      }
    ]
  },
  "user_text": "수원역 근처 CCTV 띄워줘",
  "context": {}
}
```

사용자 MCP 범위는 body 가 아니라 `X-User-*` 헤더로 갑니다.
