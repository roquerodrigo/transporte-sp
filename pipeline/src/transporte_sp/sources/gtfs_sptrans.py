"""GTFS from SPTrans — published under the access-to-information act, no sign-up.

Contrary to the common belief that this feed only covers buses, it carries the rail
network too: 6 metro routes and 7 commuter-rail routes, with the **station order per
direction** and 26 shapes tracing the real alignment. That ordering is what neither
GeoSampa nor OSM gives cleanly, and it is the reason this source exists in the pipeline.

Known gaps: Line 6-Laranja and Line 17-Ouro are absent (both opened partially in 2026),
there is no ``parent_station``/``wheelchair_boarding``, and the rail routes carry a single
trip per direction, so there is no timetable to read.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile

from transporte_sp import snapshot
from transporte_sp.config import settings
from transporte_sp.geo import douglas_peucker
from transporte_sp.model import Coordinates, ExternalIds, LineObservation, StationObservation
from transporte_sp.naming import line_number

log = logging.getLogger(__name__)

SOURCE = "gtfs_sptrans"
LICENCE = "public-record (Lei 12.527/2011)"
ARCHIVE = "gtfs.zip"

# GTFS route_type values that mean rail. 3 (bus) is deliberately excluded: municipal bus
# routes are out of scope, and the BRT corridors come from GeoSampa instead.
RAIL_ROUTE_TYPES = {"0": "lrt", "1": "subway", "2": "commuter_rail", "5": "lrt", "7": "monorail"}

SHAPE_SIMPLIFY_M = 5.0


def fetch() -> None:
    payload = snapshot.download(settings.gtfs_sptrans_url)
    if not payload.startswith(b"PK"):
        raise RuntimeError("SPTrans did not return a zip archive")
    snapshot.write(SOURCE, ARCHIVE, payload, settings.gtfs_sptrans_url, LICENCE)


def _archive() -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(snapshot.read(SOURCE, ARCHIVE)))


def _table(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    with archive.open(name) as handle:
        text = io.TextIOWrapper(handle, encoding="utf-8-sig")
        return list(csv.DictReader(text))


def _rail_routes(archive: zipfile.ZipFile) -> list[dict[str, str]]:
    return [r for r in _table(archive, "routes.txt") if r["route_type"] in RAIL_ROUTE_TYPES]


def lines() -> list[LineObservation]:
    archive = _archive()
    routes = _rail_routes(archive)
    route_ids = {route["route_id"] for route in routes}

    trips = [trip for trip in _table(archive, "trips.txt") if trip["route_id"] in route_ids]
    shapes = _shapes(archive, {trip["shape_id"] for trip in trips if trip.get("shape_id")})
    ordered_stops = _stop_sequences(archive, trips)

    observations: list[LineObservation] = []
    for route in routes:
        route_trips = [trip for trip in trips if trip["route_id"] == route["route_id"]]
        geometry = [
            shapes[trip["shape_id"]]
            for trip in route_trips
            if trip.get("shape_id") in shapes
        ]
        # The two directions retrace the same track; one of them is enough as geometry and
        # as the canonical station order.
        sequence = max(
            (ordered_stops.get(trip["trip_id"], []) for trip in route_trips),
            key=len,
            default=[],
        )
        colour = (route.get("route_color") or "").strip()
        observations.append(
            LineObservation(
                source=SOURCE,
                source_ref=route["route_id"],
                name=route.get("route_long_name") or route["route_id"],
                number=line_number(route["route_id"]),
                colour=f"#{colour}" if colour else None,
                mode=RAIL_ROUTE_TYPES[route["route_type"]],
                status="operational",
                geometry=geometry[:1],
                station_refs=sequence,
                extra={"route_short_name": route.get("route_short_name")},
            )
        )
    log.info("%s: %d rail lines", SOURCE, len(observations))
    return observations


def _shapes(archive: zipfile.ZipFile, wanted: set[str]) -> dict[str, list[list[float]]]:
    """Read only the shapes belonging to rail trips — shapes.txt is 60 MB of mostly buses."""
    points: dict[str, list[tuple[int, float, float]]] = {}
    with archive.open("shapes.txt") as handle:
        for row in csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")):
            shape_id = row["shape_id"]
            if shape_id not in wanted:
                continue
            points.setdefault(shape_id, []).append(
                (
                    int(row["shape_pt_sequence"]),
                    float(row["shape_pt_lon"]),
                    float(row["shape_pt_lat"]),
                )
            )
    return {
        shape_id: douglas_peucker(
            [[lon, lat] for _, lon, lat in sorted(rows)], SHAPE_SIMPLIFY_M
        )
        for shape_id, rows in points.items()
    }


def _stop_sequences(archive: zipfile.ZipFile, trips: list[dict]) -> dict[str, list[str]]:
    trip_ids = {trip["trip_id"] for trip in trips}
    rows: dict[str, list[tuple[int, str]]] = {}
    with archive.open("stop_times.txt") as handle:
        for row in csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")):
            if row["trip_id"] not in trip_ids:
                continue
            rows.setdefault(row["trip_id"], []).append(
                (int(row["stop_sequence"]), row["stop_id"])
            )
    return {trip_id: [stop for _, stop in sorted(items)] for trip_id, items in rows.items()}


def stations() -> list[StationObservation]:
    archive = _archive()
    routes = _rail_routes(archive)
    route_ids = {route["route_id"] for route in routes}
    trips = [trip for trip in _table(archive, "trips.txt") if trip["route_id"] in route_ids]
    trip_to_route = {trip["trip_id"]: trip["route_id"] for trip in trips}

    sequences = _stop_sequences(archive, trips)
    stop_to_routes: dict[str, set[str]] = {}
    for trip_id, stop_ids in sequences.items():
        for stop_id in stop_ids:
            stop_to_routes.setdefault(stop_id, set()).add(trip_to_route[trip_id])

    observations: list[StationObservation] = []
    for stop in _table(archive, "stops.txt"):
        routes_here = stop_to_routes.get(stop["stop_id"])
        if not routes_here:
            continue
        observations.append(
            StationObservation(
                source=SOURCE,
                source_ref=stop["stop_id"],
                name=stop["stop_name"].strip(),
                coordinates=Coordinates(lat=float(stop["stop_lat"]), lon=float(stop["stop_lon"])),
                line_refs=sorted(line_number(r) or r for r in routes_here),
                status="operational",
                external_ids=ExternalIds(gtfs_stop_id=stop["stop_id"]),
                extra={"routes": sorted(routes_here), "desc": stop.get("stop_desc") or None},
            )
        )
    log.info("%s: %d rail stations", SOURCE, len(observations))
    return observations
