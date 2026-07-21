"""Reconciling lines.

São Paulo numbers its rail lines 1–22 across every operator — Line 4 is the metro's, Line 9
is a commuter line, and no number is reused. That single namespace is the join key here.
Services without a number (VLT da Baixada, Expresso Aeroporto, Aeromóvel GRU, tourist
trains) key on their name instead, after the direction suffix is cut off, so the two
opposite-direction relations OSM keeps for each route collapse into one line.
"""

from __future__ import annotations

import logging
import re

from transporte_sp.geo import line_length_km
from transporte_sp.merge.precedence import GEOMETRY_STRATEGY, LINE_FIELDS, confidence, rank
from transporte_sp.model import Alternative, Conflict, Line, LineObservation, Sourced
from transporte_sp.naming import line_slug, normalise, slugify

log = logging.getLogger(__name__)

# The unified numbering the region actually uses. Anything outside it is a named service.
MAX_LINE_NUMBER = 30

_DIRECTION_SUFFIX = re.compile(r"\s*[:—-]\s*.*(?:→|⇒|=>|➔).*$")
_LOWERCASE_PARTICLES = {"de", "da", "do", "das", "dos", "e"}
# A letter opening the string or following anything that is not a letter — capitalising
# there keeps "CIDADE A.E. CARVALHO" and "RIO DAS PEDRAS/ARICANDUVA" readable.
_AFTER_BOUNDARY = re.compile(r"(?:^|(?<=[^a-zà-ÿ]))[a-zà-ÿ]")


def key_for(observation: LineObservation) -> str:
    """Canonical id of the line an observation describes."""
    number = observation.number
    if number and number.isdigit() and 1 <= int(number) <= MAX_LINE_NUMBER:
        return f"linha-{int(number)}"
    return slugify(base_name(observation.name))


def base_name(name: str) -> str:
    """``Linha 5 - Lilás: Capão Redondo → Chácara Klabin`` → ``Linha 5 - Lilás``."""
    head = name.split(":", 1)[0]
    return _DIRECTION_SUFFIX.sub("", head).strip()


def title_case(text: str) -> str:
    """Title-case a shouted name without capitalising Portuguese particles.

    >>> title_case("AEROPORTO DE GUARULHOS")
    'Aeroporto de Guarulhos'
    """
    capitalised = _AFTER_BOUNDARY.sub(lambda match: match.group(0).upper(), text.lower())
    return " ".join(
        word.lower() if index and word.lower() in _LOWERCASE_PARTICLES else word
        for index, word in enumerate(capitalised.split())
    )


def reconcile(observations: list[LineObservation], conflicts: list[Conflict]) -> list[Line]:
    grouped: dict[str, list[LineObservation]] = {}
    for observation in observations:
        grouped.setdefault(key_for(observation), []).append(observation)

    return [_build(key, group, conflicts) for key, group in sorted(grouped.items())]


def _build(key: str, group: list[LineObservation], conflicts: list[Conflict]) -> Line:
    number = _first(group, "number")
    display_name = _display_name(group)
    slug = line_slug(number["value"] if number else "", display_name["value"])

    line = Line(
        id=key,
        slug=slug,
        name=display_name,
        number=number,
        colour=_first(group, "colour") or _colour_from_name(display_name["value"]),
        mode=_first(group, "mode")
        or {"value": "subway", "source": "pipeline", "confidence": "E"},
        operator=_first(group, "operator"),
        status=_status(group),
        geometry=_geometry(group, conflicts, key),
        observed_by=sorted({observation.source for observation in group}),
    )
    return line


