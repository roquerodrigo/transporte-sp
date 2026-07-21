import pytest

from transporte_sp.sources import geosampa, gtfs_sptrans, overpass, wikidata


class TestGeoSampa:
    def test_reads_operating_and_projected_stations(self, geosampa_snapshot):
        stations = geosampa.stations()
        assert {station.name for station in stations} == {
            "CORINTHIANS-ITAQUERA", "BRASILÂNDIA", "ITABERABA",
        }

    def test_a_projected_station_is_referenced_only_by_its_colour(self, geosampa_snapshot):
        projected = next(s for s in geosampa.stations() if s.name == "BRASILÂNDIA")
        assert projected.line_refs == ["LARANJA"]
        assert projected.status == "planned"

    def test_an_operating_station_carries_both_number_and_colour(self, geosampa_snapshot):
        station = next(s for s in geosampa.stations() if s.name == "CORINTHIANS-ITAQUERA")
        assert station.line_refs == ["3", "VERMELHA"]
        assert station.status == "operational"

    def test_lines_keep_the_colour_name_apart_from_the_full_label(self, geosampa_snapshot):
        line = geosampa.lines()[0]
        assert (line.name, line.number, line.colour_name) == ("LINHA 3 - VERMELHA", "3",
                                                              "VERMELHA")
        assert line.geometry

    def test_corridors_are_read_as_brt(self, geosampa_snapshot):
        corridor = geosampa.corridors()[0]
        assert corridor.mode == "brt"
        assert corridor.status == "operational"

    def test_a_non_geojson_response_is_rejected(self):
        with pytest.raises(RuntimeError, match="did not return JSON"):
            geosampa._ensure_geojson("estacao_metro", b"<ows:ExceptionReport/>")


class TestGtfs:
    def test_only_rail_routes_are_read(self, gtfs_snapshot):
        assert [line.number for line in gtfs_sptrans.lines()] == ["3"]

    def test_the_station_order_comes_from_the_stop_sequence(self, gtfs_snapshot):
        assert gtfs_sptrans.lines()[0].station_refs == ["A", "B"]

    def test_bus_stops_are_left_out(self, gtfs_snapshot):
        assert {station.name for station in gtfs_sptrans.stations()} == {
            "Corinthians-Itaquera", "Artur Alvim"
        }

    def test_the_alignment_is_read_from_the_rail_shape(self, gtfs_snapshot):
        assert len(gtfs_sptrans.lines()[0].geometry[0]) == 2


class TestOverpass:
    def test_route_relations_become_lines(self, osm_snapshot):
        lines = overpass.lines()
        assert [line.number for line in lines] == ["3"]
        assert lines[0].mode == "subway"

    def test_a_heritage_route_without_an_operator_is_not_a_line(self, osm_snapshot):
        assert "Bonde Turístico de Santos" not in {line.name for line in overpass.lines()}

    def test_the_ordered_stops_are_kept_as_coordinates(self, osm_snapshot):
        assert overpass.lines()[0].stop_points == [[-46.4711, -23.5423], [-46.4850, -23.5400]]

    def test_the_station_ref_is_read_as_a_code_not_as_a_line(self, osm_snapshot):
        station = next(s for s in overpass.stations() if s.name == "Corinthians–Itaquera")
        assert station.external_ids.metro_code == "ITQ"
        assert station.line_refs == []

    def test_accessibility_is_translated(self, osm_snapshot):
        station = next(s for s in overpass.stations() if s.name == "Corinthians–Itaquera")
        assert station.accessibility == "full"

    def test_every_mirror_failing_is_an_error(self, monkeypatch):
        monkeypatch.setattr(overpass.snapshot, "download",
                            lambda *args, **kwargs: b"<html>too busy</html>")
        with pytest.raises(RuntimeError, match="every Overpass mirror failed"):
            overpass._query("[out:json];")


class TestWikidata:
    def test_rows_of_the_same_entity_collapse_into_one_station(self, wikidata_snapshot):
        stations = wikidata.stations()
        assert len(stations) == 1
        assert stations[0].extra["lines"] == [
            "Linha 3 do Metrô de São Paulo", "Linha 15 do Metrô de São Paulo",
        ]

    def test_the_station_prefix_is_dropped_from_the_label(self, wikidata_snapshot):
        assert wikidata.stations()[0].name == "Corinthians-Itaquera"

    def test_the_official_code_is_kept(self, wikidata_snapshot):
        assert wikidata.stations()[0].external_ids.metro_code == "ITQ"

    def test_results_outside_the_bounding_box_are_discarded(self, wikidata_snapshot):
        assert "Muito Longe" not in {station.name for station in wikidata.stations()}
