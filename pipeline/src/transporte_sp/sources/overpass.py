"""OpenStreetMap via Overpass — ODbL.

The only source that covers the whole metropolitan region: GeoSampa stops at the city
limit and the GTFS is missing Line 6-Laranja and Line 17-Ouro. OSM has all of them,
including alignments opened in 2026, plus the VLT da Baixada Santista and the GRU
people mover.

Two operational notes learned the hard way: the public instance answers **406** to a
request without a ``User-Agent``, and it returns an XML "server too busy" page with HTTP
200 when loaded — which is why every response is validated as JSON and the mirrors are
tried in turn.

Known gaps: accessibility is tagged on roughly a fifth of the stations, and no BRT
corridor in the region is tagged as one.
"""

from __future__ import annotations

import json
import logging

from transporte_sp import snapshot
from transporte_sp.config import settings
from transporte_sp.model import Coordinates, ExternalIds, LineObservation, StationObservation
from transporte_sp.naming import line_number

log = logging.getLogger(__name__)

SOURCE = "osm"
LICENCE = "ODbL-1.0"

ROUTE_MODES = {
    "subway": "subway",
    "light_rail": "lrt",
    "train": "commuter_rail",
    "monorail": "monorail",
    "tram": "lrt",
}

_ACCESSIBILITY = {"yes": "full", "limited": "partial", "no": "none"}


def _bbox_clause() -> str:
    min_lon, min_lat, max_lon, max_lat = settings.bbox
    return f"({min_lat},{min_lon},{max_lat},{max_lon})"


def _routes_query() -> str:
    return (
        "[out:json][timeout:600];\n"
        'relation["type"="route"]["route"~"^(subway|light_rail|train|monorail|tram)$"]'
        f"{_bbox_clause()};\nout geom;"
    )


def _stations_query() -> str:
    bbox = _bbox_clause()
    return (
        "[out:json][timeout:600];\n(\n"
        f'  node["railway"~"^(station|halt)$"]{bbox};\n'
        f'  way["railway"~"^(station|halt)$"]{bbox};\n'
        f'  node["public_transport"="station"]["train"="yes"]{bbox};\n'
        f'  node["public_transport"="station"]["subway"="yes"]{bbox};\n'
        ");\nout center tags;"
    )


def fetch() -> None:
    for filename, query in (
        ("routes.json", _routes_query()),
        ("stations.json", _stations_query()),
    ):
        payload = _query(query)
        snapshot.write(SOURCE, filename, payload, settings.overpass_mirrors[0], LICENCE)


def _query(query: str) -> bytes:
    """Run *query* against each mirror until one returns parseable JSON."""
    errors: list[str] = []
    for mirror in settings.overpass_mirrors:
        try:
            payload = snapshot.download(
                mirror,
                method="POST",
                data=query.encode(),
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )
            document = json.loads(payload)
        except Exception as error:  # noqa: BLE001 - next mirror gets a turn
            errors.append(f"{mirror}: {error}")
            continue
        if "elements" not in document:
            errors.append(f"{mirror}: response without an `elements` key")
            continue
        log.info("%s: %d elements from %s", SOURCE, len(document["elements"]), mirror)
        return payload
    raise RuntimeError("every Overpass mirror failed:\n  " + "\n  ".join(errors))


def _is_tourist(tags: dict) -> bool:
    """Heritage and sightseeing routes are not mass transit.

    ``service=tourism`` covers the Trem Republicano; the Bonde Turístico de Santos and the
    Trem de Guararema carry neither an operator nor a network, which no scheduled line in
    the region lacks.
    """
    return tags.get("service") == "tourism" or not (tags.get("operator") or tags.get("network"))


def _elements(filename: str) -> list[dict]:
    return json.loads(snapshot.read(SOURCE, filename)).get("elements", [])


def lines() -> list[LineObservation]:
    observations: list[LineObservation] = []
    for relation in _elements("routes.json"):
        tags = relation.get("tags") or {}
        name = tags.get("name")
        if not name or _is_tourist(tags):
            continue
        geometry = [
            [[point["lon"], point["lat"]] for point in member["geometry"]]
            for member in relation.get("members", [])
            if member.get("type") == "way" and member.get("geometry")
        ]
        observations.append(
            LineObservation(
                source=SOURCE,
                source_ref=f"relation/{relation['id']}",
                name=name,
                number=tags.get("ref") or line_number(name),
                colour=tags.get("colour"),
                mode=ROUTE_MODES.get(tags.get("route", ""), "commuter_rail"),
                operator=tags.get("operator"),
                status="operational",
                geometry=geometry,
                station_refs=[
                    f"{member['type']}/{member['ref']}"
                    for member in relation.get("members", [])
                    if member.get("role", "").startswith("stop")
                ],
                # `out geom` inlines the coordinate of each stop node, so the sequence is
                # usable even when the node is not itself tagged `railway=station`.
                stop_points=[
                    [member["lon"], member["lat"]]
                    for member in relation.get("members", [])
                    if member.get("role", "").startswith("stop") and "lon" in member
                ],
                extra={
                    "network": tags.get("network"),
                    "wikidata": tags.get("wikidata"),
                    "from": tags.get("from"),
                    "to": tags.get("to"),
                    "interval": tags.get("interval"),
                },
            )
        )
    log.info("%s: %d route relations", SOURCE, len(observations))
    return observations


def stations() -> list[StationObservation]:
    observations: list[StationObservation] = []
    for element in _elements("stations.json"):
        tags = element.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue
        centre = element.get("center") or element
        lat, lon = centre.get("lat"), centre.get("lon")
        if lat is None or lon is None:
            continue
        wheelchair = tags.get("wheelchair")
        observations.append(
            StationObservation(
                source=SOURCE,
                source_ref=f"{element['type']}/{element['id']}",
                name=name,
                coordinates=Coordinates(lat=lat, lon=lon),
                # `ref` on a station is the operator's station code (VMD, GBU, BAS…), not a
                # line — reading it as a line reference silently attaches platform numbers
                # to whichever line shares the digit. Line membership comes from the route
                # relations instead.
                line_refs=[],
                operator=tags.get("operator"),
                status="operational" if tags.get("disused") != "yes" else "closed",
                accessibility=_ACCESSIBILITY.get(wheelchair) if wheelchair else None,
                external_ids=ExternalIds(
                    osm=f"{element['type']}/{element['id']}",
                    wikidata=tags.get("wikidata"),
                    metro_code=tags.get("ref"),
                ),
                extra={"network": tags.get("network"), "railway": tags.get("railway")},
            )
        )
    log.info("%s: %d stations", SOURCE, len(observations))
    return observations