# Lines that are not built yet have no hex colour anywhere — no source publishes one for a
# line that does not run. Reading the colour the line is *named* after keeps the projected
# network legible on the map instead of rendering it all in the same grey. This is a
# presentation fallback, published as inferred, never as a claim about official branding.
_COLOUR_BY_NAME = {
    "azul": "#0353a4",
    "verde": "#007a33",
    "vermelha": "#d62828",
    "amarela": "#ffd500",
    "lilas": "#8e44ad",
    "laranja": "#e8590c",
    "rubi": "#9b1b30",
    "diamante": "#8e9aaf",
    "esmeralda": "#00875a",
    "turquesa": "#0f9ba8",
    "coral": "#ff7f50",
    "safira": "#0b3d91",
    "jade": "#00a86b",
    "onix": "#2b2b2b",
    "prata": "#9aa0a6",
    "violeta": "#7b2ff7",
    "ouro": "#c9a227",
    "celeste": "#4ea8de",
    "rosa": "#e75480",
    "marrom": "#6f4e37",
}


def _colour_from_name(name: str) -> dict | None:
    hex_colour = _COLOUR_BY_NAME.get(normalise(name))
    if not hex_colour:
        return None
    return {"value": hex_colour, "source": "pipeline", "confidence": "E"}


def _ordered(group: list[LineObservation], fieldname: str) -> list[LineObservation]:
    """Candidates for *fieldname*, best first — precedence, then operating over planned."""
    return sorted(
        (item for item in group if getattr(item, fieldname, None)),
        key=lambda item: (
            rank(LINE_FIELDS, fieldname, item.source),
            0 if item.status == "operational" else 1,
        ),
    )


def _first(group: list[LineObservation], fieldname: str) -> dict | None:
    candidates = _ordered(group, fieldname)
    if not candidates:
        return None
    winner = candidates[0]
    value = getattr(winner, fieldname)
    alternatives = [
        Alternative(value=getattr(item, fieldname), source=item.source,
                    confidence=confidence(item.source))
        for item in candidates[1:]
        if getattr(item, fieldname) != value
    ]
    return {
        "value": value,
        "source": winner.source,
        "confidence": confidence(winner.source),
        "alternatives": _dedupe(alternatives),
    }


def _dedupe(alternatives: list[Alternative]) -> list[Alternative]:
    seen: set[tuple] = set()
    unique = []
    for alternative in alternatives:
        marker = (str(alternative.value), alternative.source)
        if marker not in seen:
            seen.add(marker)
            unique.append(alternative)
    return unique


def _display_name(group: list[LineObservation]) -> dict:
    """São Paulo calls its lines by colour — "Amarela", not "Vila Sônia - Luz"."""
    coloured = _ordered(group, "colour_name")
    if coloured:
        winner = coloured[0]
        return {
            "value": title_case(winner.colour_name),
            "source": winner.source,
            "confidence": confidence(winner.source),
        }
    named = _ordered(group, "name")
    winner = named[0]
    # The bus-corridor names come out of GeoSampa in capitals, like everything else there.
    name = base_name(winner.name)
    return {
        "value": title_case(name) if name.isupper() else name,
        "source": winner.source,
        "confidence": confidence(winner.source),
    }


def _status(group: list[LineObservation]) -> dict:
    """Operating, partially operating, or not built yet.

    A line that GeoSampa still lists only as projected but that OSM already maps as a
    running route is **partially** open — Lines 6-Laranja and 17-Ouro both opened a first
    stretch in 2026 while the rest is under construction. The inference applies only where
    GeoSampa covers the line at all, so the VLT da Baixada Santista, which is outside the
    city and therefore outside GeoSampa, is not mislabelled.
    """
    running = {item.source for item in group if item.status == "operational"}
    geosampa_states = {item.status for item in group if item.source == "geosampa"}

    if not running:
        return {
            "value": "planned" if geosampa_states else "proposed",
            "source": "geosampa" if geosampa_states else "osm",
            "confidence": "A" if geosampa_states else "C",
        }
    if geosampa_states and "operational" not in geosampa_states:
        return {
            "value": "partial",
            "source": "pipeline",
            "confidence": "E",
            "alternatives": [
                Alternative(value="operational", source=source, confidence=confidence(source))
                for source in sorted(running)
            ]
            + [Alternative(value="planned", source="geosampa", confidence="A")],
        }
    winner = min(running, key=lambda source: rank(LINE_FIELDS, "status", source))
    return {"value": "operational", "source": winner, "confidence": confidence(winner)}


