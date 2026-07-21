"""Clustering the same real-world station across sources.

The join key is deliberately *not* the name: the same platform is ``CORINTHIANS-ITAQUERA``
in GeoSampa, ``Corinthians-Itaquera`` in the GTFS, ``Corinthians–Itaquera`` (en dash) in
OSM and ``Estação Corinthians-Itaquera`` in Wikidata. Three rules run in order of how much
they can be trusted:

1. **Shared Wikidata QID** — the only exact identifier that spans sources (OSM tags it on
   about four fifths of the region's stations).
2. **Same normalised name within the match radius** — the workhorse.
3. **One normalised name contained in the other, within a tighter radius** — catches
   ``Santo André`` versus ``Prefeito Celso Daniel - Santo André``.

Interchange complexes collapse into a single station on purpose: a station belongs to
several lines in this model, so Sé arriving once from Line 1 and once from Line 3 is one
station with two lines, not two stations.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from transporte_sp.config import settings
from transporte_sp.geo import distance_m
from transporte_sp.model import StationObservation
from transporte_sp.naming import normalise

log = logging.getLogger(__name__)

# Rule 3 is looser about the name, so it is stricter about the distance.
CONTAINMENT_RADIUS_M = 250.0


class _UnionFind:
    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, item: int) -> int:
        while self._parent[item] != item:
            self._parent[item] = self._parent[self._parent[item]]
            item = self._parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self._parent[right_root] = left_root


def cluster(observations: Iterable[StationObservation]) -> list[list[StationObservation]]:
    """Group observations that describe the same station."""
    items = [item for item in observations if item.coordinates]
    union = _UnionFind(len(items))

    by_qid: dict[str, int] = {}
    for index, item in enumerate(items):
        qid = item.external_ids.wikidata
        if not qid:
            continue
        if qid in by_qid:
            union.union(by_qid[qid], index)
        else:
            by_qid[qid] = index

    keys = [normalise(item.name) for item in items]
    by_name: dict[str, list[int]] = {}
    for index, key in enumerate(keys):
        by_name.setdefault(key, []).append(index)

    for indices in by_name.values():
        for position, left in enumerate(indices):
            for right in indices[position + 1 :]:
                if _distance(items[left], items[right]) <= settings.match_radius_m:
                    union.union(left, right)

    _link_by_containment(items, keys, union)

    groups: dict[int, list[StationObservation]] = {}
    for index, item in enumerate(items):
        groups.setdefault(union.find(index), []).append(item)

    clusters = [split for group in groups.values() for split in _split_outliers(group)]
    log.info("matched %d observations into %d stations", len(items), len(clusters))
    return clusters


def _split_outliers(group: list[StationObservation]) -> list[list[StationObservation]]:
    """Undo transitive over-merging.

    Matching is transitive, so a chain of near-misses can pull genuinely different stations
    together — two stations called Perus, 5.8 km apart, arrived in one cluster this way.
    Whatever sits farther than the cap from the cluster's medoid is split back out.
    """
    if len(group) < 3:
        return [group]
    medoid = min(
        group,
        key=lambda centre: sum(_distance(centre, other) for other in group),
    )
    core = [item for item in group if _distance(medoid, item) <= settings.cluster_max_radius_m]
    outliers = [item for item in group if item not in core]
    if not outliers:
        return [group]
    log.debug("split %d outlier(s) off %r", len(outliers), medoid.name)
    return [core, *_split_outliers(outliers)]


def _link_by_containment(items, keys, union) -> None:
    """Rule 3, restricted to pairs already close together."""
    for left in range(len(items)):
        for right in range(left + 1, len(items)):
            if union.find(left) == union.find(right):
                continue
            short, long = sorted((keys[left], keys[right]), key=len)
            if len(short) < 5 or short not in long:
                continue
            if _distance(items[left], items[right]) <= CONTAINMENT_RADIUS_M:
                union.union(left, right)


def _distance(left: StationObservation, right: StationObservation) -> float:
    return distance_m(
        left.coordinates.lat,
        left.coordinates.lon,
        right.coordinates.lat,
        right.coordinates.lon,
    )
