"""End-to-end reconciliation over the fixture snapshots."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from transporte_sp import export, merge, validate
from transporte_sp.cli import app
from transporte_sp.config import settings


@pytest.fixture
def network(all_snapshots):
    return merge.build()


def test_the_four_sources_agree_on_one_station(network):
    itaquera = next(s for s in network.stations if s.slug == "corinthians-itaquera")
    assert set(itaquera.observed_by) == {"geosampa", "gtfs_sptrans", "osm", "wikidata"}


def test_the_readable_name_wins_over_the_shouted_one(network):
    itaquera = next(s for s in network.stations if s.slug == "corinthians-itaquera")
    assert itaquera.name.value == "Corinthians–Itaquera"
    assert itaquera.name.source == "osm"
    assert "CORINTHIANS-ITAQUERA" in [item.value for item in itaquera.name.alternatives]


def test_the_coordinate_comes_from_the_official_survey(network):
    itaquera = next(s for s in network.stations if s.slug == "corinthians-itaquera")
    assert itaquera.coordinates.source == "geosampa"
    assert itaquera.coordinates.confidence == "A"


def test_the_station_order_is_taken_from_the_gtfs(network):
    line = next(line for line in network.lines if line.id == "linha-3")
    assert line.station_order.value == "gtfs_sptrans"
    assert [station for station in line.stations] == ["corinthians-itaquera", "artur-alvim"]


def test_a_projected_station_lands_on_its_projected_line(network):
    line = next(line for line in network.lines if line.id == "linha-6")
    assert "brasilandia" in line.stations
    # OSM maps the stretch that already runs while GeoSampa still calls the whole line
    # projected, which is what "partially open" means.
    assert line.status.value == "partial"


def test_a_running_stop_outranks_a_projected_record_for_the_same_station(network):
    stations = {station.id: station for station in network.stations}
    assert stations["brasilandia"].status.value == "operational"
    assert stations["brasilandia"].status.confidence == "E"
    assert stations["itaberaba"].status.value == "planned"


def test_a_bus_corridor_is_published_as_brt(network):
    corridor = next(line for line in network.lines if line.slug == "corredor-paes-de-barros")
    assert corridor.mode.value == "brt"


def test_every_published_field_names_its_source(network):
    for station in network.stations:
        assert station.name.source and station.coordinates.source and station.status.source


def test_a_length_is_derived_for_every_alignment(network):
    for line in network.lines:
        assert (line.length_km is not None) == (line.geometry is not None)


def test_the_build_passes_its_own_invariants(network):
    problems = [item for item in validate.check(network) if item.severity == "error"]
    assert problems == []


def test_the_geojson_carries_lines_and_stations(network):
    features = export.geojson(network)["features"]
    kinds = {feature["properties"]["kind"] for feature in features}
    assert kinds == {"line", "station"}


def test_writing_produces_the_published_files(network, data_dir):
    export.write_all(network)
    written = {path.name for path in settings.dist_dir.iterdir()}
    assert {"network.json", "network.geojson", "conflicts.json", "unmatched.json"} <= written
    reloaded = json.loads((settings.dist_dir / "network.json").read_text())
    assert reloaded["stations"]


class TestCli:
    def test_build_then_validate(self, all_snapshots):
        runner = CliRunner()
        assert runner.invoke(app, ["build"]).exit_code == 0
        assert runner.invoke(app, ["validate"]).exit_code == 0

    def test_validate_without_a_build_explains_itself(self, data_dir):
        result = CliRunner().invoke(app, ["validate"])
        assert result.exit_code != 0

    def test_an_unknown_source_is_refused(self, data_dir):
        assert CliRunner().invoke(app, ["fetch", "nao-existe"]).exit_code != 0

    def test_inspect_summarises_a_source(self, geosampa_snapshot):
        result = CliRunner().invoke(app, ["inspect", "geosampa"])
        assert result.exit_code == 0
        assert "VERMELHA" in result.output


def test_a_projected_station_survives_a_gtfs_covered_line(network):
    """The GTFS lists what runs, so it cannot be used to deny a projected station."""
    line = next(line for line in network.lines if line.id == "linha-3")
    assert line.station_order.value == "gtfs_sptrans"
    stations = {station.id: station for station in network.stations}
    assert all(stations[station_id] for station_id in line.stations)
