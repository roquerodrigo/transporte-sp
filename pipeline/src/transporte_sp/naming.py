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


# The number does not always sit between separators. SPTrans writes most of its rail routes
# as ``METRÔ L4``, but the stretches of Line 17-Ouro as ``METRÔ17A`` and ``METRÔ17W`` — no
# separator before the digits, a letter for the stretch after them. Requiring a word
# boundary on both sides read those as unnumbered and published each stretch as a line of
# its own. The operator prefix stands in for the opening boundary, and the closing one is
# only a guard against reading a longer number short.
_LINE_NUMBER = re.compile(r"(?:\b|(?<=metro)|(?<=cptm))L?0*(\d{1,2})(?!\d)", re.IGNORECASE)


def line_number(text: str) -> str | None:
    """Pull the line number out of free-form references like ``METRÔ L4`` or ``METRÔ17A``.

    >>> line_number("CPTM L07"), line_number("METRÔ17A"), line_number("VERMELHA")
    ('7', '17', None)
    """
    match = _LINE_NUMBER.search(unidecode(text))
    return str(int(match.group(1))) if match else None
