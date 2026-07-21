"""Name normalisation and slugs.

Cross-source matching hinges on this module: the same station is written
``CORINTHIANS-ITAQUERA`` by GeoSampa, ``Corinthians-Itaquera`` by the GTFS,
``Corinthians–Itaquera`` (en dash) by OSM and ``Estação Corinthians-Itaquera`` by Wikidata.
Matching on the raw string finds none of those pairs.
"""

from __future__ import annotations

import re

from unidecode import unidecode

# Words that decorate a station name without identifying it. Stripped before comparison,
# never before display.
_NOISE = {
    "estacao",
    "est",
    "terminal",
    "metro",
    "cptm",
    "trem",
    "linha",
    "acesso",
}

_SEPARATORS = re.compile(r"[‐-―−/\\|,;:]+")
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_SPACES = re.compile(r"\s+")


def normalise(name: str) -> str:
    """A comparable key for *name*: unaccented, lowercase, decorations removed.

    >>> normalise("Estação Corinthians–Itaquera")
    'corinthians itaquera'
    """
    text = unidecode(_SEPARATORS.sub(" ", name)).lower()
    text = _NON_ALNUM.sub(" ", text)
    words = [word for word in _SPACES.split(text) if word and word not in _NOISE]
    return " ".join(words)


def slugify(name: str) -> str:
    """A URL segment for *name*, preserving every word (including the noise ones)."""
    text = unidecode(_SEPARATORS.sub("-", name)).lower()
    text = re.sub(r"[^a-z0-9-]+", "-", text)
    return re.sub(r"-{2,}", "-", text).strip("-")


def line_slug(number: str, name: str) -> str:
    """``linha-4-amarela`` from ``("4", "Amarela")``.

    Services outside the region's 1–22 numbering (the VLT, the tourist trains, the airport
    people mover) are not "linha N" of anything, so they keep their own name as the slug.
    """
    return slugify(f"linha-{number}-{name}") if number.isdigit() else slugify(name)


_LINE_NUMBER = re.compile(r"\bL?0*(\d{1,2})\b", re.IGNORECASE)


def line_number(text: str) -> str | None:
    """Pull the line number out of free-form references like ``METRÔ L4`` or ``CPTM L07``.

    >>> line_number("CPTM L07"), line_number("LINHA 4 - AMARELA"), line_number("VERMELHA")
    ('7', '4', None)
    """
    match = _LINE_NUMBER.search(unidecode(text))
    return str(int(match.group(1))) if match else None
