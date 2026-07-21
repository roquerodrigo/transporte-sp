"""Fixtures.

Tests never reach the network: each source module is exercised against a hand-written
snapshot that mirrors the real payload's shape. Keeping the fixtures small and readable
also documents what each upstream format actually looks like.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from transporte_sp.config import settings


@pytest.fixture
def data_dir(tmp_path: Path):
    """Point the pipeline at a throwaway data directory for the duration of a test."""
    original = settings.data_dir
    object.__setattr__(settings, "data_dir", tmp_path)
    yield tmp_path
    object.__setattr__(settings, "data_dir", original)


def _store(data_dir: Path, source: str, filename: str, payload: bytes) -> None:
    directory = data_dir / "raw" / source / datetime.now(UTC).date().isoformat()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_bytes(payload)


def _feature_collection(features: list[dict]) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": features}).encode()


@pytest.fixture
def geosampa_snapshot(data_dir: Path) -> Path:
    station = {
        "type": "Feature",
        "id": "estacao_metro.1",
        "geometry": {"type": "Point", "coordinates": [-46.4711, -23.5423]},
        "properties": {
            "cd_identificador": 1,
            "nm_estacao_metro_trem": "CORINTHIANS-ITAQUERA",
            "cd_identificador_linha": 3,
            "tx_situacao_metro_trem": "OPERANDO",
            "nm_linha_metro_trem": "VERMELHA",
            "nm_empresa_metro_trem": "METRO",
        },
    }
    projected = {
        "type": "Feature",
        "id": "estacao_metro_projetada.1",
        "geometry": {"type": "Point", "coordinates": [-46.6800, -23.4900]},
        "properties": {"cd_identificador": 95, "nm_estacao_metro_trem": "BRASILÂNDIA",
                       "nm_linha_metro_trem": "LARANJA"},
    }
    projected_neighbour = {
        "type": "Feature",
        "id": "estacao_metro_projetada.2",
        "geometry": {"type": "Point", "coordinates": [-46.6700, -23.5000]},
        "properties": {"cd_identificador": 96, "nm_estacao_metro_trem": "ITABERABA",
                       "nm_linha_metro_trem": "LARANJA"},
    }
    line = {
        "type": "Feature",
        "id": "linha_metro.3",
        "geometry": {"type": "LineString",
                     "coordinates": [[-46.4711, -23.5423], [-46.5400, -23.5400]]},
        "properties": {"cd_identificador_linha": 3, "nr_nome_linha": "LINHA 3 - VERMELHA",
                       "nm_linha_metro_trem": "VERMELHA", "nm_empresa_metro_trem": "METRO"},
    }
    corridor = {
        "type": "Feature",
        "id": "corredor_onibus.1",
        "geometry": {"type": "LineString",
                     "coordinates": [[-46.60, -23.55], [-46.58, -23.55]]},
        "properties": {"nm_corredor": "CORREDOR PAES DE BARROS", "an_corredor": 1980,
                       "qt_quilometro": 3.9, "cd_tipo_status_corredor_onibus": 1,
                       "dc_tipo_status_corredor_onibus": "Em Operação"},
    }
    projected_line = {
        "type": "Feature",
        "id": "linha_metro_projetada.6",
        "geometry": {"type": "LineString",
                     "coordinates": [[-46.6800, -23.4900], [-46.6700, -23.5000]]},
        "properties": {"cd_identificador_linha": 6, "nr_nome_linha": "LINHA 6 - LARANJA",
                       "nm_linha_metro_trem": "LARANJA", "nm_empresa_metro_trem": "LINHA UNI"},
    }
    contents = {
        "estacao_metro": [station],
        "linha_metro_projetada": [projected_line],
        "estacao_metro_projetada": [projected, projected_neighbour],
        "linha_metro": [line],
        "corredor_onibus": [corridor],
    }
    from transporte_sp.config import GEOSAMPA_LAYERS

    for layer in GEOSAMPA_LAYERS:
        _store(data_dir, "geosampa", f"{layer}.geojson",
               _feature_collection(contents.get(layer, [])))
    return data_dir


def _csv(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


@pytest.fixture
def gtfs_snapshot(data_dir: Path) -> Path:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("routes.txt", _csv([
            {"route_id": "METRÔ L3", "route_short_name": "METRÔ L3",
             "route_long_name": "CORINTHIANS - ITAQUERA - PALMEIRAS - BARRA FUNDA",
             "route_type": "1", "route_color": "EE372F"},
            {"route_id": "1234-10", "route_short_name": "1234",
             "route_long_name": "A BUS ROUTE", "route_type": "3", "route_color": ""},
        ]))
        bundle.writestr("trips.txt", _csv([
            {"route_id": "METRÔ L3", "trip_id": "T1", "shape_id": "S1"},
            {"route_id": "1234-10", "trip_id": "T9", "shape_id": "S9"},
        ]))
        bundle.writestr("stop_times.txt", _csv([
            {"trip_id": "T1", "stop_id": "A", "stop_sequence": "1"},
            {"trip_id": "T1", "stop_id": "B", "stop_sequence": "2"},
            {"trip_id": "T9", "stop_id": "Z", "stop_sequence": "1"},
        ]))
        bundle.writestr("stops.txt", _csv([
            {"stop_id": "A", "stop_name": "Corinthians-Itaquera",
             "stop_lat": "-23.5423", "stop_lon": "-46.4711", "stop_desc": ""},
            {"stop_id": "B", "stop_name": "Artur Alvim",
             "stop_lat": "-23.5400", "stop_lon": "-46.4850", "stop_desc": ""},
            {"stop_id": "Z", "stop_name": "A BUS STOP",
             "stop_lat": "-23.5500", "stop_lon": "-46.6333", "stop_desc": ""},
        ]))
        bundle.writestr("shapes.txt", _csv([
            {"shape_id": "S1", "shape_pt_sequence": "1",
             "shape_pt_lat": "-23.5423", "shape_pt_lon": "-46.4711"},
            {"shape_id": "S1", "shape_pt_sequence": "2",
             "shape_pt_lat": "-23.5400", "shape_pt_lon": "-46.4850"},
            {"shape_id": "S9", "shape_pt_sequence": "1",
             "shape_pt_lat": "-23.5500", "shape_pt_lon": "-46.6333"},
        ]))
    _store(data_dir, "gtfs_sptrans", "gtfs.zip", archive.getvalue())
    return data_dir


@pytest.fixture
def osm_snapshot(data_dir: Path) -> Path:
    route = {
        "type": "relation",
        "id": 100,
        "tags": {"name": "Linha 3 - Vermelha: Corinthians - Itaquera ⇒ Palmeiras",
                 "ref": "3", "route": "subway", "colour": "#EE372F",
                 "operator": "Metrô de São Paulo", "network": "Metrô de São Paulo"},
        "members": [
            {"type": "node", "ref": 1, "role": "stop", "lat": -23.5423, "lon": -46.4711},
            {"type": "node", "ref": 2, "role": "stop", "lat": -23.5400, "lon": -46.4850},
            {"type": "way", "ref": 9, "role": "",
             "geometry": [{"lat": -23.5423, "lon": -46.4711},
                          {"lat": -23.5400, "lon": -46.4850}]},
        ],
    }
    # Line 6 mirrors the real one: OSM maps the stretch that already runs, while GeoSampa
    # still lists every station of the line as projected.
    parcial = {
        "type": "relation",
        "id": 300,
        "tags": {"name": "Linha 6 - Laranja: Brasilândia ⇒ Itaberaba", "ref": "6",
                 "route": "subway", "operator": "Linha Uni", "network": "Metrô de São Paulo"},
        "members": [
            {"type": "node", "ref": 6, "role": "stop", "lat": -23.4900, "lon": -46.6800},
            {"type": "way", "ref": 60, "role": "",
             "geometry": [{"lat": -23.4900, "lon": -46.6800},
                          {"lat": -23.4950, "lon": -46.6750}]},
        ],
    }
    tourist = {
        "type": "relation",
        "id": 200,
        "tags": {"name": "Bonde Turístico de Santos", "route": "tram"},
        "members": [],
    }
    _store(
        data_dir,
        "osm",
        "routes.json",
        json.dumps({"elements": [route, parcial, tourist]}).encode(),
    )
    _store(data_dir, "osm", "stations.json", json.dumps({"elements": [
        {"type": "node", "id": 1, "lat": -23.5423, "lon": -46.4711,
         "tags": {"name": "Corinthians–Itaquera", "railway": "station", "ref": "ITQ",
                  "wheelchair": "yes", "wikidata": "Q1"}},
        {"type": "node", "id": 2, "lat": -23.5400, "lon": -46.4850,
         "tags": {"name": "Artur Alvim", "railway": "station"}},
    ]}).encode())
    return data_dir


@pytest.fixture
def wikidata_snapshot(data_dir: Path) -> Path:
    def binding(qid, label, lon, lat, code=None, line=None):
        row = {
            "station": {"type": "uri", "value": f"http://www.wikidata.org/entity/{qid}"},
            "stationLabel": {"type": "literal", "value": label},
            "coord": {"type": "literal", "value": f"Point({lon} {lat})"},
        }
        if code:
            row["code"] = {"type": "literal", "value": code}
        if line:
            row["lineLabel"] = {"type": "literal", "value": line}
        return row

    payload = {"results": {"bindings": [
        binding("Q1", "Estação Corinthians-Itaquera", -46.4711, -23.5423, "ITQ",
                "Linha 3 do Metrô de São Paulo"),
        binding("Q1", "Estação Corinthians-Itaquera", -46.4711, -23.5423, "ITQ",
                "Linha 15 do Metrô de São Paulo"),
        binding("Q9", "Estação Muito Longe", -60.0, -10.0),
    ]}}
    _store(data_dir, "wikidata", "stations.json", json.dumps(payload).encode())
    return data_dir


@pytest.fixture
def all_snapshots(geosampa_snapshot, gtfs_snapshot, osm_snapshot, wikidata_snapshot) -> Path:
    return geosampa_snapshot
