from datetime import date

from transporte_sp import validate
from transporte_sp.config import settings
from transporte_sp.model import Line, Network, Station


def sourced(value, source="geosampa", confidence="A"):
    return {"value": value, "source": source, "confidence": confidence}


def station(slug, lat=-23.55, lon=-46.63, lines=("linha-1",)):
    return Station(
        id=slug,
        slug=slug,
        name=sourced(slug.title()),
        coordinates=sourced({"lat": lat, "lon": lon}),
        lines=list(lines),
        status=sourced("operational"),
    )


def line(identifier="linha-1", stations=("a", "b"), geometry=True):
    return Line(
        id=identifier,
        slug=identifier,
        name=sourced("Azul"),
        mode=sourced("subway"),
        status=sourced("operational"),
        stations=list(stations),
        geometry=sourced([[[-46.63, -23.55], [-46.62, -23.54]]]) if geometry else None,
        length_km=sourced(1.2) if geometry else None,
    )


def network(**kwargs):
    defaults = {
        "generated_at": date(2026, 7, 21),
        "bbox": settings.bbox,
        "lines": [line()],
        "stations": [station("a"), station("b")],
    }
    return Network(**{**defaults, **kwargs})


def errors(result):
    return [problem.message for problem in result if problem.severity == "error"]


def test_a_consistent_network_has_no_errors():
    assert errors(validate.check(network())) == []


def test_a_station_outside_the_bounding_box_is_an_error():
    problems = validate.check(network(stations=[station("a", lat=0.0, lon=0.0), station("b")]))
    assert any("outside the bounding box" in message for message in errors(problems))


def test_a_rail_line_with_one_station_is_an_error():
    problems = validate.check(network(lines=[line(stations=["a"])]))
    assert any("station(s)" in message for message in errors(problems))


def test_a_running_line_without_an_alignment_is_an_error():
    problems = validate.check(network(lines=[line(geometry=False)]))
    assert any("without an alignment" in message for message in errors(problems))


def test_membership_must_be_symmetric():
    problems = validate.check(network(stations=[station("a"), station("b", lines=["linha-9"])]))
    assert any("unknown line" in message for message in errors(problems))


def test_a_station_missing_from_its_line_sequence_is_an_error():
    problems = validate.check(network(lines=[line(stations=["a"])], stations=[station("a"),
                                                                             station("b")]))
    assert any("not in the sequence" in message for message in errors(problems))


def test_a_station_without_a_line_is_only_a_warning():
    problems = validate.check(network(stations=[station("a"), station("b", lines=[])]))
    assert errors(problems) == []
    assert any("not attached to any line" in problem.message for problem in problems)


def test_report_counts_the_errors():
    assert validate.report(validate.check(network(lines=[line(geometry=False)]))) >= 1
