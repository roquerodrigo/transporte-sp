"""Domain model.

Two layers live here:

* the **observation** layer (``StationObservation``, ``LineObservation``) — what a single
  source claims, already normalised to a common shape but not yet reconciled;
* the **network** layer (``Station``, ``Line``, ``Network``) — the reconciled result, where
  every field is wrapped in a :class:`Sourced` envelope carrying its provenance.

Nothing in the published dataset states a fact without saying where it came from, which is
why the envelope is part of the model rather than a side table.
"""

from __future__ import annotations

from datetime import date
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

Confidence = Literal["A", "B", "C", "D", "E"]

Mode = Literal[
    "subway", "monorail", "commuter_rail", "intercity_rail", "lrt", "brt", "people_mover"
]

Status = Literal["operational", "partial", "under_construction", "planned", "proposed", "closed"]

Accessibility = Literal["full", "partial", "none", "unknown"]

T = TypeVar("T")


class Alternative(BaseModel):
    """A value another source proposed for a field the reconciler did not pick."""

    value: object
    source: str
    confidence: Confidence
    note: str | None = None


class Sourced(BaseModel, Generic[T]):
    """A field value plus where it came from."""

    value: T
    source: str
    confidence: Confidence
    alternatives: list[Alternative] = Field(default_factory=list)


class Coordinates(BaseModel):
    lat: float
    lon: float


class ExternalIds(BaseModel):
    """Identifiers of this entity in each upstream source, for round-tripping and audit."""

    wikidata: str | None = None
    osm: str | None = None
    gtfs_stop_id: str | None = None
    gtfs_route_id: str | None = None
    geosampa_id: str | None = None
    metro_code: str | None = None


class StationObservation(BaseModel):
    """One source's claim about one station."""

    source: str
    source_ref: str
    name: str
    coordinates: Coordinates | None = None
    line_refs: list[str] = Field(default_factory=list)
    operator: str | None = None
    status: Status | None = None
    accessibility: Accessibility | None = None
    opened: date | None = None
    external_ids: ExternalIds = Field(default_factory=ExternalIds)
    extra: dict[str, object] = Field(default_factory=dict)


class LineObservation(BaseModel):
    """One source's claim about one line."""

    source: str
    source_ref: str
    name: str
    number: str | None = None
    colour: str | None = None
    # São Paulo identifies lines by colour as much as by number ("Linha 4-Amarela"), and
    # several sources give only the colour, so it is a join key of its own.
    colour_name: str | None = None
    mode: Mode | None = None
    operator: str | None = None
    status: Status | None = None
    geometry: list[list[list[float]]] = Field(default_factory=list)
    station_refs: list[str] = Field(default_factory=list)
    # Ordered ``[lon, lat]`` of each stop along the route, when the source states the order
    # positionally rather than by identifier. Lines absent from the GTFS get their sequence
    # from here.
    stop_points: list[list[float]] = Field(default_factory=list)
    extra: dict[str, object] = Field(default_factory=dict)


class Station(BaseModel):
    id: str
    slug: str
    name: Sourced[str]
    coordinates: Sourced[Coordinates]
    lines: list[str]
    status: Sourced[Status]
    code: Sourced[str] | None = None
    accessibility: Sourced[Accessibility] | None = None
    opened: Sourced[date] | None = None
    address: Sourced[str] | None = None
    external_ids: ExternalIds = Field(default_factory=ExternalIds)
    is_interchange: bool = False
    observed_by: list[str] = Field(default_factory=list)


class Line(BaseModel):
    id: str
    slug: str
    name: Sourced[str]
    number: Sourced[str] | None = None
    colour: Sourced[str] | None = None
    mode: Sourced[Mode]
    operator: Sourced[str] | None = None
    status: Sourced[Status]
    stations: list[str] = Field(default_factory=list)
    # Where the station *order* came from — the GTFS states it, OSM implies it from the
    # ordered stop members, and for lines that are not built yet it can only be inferred.
    station_order: Sourced[str] | None = None
    geometry: Sourced[list[list[list[float]]]] | None = None
    length_km: Sourced[float] | None = None
    observed_by: list[str] = Field(default_factory=list)


class Conflict(BaseModel):
    """A disagreement the reconciler refused to resolve silently."""

    entity: str
    entity_id: str
    fieldname: str
    chosen: object
    chosen_source: str
    rejected: object
    rejected_source: str
    detail: str


class SourceRecord(BaseModel):
    """Provenance of one snapshot that fed this build."""

    id: str
    name: str
    url: str
    licence: str
    confidence: Confidence
    fetched_at: date
    sha256: str | None = None


class Network(BaseModel):
    generated_at: date
    bbox: tuple[float, float, float, float]
    sources: list[SourceRecord] = Field(default_factory=list)
    lines: list[Line] = Field(default_factory=list)
    stations: list[Station] = Field(default_factory=list)
    # Rail-tagged places the sources returned that belong to no line in scope: airports,
    # long-closed stations, freight yards. Kept out of the network but published, because a
    # real station landing here means the pipeline missed a link, not that it does not exist.
    unmatched: list[Station] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
