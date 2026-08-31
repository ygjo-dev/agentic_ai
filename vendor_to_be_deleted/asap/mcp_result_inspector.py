# -*- coding: utf-8 -*-
"""Inspect arbitrary MCP results and normalize displayable shapes.

This module intentionally avoids relying on MCP tool names. New MCP servers can
return familiar data shapes, and the orchestrator can still decide how to show
them on the map.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from vendor_to_be_deleted.asap.isochrone_geometry import validate_and_repair_isochrone_polygons

DisplayArtifact = Dict[str, Any]

_MAX_ARTIFACTS = 20
_MAX_DEPTH = 4


def inspect_mcp_result(result: Any, source: Optional[Dict[str, Any]] = None) -> List[DisplayArtifact]:
    """Return display artifacts inferred from one raw MCP tool result."""
    artifacts = _inspect_value(_unwrap_mcp_result(result), source or {}, "$", 0)
    return _dedupe_artifacts(artifacts)[:_MAX_ARTIFACTS]


def inspect_mcp_trace(trace: List[Dict[str, Any]]) -> List[DisplayArtifact]:
    """Return display artifacts inferred from a workflow trace."""
    artifacts: List[DisplayArtifact] = []
    for item in trace:
        if not isinstance(item, dict) or "result" not in item:
            continue

        source = {
            "step_id": item.get("id"),
            "tool": item.get("tool"),
            "server_id": item.get("server_id"),
        }
        artifacts.extend(inspect_mcp_result(item.get("result"), source))

    return _prefer_artifacts(_dedupe_artifacts(artifacts))[:_MAX_ARTIFACTS]


def _inspect_value(value: Any, source: Dict[str, Any], path: str, depth: int) -> List[DisplayArtifact]:
    value = _unwrap_mcp_result(value)
    artifacts: List[DisplayArtifact] = []

    if depth > _MAX_DEPTH:
        return artifacts

    if _is_transit_route(value):
        return [_artifact("transit_route", value, source, path, title="대중교통 경로")]

    isochrone = _extract_isochrone(value)
    if isochrone:
        return [_artifact(
            "isochrone",
            isochrone,
            source,
            path,
            title="도달 가능 영역",
            bbox=isochrone.get("bbox"),
        )]

    if _is_geojson(value):
        return [_artifact("geojson", value, source, path, title="지도 데이터", bbox=_compute_geojson_bbox(value))]

    geometry_feature = _extract_geometry_feature(value)
    if geometry_feature:
        bbox = _extract_bbox(value) or _compute_geojson_bbox(geometry_feature)
        return [_artifact("geojson", geometry_feature, source, path, title="지도 데이터", bbox=bbox)]

    point_collection = _extract_point_collection(value)
    if point_collection:
        return [_artifact(
            "point_collection",
            point_collection,
            source,
            path,
            title="위치 목록",
            bbox=_compute_feature_bbox(point_collection.get("features") or []),
        )]

    place = _extract_place(value)
    if place:
        return [_artifact("place", place, source, path, title=place.get("label") or "검색 위치", bbox=place.get("bbox"))]

    bbox = _extract_bbox(value)
    if bbox:
        artifacts.append(_artifact("viewport", {"bbox": bbox}, source, path, title="지도 이동 영역", bbox=bbox))

    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {"bbox", "location"}:
                continue
            artifacts.extend(_inspect_value(nested, source, f"{path}.{key}", depth + 1))
    elif isinstance(value, list):
        for index, nested in enumerate(value[:10]):
            artifacts.extend(_inspect_value(nested, source, f"{path}.{index}", depth + 1))

    return artifacts


def _artifact(
    kind: str,
    data: Any,
    source: Dict[str, Any],
    path: str,
    title: str,
    bbox: Optional[List[List[float]]] = None,
) -> DisplayArtifact:
    artifact: DisplayArtifact = {
        "kind": kind,
        "title": title,
        "data": data,
        "source": {key: value for key, value in source.items() if value},
        "path": path,
    }
    if bbox:
        artifact["bbox"] = bbox
    return artifact


def _unwrap_mcp_result(value: Any) -> Any:
    """Unwrap common MCP response envelopes when possible."""
    if not isinstance(value, dict):
        return value

    structured = value.get("structuredContent")
    if structured is not None:
        return structured

    content = value.get("content")
    if isinstance(content, list) and content:
        parsed_items: List[Any] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                parsed_items.append(_parse_json_text(item["text"]))
            elif "data" in item:
                parsed_items.append(item.get("data"))

        if len(parsed_items) == 1:
            return parsed_items[0]
        if parsed_items:
            return parsed_items

    return value


def _parse_json_text(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return text


def _is_transit_route(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    itineraries = value.get("itineraries")
    if not isinstance(itineraries, list) or not itineraries:
        return False
    return any(isinstance(item, dict) and isinstance(item.get("legs"), list) for item in itineraries)


def _is_geojson(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    geo_type = value.get("type")
    if geo_type == "FeatureCollection":
        return isinstance(value.get("features"), list)
    if geo_type == "Feature":
        return isinstance(value.get("geometry"), dict)
    return False


def _is_geojson_geometry(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return value.get("type") in {
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
    } and "coordinates" in value


def _extract_geometry_feature(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None

    geometry = value.get("geometry")
    if not _is_geojson_geometry(geometry):
        return None

    properties = {
        key: item
        for key, item in value.items()
        if key not in {"geometry", "bbox"} and isinstance(item, (str, int, float, bool))
    }
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": properties,
    }


def _extract_isochrone(value: Any) -> Optional[Dict[str, Any]]:
    """Normalize R5-style isochrone responses into one display artifact."""
    if not isinstance(value, dict):
        return None

    feature_collections = value.get("feature_collections")
    if not isinstance(feature_collections, dict):
        return None

    points = feature_collections.get("points")
    lines = feature_collections.get("lines")
    polygons = feature_collections.get("polygons")
    if not any(_is_geojson(item) for item in (points, lines, polygons)):
        return None

    origin = _extract_isochrone_origin(value.get("origin"))
    cutoffs = _extract_isochrone_cutoffs(value, points, lines, polygons)
    display_polygons, geometry_validation = validate_and_repair_isochrone_polygons(
        origin=origin,
        points=points,
        polygons=polygons,
        cutoffs_minutes=cutoffs,
    )
    fallback_applied = bool(geometry_validation.get("fallback_applied"))
    bbox = (
        _compute_geojson_bbox(display_polygons) if _is_geojson(display_polygons) else None
    ) or (
        _compute_geojson_bbox(lines) if _is_geojson(lines) and not fallback_applied else None
    ) or (
        _compute_geojson_bbox(points) if _is_geojson(points) else None
    )

    data: Dict[str, Any] = {
        "status": value.get("status"),
        "scenario_id": value.get("scenario_id"),
        "mode": value.get("mode"),
        "max_minutes": value.get("max_minutes"),
        "cutoffs_minutes": cutoffs,
        "reachable_cell_count": value.get("reachable_cell_count"),
        "elapsed_ms": value.get("elapsed_ms"),
        "geometry_validation": geometry_validation,
    }
    if origin:
        data["origin"] = origin
    if bbox:
        data["bbox"] = bbox
    if _is_geojson(display_polygons):
        data["polygons"] = display_polygons
    # A rejected contour line describes the same broken geometry as its polygon.
    # Do not combine it with a reachable-cell fallback.
    if _is_geojson(lines) and not fallback_applied:
        data["lines"] = lines
    # Reachable points are repair evidence, not an additional display layer.
    # Keep them only when no polygon geometry (original or repaired) is usable.
    if _is_geojson(points) and not _is_geojson(display_polygons):
        data["points"] = points

    return data


def _extract_isochrone_origin(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None

    point = _extract_lon_lat(value)
    if not point:
        return None

    lon, lat = point
    return {
        "lon": lon,
        "lat": lat,
        "label": str(value.get("label") or value.get("name") or "출발지"),
    }


def _extract_isochrone_cutoffs(value: Dict[str, Any], *collections: Any) -> List[int]:
    raw_cutoffs = value.get("cutoffs_minutes")
    cutoffs: set[int] = set()
    if isinstance(raw_cutoffs, list):
        for item in raw_cutoffs:
            if _is_number(item):
                cutoffs.add(int(float(item)))

    for collection in collections:
        if not isinstance(collection, dict):
            continue
        for feature in collection.get("features") or []:
            if not isinstance(feature, dict):
                continue
            properties = feature.get("properties") or {}
            cutoff = properties.get("cutoff_min")
            if _is_number(cutoff):
                cutoffs.add(int(float(cutoff)))

    return sorted(cutoffs)


def _extract_place(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None

    location = value.get("location")
    if _is_lon_lat_pair(location):
        lon, lat = float(location[0]), float(location[1])
    else:
        point = _extract_lon_lat(value)
        if not point:
            return None
        lon, lat = point

    label = (
        value.get("title")
        or value.get("name")
        or value.get("label")
        or value.get("address")
        or "검색 위치"
    )
    place = {
        "lon": lon,
        "lat": lat,
        "label": str(label),
        "address": value.get("address"),
        "color": value.get("color") or "#0088FF",
    }
    bbox = _extract_bbox(value)
    if bbox:
        place["bbox"] = bbox
    return place


def _extract_point_collection(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, list):
        return None

    features: List[Dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        point = _extract_lon_lat(item)
        if not point:
            continue

        lon, lat = point
        is_cctv = any(key in item for key in ("cctvUrl", "cctvId", "cctvName"))
        label = item.get("cctvName") or item.get("name") or item.get("title") or item.get("label") or item.get("id") or f"위치 {index + 1}"
        feature_id = item.get("cctvId") or item.get("id") or item.get("code") or f"mcp-point-{index}"
        properties: Dict[str, Any] = {
            "id": str(feature_id),
            "label": str(label),
            "name": str(label),
            "type": "cctv" if is_cctv else "poi",
            "color": item.get("color") or ("#10B981" if is_cctv else "#0088FF"),
        }

        url = item.get("cctvUrl") or item.get("url") or item.get("streamUrl")
        if url:
            properties["url"] = url

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": properties,
        })

    if not features:
        return None

    return {
        "features": features,
        "count": len(features),
    }


def _extract_lon_lat(value: Dict[str, Any]) -> Optional[tuple[float, float]]:
    candidates = [
        ("centerLon", "centerLat"),
        ("lon", "lat"),
        ("lng", "lat"),
        ("longitude", "latitude"),
        ("x", "y"),
    ]
    for lon_key, lat_key in candidates:
        lon = value.get(lon_key)
        lat = value.get(lat_key)
        if _is_number(lon) and _is_number(lat):
            lon_float = float(lon)
            lat_float = float(lat)
            if -180 <= lon_float <= 180 and -90 <= lat_float <= 90:
                return lon_float, lat_float
    return None


def _extract_bbox(value: Any) -> Optional[List[List[float]]]:
    if not isinstance(value, dict):
        return None

    bbox = value.get("bbox") or value.get("bounds")
    if isinstance(bbox, list):
        if len(bbox) == 2 and all(isinstance(item, list) and len(item) >= 2 for item in bbox):
            return [
                [float(bbox[0][0]), float(bbox[0][1])],
                [float(bbox[1][0]), float(bbox[1][1])],
            ]
        if len(bbox) >= 4 and all(_is_number(item) for item in bbox[:4]):
            return [[float(bbox[0]), float(bbox[1])], [float(bbox[2]), float(bbox[3])]]

    if isinstance(bbox, dict):
        keys = ("minLon", "minLat", "maxLon", "maxLat")
        if all(_is_number(bbox.get(key)) for key in keys):
            return [
                [float(bbox["minLon"]), float(bbox["minLat"])],
                [float(bbox["maxLon"]), float(bbox["maxLat"])],
            ]

    keys = ("minLon", "minLat", "maxLon", "maxLat")
    if all(_is_number(value.get(key)) for key in keys):
        return [
            [float(value["minLon"]), float(value["minLat"])],
            [float(value["maxLon"]), float(value["maxLat"])],
        ]

    return None


def _compute_geojson_bbox(value: Dict[str, Any]) -> Optional[List[List[float]]]:
    coordinates: List[tuple[float, float]] = []
    if value.get("type") == "FeatureCollection":
        for feature in value.get("features") or []:
            if isinstance(feature, dict):
                _collect_geometry_coordinates(feature.get("geometry"), coordinates)
    elif value.get("type") == "Feature":
        _collect_geometry_coordinates(value.get("geometry"), coordinates)
    return _bbox_from_coordinates(coordinates)


def _compute_feature_bbox(features: List[Dict[str, Any]]) -> Optional[List[List[float]]]:
    coordinates: List[tuple[float, float]] = []
    for feature in features:
        _collect_geometry_coordinates(feature.get("geometry"), coordinates)
    return _bbox_from_coordinates(coordinates)


def _collect_geometry_coordinates(geometry: Any, coordinates: List[tuple[float, float]]) -> None:
    if not isinstance(geometry, dict):
        return
    _collect_coordinate_pairs(geometry.get("coordinates"), coordinates)


def _collect_coordinate_pairs(value: Any, coordinates: List[tuple[float, float]]) -> None:
    if _is_lon_lat_pair(value):
        coordinates.append((float(value[0]), float(value[1])))
        return
    if isinstance(value, list):
        for item in value:
            _collect_coordinate_pairs(item, coordinates)


def _bbox_from_coordinates(coordinates: List[tuple[float, float]]) -> Optional[List[List[float]]]:
    if not coordinates:
        return None
    lons = [item[0] for item in coordinates]
    lats = [item[1] for item in coordinates]
    return [[min(lons), min(lats)], [max(lons), max(lats)]]


def _is_lon_lat_pair(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 2
        and _is_number(value[0])
        and _is_number(value[1])
        and -180 <= float(value[0]) <= 180
        and -90 <= float(value[1]) <= 90
    )


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _dedupe_artifacts(artifacts: List[DisplayArtifact]) -> List[DisplayArtifact]:
    seen: set[str] = set()
    items: List[DisplayArtifact] = []
    for artifact in artifacts:
        key = f"{artifact.get('kind')}:{artifact.get('path')}:{json.dumps(artifact.get('source', {}), sort_keys=True, ensure_ascii=False)}"
        if key in seen:
            continue
        seen.add(key)
        items.append(artifact)
    return items


def _prefer_artifacts(artifacts: List[DisplayArtifact]) -> List[DisplayArtifact]:
    """Suppress helper geocode artifacts when a richer artifact exists."""
    has_route = any(artifact.get("kind") == "transit_route" for artifact in artifacts)
    has_isochrone = any(artifact.get("kind") == "isochrone" for artifact in artifacts)
    if has_route or has_isochrone:
        artifacts = [
            artifact
            for artifact in artifacts
            if artifact.get("kind") not in {"place", "viewport"}
        ]

    priority = {
        "transit_route": 10,
        "isochrone": 15,
        "geojson": 20,
        "point_collection": 30,
        "place": 40,
        "viewport": 50,
    }
    return sorted(artifacts, key=lambda artifact: priority.get(str(artifact.get("kind")), 100))