def _geometry(
    group: list[LineObservation], conflicts: list[Conflict], key: str
) -> dict | None:
    """Best available alignment.

    GeoSampa splits a line into segments (join them) while OSM repeats the whole line once
    per direction (keep one). After that the longest candidate wins, because the usual
    disagreement is coverage: GeoSampa is clipped at the city limit, so for anything
    reaching Jundiaí, Mogi or the ABC only OSM has the full alignment.
    """
    candidates: list[tuple[str, list, float]] = []
    for source in {item.source for item in group}:
        parts = [item for item in group if item.source == source and item.geometry]
        if not parts:
            continue
        if GEOMETRY_STRATEGY.get(source, "longest") == "concat":
            geometry = [segment for item in parts for segment in item.geometry]
        else:
            geometry = max(
                (item.geometry for item in parts), key=line_length_km, default=[]
            )
        if geometry:
            candidates.append((source, geometry, line_length_km(geometry)))
    if not candidates:
        return None

    candidates.sort(key=lambda entry: entry[2], reverse=True)
    source, geometry, length = candidates[0]
    alternatives = [
        Alternative(
            value=f"{other_length} km",
            source=other_source,
            confidence=confidence(other_source),
            note=(
                "clipped at the city limit"
                if other_source == "geosampa"
                else "shorter alignment, not used"
            ),
        )
        for other_source, _, other_length in candidates[1:]
    ]
    for other_source, _, other_length in candidates[1:]:
        # GeoSampa covering less than OSM is its documented extent, not a disagreement.
        if other_source == "geosampa" and other_length < length:
            continue
        if other_length and abs(length - other_length) / max(length, other_length) > 0.25:
            conflicts.append(
                Conflict(
                    entity="line",
                    entity_id=key,
                    fieldname="geometry",
                    chosen=f"{length} km",
                    chosen_source=source,
                    rejected=f"{other_length} km",
                    rejected_source=other_source,
                    detail="alignments differ by more than a quarter of their length",
                )
            )
    return {
        "value": geometry,
        "source": source,
        "confidence": confidence(source),
        "alternatives": alternatives,
    }


def order_stations(lines, stations, clusters, observations) -> None:
    """Give every line its station sequence.

    The GTFS is the only source that states the order outright, so it is used wherever it
    reaches. For the lines it does not cover — 6-Laranja, 17-Ouro, the VLT, the airport
    people mover — the order comes from the ordered stop members of the OSM route relation,
    matched to stations by position.
    """
    from transporte_sp.merge import nearest

    by_key: dict[str, list[LineObservation]] = {}
    for observation in observations:
        by_key.setdefault(key_for(observation), []).append(observation)

    gtfs_index = {
        observation.source_ref: station
        for station, cluster in zip(stations, clusters, strict=True)
        for observation in cluster
        if observation.source == "gtfs_sptrans"
    }

    by_id = {station.id: station for station in stations}

    for line in lines:
        group = by_key.get(line.id, [])
        from_gtfs = _from_gtfs(group, gtfs_index)
        sequence = from_gtfs or _from_stop_points(group, stations, clusters, nearest)
        basis = "gtfs_sptrans" if from_gtfs else ("osm" if sequence else "pipeline")
        members = [station for station in stations if line.id in station.lines]

        if from_gtfs and line.status.value == "operational":
            # The GTFS enumerates the whole operating line, so a station it omits was
            # attached by a weaker source — usually a historical assignment (Luz and
            # Palmeiras-Barra Funda still show up on Line 10 in the collaborative sources).
            keep = set(sequence)
            for station in members:
                if station.id not in keep:
                    station.lines.remove(line.id)
            ordered = sequence
        else:
            ordered = _append_unsequenced(sequence, members, by_id, line)

        line.stations = ordered
        line.station_order = Sourced[str](
            value=basis,
            source=basis,
            confidence="A" if basis == "gtfs_sptrans" else ("C" if basis == "osm" else "E"),
        )
        for station_id in ordered:
            station = by_id[station_id]
            if line.id not in station.lines:
                station.lines.append(line.id)


