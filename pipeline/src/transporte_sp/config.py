"""Single source of truth for the pipeline: source URLs, bounding box, paths, knobs.

Every scalar knob can be overridden from the environment or a ``.env`` file at the
repository root — the env var name is shown next to each field. A real shell ``export``
wins over ``.env`` (``load_dotenv`` does not clobber vars already set). Non-scalar knobs
(dicts/tuples) stay as code constants below the dataclass.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

_FALSEY = {"0", "false", "no", ""}


def _env(name: str, default, cast):
    def factory(n=name, d=default, c=cast):
        raw = os.environ.get(n)
        return d if raw is None or raw == "" else c(raw)

    return field(default_factory=factory)


def env_str(name: str, default: str):
    return _env(name, default, str)


def env_int(name: str, default: int):
    return _env(name, default, int)


def env_float(name: str, default: float):
    return _env(name, default, float)


def env_bool(name: str, default: bool):
    return _env(name, default, lambda raw: raw.strip().lower() not in _FALSEY)


@dataclass(frozen=True)
class Settings:
    """Knobs for the whole pipeline."""

    data_dir: Path = _env("TSP_DATA_DIR", PROJECT_ROOT / "data", Path)

    # Bounding box of the São Paulo metropolitan region (min_lon, min_lat, max_lon, max_lat).
    # Wide enough to hold Jundiaí (north), Santos (south-east), Sorocaba's approach (west) and
    # Mogi das Cruzes (east), so intercity projects are not clipped out.
    bbox_min_lon: float = env_float("TSP_BBOX_MIN_LON", -47.60)
    bbox_min_lat: float = env_float("TSP_BBOX_MIN_LAT", -24.20)
    bbox_max_lon: float = env_float("TSP_BBOX_MAX_LON", -45.70)
    bbox_max_lat: float = env_float("TSP_BBOX_MAX_LAT", -23.10)

    geosampa_wfs: str = env_str(
        "TSP_GEOSAMPA_WFS",
        "http://wfs.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wfs",
    )
    gtfs_sptrans_url: str = env_str(
        "TSP_GTFS_SPTRANS_URL",
        "https://www.sptrans.com.br/umbraco/Surface/PerfilDesenvolvedor/BaixarGTFS",
    )
    # Overpass mirrors are tried in order. The public instances answer an XML "too busy"
    # page with HTTP 200 under load, so a failure here is normal and not fatal.
    overpass_mirrors_raw: str = env_str(
        "TSP_OVERPASS_MIRRORS",
        ",".join(
            (
                "https://overpass-api.de/api/interpreter",
                "https://overpass.kumi.systems/api/interpreter",
                "https://overpass.private.coffee/api/interpreter",
                "https://overpass.osm.jp/api/interpreter",
            )
        ),
    )
    wikidata_sparql_url: str = env_str(
        "TSP_WIKIDATA_SPARQL_URL", "https://query.wikidata.org/sparql"
    )
    # `wikibase:around` radius from the bbox centre; 60 km reaches Jundiaí and the Baixada.
    wikidata_radius_km: int = env_int("TSP_WIKIDATA_RADIUS_KM", 60)
    metro_ckan_url: str = env_str("TSP_METRO_CKAN_URL", "https://transparencia.metrosp.com.br")
    line_status_url: str = env_str(
        "TSP_LINE_STATUS_URL",
        "https://apim-proximotrem-prd-brazilsouth-001.azure-api.net/api/v1/lines",
    )

    user_agent: str = env_str(
        "TSP_USER_AGENT",
        "transporte-sp/0.1 (+https://github.com/roquerodrigo/transporte-sp)",
    )
    http_timeout: float = env_float("TSP_HTTP_TIMEOUT", 180.0)
    http_retries: int = env_int("TSP_HTTP_RETRIES", 3)

    # Two stations from different sources are considered the same place when their names
    # normalise equal and they sit within this distance. 400 m covers long platforms and the
    # gap between a GeoSampa access point and the OSM station node.
    match_radius_m: float = env_float("TSP_MATCH_RADIUS_M", 400.0)
    # Above this distance the winning coordinate and the runner-up are reported as a
    # conflict. Below it the spread is just where each source puts a long platform.
    coordinate_conflict_m: float = env_float("TSP_COORDINATE_CONFLICT_M", 250.0)
    # Matching is transitive, so a chain of near-misses can pull two genuinely different
    # stations of the same name into one cluster. Observations farther than this from their
    # cluster's medoid are split back out.
    cluster_max_radius_m: float = env_float("TSP_CLUSTER_MAX_RADIUS_M", 600.0)

    @property
    def overpass_mirrors(self) -> list[str]:
        return [url.strip() for url in self.overpass_mirrors_raw.split(",") if url.strip()]

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def dist_dir(self) -> Path:
        return self.data_dir / "dist"

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.bbox_min_lon, self.bbox_min_lat, self.bbox_max_lon, self.bbox_max_lat)

    def contains(self, lon: float, lat: float) -> bool:
        min_lon, min_lat, max_lon, max_lat = self.bbox
        return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


settings = Settings()

# GeoSampa WFS layers consumed by the pipeline, mapped to the network status they describe.
GEOSAMPA_LAYERS: dict[str, str] = {
    "estacao_metro": "operational",
    "estacao_trem": "operational",
    "estacao_metro_projetada": "planned",
    "estacao_trem_projetada": "planned",
    "linha_metro": "operational",
    "linha_trem": "operational",
    "linha_metro_projetada": "planned",
    "linha_trem_projetada": "planned",
    "corredor_onibus": "operational",
}

# Confidence tiers, as documented in the methodology page.
#   A  official primary, structured        B  official secondary or unstructured
#   C  collaborative                        D  press
#   E  inferred by this pipeline
SOURCE_CONFIDENCE: dict[str, str] = {
    "geosampa": "A",
    "gtfs_sptrans": "A",
    "metro_transparencia": "A",
    "artesp": "A",
    "metro_site": "B",
    "operator_site": "B",
    "proximo_trem": "B",
    "osm": "C",
    "wikidata": "C",
    "wikipedia": "C",
    "press": "D",
    "pipeline": "E",
}
