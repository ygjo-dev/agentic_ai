# -*- coding: utf-8 -*-
"""Validate and conservatively repair display geometry for R5 isochrones.

R5 returns reachable grid-cell centres as points in addition to generated
contours.  A contour is not safe to display when it does not contain the
origin or most of those reachable cells.  This module detects that condition
without a GIS dependency and builds a cell-based fallback geometry.

The fallback intentionally favours disconnected cell rectangles over a convex
hull.  A convex hull can incorrectly bridge mountains, rivers, or disconnected
network components.  A convex hull is used only when there are too few points
to infer a representative cell size, and that method is exposed in metadata.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

GeoJson = Dict[str, Any]
Coordinate = Tuple[float, float]
PointSample = Tuple[float, float, Optional[float]]

_DEFAULT_MIN_POINT_COVERAGE = 0.8
_GRID_RESIDUAL_LIMIT = 0.35
_MIN_REGULAR_GRID_RATIO = 0.85
_MAX_GRID_STEP_SAMPLE = 1024
_METERS_PER_LATITUDE_DEGREE = 111_320.0


def validate_and_repair_isochrone_polygons(
    *,
    origin: Optional[Dict[str, Any]],
    points: Any,
    polygons: Any,
    cutoffs_minutes: Sequence[Any] = (),
    min_point_coverage: float = _DEFAULT_MIN_POINT_COVERAGE,
) -> Tuple[Optional[GeoJson], Dict[str, Any]]:
    """Return display polygons and spatial-validation diagnostics.

    The original polygons are preserved when they contain the origin and at
    least ``min_point_coverage`` of unique reachable points.  When validation
    fails and reachable points are available, polygons are replaced with a
    conservative approximation made from reachable-cell rectangles.
    """

    point_samples = _extract_point_samples(points)
    unique_points = _unique_coordinates((lon, lat) for lon, lat, _ in point_samples)
    origin_coordinate = _extract_origin_coordinate(origin)
    polygon_geometries = _extract_polygon_geometries(polygons)

    covered_count = sum(
        1 for coordinate in unique_points if _geometries_contain_point(polygon_geometries, coordinate)
    )
    coverage_ratio = covered_count / len(unique_points) if unique_points else None
    origin_covered = (
        _geometries_contain_point(polygon_geometries, origin_coordinate)
        if origin_coordinate is not None
        else None
    )

    reasons: List[str] = []
    if not polygon_geometries:
        reasons.append("missing_or_invalid_polygon")
    if origin_coordinate is not None and polygon_geometries and not origin_covered:
        reasons.append("origin_not_covered")
    if (
        unique_points
        and polygon_geometries
        and coverage_ratio is not None
        and coverage_ratio < min_point_coverage
    ):
        reasons.append("insufficient_reachable_point_coverage")

    diagnostics: Dict[str, Any] = {
        "original_valid": not reasons,
        "valid": not reasons,
        "fallback_applied": False,
        "reasons": reasons,
        "origin_covered": origin_covered,
        "reachable_point_count": len(unique_points),
        "covered_reachable_point_count": covered_count,
        "reachable_point_coverage_ratio": coverage_ratio,
        "minimum_reachable_point_coverage_ratio": min_point_coverage,
        "original_polygon_feature_count": len(polygon_geometries),
    }

    if not reasons:
        return polygons if isinstance(polygons, dict) else None, diagnostics

    # An invalid existing contour should only be discarded when reachable-cell
    # evidence can replace it.  A single point is enough when no contour exists;
    # for an existing contour require a small point set to avoid replacing a
    # rich shape based on a partial/debug point response.
    minimum_repair_points = 1 if not polygon_geometries else 3
    if len(unique_points) < minimum_repair_points:
        diagnostics["repair_skipped_reason"] = "insufficient_reachable_points"
        return polygons if isinstance(polygons, dict) else None, diagnostics

    fallback, method = _build_fallback_feature_collection(
        point_samples=point_samples,
        origin=origin_coordinate,
        cutoffs_minutes=cutoffs_minutes,
        reasons=reasons,
    )
    if fallback is None:
        diagnostics["repair_skipped_reason"] = "fallback_geometry_unavailable"
        return polygons if isinstance(polygons, dict) else None, diagnostics

    fallback_geometries = _extract_polygon_geometries(fallback)
    fallback_covered_count = sum(
        1 for coordinate in unique_points if _geometries_contain_point(fallback_geometries, coordinate)
    )
    fallback_origin_covered = (
        _geometries_contain_point(fallback_geometries, origin_coordinate)
        if origin_coordinate is not None
        else None
    )

    # Do not replace one bad geometry with another.  Cell-based geometry should
    # cover every source centre; tolerate only floating-point edge noise.
    fallback_coverage_ratio = fallback_covered_count / len(unique_points)
    if fallback_coverage_ratio < 0.999 or fallback_origin_covered is False:
        diagnostics["repair_skipped_reason"] = "fallback_failed_validation"
        diagnostics["fallback_method"] = method
        diagnostics["fallback_reachable_point_coverage_ratio"] = fallback_coverage_ratio
        diagnostics["fallback_origin_covered"] = fallback_origin_covered
        return polygons if isinstance(polygons, dict) else None, diagnostics

    diagnostics.update({
        "valid": True,
        "fallback_applied": True,
        "fallback_method": method,
        "fallback_origin_covered": fallback_origin_covered,
        "fallback_covered_reachable_point_count": fallback_covered_count,
        "fallback_reachable_point_coverage_ratio": fallback_coverage_ratio,
    })
    return fallback, diagnostics


def _build_fallback_feature_collection(
    *,
    point_samples: List[PointSample],
    origin: Optional[Coordinate],
    cutoffs_minutes: Sequence[Any],
    reasons: Sequence[str],
) -> Tuple[Optional[GeoJson], Optional[str]]:
    targets = _fallback_cutoff_targets(point_samples, cutoffs_minutes)
    features: List[GeoJson] = []
    methods: List[str] = []

    for cutoff in targets:
        selected = [
            (lon, lat)
            for lon, lat, point_cutoff in point_samples
            if cutoff is None or point_cutoff is None or point_cutoff <= cutoff
        ]
        selected = _unique_coordinates(selected)
        if not selected:
            continue

        geometry, method, cell_size_meters = _build_reachable_cell_geometry(selected, origin)
        if geometry is None or method is None:
            continue

        methods.append(method)
        cutoff_label = _format_cutoff(cutoff)
        properties: Dict[str, Any] = {
            "id": f"isochrone-fallback-{cutoff_label or 'unknown'}",
            "name": f"{cutoff_label}분 도달 영역 (근사)" if cutoff_label else "도달 가능 영역 (근사)",
            "geometry_fallback": True,
            "fallback_method": method,
            "fallback_reasons": list(reasons),
            "source_reachable_point_count": len(selected),
        }
        if cutoff is not None:
            properties["cutoff_min"] = cutoff
        if cell_size_meters is not None:
            properties["estimated_cell_size_meters"] = round(cell_size_meters, 3)

        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": properties,
        })

    if not features:
        return None, None

    method = methods[0] if len(set(methods)) == 1 else "mixed_reachable_point_approximation"
    return {"type": "FeatureCollection", "features": features}, method


def _build_reachable_cell_geometry(
    coordinates: List[Coordinate],
    origin: Optional[Coordinate],
) -> Tuple[Optional[GeoJson], Optional[str], Optional[float]]:
    projection = _LocalProjection.from_coordinates(coordinates + ([origin] if origin else []))
    projected = [projection.forward(coordinate) for coordinate in coordinates]
    steps = _estimate_cell_steps(projected)

    if steps is not None:
        step_x, step_y = steps
        grid_geometry = _build_regular_grid_geometry(projected, projection, step_x, step_y, origin)
        if grid_geometry is not None:
            representative_step = math.sqrt(step_x * step_y)
            return grid_geometry, "reachable_cell_grid", representative_step * _METERS_PER_LATITUDE_DEGREE

        point_cell_geometry = _build_point_cell_geometry(projected, projection, step_x, step_y, origin)
        if point_cell_geometry is not None:
            representative_step = math.sqrt(step_x * step_y)
            return point_cell_geometry, "reachable_point_cells", representative_step * _METERS_PER_LATITUDE_DEGREE

    hull_coordinates = list(coordinates)
    if origin is not None:
        hull_coordinates.append(origin)
    hull_geometry = _build_convex_hull_geometry(hull_coordinates)
    if hull_geometry is not None:
        return hull_geometry, "reachable_points_convex_hull", None
    return None, None, None


class _LocalProjection:
    """Small-area equirectangular projection in latitude-degree units."""

    def __init__(self, lon0: float, lat0: float, cos_latitude: float) -> None:
        self.lon0 = lon0
        self.lat0 = lat0
        self.cos_latitude = cos_latitude

    @classmethod
    def from_coordinates(cls, coordinates: List[Coordinate]) -> "_LocalProjection":
        lon0 = sum(item[0] for item in coordinates) / len(coordinates)
        lat0 = sum(item[1] for item in coordinates) / len(coordinates)
        cos_latitude = max(math.cos(math.radians(lat0)), 1e-6)
        return cls(lon0, lat0, cos_latitude)

    def forward(self, coordinate: Coordinate) -> Coordinate:
        return (
            (coordinate[0] - self.lon0) * self.cos_latitude,
            coordinate[1] - self.lat0,
        )

    def inverse(self, coordinate: Coordinate) -> List[float]:
        return [
            self.lon0 + coordinate[0] / self.cos_latitude,
            self.lat0 + coordinate[1],
        ]


def _estimate_cell_steps(points: List[Coordinate]) -> Optional[Tuple[float, float]]:
    if len(points) < 2:
        return None

    # Sorting spatially keeps a bounded prefix locally dense when a response has
    # thousands of cells; this avoids an unbounded O(n^2) nearest-neighbour pass.
    sample = sorted(points, key=lambda item: (item[1], item[0]))[:_MAX_GRID_STEP_SAMPLE]
    nearest_distances: List[float] = []
    for index, left in enumerate(sample):
        nearest = math.inf
        for right_index, right in enumerate(sample):
            if index == right_index:
                continue
            distance = math.hypot(left[0] - right[0], left[1] - right[1])
            if 1e-12 < distance < nearest:
                nearest = distance
        if math.isfinite(nearest):
            nearest_distances.append(nearest)

    if not nearest_distances:
        return None
    nearest_distances.sort()
    lower_half = nearest_distances[: max(1, (len(nearest_distances) + 1) // 2)]
    base_step = median(lower_half)
    if not math.isfinite(base_step) or base_step <= 1e-10:
        return None

    # R5 grids are generally axis-aligned after conversion to WGS84, but their
    # longitude/latitude pitch need not be identical.  Infer each pitch from
    # near-horizontal/near-vertical neighbours, falling back to the common
    # nearest-neighbour distance for a one-row/one-column response.
    alignment_tolerance = base_step * 0.1
    x_candidates: List[float] = []
    y_candidates: List[float] = []
    for index, left in enumerate(sample):
        for right in sample[index + 1:]:
            dx = abs(left[0] - right[0])
            dy = abs(left[1] - right[1])
            if dx > 1e-10 and dy <= alignment_tolerance:
                x_candidates.append(dx)
            if dy > 1e-10 and dx <= alignment_tolerance:
                y_candidates.append(dy)

    step_x = _lower_cluster_median(x_candidates) or base_step
    step_y = _lower_cluster_median(y_candidates) or base_step
    if not (math.isfinite(step_x) and math.isfinite(step_y) and step_x > 1e-10 and step_y > 1e-10):
        return None
    return step_x, step_y


def _lower_cluster_median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    values = sorted(value for value in values if math.isfinite(value) and value > 1e-10)
    if not values:
        return None
    minimum = values[0]
    first_cluster = [value for value in values if value <= minimum * 1.25]
    return median(first_cluster)


def _build_regular_grid_geometry(
    points: List[Coordinate],
    projection: _LocalProjection,
    step_x: float,
    step_y: float,
    origin: Optional[Coordinate],
) -> Optional[GeoJson]:
    reference_x, reference_y = points[0]
    cells: set[Tuple[int, int]] = set()
    regular_count = 0
    unaligned_points: List[Coordinate] = []

    for x, y in points:
        ix = round((x - reference_x) / step_x)
        iy = round((y - reference_y) / step_y)
        center_x = reference_x + ix * step_x
        center_y = reference_y + iy * step_y
        residual = math.hypot((x - center_x) / step_x, (y - center_y) / step_y)
        if residual <= _GRID_RESIDUAL_LIMIT:
            regular_count += 1
            cells.add((ix, iy))
        else:
            unaligned_points.append((x, y))

    if regular_count / len(points) < _MIN_REGULAR_GRID_RATIO:
        return None
    if len(cells) / len(points) < _MIN_REGULAR_GRID_RATIO:
        return None

    polygons: List[List[List[List[float]]]] = []
    rows: Dict[int, List[int]] = {}
    for ix, iy in cells:
        rows.setdefault(iy, []).append(ix)

    for iy, row_cells in sorted(rows.items()):
        sorted_cells = sorted(row_cells)
        run_start = sorted_cells[0]
        run_end = run_start
        for ix in sorted_cells[1:] + [sorted_cells[-1] + 2]:
            if ix == run_end + 1:
                run_end = ix
                continue
            polygons.append(_projected_rectangle_ring(
                projection,
                reference_x + (run_start - 0.5) * step_x,
                reference_y + (iy - 0.5) * step_y,
                reference_x + (run_end + 0.5) * step_x,
                reference_y + (iy + 0.5) * step_y,
            ))
            run_start = ix
            run_end = ix

    # A mostly regular R5 grid can still contain a few projection/rounding
    # outliers. Preserve those source cells as individual rectangles so the
    # repaired geometry always covers all evidence used to construct it.
    for x, y in unaligned_points:
        polygons.append(_projected_rectangle_ring(
            projection,
            x - step_x * 0.45,
            y - step_y * 0.45,
            x + step_x * 0.45,
            y + step_y * 0.45,
        ))

    geometry: GeoJson = {"type": "MultiPolygon", "coordinates": polygons}
    return _ensure_origin_cell(geometry, projection, step_x, step_y, origin)


def _build_point_cell_geometry(
    points: List[Coordinate],
    projection: _LocalProjection,
    step_x: float,
    step_y: float,
    origin: Optional[Coordinate],
) -> Optional[GeoJson]:
    if not points:
        return None
    half_width = step_x * 0.45
    half_height = step_y * 0.45
    polygons = [
        _projected_rectangle_ring(
            projection,
            x - half_width,
            y - half_height,
            x + half_width,
            y + half_height,
        )
        for x, y in points
    ]
    geometry: GeoJson = {"type": "MultiPolygon", "coordinates": polygons}
    return _ensure_origin_cell(geometry, projection, step_x, step_y, origin)


def _ensure_origin_cell(
    geometry: GeoJson,
    projection: _LocalProjection,
    step_x: float,
    step_y: float,
    origin: Optional[Coordinate],
) -> GeoJson:
    if origin is None or _geometry_contains_point(geometry, origin):
        return geometry

    origin_x, origin_y = projection.forward(origin)
    half_width = step_x * 0.5
    half_height = step_y * 0.5
    coordinates = list(geometry.get("coordinates") or [])
    coordinates.append(_projected_rectangle_ring(
        projection,
        origin_x - half_width,
        origin_y - half_height,
        origin_x + half_width,
        origin_y + half_height,
    ))
    return {"type": "MultiPolygon", "coordinates": coordinates}


def _projected_rectangle_ring(
    projection: _LocalProjection,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> List[List[List[float]]]:
    return [[
        projection.inverse((min_x, min_y)),
        projection.inverse((max_x, min_y)),
        projection.inverse((max_x, max_y)),
        projection.inverse((min_x, max_y)),
        projection.inverse((min_x, min_y)),
    ]]


def _build_convex_hull_geometry(coordinates: List[Coordinate]) -> Optional[GeoJson]:
    unique = sorted(_unique_coordinates(coordinates))
    if not unique:
        return None
    if len(unique) == 1:
        lon, lat = unique[0]
        padding = 0.0001
        ring = [
            [lon - padding, lat - padding],
            [lon + padding, lat - padding],
            [lon + padding, lat + padding],
            [lon - padding, lat + padding],
            [lon - padding, lat - padding],
        ]
        return {"type": "Polygon", "coordinates": [ring]}

    def cross(origin: Coordinate, left: Coordinate, right: Coordinate) -> float:
        return (left[0] - origin[0]) * (right[1] - origin[1]) - (left[1] - origin[1]) * (right[0] - origin[0])

    lower: List[Coordinate] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper: List[Coordinate] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        min_lon = min(item[0] for item in unique)
        max_lon = max(item[0] for item in unique)
        min_lat = min(item[1] for item in unique)
        max_lat = max(item[1] for item in unique)
        padding = max(max_lon - min_lon, max_lat - min_lat, 0.0001) * 0.05
        ring = [
            [min_lon - padding, min_lat - padding],
            [max_lon + padding, min_lat - padding],
            [max_lon + padding, max_lat + padding],
            [min_lon - padding, max_lat + padding],
            [min_lon - padding, min_lat - padding],
        ]
        return {"type": "Polygon", "coordinates": [ring]}

    ring = [[lon, lat] for lon, lat in hull]
    ring.append(list(ring[0]))
    return {"type": "Polygon", "coordinates": [ring]}


def _fallback_cutoff_targets(point_samples: List[PointSample], raw_cutoffs: Sequence[Any]) -> List[Optional[float]]:
    declared_cutoffs = {
        cutoff
        for item in raw_cutoffs
        if (cutoff := _finite_number(item)) is not None
    }
    if declared_cutoffs:
        return sorted(declared_cutoffs)

    point_cutoffs = [cutoff for _, _, cutoff in point_samples if cutoff is not None]
    # Point properties often hold per-cell travel time, not requested display
    # bands.  Without declared cutoffs, produce one maximum-time shape instead
    # of dozens of accidental nested polygons.
    return [max(point_cutoffs)] if point_cutoffs else [None]


def _extract_point_samples(value: Any) -> List[PointSample]:
    features: Iterable[Any]
    if isinstance(value, dict) and value.get("type") == "FeatureCollection":
        features = value.get("features") or []
    elif isinstance(value, dict) and value.get("type") == "Feature":
        features = [value]
    else:
        return []

    samples: List[PointSample] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict):
            continue
        properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        cutoff = _extract_point_cutoff(properties)

        if geometry.get("type") == "Point":
            coordinate = _valid_coordinate(geometry.get("coordinates"))
            if coordinate is not None:
                samples.append((coordinate[0], coordinate[1], cutoff))
        elif geometry.get("type") == "MultiPoint":
            for raw_coordinate in geometry.get("coordinates") or []:
                coordinate = _valid_coordinate(raw_coordinate)
                if coordinate is not None:
                    samples.append((coordinate[0], coordinate[1], cutoff))
    return samples


def _extract_point_cutoff(properties: Dict[str, Any]) -> Optional[float]:
    for key in ("cutoff_min", "travel_time_min", "minutes"):
        cutoff = _finite_number(properties.get(key))
        if cutoff is not None:
            return cutoff
    return None


def _extract_origin_coordinate(origin: Any) -> Optional[Coordinate]:
    if not isinstance(origin, dict):
        return None
    lon = _finite_number(origin.get("lon"))
    lat = _finite_number(origin.get("lat"))
    if lon is None or lat is None or not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    return lon, lat


def _extract_polygon_geometries(value: Any) -> List[GeoJson]:
    if not isinstance(value, dict):
        return []
    if value.get("type") == "FeatureCollection":
        geometries = [
            feature.get("geometry")
            for feature in value.get("features") or []
            if isinstance(feature, dict)
        ]
    elif value.get("type") == "Feature":
        geometries = [value.get("geometry")]
    else:
        geometries = [value]
    return [
        geometry
        for geometry in geometries
        if isinstance(geometry, dict)
        and geometry.get("type") in {"Polygon", "MultiPolygon"}
        and isinstance(geometry.get("coordinates"), list)
        and geometry.get("coordinates")
    ]


def _geometries_contain_point(geometries: Iterable[GeoJson], coordinate: Optional[Coordinate]) -> bool:
    if coordinate is None:
        return False
    return any(_geometry_contains_point(geometry, coordinate) for geometry in geometries)


def _geometry_contains_point(geometry: GeoJson, coordinate: Coordinate) -> bool:
    geometry_type = geometry.get("type")
    raw_coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon":
        return _polygon_contains_point(raw_coordinates, coordinate)
    if geometry_type == "MultiPolygon" and isinstance(raw_coordinates, list):
        return any(_polygon_contains_point(polygon, coordinate) for polygon in raw_coordinates)
    return False


def _polygon_contains_point(raw_rings: Any, coordinate: Coordinate) -> bool:
    if not isinstance(raw_rings, list) or not raw_rings:
        return False
    shell = _valid_ring(raw_rings[0])
    if shell is None or not _ring_contains_point(shell, coordinate):
        return False
    for raw_hole in raw_rings[1:]:
        hole = _valid_ring(raw_hole)
        if hole is not None and _ring_contains_point(hole, coordinate):
            return False
    return True


def _ring_contains_point(ring: List[Coordinate], coordinate: Coordinate) -> bool:
    x, y = coordinate
    inside = False
    previous = ring[-1]
    for current in ring:
        if _point_on_segment(coordinate, previous, current):
            return True
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            crossing_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing_x:
                inside = not inside
        previous = current
    return inside


def _point_on_segment(point: Coordinate, start: Coordinate, end: Coordinate) -> bool:
    x, y = point
    x1, y1 = start
    x2, y2 = end
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    tolerance = 1e-10 * max(1.0, abs(x1), abs(y1), abs(x2), abs(y2))
    if abs(cross) > tolerance:
        return False
    return (
        min(x1, x2) - tolerance <= x <= max(x1, x2) + tolerance
        and min(y1, y2) - tolerance <= y <= max(y1, y2) + tolerance
    )


def _valid_ring(value: Any) -> Optional[List[Coordinate]]:
    if not isinstance(value, list):
        return None
    ring = [coordinate for item in value if (coordinate := _valid_coordinate(item)) is not None]
    return ring if len(ring) >= 3 else None


def _valid_coordinate(value: Any) -> Optional[Coordinate]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    lon = _finite_number(value[0])
    lat = _finite_number(value[1])
    if lon is None or lat is None or not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    return lon, lat


def _unique_coordinates(coordinates: Iterable[Coordinate]) -> List[Coordinate]:
    seen: set[Tuple[float, float]] = set()
    unique: List[Coordinate] = []
    for lon, lat in coordinates:
        key = (round(lon, 12), round(lat, 12))
        if key in seen:
            continue
        seen.add(key)
        unique.append((lon, lat))
    return unique


def _finite_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _format_cutoff(value: Optional[float]) -> str:
    if value is None:
        return ""
    return str(int(value)) if value.is_integer() else f"{value:g}"
