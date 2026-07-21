"""The generated site content."""

from __future__ import annotations

import pytest

from transporte_sp import merge
from transporte_sp.export import pages


@pytest.fixture
def generated(all_snapshots, tmp_path, monkeypatch):
    monkeypatch.setattr(pages, "CONTENT_DIR", tmp_path / "docs")
    monkeypatch.setattr(pages, "PUBLIC_DATA_DIR", tmp_path / "public")
    monkeypatch.setattr(pages, "BUILD_DATA_DIR", tmp_path / "build")
    network = merge.build()
    pages.write_all(network)
    return tmp_path, network


def read(root, *parts) -> str:
    return (root / "docs" / "linhas" / "/".join(parts)).read_text()


def read_station(root, slug: str) -> str:
    return (root / "docs" / "estacao" / f"{slug}.mdx").read_text()


def test_a_page_is_written_for_every_line_and_station(generated):
    root, network = generated
    assert len(list((root / "docs" / "linhas").rglob("*.mdx"))) == len(network.lines)
    assert len(list((root / "docs" / "estacao").rglob("*.mdx"))) == len(network.stations)


def test_a_line_page_lists_its_stations_in_order(generated):
    root, _ = generated
    body = read(root, "linha-3-vermelha.mdx")
    assert body.index("Corinthians–Itaquera") < body.index("Artur Alvim")


def test_a_line_page_states_where_the_order_came_from(generated):
    root, _ = generated
    assert "A ordem das estações vem de GTFS SPTrans." in read(root, "linha-3-vermelha.mdx")


def test_a_corridor_without_stations_says_so_instead_of_showing_an_empty_table(generated):
    root, _ = generated
    assert "sem pontos" in read(root, "corredor-paes-de-barros.mdx")


def test_a_station_gets_one_page_outside_any_line(generated):
    """A station served by several lines cannot be filed under one of them."""
    root, _ = generated
    written = list((root / "docs").rglob("corinthians-itaquera.mdx"))
    assert len(written) == 1
    assert written[0].parent.name == "estacao"


def test_a_line_links_its_stations_at_the_station_path(generated):
    root, _ = generated
    assert "(/estacao/corinthians-itaquera/)" in read(root, "linha-3-vermelha.mdx")


def test_the_old_station_address_is_redirected(generated):
    import json

    root, _ = generated
    redirects = json.loads((root / "build" / "redirects.json").read_text())
    assert redirects["/linhas/linha-3-vermelha/corinthians-itaquera"] == (
        "/estacao/corinthians-itaquera"
    )


def test_the_sidebar_is_grouped_by_mode(generated):
    import json

    root, _ = generated
    groups = json.loads((root / "build" / "sidebar.json").read_text())
    assert [group["label"] for group in groups][:1] == ["Metrô"]
    assert all("items" in group for group in groups)


def test_the_provenance_table_translates_vocabularies(generated):
    root, _ = generated
    body = read(root, "linha-3-vermelha.mdx")
    assert "| Situação | Em operação |" in body
    assert "operational |" not in body


def test_a_length_is_shown_with_its_unit(generated):
    root, _ = generated
    assert "km |" in read(root, "linha-3-vermelha.mdx")


def test_the_map_payload_is_published_separately_from_the_page_data(generated):
    root, _ = generated
    assert (root / "public" / "network.geojson").exists()
    assert (root / "build" / "network.json").exists()


def test_the_page_data_drops_the_alignments_it_does_not_need(generated):
    import json

    root, _ = generated
    payload = json.loads((root / "build" / "network.json").read_text())
    assert all("geometry" not in line for line in payload["lines"])


def test_frontmatter_escapes_quotes_in_a_title():
    assert '\\"' in pages._frontmatter('Estação "X"', "d")


def test_a_mixed_line_splits_its_stations_by_state(generated):
    """Line 6 runs a first stretch while the rest is still projected."""
    root, _ = generated
    body = read(root, "linha-6-laranja.mdx")
    assert "### Em operação" in body
    assert "### Projetada" in body


def test_a_line_in_a_single_state_keeps_one_table(generated):
    root, _ = generated
    body = read(root, "linha-3-vermelha.mdx")
    assert "### " not in body


def test_the_index_is_split_by_mode(generated):
    root, _ = generated
    index = (root / "docs" / "linhas.mdx").read_text()
    assert "## Metrô" in index
    assert "## BRT" in index


def test_a_handful_of_alternative_readings_is_listed(generated):
    root, _ = generated
    body = read_station(root, "corinthians-itaquera")
    assert '<Origem fonte="geosampa" nivel="A" />' in body


def test_the_provenance_column_carries_the_badge(generated):
    """Source and confidence are one fact and travel as one badge."""
    root, _ = generated
    body = read_station(root, "corinthians-itaquera")
    assert "| Campo | Valor | Procedência | Outras leituras |" in body


def test_a_station_state_is_a_badge_not_a_word(generated):
    root, _ = generated
    assert '<Situacao valor="operational" />' in read(root, "linha-3-vermelha.mdx")


def test_many_alternative_readings_are_summarised():
    """An interchange collects a coordinate per line per direction; Luz arrives with eight."""
    from transporte_sp.export import pages
    from transporte_sp.model import Alternative, Coordinates, Sourced

    leituras = [
        Alternative(
            value={"lat": -23.5 - n / 1000, "lon": -46.6},
            source="gtfs_sptrans" if n % 2 else "osm",
            confidence="C",
            note=f"{n * 40} m de distância",
        )
        for n in range(1, 9)
    ]
    campo = Sourced[Coordinates](
        value=Coordinates(lat=-23.5, lon=-46.6),
        source="geosampa",
        confidence="A",
        alternatives=leituras,
    )
    cell = pages._alternatives_cell(campo, "coordinates")
    assert cell.startswith("8 leituras")
    assert "até 320 m de distância" in cell
    assert '<Origem fonte="gtfs_sptrans" nivel="C" />' in cell
    assert '<Origem fonte="osm" nivel="C" />' in cell


def test_no_alternative_reading_renders_as_a_dash():
    from transporte_sp.export import pages
    from transporte_sp.model import Sourced

    campo = Sourced[str](value="x", source="osm", confidence="C")
    assert pages._alternatives_cell(campo, "name") == "—"


def test_numbers_and_dates_are_written_in_brazilian_form():
    from transporte_sp.export.formato import data, numero, quilometros

    assert numero(1234.5, 1) == "1.234,5"
    assert numero(371) == "371"
    assert numero(1371) == "1.371"
    assert quilometros(12.765) == "12,8 km"
    assert quilometros(160.9) == "160,9 km"
    assert data("1974-09-14") == "14/09/1974"


def test_an_unparseable_date_is_left_alone():
    from transporte_sp.export.formato import data

    assert data("em obras") == "em obras"


def test_the_provenance_table_uses_the_brazilian_forms(generated):
    root, _ = generated
    body = read(root, "linha-3-vermelha.mdx")
    assert " km |" in body
    assert not any(linha.startswith("| Extensão") and "." in linha.split("|")[2]
                   for linha in body.splitlines())
