"""Reconciling stations.

The clustering itself lives in :mod:`transporte_sp.merge.matching`; this module turns each
cluster into a published station, choosing a value per field by declared precedence and
recording what it did not choose.

Line membership is assembled from three signals, because no single one covers everything:
the line references a source attaches to the station, the colour name several sources use
instead of a number, and — for the stations only OSM knows — the position of the stop
along a route relation.
"""

from __future__ import annotations

import logging

from transporte_sp.config import settings
from transporte_sp.geo import centroid, distance_m
from transporte_sp.merge import lines as line_merge
from transporte_sp.merge.matching import cluster
from transporte_sp.merge.precedence import STATION_FIELDS, confidence, rank
from transporte_sp.model import Alternative, Conflict, Station, StationObservation
from transporte_sp.naming import normalise, slugify

log = logging.getLogger(__name__)


def reconcile(
    observations: list[StationObservation], conflicts: list[Conflict]
) -> tuple[list[Station], list[list[StationObservation]]]:
    clusters, aproximados = cluster(observations)
    for um, outro, gap in aproximados:
        conflicts.append(
            Conflict(
                entity="station",
                entity_id=slugify(um),
                fieldname="identidade",
                chosen=um,
                chosen_source="pipeline",
                rejected=outro,
                rejected_source="pipeline",
                detail=(
                    f"nomes diferentes a {gap} m: tratados como a mesma estação, porque as "
                    "camadas de planejamento nomeiam uma baldeação por linha"
                ),
            )
        )
    stations: list[Station] = []
    used_slugs: dict[str, int] = {}

    for group in clusters:
        name = _pick(group, "name")
        slug = slugify(name["value"])
        used_slugs[slug] = used_slugs.get(slug, 0) + 1
        if used_slugs[slug] > 1:
            slug = f"{slug}-{used_slugs[slug]}"

        stations.append(
            Station(
                id=slug,
                slug=slug,
                name=name,
                coordinates=_coordinates(group, conflicts, slug),
                lines=[],
                status=_pick(group, "status")
                or {"value": "operational", "source": "pipeline", "confidence": "E"},
                code=_pick(group, "code"),
                accessibility=_pick(group, "accessibility"),
                opened=_pick(group, "opened"),
                external_ids=_external_ids(group),
                observed_by=sorted({item.source for item in group}),
            )
        )
    return stations, clusters


def _values(
    group: list[StationObservation], fieldname: str
) -> list[tuple[StationObservation, object]]:
    """Candidate ``(observation, value)`` pairs for *fieldname*, best source first."""
    pairs = []
    for item in group:
        value = _extract(item, fieldname)
        if value not in (None, ""):
            pairs.append((item, value))
    return sorted(pairs, key=lambda pair: rank(STATION_FIELDS, fieldname, pair[0].source))


def _extract(observation: StationObservation, fieldname: str):
    if fieldname == "code":
        return observation.external_ids.metro_code
    return getattr(observation, fieldname, None)


def _pick(group: list[StationObservation], fieldname: str) -> dict | None:
    candidates = _values(group, fieldname)
    if not candidates:
        return None
    winner, value = candidates[0]
    if fieldname == "name":
        value = _readable(value, winner.source)
    # "SÃO CARLOS" alongside "São Carlos" is not a second reading, it is the same one in
    # capitals; and two sources spelling it identically only need saying once.
    alternatives = []
    vistos = {_comparable(value, fieldname)}
    for item, other_value in candidates[1:]:
        marcador = _comparable(other_value, fieldname)
        if marcador in vistos:
            continue
        vistos.add(marcador)
        alternatives.append(
            Alternative(value=other_value, source=item.source, confidence=confidence(item.source))
        )
    return {
        "value": value,
        "source": winner.source,
        "confidence": confidence(winner.source),
        "alternatives": alternatives,
    }


def _comparable(value, fieldname: str):
    """How two readings of a field are told apart when deciding what to publish."""
    return normalise(str(value)) if fieldname == "name" else str(value)


def _readable(name: str, source: str) -> str:
    """GeoSampa shouts every name; repair it rather than publish ``CORINTHIANS-ITAQUERA``."""
    return line_merge.title_case(name) if source == "geosampa" and name.isupper() else name


