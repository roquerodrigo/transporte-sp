"""GeoSampa (Prefeitura de São Paulo) — WFS, CC-BY-SA 4.0.

The strongest source available: structured geometry for the operating network *and* for
the planned one (142 projected stations, 20 projected lines), served as GeoJSON without a
sign-up. Its one limitation is decisive — it stops at the city limit, so everything in the
ABC, Guarulhos, Osasco, Jundiaí and the Baixada has to come from OSM or the GTFS.

The server answers in SIRGAS 2000 / UTM 23S (EPSG:31983) by default; ``srsName=EPSG:4326``
makes it reproject, which is why this module needs no projection library.
"""

from __future__ import annotations

import json
import logging

from transporte_sp import snapshot
from transporte_sp.config import GEOSAMPA_LAYERS, settings
from transporte_sp.geo import flatten
from transporte_sp.model import Coordinates, ExternalIds, LineObservation, StationObservation
from transporte_sp.naming import line_number

log = logging.getLogger(__name__)

SOURCE = "geosampa"
LICENCE = "CC-BY-SA-4.0"

# The layer's `tx_situacao_metro_trem` vocabulary, mapped onto the model's Status.
_SITUATION = {
    "OPERANDO": "operational",
    "EM OPERACAO": "operational",
    "EM OBRAS": "under_construction",
    "EM CONSTRUCAO": "under_construction",
    "PROJETADA": "planned",
    "PROJETO": "planned",
}


def fetch() -> None:
    """Download every configured layer as GeoJSON in WGS84."""
    for layer in GEOSAMPA_LAYERS:
        payload = snapshot.download(
            settings.geosampa_wfs,
            params={
                "service": "WFS",
                "version": "1.0.0",
                "request": "GetFeature",
                "typeName": f"geoportal:{layer}",
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
            },
        )
        _ensure_geojson(layer, payload)
        snapshot.write(SOURCE, f"{layer}.geojson", payload, settings.geosampa_wfs, LICENCE)


def _ensure_geojson(layer: str, payload: bytes) -> None:
    """A WFS error comes back as XML with a 200, so the content has to be checked."""
    try:
        document = json.loads(payload)
    except ValueError as error:
        raise RuntimeError(f"GeoSampa layer {layer!r} did not return JSON") from error
    if document.get("type") != "FeatureCollection":
        raise RuntimeError(f"GeoSampa layer {layer!r} returned {document.get('type')!r}")


def _layer(name: str) -> list[dict]:
    return json.loads(snapshot.read(SOURCE, f"{name}.geojson")).get("features", [])


def _status(properties: dict, fallback: str) -> str:
    raw = str(properties.get("tx_situacao_metro_trem") or "").strip().upper()
    return _SITUATION.get(raw, fallback)


def stations() -> list[StationObservation]:
    observations: list[StationObservation] = []
    for layer, fallback in GEOSAMPA_LAYERS.items():
        if not layer.startswith("estacao_"):
            continue
        for feature in _layer(layer):
            properties = feature.get("properties") or {}
            geometry = feature.get("geometry") or {}
            if geometry.get("type") != "Point":
                continue
            lon, lat = geometry["coordinates"][:2]
            name = (properties.get("nm_estacao_metro_trem") or "").strip()
            if not name:
                continue
            line_name = (properties.get("nm_linha_metro_trem") or "").strip()
            number = properties.get("cd_identificador_linha")
            # The projected-station layers carry only the colour name, never the number.
            line_refs = [str(number)] if number else []
            if line_name:
                line_refs.append(line_name)
            observations.append(
                StationObservation(
                    source=SOURCE,
                    source_ref=f"{layer}:{feature.get('id')}",
                    name=name,
                    coordinates=Coordinates(lat=lat, lon=lon),
                    line_refs=line_refs,
                    operator=(properties.get("nm_empresa_metro_trem") or "").strip() or None,
                    status=_status(properties, fallback),
                    external_ids=ExternalIds(geosampa_id=str(properties.get("cd_identificador"))),
                    extra={"line_name": line_name, "layer": layer},
                )
            )
    log.info("%s: %d station observations", SOURCE, len(observations))
    return observations


def lines() -> list[LineObservation]:
    observations: list[LineObservation] = []
    for layer, fallback in GEOSAMPA_LAYERS.items():
        if not layer.startswith("linha_"):
            continue
        for feature in _layer(layer):
            properties = feature.get("properties") or {}
            name = (properties.get("nr_nome_linha") or properties.get("nm_linha_metro_trem") or "")
            name = name.strip()
            if not name:
                continue
            # `cd_identificador_linha` is authoritative and is null on the connections that
            # have no line number yet (e.g. "LIGAÇÃO ALPHAVILLE - CAMPO LIMPO").
            number = properties.get("cd_identificador_linha")
            observations.append(
                LineObservation(
                    source=SOURCE,
                    source_ref=f"{layer}:{feature.get('id')}",
                    name=name,
                    number=str(number) if number else line_number(name),
                    colour_name=(properties.get("nm_linha_metro_trem") or "").strip() or None,
                    mode="commuter_rail" if "trem" in layer else "subway",
                    operator=(properties.get("nm_empresa_metro_trem") or "").strip() or None,
                    status=_status(properties, fallback),
                    geometry=flatten(feature.get("geometry") or {}),
                    extra={"layer": layer},
                )
            )
    log.info("%s: %d line observations", SOURCE, len(observations))
    return observations


def corridors() -> list[LineObservation]:
    """Bus corridors — the only structured BRT-ish geometry that exists for São Paulo."""
    observations = []
    for feature in _layer("corredor_onibus"):
        properties = feature.get("properties") or {}
        name = str(properties.get("nm_corredor") or "").strip()
        if not name:
            continue
        operating = properties.get("cd_tipo_status_corredor_onibus") == 1
        observations.append(
            LineObservation(
                source=SOURCE,
                source_ref=f"corredor_onibus:{feature.get('id')}",
                name=name,
                mode="brt",
                operator="SPTrans",
                status="operational" if operating else "under_construction",
                geometry=flatten(feature.get("geometry") or {}),
                extra={
                    "layer": "corredor_onibus",
                    "year": properties.get("an_corredor"),
                    "length_km": properties.get("qt_quilometro"),
                    "note": properties.get("tx_observacao"),
                    "status_label": properties.get("dc_tipo_status_corredor_onibus"),
                },
            )
        )
    log.info("%s: %d bus corridors", SOURCE, len(observations))
    return observations
