from transporte_sp.merge.matching import cluster
from transporte_sp.model import Coordinates, ExternalIds, StationObservation

SE_LAT, SE_LON = -23.5505, -46.6333


def observation(source, name, lat=SE_LAT, lon=SE_LON, wikidata=None):
    return StationObservation(
        source=source,
        source_ref=f"{source}:{name}",
        name=name,
        coordinates=Coordinates(lat=lat, lon=lon),
        external_ids=ExternalIds(wikidata=wikidata),
    )


def test_the_same_station_written_four_ways_becomes_one():
    groups = cluster(
        [
            observation("geosampa", "CORINTHIANS-ITAQUERA"),
            observation("gtfs_sptrans", "Corinthians-Itaquera"),
            observation("osm", "Corinthians–Itaquera"),
            observation("wikidata", "Estação Corinthians-Itaquera"),
        ]
    )
    assert len(groups) == 1


def test_a_shared_wikidata_id_matches_across_different_names():
    groups = cluster(
        [
            observation("osm", "Pinheiros", wikidata="Q123"),
            observation("wikidata", "Estação Pinheiros da CPTM", wikidata="Q123"),
        ]
    )
    assert len(groups) == 1


def test_two_distant_stations_of_the_same_name_stay_apart():
    groups = cluster(
        [
            observation("osm", "Santa Cruz"),
            observation("geosampa", "SANTA CRUZ", lat=-23.60, lon=-46.70),
        ]
    )
    assert len(groups) == 2


def test_a_qualified_name_matches_its_short_form_when_they_are_close():
    groups = cluster(
        [
            observation("gtfs_sptrans", "Santo André"),
            observation("osm", "Prefeito Celso Daniel - Santo André", lat=SE_LAT + 0.001),
        ]
    )
    assert len(groups) == 1


def test_transitive_over_merging_is_undone():
    """A chain of near-misses must not drag two real stations into one cluster."""
    groups = cluster(
        [
            observation("osm", "Perus"),
            observation("geosampa", "PERUS", lat=SE_LAT + 0.003),
            observation("wikidata", "Estação Perus", lat=SE_LAT + 0.05),
        ]
    )
    assert len(groups) == 2