def _coordinates(group, conflicts: list[Conflict], station_id: str) -> dict:
    """Best coordinate, with any far-away runner-up reported as a conflict."""
    ranked = sorted(group, key=lambda item: rank(STATION_FIELDS, "coordinates", item.source))
    winner = ranked[0]
    chosen = {"lat": winner.coordinates.lat, "lon": winner.coordinates.lon}

    alternatives = []
    # A source that observed the station twice — the GTFS lists a stop per direction, and
    # GeoSampa a point per layer — would otherwise repeat the same reading. Rounding to five
    # decimals (about a metre) is what the page shows anyway.
    vistos: set[tuple] = set()
    for item in ranked[1:]:
        gap = distance_m(
            winner.coordinates.lat, winner.coordinates.lon,
            item.coordinates.lat, item.coordinates.lon,
        )
        marcador = (item.source, round(item.coordinates.lat, 5), round(item.coordinates.lon, 5))
        if marcador not in vistos:
            vistos.add(marcador)
            alternatives.append(
                Alternative(
                    value={"lat": item.coordinates.lat, "lon": item.coordinates.lon},
                    source=item.source,
                    confidence=confidence(item.source),
                    note=f"{round(gap)} m de distância",
                )
            )
        if gap > settings.coordinate_conflict_m:
            conflicts.append(
                Conflict(
                    entity="station",
                    entity_id=station_id,
                    fieldname="coordinates",
                    chosen=chosen,
                    chosen_source=winner.source,
                    rejected={"lat": item.coordinates.lat, "lon": item.coordinates.lon},
                    rejected_source=item.source,
                    detail=f"sources place this station {round(gap)} m apart",
                )
            )
    return {
        "value": chosen,
        "source": winner.source,
        "confidence": confidence(winner.source),
        "alternatives": alternatives,
    }


def _external_ids(group: list[StationObservation]) -> dict:
    merged: dict[str, str] = {}
    for item in group:
        for key, value in item.external_ids.model_dump().items():
            if value and key not in merged:
                merged[key] = value
    return merged


def assign_lines(stations, clusters, network_lines, line_observations) -> dict[str, set[str]]:
    """Attach every station to the lines that serve it.

    Returns, per station, the lines it is only *projected* to serve. An operating station
    can be a future stop of another line — Ipiranga runs on Line 10 today and appears in
    GeoSampa's projected layer for Line 15 — and that distinction has to survive, or the
    step that trims a line to its timetable will delete the future half of the network.
    """
    by_number = {line.id: line for line in network_lines}
    by_colour = line_merge.colour_index(network_lines)
    by_slug = {line.slug: line.id for line in network_lines}
    planejadas: dict[str, set[str]] = {}

    for station, group in zip(stations, clusters, strict=True):
        found: set[str] = set()
        for observation in group:
            for reference in _references(observation):
                line_id = _resolve(reference, by_number, by_colour, by_slug)
                if not line_id:
                    continue
                found.add(line_id)
                if observation.status and observation.status != "operational":
                    planejadas.setdefault(station.id, set()).add(line_id)
        station.lines = sorted_lines(found)
        # A line asserted by an operating record is not projected, whatever else said so.
        for observation in group:
            if observation.status != "operational":
                continue
            for reference in _references(observation):
                line_id = _resolve(reference, by_number, by_colour, by_slug)
                if line_id:
                    planejadas.get(station.id, set()).discard(line_id)
    return planejadas


def _references(observation: StationObservation) -> list[str]:
    references = list(observation.line_refs)
    # Wikidata states the line as a label ("Linha 5 do Metrô de São Paulo"), and for the
    # commuter network it often names a railway that no longer runs — hence hint, not fact.
    references.extend(str(item) for item in observation.extra.get("lines", []))
    references.extend(str(item) for item in observation.extra.get("routes", []))
    return references


def _resolve(reference: str, by_number, by_colour, by_slug) -> str | None:
    from transporte_sp.naming import line_number

    text = reference.strip()
    if not text:
        return None
    if text.isdigit() and f"linha-{int(text)}" in by_number:
        return f"linha-{int(text)}"
    colour = by_colour.get(normalise(text))
    if colour:
        return colour
    number = line_number(text)
    if number and f"linha-{int(number)}" in by_number:
        return f"linha-{int(number)}"
    return by_slug.get(slugify(text))


def sorted_lines(line_ids) -> list[str]:
    """Line ids in the order a reader expects: by number, named services last."""
    return sorted(set(line_ids), key=_line_order)


def _line_order(line_id: str) -> tuple[int, str]:
    suffix = line_id.removeprefix("linha-")
    return (int(suffix), "") if suffix.isdigit() else (999, line_id)


def primary_line(station: Station) -> str | None:
    """The line whose section owns the station's canonical page."""
    return station.lines[0] if station.lines else None


def centre(group: list[StationObservation]) -> tuple[float, float]:
    return centroid([(item.coordinates.lat, item.coordinates.lon) for item in group])
