/**
 * Build-time access to the reconciled dataset.
 *
 * `network.json` here is written by the pipeline (`transporte-sp pages`) with the line
 * alignments stripped out — the map fetches those separately as GeoJSON, so no page has to
 * ship four megabytes to render a fact box.
 */
import raw from "./network.json";

export type Confidence = "A" | "B" | "C" | "D" | "E";

export interface Alternative {
  value: unknown;
  source: string;
  confidence: Confidence;
  note?: string | null;
}

export interface Sourced<T> {
  value: T;
  source: string;
  confidence: Confidence;
  alternatives: Alternative[];
}

export interface Coordinates {
  lat: number;
  lon: number;
}

export interface Station {
  id: string;
  slug: string;
  name: Sourced<string>;
  coordinates: Sourced<Coordinates>;
  lines: string[];
  status: Sourced<string>;
  code?: Sourced<string> | null;
  accessibility?: Sourced<string> | null;
  opened?: Sourced<string> | null;
  external_ids: Record<string, string | null>;
  is_interchange: boolean;
  observed_by: string[];
}

export interface Line {
  id: string;
  slug: string;
  name: Sourced<string>;
  number?: Sourced<string> | null;
  colour?: Sourced<string> | null;
  mode: Sourced<string>;
  operator?: Sourced<string> | null;
  status: Sourced<string>;
  stations: string[];
  station_order?: Sourced<string> | null;
  length_km?: Sourced<number> | null;
  planned_length_km?: Sourced<number> | null;
  observed_by: string[];
}

export interface SourceRecord {
  id: string;
  name: string;
  licence: string;
  confidence: Confidence;
  fetched_at: string;
}

export interface Network {
  generated_at: string;
  bbox: [number, number, number, number];
  sources: SourceRecord[];
  lines: Line[];
  stations: Station[];
}

export const network = raw as unknown as Network;

const linesById = new Map(network.lines.map((line) => [line.id, line]));
const stationsById = new Map(network.stations.map((station) => [station.id, station]));

export const lineById = (id: string): Line | undefined => linesById.get(id);
export const stationById = (id: string): Station | undefined => stationsById.get(id);

export const MODE_LABELS: Record<string, string> = {
  subway: "Metrô",
  monorail: "Monotrilho",
  commuter_rail: "Trem metropolitano",
  intercity_rail: "Trem intercidades",
  lrt: "VLT",
  brt: "BRT",
  people_mover: "Aeromóvel",
};

export const STATUS_LABELS: Record<string, string> = {
  operational: "Em operação",
  partial: "Operação parcial",
  under_construction: "Em obras",
  planned: "Projetada",
  proposed: "Proposta",
  closed: "Desativada",
};

export const ACCESSIBILITY_LABELS: Record<string, string> = {
  full: "Acessível",
  partial: "Parcialmente acessível",
  none: "Sem acessibilidade",
  unknown: "Não informado",
};

export const SOURCE_LABELS: Record<string, string> = {
  geosampa: "GeoSampa",
  gtfs_sptrans: "GTFS SPTrans",
  osm: "OpenStreetMap",
  wikidata: "Wikidata",
  pipeline: "inferido",
};

/** The tier each source sits in, for the places that carry a source id but no level. */
export const SOURCE_CONFIDENCE: Record<string, Confidence> = {
  geosampa: "A",
  gtfs_sptrans: "A",
  metro_transparencia: "A",
  artesp: "A",
  metro_site: "B",
  operator_site: "B",
  proximo_trem: "B",
  osm: "C",
  wikidata: "C",
  wikipedia: "C",
  press: "D",
  pipeline: "E",
};

/** How confident the dataset is in a value, spelled out for a reader. */
export const CONFIDENCE_LABELS: Record<Confidence, string> = {
  A: "oficial primária",
  B: "oficial secundária",
  C: "colaborativa",
  D: "imprensa",
  E: "inferida",
};

export const lineTitle = (line: Line): string =>
  line.number ? `Linha ${line.number.value} - ${line.name.value}` : line.name.value;

/** The line whose section owns a station's page. */
export const canonicalLine = (station: Station): Line | undefined =>
  station.lines.length ? lineById(station.lines[0]!) : undefined;

export const stationHref = (base: string, station: Station): string => {
  const owner = canonicalLine(station);
  return owner ? `${base}linhas/${owner.slug}/${station.slug}/` : base;
};

export const lineColour = (line: Line): string => line.colour?.value ?? "#6b7280";
