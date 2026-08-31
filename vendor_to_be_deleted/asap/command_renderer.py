# -*- coding: utf-8 -*-
"""Render normalized display artifacts into frontend commands."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from vendor_to_be_deleted.asap.schemas_chat import Command

DisplayArtifact = Dict[str, Any]

_DEFAULT_LAYER_BY_KIND = {
    "transit_route": "transit-route",
    "isochrone": "r5-isochrone",
    "geojson": "mcp-geojson",
    "point_collection": "mcp-points",
    "place": "mcp-place",
}

_ISOCHRONE_PALETTE = ["#22C55E", "#84CC16", "#EAB308", "#F97316", "#EF4444", "#B91C1C"]


def build_commands_from_artifacts(artifacts: List[DisplayArtifact]) -> List[Command]:
    """Build map/UI commands from display artifacts.

    The renderer is artifact-kind based, not scenario based. This keeps new MCP
    tools usable as long as their output has a known shape.
    """
    commands: List[Command] = []
    focus_added = False

    for artifact in _sort_artifacts(artifacts):
        kind = artifact.get("kind")

        if kind == "transit_route":
            commands.extend(_render_transit_route(artifact))
            focus_added = True
            continue

        if kind == "isochrone":
            commands.extend(_render_isochrone(artifact, include_focus=not focus_added))
            focus_added = focus_added or _has_bbox(artifact)
            continue

        if kind == "geojson":
            commands.extend(_render_geojson(artifact, include_focus=not focus_added))
            focus_added = focus_added or _has_bbox(artifact)
            continue

        if kind == "point_collection":
            commands.extend(_render_point_collection(artifact, include_focus=not focus_added))
            focus_added = focus_added or _has_bbox(artifact)
            continue

        if kind == "place":
            commands.extend(_render_place(artifact, include_focus=not focus_added))
            focus_added = focus_added or _has_bbox(artifact)
            continue

        if kind == "viewport" and not focus_added:
            command = _render_viewport(artifact)
            if command:
                commands.append(command)
                focus_added = True

    return commands[:50]


def _render_transit_route(artifact: DisplayArtifact) -> List[Command]:
    route = artifact.get("data")
    if not isinstance(route, dict):
        return []

    return [
        Command(
            op="transit.route.show",
            args={
                "route": route,
                "layerId": _layer_id(artifact),
                "fitBounds": True,
            },
        )
    ]


def _render_isochrone(artifact: DisplayArtifact, include_focus: bool) -> List[Command]:
    data = artifact.get("data")
    if not isinstance(data, dict):
        return []

    base_layer_id = _layer_id(artifact)
    cutoffs = _numeric_cutoffs(data.get("cutoffs_minutes"))
    commands: List[Command] = []

    polygon_features = _style_isochrone_features(
        _geojson_features(data.get("polygons")),
        cutoffs,
        role="polygon",
    )
    line_features = _style_isochrone_features(
        _geojson_features(data.get("lines")),
        cutoffs,
        role="line",
    )
    point_features = _style_isochrone_features(
        _geojson_features(data.get("points")),
        cutoffs,
        role="point",
    )
    origin_feature = _isochrone_origin_feature(data.get("origin"))
    # Clear the complete isochrone layer family up front. R5 may omit one of
    # the geometry collections on a later request; conditional clears would
    # otherwise leave a polygon or origin marker from the previous result.
    commands.extend([
        _clear_command(f"{base_layer_id}-polygons"),
        _clear_command(f"{base_layer_id}-lines"),
        _clear_command(f"{base_layer_id}-points"),
        _clear_command(f"{base_layer_id}-origin"),
    ])

    # Draw fills first so their translucent layer cannot cover the explicit
    # boundary, reachable cells, or origin marker in MapLibre.
    if polygon_features:
        commands.append(Command(
            op="map.draw",
            args={
                "layerId": f"{base_layer_id}-polygons",
                "features": polygon_features,
            },
        ))

    if line_features:
        commands.append(Command(
            op="map.draw",
            args={
                "layerId": f"{base_layer_id}-lines",
                "features": line_features,
            },
        ))

    if point_features:
        commands.append(Command(
            op="map.draw",
            args={
                "layerId": f"{base_layer_id}-points",
                "features": point_features,
            },
        ))

    if origin_feature:
        commands.append(Command(
            op="map.draw",
            args={
                "layerId": f"{base_layer_id}-origin",
                "features": [origin_feature],
            },
        ))

    if include_focus:
        focus = _focus_command(artifact)
        if focus:
            commands.append(focus)

    return commands


def _render_geojson(artifact: DisplayArtifact, include_focus: bool) -> List[Command]:
    data = artifact.get("data")
    if not isinstance(data, dict):
        return []

    features = data.get("features") if data.get("type") == "FeatureCollection" else [data]
    commands = [
        Command(
            op="map.draw",
            args={
                "layerId": _layer_id(artifact),
                "features": features,
            },
        )
    ]
    if include_focus:
        focus = _focus_command(artifact)
        if focus:
            commands.append(focus)
    return commands


def _render_point_collection(artifact: DisplayArtifact, include_focus: bool) -> List[Command]:
    data = artifact.get("data")
    if not isinstance(data, dict):
        return []

    features = data.get("features")
    if not isinstance(features, list) or not features:
        return []

    commands = [
        Command(
            op="map.draw",
            args={
                "layerId": _layer_id(artifact),
                "features": features,
            },
        )
    ]
    if include_focus:
        focus = _focus_command(artifact)
        if focus:
            commands.append(focus)
    return commands


def _render_place(artifact: DisplayArtifact, include_focus: bool) -> List[Command]:
    data = artifact.get("data")
    if not isinstance(data, dict):
        return []

    lon = data.get("lon")
    lat = data.get("lat")
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        return []

    feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "id": f"mcp-place-{lon}-{lat}",
            "label": data.get("label") or artifact.get("title") or "검색 위치",
            "name": data.get("label") or artifact.get("title") or "검색 위치",
            "type": "poi",
            "color": data.get("color") or "#0088FF",
            "showLabel": True,
        },
    }

    commands = [
        Command(
            op="map.draw",
            args={
                "layerId": _layer_id(artifact),
                "features": [feature],
            },
        )
    ]
    if include_focus:
        focus = _focus_command(artifact) or _point_focus_command(float(lon), float(lat))
        if focus:
            commands.append(focus)
    return commands


def _render_viewport(artifact: DisplayArtifact) -> Optional[Command]:
    return _focus_command(artifact)


def _clear_command(layer_id: str) -> Command:
    return Command(
        op="map.clear",
        args={
            "layerId": layer_id,
        },
    )


def _focus_command(artifact: DisplayArtifact) -> Optional[Command]:
    bbox = artifact.get("bbox")
    if not _valid_bbox(bbox):
        return None

    return Command(
        op="view.camera.flyTo",
        args={
            "bbox": _pad_bbox(bbox),
            "duration": 2.0,
        },
    )


def _point_focus_command(lon: float, lat: float) -> Command:
    delta = 0.02
    return Command(
        op="view.camera.flyTo",
        args={
            "bbox": [[lon - delta, lat - delta], [lon + delta, lat + delta]],
            "duration": 2.0,
        },
    )


def _geojson_features(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    if value.get("type") == "FeatureCollection":
        features = value.get("features")
        return [feature for feature in features if isinstance(feature, dict)] if isinstance(features, list) else []
    if value.get("type") == "Feature":
        return [value]
    return []


def _style_isochrone_features(features: List[Dict[str, Any]], cutoffs: List[float], role: str) -> List[Dict[str, Any]]:
    styled: List[Dict[str, Any]] = []
    for index, feature in enumerate(features):
        properties = dict(feature.get("properties") or {})
        cutoff = _feature_cutoff(properties)
        color = _isochrone_color(cutoff, cutoffs)
        label = _cutoff_label(cutoff)

        properties["type"] = "isochrone"
        properties["cutoff_min"] = cutoff if cutoff is not None else properties.get("cutoff_min")
        properties.setdefault("name", f"{label} 도달 영역" if label else "도달 가능 영역")

        if role == "polygon":
            properties.setdefault("id", f"isochrone-polygon-{label or 'unknown'}-{index}")
            properties.update({
                "fill": color,
                "fillOpacity": 0.18,
                "outline": False,
                "outlineColor": color,
            })
        elif role == "point":
            properties.setdefault("id", f"isochrone-point-{label or 'unknown'}-{index}")
            properties.update({
                "color": color,
                "radius": 4,
                "pointSize": 5,
                "showLabel": False,
            })
        else:
            properties.setdefault("id", f"isochrone-line-{label or 'unknown'}-{index}")
            properties.update({
                "color": color,
                "width": 4,
                "lineStyle": "outline",
                "outlineColor": "#FFFFFF",
                "outlineWidth": 2,
            })

        styled.append({
            **feature,
            "properties": properties,
        })

    if role == "polygon":
        return sorted(styled, key=lambda item: _sort_cutoff(item.get("properties")), reverse=True)
    return sorted(styled, key=lambda item: _sort_cutoff(item.get("properties")))


def _isochrone_origin_feature(origin: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(origin, dict):
        return None

    lon = origin.get("lon")
    lat = origin.get("lat")
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        return None

    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "id": f"isochrone-origin-{lon}-{lat}",
            "label": origin.get("label") or "출발지",
            "name": origin.get("label") or "출발지",
            "type": "poi",
            "color": "#2563EB",
            "showLabel": True,
            "scale": 1.1,
        },
    }


def _numeric_cutoffs(value: Any) -> List[float]:
    if not isinstance(value, list):
        return []
    cutoffs: List[float] = []
    for item in value:
        number = _number_value(item)
        if number is not None:
            cutoffs.append(number)
    return sorted(set(cutoffs))


def _feature_cutoff(properties: Dict[str, Any]) -> Optional[float]:
    return _number_value(properties.get("cutoff_min"))


def _number_value(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _sort_cutoff(properties: Any) -> float:
    if not isinstance(properties, dict):
        return 0.0
    return _feature_cutoff(properties) or 0.0


def _isochrone_color(cutoff: Optional[float], cutoffs: List[float]) -> str:
    if cutoff is None or not cutoffs:
        return "#0EA5E9"

    try:
        index = cutoffs.index(float(cutoff))
    except ValueError:
        index = len(cutoffs) - 1

    if len(cutoffs) == 1:
        return "#0EA5E9"

    palette_index = round(index * (len(_ISOCHRONE_PALETTE) - 1) / max(len(cutoffs) - 1, 1))
    return _ISOCHRONE_PALETTE[palette_index]


def _cutoff_label(cutoff: Optional[float]) -> str:
    if cutoff is None:
        return ""
    if float(cutoff).is_integer():
        return f"{int(cutoff)}분"
    return f"{cutoff:g}분"


def _layer_id(artifact: DisplayArtifact) -> str:
    explicit = artifact.get("layerId") or artifact.get("layer_id")
    if explicit:
        return str(explicit)
    return _DEFAULT_LAYER_BY_KIND.get(str(artifact.get("kind")), "mcp-display")


def _has_bbox(artifact: DisplayArtifact) -> bool:
    return _valid_bbox(artifact.get("bbox"))


def _valid_bbox(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(point, list) and len(point) >= 2 for point in value)
        and all(isinstance(coord, (int, float)) for point in value for coord in point[:2])
    )


def _pad_bbox(bbox: List[List[float]]) -> List[List[float]]:
    min_lon, min_lat = bbox[0]
    max_lon, max_lat = bbox[1]
    lon_padding = max((max_lon - min_lon) * 0.2, 0.003)
    lat_padding = max((max_lat - min_lat) * 0.2, 0.003)
    return [
        [min_lon - lon_padding, min_lat - lat_padding],
        [max_lon + lon_padding, max_lat + lat_padding],
    ]


def _sort_artifacts(artifacts: List[DisplayArtifact]) -> List[DisplayArtifact]:
    priority = {
        "transit_route": 10,
        "isochrone": 15,
        "geojson": 20,
        "point_collection": 30,
        "place": 40,
        "viewport": 50,
    }
    return sorted(artifacts, key=lambda artifact: priority.get(str(artifact.get("kind")), 100))
