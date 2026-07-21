"""Wikidata SPARQL — CC0.

Used for what no official source publishes in a machine-readable way: the **official
three-letter station code** (P296, present on most metro stations), the opening date and
a canonical coordinate to cross-check the others against.

Two constraints shape the query. The endpoint times out on POST but answers the same query
over GET, and the administrative hierarchy is unreliable — ``wdt:P131*`` misses most
stations, so the spatial ``wikibase:around`` service is used instead.

Coverage is uneven on purpose in the reconciler: excellent for the metro, poor for the
commuter rail, where P81 often points at the historical railway ("Linha Santos-Jundiaí")
rather than the commercial line. Line references from here are therefore treated as hints,
never as the line assignment.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date

from transporte_sp import snapshot
from transporte_sp.config import settings
from transporte_sp.model import Coordinates, ExternalIds, StationObservation

log = logging.getLogger(__name__)

SOURCE = "wikidata"
LICENCE = "CC0-1.0"
RESULTS = "stations.json"

# Q548662 = train station; the subclass walk picks up metro, monorail and tram stops.
QUERY = """
SELECT ?station ?stationLabel ?coord ?code ?opened ?line ?lineLabel ?operatorLabel WHERE {
  ?station wdt:P31/wdt:P279* wd:Q548662 .
  SERVICE wikibase:around {
    ?station wdt:P625 ?coord .
    bd:serviceParam wikibase:center "Point(%(lon)s %(lat)s)"^^geo:wktLiteral .
    bd:serviceParam wikibase:radius "%(radius)s" .
  }
  OPTIONAL { ?station wdt:P296 ?code }
  OPTIONAL { ?station wdt:P1619 ?opened }
  OPTIONAL { ?station wdt:P81 ?line }
  OPTIONAL { ?station wdt:P137 ?operator }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "pt-br,pt,en". }
}
"""

_POINT = re.compile(r"Point\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)")
_STATION_PREFIX = re.compile(r"^Esta[çc][ãa]o\s+", re.IGNORECASE)


def fetch() -> None:
    min_lon, min_lat, max_lon, max_lat = settings.bbox
    query = QUERY % {
        "lon": (min_lon + max_lon) / 2,
        "lat": (min_lat + max_lat) / 2,
        "radius": settings.wikidata_radius_km,
    }
    payload = snapshot.download(
        settings.wikidata_sparql_url,
        params={"query": query},
        headers={"Accept": "application/sparql-results+json"},
    )
    if b"bindings" not in payload:
        raise RuntimeError("Wikidata returned no result bindings")
    snapshot.write(SOURCE, RESULTS, payload, settings.wikidata_sparql_url, LICENCE)


def _rows() -> list[dict]:
    document = json.loads(snapshot.read(SOURCE, RESULTS))
    return document.get("results", {}).get("bindings", [])


def _value(row: dict, key: str) -> str | None:
    entry = row.get(key)
    return entry.get("value") if entry else None


def stations() -> list[StationObservation]:
    """One observation per entity — the SPARQL result has a row per (station, line) pair."""
    merged: dict[str, StationObservation] = {}
    for row in _rows():
        uri = _value(row, "station")
        coord = _value(row, "coord")
        if not uri or not coord:
            continue
        match = _POINT.match(coord)
        if not match:
            continue
        lon, lat = float(match.group(1)), float(match.group(2))
        if not settings.contains(lon, lat):
            continue

        qid = uri.rsplit("/", 1)[-1]
        existing = merged.get(qid)
        if existing is None:
            name = _STATION_PREFIX.sub("", _value(row, "stationLabel") or qid).strip()
            existing = merged[qid] = StationObservation(
                source=SOURCE,
                source_ref=qid,
                name=name,
                coordinates=Coordinates(lat=lat, lon=lon),
                opened=_parse_date(_value(row, "opened")),
                operator=_value(row, "operatorLabel"),
                external_ids=ExternalIds(wikidata=qid, metro_code=_value(row, "code")),
                extra={"lines": []},
            )
        line_label = _value(row, "lineLabel")
        if line_label and line_label not in existing.extra["lines"]:
            existing.extra["lines"].append(line_label)
    observations = list(merged.values())
    log.info("%s: %d stations", SOURCE, len(observations))
    return observations


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None
