from transporte_sp.merge.lines import key_for, reconcile
from transporte_sp.model import LineObservation


def observation(source, name, **kwargs):
    return LineObservation(source=source, source_ref=name, name=name, **kwargs)


def test_every_source_spelling_of_line_four_keys_to_the_same_line():
    written = [
        observation("geosampa", "LINHA 4 - AMARELA", number="4"),
        observation("gtfs_sptrans", "VILA SÔNIA - LUZ", number="4"),
        observation("osm", "Linha 4 - Amarela: Luz → Vila Sônia", number="4"),
    ]
    assert {key_for(item) for item in written} == {"linha-4"}


def test_services_outside_the_numbering_key_on_their_name():
    forward = observation("osm", "VLT Linha 1: Terminal Barreiros → Terminal Porto", number="L1")
    backward = observation("osm", "VLT Linha 1: Terminal Porto → Terminal Barreiros", number="L1")
    assert key_for(forward) == key_for(backward) == "vlt-linha-1"


def test_a_line_is_named_by_its_colour_not_by_its_termini():
    conflicts = []
    lines = reconcile(
        [
            observation("gtfs_sptrans", "VILA SÔNIA - LUZ", number="4", status="operational"),
            observation(
                "geosampa", "LINHA 4 - AMARELA", number="4",
                colour_name="AMARELA", status="operational",
            ),
        ],
        conflicts,
    )
    assert lines[0].name.value == "Amarela"
    assert lines[0].slug == "linha-4-amarela"


def test_a_line_running_but_still_only_projected_in_geosampa_is_partial():
    """Lines 6 and 17 opened a first stretch while the rest is still being built."""
    conflicts = []
    lines = reconcile(
        [
            observation("geosampa", "LINHA 6 - LARANJA", number="6",
                        colour_name="LARANJA", status="planned"),
            observation("osm", "Linha 6 - Laranja: João Paulo I ⇒ Perdizes",
                        number="6", status="operational"),
        ],
        conflicts,
    )
    assert lines[0].status.value == "partial"
    assert lines[0].status.confidence == "E"


def test_a_line_geosampa_does_not_cover_is_not_downgraded_to_partial():
    conflicts = []
    lines = reconcile(
        [observation("osm", "VLT Linha 1: Barreiros → Porto", number="L1", status="operational")],
        conflicts,
    )
    assert lines[0].status.value == "operational"


def test_the_longer_alignment_wins_and_the_clipped_one_is_kept_as_an_alternative():
    long_way = [[[-46.7, -23.5], [-46.5, -23.5], [-46.3, -23.5]]]
    clipped = [[[-46.7, -23.5], [-46.6, -23.5]]]
    conflicts = []
    lines = reconcile(
        [
            observation("geosampa", "RUBI", number="7", status="operational", geometry=clipped),
            observation("osm", "Linha 7 - Rubi", number="7", status="operational",
                        geometry=long_way),
        ],
        conflicts,
    )
    assert lines[0].geometry.source == "osm"
    assert [item.source for item in lines[0].geometry.alternatives] == ["geosampa"]
    # GeoSampa covering less is its documented extent, not a disagreement worth reporting.
    assert conflicts == []


def test_a_station_osm_serves_is_running_even_if_geosampa_calls_it_projected():
    """The station-level counterpart of the `partial` line status."""
    from transporte_sp.merge.lines import _mark_running
    from transporte_sp.model import Sourced

    class FakeStation:
        def __init__(self):
            self.status = Sourced[str](value="planned", source="geosampa", confidence="A")

    station = FakeStation()
    _mark_running(["x"], {"x": station})
    assert station.status.value == "operational"
    assert station.status.confidence == "E"
    assert station.status.alternatives[0].value == "planned"


def test_a_station_already_running_is_left_alone():
    from transporte_sp.merge.lines import _mark_running
    from transporte_sp.model import Sourced

    class FakeStation:
        def __init__(self):
            self.status = Sourced[str](value="operational", source="geosampa", confidence="A")

    station = FakeStation()
    _mark_running(["x"], {"x": station})
    assert station.status.source == "geosampa"
    assert station.status.alternatives == []


def test_the_planned_alignment_is_kept_apart_from_the_running_one():
    """A projected extension must not be drawn as, or measured as, track in service."""
    running = [[[-46.70, -23.50], [-46.60, -23.50]]]
    extension = [[[-46.60, -23.50], [-46.50, -23.50]]]
    conflicts = []
    lines = reconcile(
        [
            observation("osm", "Linha 4 - Amarela", number="4", status="operational",
                        geometry=running),
            observation("geosampa", "LINHA 4 - AMARELA", number="4", colour_name="AMARELA",
                        status="operational", geometry=running),
            observation("geosampa", "LINHA 4 - AMARELA", number="4", colour_name="AMARELA",
                        status="planned", geometry=extension),
        ],
        conflicts,
    )
    line = lines[0]
    assert line.geometry.value == running
    assert line.planned_geometry.value == extension
    assert line.status.value == "operational"


def test_the_running_alignment_prefers_a_single_traversal_over_a_track_by_track_map():
    """GeoSampa maps each commuter track separately, which doubles the length."""
    single = [[[-46.70, -23.50], [-46.60, -23.50]]]
    both_tracks = [
        [[-46.70, -23.50], [-46.60, -23.50]],
        [[-46.70, -23.5001], [-46.60, -23.5001]],
    ]
    conflicts = []
    lines = reconcile(
        [
            observation("geosampa", "RUBI", number="7", status="operational",
                        geometry=both_tracks),
            observation("osm", "Linha 7 - Rubi", number="7", status="operational",
                        geometry=single),
        ],
        conflicts,
    )
    assert lines[0].geometry.source == "osm"
    assert [item.source for item in lines[0].geometry.alternatives] == ["geosampa"]
