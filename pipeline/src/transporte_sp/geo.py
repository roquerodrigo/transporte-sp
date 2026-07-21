"""Geometry helpers, in WGS84 degrees throughout.

Coordinates are always ``[lon, lat]`` in geometry lists (GeoJSON order) and named
``lat``/``lon`` in the model — mixing the two is the classic way to put every station in
the Atlantic, so the conversion happens only here.
"""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_008.8


def distance_m(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Great-circle distance in metres."""
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    delta_phi = phi_b - phi_a
    delta_lambda = math.radians(lon_b - lon_a)
    hav = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(hav))


def line_length_km(geometry: list[list[list[float]]]) -> float:
    """Total length of a MultiLineString-shaped nested list."""
    total = 0.0
    for part in geometry:
        for (lon_a, lat_a), (lon_b, lat_b) in zip(part, part[1:], strict=False):
            total += distance_m(lat_a, lon_a, lat_b, lon_b)
    return round(total / 1000, 3)


def centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Mean ``(lat, lon)`` of *points*. Fine at city scale; no projection needed."""
    return (
        sum(lat for lat, _ in points) / len(points),
        sum(lon for _, lon in points) / len(points),
    )


def flatten(geometry: dict) -> list[list[list[float]]]:
    """Normalise any GeoJSON line geometry into a list of coordinate lists."""
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if kind == "LineString":
        return [coordinates]
    if kind == "MultiLineString":
        return list(coordinates)
    if kind == "GeometryCollection":
        parts: list[list[list[float]]] = []
        for member in geometry.get("geometries", []):
            parts.extend(flatten(member))
        return parts
    return []


def chain_parts(parts: list[list[list[float]]]) -> list[list[float]]:
    """Join disjoint line segments into one continuous polyline, end to end.

    GeoSampa publishes a line as several unordered segments, so measuring how far along a
    line a station sits requires putting them back in order first. Each remaining segment
    is attached — forwards or reversed — at whichever end of the growing polyline it comes
    closest to.
    """
    remaining = [part for part in parts if len(part) >= 2]
    if not remaining:
        return []
    chained = list(remaining.pop(0))
    while remaining:
        best = None
        for index, part in enumerate(remaining):
            for reverse in (False, True):
                candidate = part[::-1] if reverse else part
                for at_tail in (True, False):
                    gap = (
                        _gap(chained[-1], candidate[0])
                        if at_tail
                        else _gap(candidate[-1], chained[0])
                    )
                    if best is None or gap < best[0]:
                        best = (gap, index, candidate, at_tail)
        _, index, candidate, at_tail = best
        remaining.pop(index)
        chained = chained + candidate if at_tail else candidate + chained
    return chained


def _gap(left: list[float], right: list[float]) -> float:
    return distance_m(left[1], left[0], right[1], right[0])


def along_track(polyline: list[list[float]], lat: float, lon: float) -> float:
    """Distance in metres from the start of *polyline* to the vertex nearest ``(lat, lon)``."""
    travelled = 0.0
    best_position, best_gap = 0.0, float("inf")
    for index, (vertex_lon, vertex_lat) in enumerate(polyline):
        if index:
            previous_lon, previous_lat = polyline[index - 1]
            travelled += distance_m(previous_lat, previous_lon, vertex_lat, vertex_lon)
        gap = distance_m(lat, lon, vertex_lat, vertex_lon)
        if gap < best_gap:
            best_position, best_gap = travelled, gap
    return best_position


def douglas_peucker(points: list[list[float]], tolerance_m: float) -> list[list[float]]:
    """Simplify a coordinate list, keeping endpoints. Tolerance is metres on the ground."""
    if len(points) < 3:
        return points
    tolerance_deg = tolerance_m / 111_320
    first, last = points[0], points[-1]
    index, worst = 0, 0.0
    for position in range(1, len(points) - 1):
        offset = _perpendicular_distance(points[position], first, last)
        if offset > worst:
            index, worst = position, offset
    if worst <= tolerance_deg:
        return [first, last]
    left = douglas_peucker(points[: index + 1], tolerance_m)
    right = douglas_peucker(points[index:], tolerance_m)
    return left[:-1] + right


def _perpendicular_distance(point, start, end) -> float:
    (x, y), (x1, y1), (x2, y2) = point, start, end
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    return abs(dy * x - dx * y + x2 * y1 - y2 * x1) / math.hypot(dx, dy)
