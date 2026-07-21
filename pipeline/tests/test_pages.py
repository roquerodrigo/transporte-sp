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


def test_a_page_is_written_for_every_line_and_station(generated):
    root, network = generated
    written = list((root / "docs" / "linhas").rglob("*.mdx"))
    assert len(written) == len(network.lines) + len(network.stations)


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


def test_an_interchange_gets_one_page_under_its_first_line(generated):
    root, _ = generated
    pages_for_itaquera = list((root / "docs" / "linhas").rglob("corinthians-itaquera.mdx"))
    assert len(pages_for_itaquera) == 1
    assert pages_for_itaquera[0].parent.name == "linha-3-vermelha"


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
