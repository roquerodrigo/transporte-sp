"""Generating the site's content from the dataset.

One MDX file per line and per station, written into ``site/src/content/docs/`` and
committed. Generating into the repository rather than at build time means a pull request
shows exactly how the network changed — a new station appears as a new file, a renamed one
as a rename — which is the whole point of versioning the data.

Lines live at ``/linhas/<slug>/`` and stations at ``/estacao/<slug>/``, deliberately apart:
a station can be served by four lines, and filing it under one of them would make the other
three link to a URL that claims otherwise.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from transporte_sp.config import PROJECT_ROOT
from transporte_sp.model import Line, Network, Station

log = logging.getLogger(__name__)

CONTENT_DIR = PROJECT_ROOT / "site" / "src" / "content" / "docs"
PUBLIC_DATA_DIR = PROJECT_ROOT / "site" / "public" / "dados"
BUILD_DATA_DIR = PROJECT_ROOT / "site" / "src" / "data"

# Alignment simplification for the web map. At city zoom an 8 m deviation is well under a
# pixel, and it cuts the payload by roughly three quarters.
MAP_SIMPLIFY_M = 8.0

MODE_LABELS = {
    "subway": "Metrô",
    "monorail": "Monotrilho",
    "commuter_rail": "Trem metropolitano",
    "intercity_rail": "Trem intercidades",
    "lrt": "VLT",
    "brt": "BRT",
    "people_mover": "Aeromóvel",
}

STATUS_LABELS = {
    "operational": "Em operação",
    "partial": "Operação parcial",
    "under_construction": "Em obras",
    "planned": "Projetada",
    "proposed": "Proposta",
    "closed": "Desativada",
}

ACCESSIBILITY_LABELS = {
    "full": "Acessível",
    "partial": "Parcialmente acessível",
    "none": "Sem acessibilidade",
    "unknown": "Não informado",
}

SOURCE_LABELS = {
    "geosampa": "GeoSampa",
    "gtfs_sptrans": "GTFS SPTrans",
    "osm": "OpenStreetMap",
    "wikidata": "Wikidata",
    "pipeline": "inferido",
}


def write_all(network: Network) -> None:
    _reset(CONTENT_DIR / "linhas")
    _reset(CONTENT_DIR / "estacao")
    BUILD_DATA_DIR.mkdir(parents=True, exist_ok=True)
    stations = {station.id: station for station in network.stations}

    for line in network.lines:
        _write(_line_path(line), _line_page(line, network, stations))
    for station in network.stations:
        _write(_station_path(station), _station_page(station, network))
    _write(CONTENT_DIR / "linhas.mdx", _index_page(network))
    _write_sidebar(network)
    _write_redirects(network)
    _publish_data(network)
    log.info(
        "site: %d line pages, %d station pages", len(network.lines), len(network.stations)
    )


def _reset(directory: Path) -> None:
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True, exist_ok=True)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def _line_path(line: Line) -> Path:
    return CONTENT_DIR / "linhas" / f"{line.slug}.mdx"


def _station_path(station: Station) -> Path:
    """Stations live at ``/estacao/<slug>/``, outside any line.

    Nesting a station under a line meant picking one owner for a place that has several:
    the Sé serves four lines, and filing it under the lowest-numbered one made the other
    three link away to a URL that reads as if the station belonged elsewhere.
    """
    return CONTENT_DIR / "estacao" / f"{station.slug}.mdx"


def station_href(station: Station) -> str:
    return f"/estacao/{station.slug}/"


def _escape(text: str) -> str:
    return text.replace('"', '\\"')


def _frontmatter(title: str, description: str, **extra) -> str:
    lines = ["---", f'title: "{_escape(title)}"', f'description: "{_escape(description)}"']
    for key, value in extra.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def _line_page(line: Line, network: Network, stations) -> str:
    title = _line_title(line)
    mode = MODE_LABELS.get(line.mode.value, line.mode.value)
    status = STATUS_LABELS.get(line.status.value, line.status.value)
    description = f"{mode} · {status}" + (
        f" · {line.length_km.value} km" if line.length_km else ""
    )

    sections = _station_sections(line, network, stations)

    body = [
        _frontmatter(title, description),
        "",
        'import FichaLinha from "@components/FichaLinha.astro";',
        'import MapaLinha from "@components/MapaLinha.astro";',
        "",
        f'<FichaLinha linha="{line.id}" />',
        "",
        f'<MapaLinha linha="{line.id}" />',
        "",
        "## Estações",
        "",
    ]
    if sections:
        for heading, rows in sections:
            # A line whose stations are all in the same state needs no section headings;
            # only 6-Laranja, 17-Ouro and the projected lines have more than one.
            if heading:
                body += [f"### {heading}", ""]
            body += [
                "| # | Estação | Sigla | Situação | Baldeação |",
                "| --: | --- | --- | --- | --- |",
                *rows,
                "",
            ]
        body += [
            f"A ordem das estações vem de {SOURCE_LABELS.get(line.station_order.source, '—')}."
            if line.station_order
            else "",
        ]
    else:
        body.append(
            "Nenhuma fonte consultada publica estações para esta linha — os corredores de "
            "ônibus são mapeados como traçado, sem pontos."
        )
    body += ["", "## Procedência", "", _provenance_table(line)]
    return "\n".join(body) + "\n"


# The order sections appear in when a line mixes them: what runs today comes first.
STATUS_ORDER = ["operational", "partial", "under_construction", "planned", "proposed", "closed"]


def _station_sections(line: Line, network: Network, stations):
    """The station table, split by state when the line has more than one.

    Lines 6-Laranja and 17-Ouro run a first stretch while the rest is still being built, and
    the eight projected lines exist only on paper. Listing forty stations in one table hides
    exactly the thing a reader is looking for — which of them you can actually board today.
    """
    grouped: dict[str, list[str]] = {}
    for position, station_id in enumerate(line.stations, start=1):
        station = stations.get(station_id)
        if station is None:
            continue
        others = [other for other in station.lines if other != line.id]
        row = "| {} | [{}]({}) | {} | {} | {} |".format(
            position,
            station.name.value,
            station_href(station),
            station.code.value if station.code else "—",
            _unbreakable(STATUS_LABELS.get(station.status.value, station.status.value)),
            ", ".join(_line_label(network, other) for other in others) or "—",
        )
        grouped.setdefault(station.status.value, []).append(row)

    if not grouped:
        return []
    order = [status for status in STATUS_ORDER if status in grouped]
    order += [status for status in grouped if status not in STATUS_ORDER]
    if len(order) == 1:
        return [("", grouped[order[0]])]
    return [
        (f"{STATUS_LABELS.get(status, status)} ({len(grouped[status])})", grouped[status])
        for status in order
    ]


def _unbreakable(text: str) -> str:
    """Keep a short label on one line inside a table cell.

    "Em operação" is two words in a narrow column, and letting it wrap doubles the height of
    every row in a 23-station table for no gain.
    """
    return text.replace(" ", "\u00a0")


def _line_label(network: Network, line_id: str) -> str:
    line = next((item for item in network.lines if item.id == line_id), None)
    if line is None:
        return line_id
    return f"[{_line_title(line)}](/linhas/{line.slug}/)"


def _station_page(station: Station, network: Network) -> str:
    served = [_line_label(network, item) for item in station.lines]
    description = "Estação de " + ", ".join(
        _plain_line_label(network, item) for item in station.lines
    )
    body = [
        _frontmatter(station.name.value, description),
        "",
        'import FichaEstacao from "@components/FichaEstacao.astro";',
        'import MapaEstacao from "@components/MapaEstacao.astro";',
        "",
        f'<FichaEstacao estacao="{station.id}" />',
        "",
        f'<MapaEstacao estacao="{station.id}" />',
        "",
        "## Linhas",
        "",
        *[f"- {item}" for item in served],
        "",
        "## Procedência",
        "",
        _provenance_table(station),
    ]
    return "\n".join(body) + "\n"


def _plain_line_label(network: Network, line_id: str) -> str:
    line = next((item for item in network.lines if item.id == line_id), None)
    if line is None:
        return line_id
    return _line_title(line)


def _provenance_table(entity) -> str:
    rows = ["| Campo | Valor | Fonte | Confiança | Outras leituras |",
            "| --- | --- | --- | --- | --- |"]
    for label, key, field in _sourced_fields(entity):
        alternatives = "; ".join(
            f"{_readable(item.value, key)} ({SOURCE_LABELS.get(item.source, item.source)})"
            for item in field.alternatives
        )
        rows.append(
            f"| {label} | {_readable(field.value, key)} | "
            f"{SOURCE_LABELS.get(field.source, field.source)} | {field.confidence} | "
            f"{alternatives or '—'} |"
        )
    return "\n".join(rows)


def _sourced_fields(entity):
    labels = {
        "name": "Nome",
        "coordinates": "Coordenada",
        "code": "Sigla",
        "accessibility": "Acessibilidade",
        "opened": "Inauguração",
        "status": "Situação",
        "number": "Número",
        "colour": "Cor",
        "mode": "Modo",
        "operator": "Operadora",
        "length_km": "Extensão",
        "station_order": "Ordem das estações",
    }
    for fieldname, label in labels.items():
        field = getattr(entity, fieldname, None)
        if field is not None and hasattr(field, "source"):
            yield label, fieldname, field


# Vocabularies that must be shown the way the rest of the page shows them, not raw.
_VALUE_LABELS = {
    "status": STATUS_LABELS,
    "mode": MODE_LABELS,
    "accessibility": ACCESSIBILITY_LABELS,
    "station_order": SOURCE_LABELS,
}


def _readable(value, fieldname: str = "") -> str:
    """A value as a reader should see it — translated, rounded, or summarised.

    Coordinates arrive either as the parsed model (the chosen value) or as a plain mapping
    (the alternatives, which the model keeps untyped), and both must render the same.
    """
    latitude = getattr(value, "lat", None)
    longitude = getattr(value, "lon", None)
    if isinstance(value, dict) and {"lat", "lon"} <= value.keys():
        latitude, longitude = value["lat"], value["lon"]
    if latitude is not None and longitude is not None:
        return f"{latitude:.5f}, {longitude:.5f}"
    if isinstance(value, list):
        return f"{len(value)} trecho(s)"
    if fieldname == "length_km":
        return f"{value} km"
    vocabulary = _VALUE_LABELS.get(fieldname)
    text = str(value)
    return vocabulary.get(text, text) if vocabulary else text


# Heaviest mode first: the reader looking for "the metro" should not scroll past 22 bus
# corridors to find it.
MODE_ORDER = [
    "subway",
    "monorail",
    "commuter_rail",
    "intercity_rail",
    "lrt",
    "people_mover",
    "brt",
]


def _index_page(network: Network) -> str:
    """The line index, in a section per mode.

    A single 46-row table mixes six metro lines with 22 bus corridors, which are not the
    same kind of thing and are almost never looked up together. The sections use the same
    vocabulary as the filter on the network map.
    """
    grouped: dict[str, list[Line]] = {}
    for line in network.lines:
        grouped.setdefault(line.mode.value, []).append(line)
    order = [mode for mode in MODE_ORDER if mode in grouped]
    order += [mode for mode in grouped if mode not in MODE_ORDER]

    body = []
    for mode in order:
        lines = grouped[mode]
        body += [
            f"## {MODE_LABELS.get(mode, mode)} ({len(lines)})",
            "",
            "| Linha | Situação | Estações | Extensão |",
            "| --- | --- | --: | --: |",
        ]
        for line in lines:
            body.append(
                f"| [{_line_title(line)}](/linhas/{line.slug}/) | "
                f"{STATUS_LABELS.get(line.status.value, line.status.value)} | "
                f"{len(line.stations) or '—'} | "
                f"{f'{line.length_km.value} km' if line.length_km else '—'} |"
            )
        body.append("")

    return "\n".join([
        _frontmatter("Linhas", "Todas as linhas de transporte de massa da região metropolitana"),
        "",
        f"{len(network.lines)} linhas e {len(network.stations)} estações, "
        f"reconciliadas em {network.generated_at.isoformat()}.",
        "",
        *body,
    ]) + "\n"


def _write_sidebar(network: Network) -> None:
    """Emit the sidebar grouped by mode, the same way the index groups its tables.

    Starlight's autogenerated groups take their label from the directory on disk, which
    would show every line as ``linha-1-azul`` and would file the 333 stations under it.
    Stations are reachable from their line and from the search; the sidebar lists lines,
    sectioned by mode so a reader is not scrolling past 21 bus corridors to reach the metro.
    """
    grouped: dict[str, list[Line]] = {}
    for line in network.lines:
        grouped.setdefault(line.mode.value, []).append(line)
    order = [mode for mode in MODE_ORDER if mode in grouped]
    order += [mode for mode in grouped if mode not in MODE_ORDER]

    groups = [
        {
            "label": MODE_LABELS.get(mode, mode),
            "items": [
                {"label": _line_title(line), "link": f"/linhas/{line.slug}/"}
                for line in grouped[mode]
            ],
        }
        for mode in order
    ]
    _write(BUILD_DATA_DIR / "sidebar.json", json.dumps(groups, ensure_ascii=False, indent=1))


def _write_redirects(network: Network) -> None:
    """Keep the URLs the stations used to live at working.

    Station pages moved out from under the lines. The old address of each one was
    ``/linhas/<lowest-numbered line>/<station>/``, which is reproducible from the dataset,
    so every one of them is redirected rather than left to 404.
    """
    by_id = {line.id: line for line in network.lines}
    redirects = {}
    for station in network.stations:
        if not station.lines or station.lines[0] not in by_id:
            continue
        antigo = f"/linhas/{by_id[station.lines[0]].slug}/{station.slug}"
        redirects[antigo] = station_href(station).rstrip("/")
    _write(BUILD_DATA_DIR / "redirects.json", json.dumps(redirects, ensure_ascii=False, indent=1))


def _line_title(line: Line) -> str:
    number = line.number.value if line.number else None
    return f"Linha {number} - {line.name.value}" if number else line.name.value


def _publish_data(network: Network) -> None:
    """Split the dataset the way the site consumes it.

    The fact boxes are rendered at build time and never need the alignments, which are the
    bulk of the file; the map needs only the alignments, simplified. Shipping one 4 MB JSON
    for both would make every page download the whole network.
    """
    from transporte_sp import export
    from transporte_sp.config import settings

    payload = network.model_dump(mode="json", exclude={"unmatched"})
    for line in payload["lines"]:
        line.pop("geometry", None)
    _write(BUILD_DATA_DIR / "network.json", json.dumps(payload, ensure_ascii=False))

    PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    _write(
        PUBLIC_DATA_DIR / "network.geojson",
        json.dumps(export.geojson(network, simplify_m=MAP_SIMPLIFY_M), ensure_ascii=False),
    )
    conflicts = settings.dist_dir / "conflicts.json"
    if conflicts.exists():
        shutil.copy(conflicts, PUBLIC_DATA_DIR / "conflicts.json")
