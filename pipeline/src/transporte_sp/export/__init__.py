"""Writing the reconciled network out."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from transporte_sp.config import settings
from transporte_sp.geo import douglas_peucker
from transporte_sp.model import Network

log = logging.getLogger(__name__)


def write_all(network: Network) -> None:
    settings.dist_dir.mkdir(parents=True, exist_ok=True)
    _write(settings.dist_dir / "network.json", network.model_dump(mode="json"))
    _write(settings.dist_dir / "network.geojson", geojson(network))
    _write(
        settings.dist_dir / "unmatched.json",
        [station.model_dump(mode="json") for station in network.unmatched],
    )
    _write(
        settings.dist_dir / "conflicts.json",
        [conflict.model_dump(mode="json") for conflict in network.conflicts],
    )
    _write_per_line(network)


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    log.info("wrote %s (%.1f KB)", path.name, path.stat().st_size / 1024)


def _write_per_line(network: Network) -> None:
    # Rebuilt from scratch: a line dropped from the network must not linger as a stale file.
    directory = settings.dist_dir / "lines"
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stations = {station.id: station for station in network.stations}
    for line in network.lines:
        _write(
            directory / f"{line.slug}.json",
            {
                "line": line.model_dump(mode="json"),
                "stations": [
                    stations[station_id].model_dump(mode="json")
                    for station_id in line.stations
                    if station_id in stations
                ],
            },
        )


def geojson(network: Network, simplify_m: float = 0.0) -> dict:
    """One FeatureCollection with every line and every station, for the map."""
    features = []
    for line in network.lines:
        if not line.geometry:
            continue
        coordinates = line.geometry.value
        if simplify_m:
            coordinates = [douglas_peucker(part, simplify_m) for part in coordinates]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "MultiLineString", "coordinates": coordinates},
                "properties": {
                    "kind": "line",
                    "id": line.id,
                    "slug": line.slug,
                    "name": line.name.value,
                    "number": line.number.value if line.number else None,
                    "colour": line.colour.value if line.colour else None,
                    "mode": line.mode.value,
                    "status": line.status.value,
                    "operator": line.operator.value if line.operator else None,
                    "length_km": line.length_km.value if line.length_km else None,
                },
            }
        )
    for station in network.stations:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [station.coordinates.value.lon, station.coordinates.value.lat],
                },
                "properties": {
                    "kind": "station",
                    "id": station.id,
                    "slug": station.slug,
                    "name": station.name.value,
                    "lines": station.lines,
                    "status": station.status.value,
                    "code": station.code.value if station.code else None,
                    "interchange": station.is_interchange,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}
