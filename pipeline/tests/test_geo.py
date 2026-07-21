import pytest

from transporte_sp.geo import along_track, chain_parts, distance_m, line_length_km

SE = (-23.5505, -46.6333)
LUZ = (-23.5347, -46.6356)


def test_distance_between_two_known_stations():
    # Sé to Luz is a little under two kilometres in a straight line.
    assert 1_700 < distance_m(*SE, *LUZ) < 1_900


def test_distance_is_zero_for_the_same_point():
    assert distance_m(*SE, *SE) == pytest.approx(0)


def test_line_length_sums_every_part():
    geometry = [[[-46.6333, -23.5505], [-46.6356, -23.5347]]]
    assert line_length_km(geometry) == pytest.approx(1.77, abs=0.05)


def test_chain_parts_joins_segments_regardless_of_their_order_or_direction():
    first = [[0.0, 0.0], [0.01, 0.0]]
    second = [[0.02, 0.0], [0.01, 0.0]]  # reversed, and given second
    chained = chain_parts([first, second])
    assert chained[0] == [0.0, 0.0]
    assert chained[-1] == [0.02, 0.0]


def test_chain_parts_ignores_degenerate_segments():
    assert chain_parts([[[0.0, 0.0]]]) == []


def test_along_track_grows_with_distance_from_the_start():
    polyline = [[0.0, 0.0], [0.01, 0.0], [0.02, 0.0]]
    near = along_track(polyline, 0.0, 0.001)
    far = along_track(polyline, 0.0, 0.019)
    assert near < far
