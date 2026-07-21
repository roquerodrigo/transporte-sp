from transporte_sp.merge.lines import base_name, title_case
from transporte_sp.naming import line_number, line_slug, normalise, slugify


def test_normalise_collapses_the_four_spellings_of_one_station():
    written = [
        "CORINTHIANS-ITAQUERA",
        "Corinthians-Itaquera",
        "Corinthians–Itaquera",
        "Estação Corinthians-Itaquera",
    ]
    assert {normalise(name) for name in written} == {"corinthians itaquera"}


def test_normalise_drops_decorations_but_keeps_the_identifying_words():
    assert normalise("Terminal Rodoviário Tietê") == "rodoviario tiete"


def test_slugify_keeps_every_word():
    assert slugify("Palmeiras-Barra Funda") == "palmeiras-barra-funda"
    assert slugify("São Paulo – Morumbi") == "sao-paulo-morumbi"


def test_line_number_reads_the_many_ways_sources_write_it():
    assert line_number("CPTM L07") == "7"
    assert line_number("METRÔ L4") == "4"
    assert line_number("LINHA 15 - PRATA") == "15"
    assert line_number("VERMELHA") is None


def test_line_slug_only_prefixes_numbered_lines():
    assert line_slug("4", "Amarela") == "linha-4-amarela"
    assert line_slug("L1", "VLT Linha 1") == "vlt-linha-1"


def test_base_name_strips_the_direction():
    assert base_name("Linha 5 - Lilás: Capão Redondo → Chácara Klabin") == "Linha 5 - Lilás"
    assert base_name("Linha 13 - Jade") == "Linha 13 - Jade"


def test_title_case_repairs_shouted_names():
    assert title_case("AEROPORTO DE GUARULHOS") == "Aeroporto de Guarulhos"
    assert title_case("CIDADE A.E. CARVALHO") == "Cidade A.E. Carvalho"
    assert title_case("RIO DAS PEDRAS/ARICANDUVA") == "Rio das Pedras/Aricanduva"
