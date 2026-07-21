"""Reconciliation: observations from every source in, one auditable network out."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime

from transporte_sp import snapshot
from transporte_sp.config import settings
from transporte_sp.geo import distance_m, line_length_km
from transporte_sp.merge import lines as line_merge
from transporte_sp.merge import stations as station_merge
from transporte_sp.model import Conflict, Network, SourceRecord
from transporte_sp.sources import REGISTRY

log = logging.getLogger(__name__)

LICENCES = {
    "geosampa": ("GeoSampa (Prefeitura de São Paulo)", "CC-BY-SA-4.0"),
    "gtfs_sptrans": ("GTFS SPTrans", "public-record (Lei 12.527/2011)"),
    "osm": ("OpenStreetMap", "ODbL-1.0"),
    "wikidata": ("Wikidata", "CC0-1.0"),
}


def build() -> Network:
    """Read the latest snapshot of every source and reconcile it into a :class:`Network`."""
    line_observations = []
    station_observations = []
    records: list[SourceRecord] = []

    for name, module in REGISTRY.items():
        if snapshot.latest_snapshot(name) is None:
            log.warning("%s: no snapshot, skipping", name)
            continue
        if hasattr(module, "lines"):
            line_observations.extend(module.lines())
        if hasattr(module, "corridors"):
            line_observations.extend(module.corridors())
        if hasattr(module, "stations"):
            station_observations.extend(module.stations())
        label, licence = LICENCES.get(name, (name, "unknown"))
        records.append(
            SourceRecord(
                id=name,
                name=label,
                url=getattr(module, "SOURCE_URL", ""),
                licence=licence,
                confidence=_confidence(name),
                fetched_at=snapshot.fetched_on(name),
            )
        )

    conflicts: list[Conflict] = []
    network_lines = line_merge.reconcile(line_observations, conflicts)
    network_stations, clusters = station_merge.reconcile(station_observations, conflicts)

    station_merge.assign_lines(network_stations, clusters, network_lines, line_observations)
    line_merge.order_stations(network_lines, network_stations, clusters, line_observations)
    _flag_interchanges(network_stations)
    _measure(network_lines)

    attached = [station for station in network_stations if station.lines]
    unmatched = [station for station in network_stations if not station.lines]

    network = Network(
        generated_at=datetime.now(UTC).date(),
        bbox=settings.bbox,
        sources=records,
        lines=sorted(network_lines, key=_line_sort_key),
        stations=sorted(attached, key=lambda station: station.slug),
        unmatched=sorted(unmatched, key=lambda station: station.slug),
        conflicts=_worst_per_pair(conflicts),
    )
    _report(network)
    return network


def _worst_per_pair(conflicts: list[Conflict]) -> list[Conflict]:
    """One conflict per (entity, field, losing source).

    A station observed three times by the same source would otherwise report the same
    disagreement three times over.
    """
    kept: dict[tuple, Conflict] = {}
    for conflict in conflicts:
        marker = (conflict.entity_id, conflict.fieldname, conflict.rejected_source)
        kept.setdefault(marker, conflict)
    return sorted(kept.values(), key=lambda item: (item.entity, item.entity_id, item.fieldname))


def _confidence(source: str) -> str:
    from transporte_sp.merge.precedence import confidence

    return confidence(source)


def _line_sort_key(line) -> tuple[int, str]:
    number = line.number.value if line.number else None
    return (int(number), "") if number and number.isdigit() else (999, line.slug)


def _flag_interchanges(stations) -> None:
    for station in stations:
        station.is_interchange = len(station.lines) > 1


def _measure(lines) -> None:
    from transporte_sp.model import Sourced

    for line in lines:
        if line.geometry and line.geometry.value:
            line.length_km = Sourced[float](
                value=line_length_km(line.geometry.value),
                source=line.geometry.source,
                confidence="E",
            )


def _report(network: Network) -> None:
    by_status = Counter(line.status.value for line in network.lines)
    log.info(
        "network: %d lines (%s), %d stations, %d interchanges, %d conflicts, "
        "%d rail places out of scope",
        len(network.lines),
        ", ".join(f"{count} {status}" for status, count in sorted(by_status.items())),
        len(network.stations),
        sum(1 for station in network.stations if station.is_interchange),
        len(network.conflicts),
        len(network.unmatched),
    )
    orphans = [
        line.slug
        for line in network.lines
        if not line.stations and line.mode.value != "brt"
    ]
    if orphans:
        log.warning("lines without a station sequence: %s", ", ".join(orphans))


def nearest(stations, clusters, lon: float, lat: float, radius_m: float):
    """The station whose cluster has an observation closest to ``(lon, lat)``."""
    best, best_distance = None, radius_m
    for station, cluster in zip(stations, clusters, strict=True):
        for observation in cluster:
            gap = distance_m(lat, lon, observation.coordinates.lat, observation.coordinates.lon)
            if gap < best_distance:
                best, best_distance = station, gap
    return best
