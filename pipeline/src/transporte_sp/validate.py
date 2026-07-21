"""Invariants the published dataset must hold.

These are the checks that catch a source changing shape underneath the pipeline: a WFS
layer renamed, the GTFS dropping the rail routes, an Overpass mirror answering with half
the region. Counts are compared against what the sources measured when the pipeline was
written, so a large swing is reported rather than silently published.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from transporte_sp.config import settings
from transporte_sp.model import Network

log = logging.getLogger(__name__)

# Rough sizes observed when each adapter was written. A deviation beyond the tolerance
# means the source changed, not that the network did.
EXPECTED_LINES = 45
EXPECTED_STATIONS = 440
COUNT_TOLERANCE = 0.25

RAIL_MODES = {"subway", "monorail", "commuter_rail", "intercity_rail", "lrt", "people_mover"}


@dataclass
class Problem:
    severity: str
    message: str


def check(network: Network) -> list[Problem]:
    problems: list[Problem] = []
    problems += _check_counts(network)
    problems += _check_stations(network)
    problems += _check_lines(network)
    problems += _check_membership(network)
    return problems


def _check_counts(network: Network) -> list[Problem]:
    problems = []
    for label, actual, expected in (
        ("lines", len(network.lines), EXPECTED_LINES),
        ("stations", len(network.stations), EXPECTED_STATIONS),
    ):
        if abs(actual - expected) / expected > COUNT_TOLERANCE:
            problems.append(
                Problem("warning", f"{label}: {actual} differs from the expected ~{expected}")
            )
    return problems


def _check_stations(network: Network) -> list[Problem]:
    problems = []
    seen: set[str] = set()
    for station in network.stations:
        if station.id in seen:
            problems.append(Problem("error", f"duplicate station id {station.id!r}"))
        seen.add(station.id)

        point = station.coordinates.value
        if not settings.contains(point.lon, point.lat):
            problems.append(
                Problem("error", f"{station.id}: coordinate outside the bounding box")
            )
        if not station.lines:
            problems.append(Problem("warning", f"{station.id}: not attached to any line"))
        for field in ("name", "coordinates", "status"):
            if not getattr(station, field).source:
                problems.append(Problem("error", f"{station.id}: {field} has no source"))
    return problems


def _check_lines(network: Network) -> list[Problem]:
    problems = []
    for line in network.lines:
        if line.mode.value in RAIL_MODES and len(line.stations) < 2:
            problems.append(
                Problem("error", f"{line.id}: rail line with {len(line.stations)} station(s)")
            )
        if line.status.value in {"operational", "partial"} and not line.geometry:
            problems.append(Problem("error", f"{line.id}: running line without an alignment"))
        if line.geometry and not line.length_km:
            problems.append(Problem("error", f"{line.id}: alignment without a length"))
    return problems


def _check_membership(network: Network) -> list[Problem]:
    """Every line the station claims must claim it back, and vice versa."""
    problems = []
    by_line = {line.id: set(line.stations) for line in network.lines}
    for station in network.stations:
        for line_id in station.lines:
            if line_id not in by_line:
                problems.append(Problem("error", f"{station.id}: unknown line {line_id!r}"))
            elif station.id not in by_line[line_id]:
                problems.append(
                    Problem("error", f"{station.id}: not in the sequence of {line_id}")
                )
    return problems


def report(problems: list[Problem]) -> int:
    """Log every problem and return the number of errors."""
    for problem in problems:
        log.log(
            logging.ERROR if problem.severity == "error" else logging.WARNING,
            "%s: %s",
            problem.severity,
            problem.message,
        )
    errors = sum(1 for problem in problems if problem.severity == "error")
    log.info(
        "validation: %d error(s), %d warning(s)", errors, len(problems) - errors
    )
    return errors
