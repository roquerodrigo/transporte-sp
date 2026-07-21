"""Source adapters.

Each module owns one upstream source and exposes the same surface: ``fetch()`` stores a
raw snapshot, and ``stations()``/``lines()`` parse the latest snapshot into observations.
Nothing here reconciles anything — every module reports what its source claims, conflicts
included, and :mod:`transporte_sp.merge` decides.
"""

from __future__ import annotations

from types import ModuleType

from transporte_sp.sources import geosampa, gtfs_sptrans, overpass, wikidata

REGISTRY: dict[str, ModuleType] = {
    geosampa.SOURCE: geosampa,
    gtfs_sptrans.SOURCE: gtfs_sptrans,
    overpass.SOURCE: overpass,
    wikidata.SOURCE: wikidata,
}

__all__ = ["REGISTRY", "geosampa", "gtfs_sptrans", "overpass", "wikidata"]