def _append_unsequenced(sequence: list[str], members, by_id, line) -> list[str]:
    """Order the stations no source put in sequence.

    Lines that are not built yet — and the unbuilt half of Lines 6 and 17 — exist only as a
    set of projected stations. Where the line has an alignment, ordering them by how far
    along it they sit is exact; the known sequence then only decides which way round the
    result runs. Without an alignment there is nothing to project onto and the stations are
    chained nearest-neighbour, which is why this order is published as inferred.
    """
    if not members:
        return sequence
    if line.geometry and line.geometry.value:
        return _order_along(line.geometry.value, sequence, members, by_id)
    return _chain_nearest(sequence, members, by_id)


def _order_along(geometry, sequence: list[str], members, by_id) -> list[str]:
    from transporte_sp.geo import along_track, chain_parts

    polyline = chain_parts(geometry)
    if len(polyline) < 2:
        return _chain_nearest(sequence, members, by_id)

    position = {
        station.id: along_track(
            polyline, station.coordinates.value.lat, station.coordinates.value.lon
        )
        for station in members
    }
    ordered = sorted(position, key=position.get)
    known = [station_id for station_id in sequence if station_id in position]
    if len(known) >= 2 and position[known[0]] > position[known[-1]]:
        ordered.reverse()
    return ordered


def _chain_nearest(sequence: list[str], members, by_id) -> list[str]:
    remaining = [station for station in members if station.id not in set(sequence)]
    ordered = list(sequence)
    if not ordered:
        centre = _centroid(remaining)
        current = max(remaining, key=lambda station: _gap(station, centre))
        ordered.append(current.id)
        remaining.remove(current)
    current = by_id[ordered[-1]]
    while remaining:
        nearest_station = min(
            remaining,
            key=lambda station: _gap(station, (current.coordinates.value.lat,
                                               current.coordinates.value.lon)),
        )
        ordered.append(nearest_station.id)
        remaining.remove(nearest_station)
        current = nearest_station
    return ordered


def _centroid(stations) -> tuple[float, float]:
    return (
        sum(station.coordinates.value.lat for station in stations) / len(stations),
        sum(station.coordinates.value.lon for station in stations) / len(stations),
    )


def _gap(station, point: tuple[float, float]) -> float:
    from transporte_sp.geo import distance_m

    return distance_m(station.coordinates.value.lat, station.coordinates.value.lon, *point)


def _from_gtfs(group, index) -> list[str]:
    for observation in group:
        if observation.source != "gtfs_sptrans" or not observation.station_refs:
            continue
        ordered = [index[ref].id for ref in observation.station_refs if ref in index]
        return _dedupe_preserving(ordered)
    return []


def _from_stop_points(group, stations, clusters, nearest) -> list[str]:
    candidates = [item for item in group if item.source == "osm" and item.stop_points]
    if not candidates:
        return []
    longest = max(candidates, key=lambda item: len(item.stop_points))
    ordered = []
    for lon, lat in longest.stop_points:
        station = nearest(stations, clusters, lon, lat, 500.0)
        if station:
            ordered.append(station.id)
    return _dedupe_preserving(ordered)


def _dedupe_preserving(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique = []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def colour_index(lines) -> dict[str, str]:
    """``{"amarela": "linha-4", …}`` — several sources name a line only by its colour."""
    return {normalise(line.name.value): line.id for line in lines if line.name.value}
