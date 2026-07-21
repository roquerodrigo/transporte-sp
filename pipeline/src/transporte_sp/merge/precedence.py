"""Which source wins which field.

Precedence is declared **per field**, never globally, because no source is best at
everything: GeoSampa has the most accurate coordinates but writes every name in capitals;
Wikidata is the only source with the official station code but assigns commuter-rail
stations to railways that stopped existing decades ago; the GTFS is the only source that
states the order of the stations.

A field whose runner-up disagrees materially is not silently overwritten — the reconciler
records the loser as an alternative and, past the configured threshold, as a conflict.
"""

from __future__ import annotations

from transporte_sp.config import SOURCE_CONFIDENCE

# First source present wins. A source absent from a list is never used for that field.
STATION_FIELDS: dict[str, tuple[str, ...]] = {
    # OSM and Wikidata write names the way a reader expects them; GeoSampa shouts them.
    "name": ("osm", "wikidata", "gtfs_sptrans", "geosampa"),
    "coordinates": ("geosampa", "osm", "wikidata", "gtfs_sptrans"),
    "code": ("metro_transparencia", "wikidata", "osm"),
    "accessibility": ("metro_site", "osm"),
    "opened": ("metro_transparencia", "wikidata"),
    "status": ("geosampa", "osm", "gtfs_sptrans"),
}

LINE_FIELDS: dict[str, tuple[str, ...]] = {
    "name": ("geosampa", "osm", "gtfs_sptrans"),
    "colour": ("osm", "gtfs_sptrans"),
    "mode": ("osm", "geosampa", "gtfs_sptrans"),
    "operator": ("osm", "geosampa"),
    "status": ("osm", "geosampa", "gtfs_sptrans"),
}

# How each source's line geometry is assembled before lines are compared.
#   concat  — the source splits a line into disjoint segments; join them all
#   longest — the source repeats the whole line once per direction; keep one
GEOMETRY_STRATEGY: dict[str, str] = {
    "geosampa": "concat",
    "osm": "longest",
    "gtfs_sptrans": "longest",
}

# Which source's alignment to publish, in order.
#
# Not "the longest one", which is what this used to be. GeoSampa maps the commuter lines
# **track by track**, so concatenating its segments traverses the corridor twice and reports
# Line 7 as 130 km against a real 60. An OSM route relation and a GTFS shape are each a
# single traversal and land within a few per cent of the real length, so they come first;
# GeoSampa is the fallback, and remains the only source of a *planned* alignment.
GEOMETRY_ORDER: tuple[str, ...] = ("osm", "gtfs_sptrans", "geosampa")


def confidence(source: str) -> str:
    return SOURCE_CONFIDENCE.get(source, "E")


def rank(field_map: dict[str, tuple[str, ...]], fieldname: str, source: str) -> int:
    """Position of *source* for *fieldname*; unlisted sources sort last."""
    order = field_map.get(fieldname, ())
    return order.index(source) if source in order else len(order)
