/**
 * Numbers and dates as they are written in Brazil, for the values the components render.
 *
 * The generated pages get the same treatment from the pipeline; this is the other half, so
 * a length in a card and the same length in a table read identically.
 */

/**
 * Line lengths are shown to one decimal. The sources place the same station up to a few
 * hundred metres apart, so writing a length to the metre would claim a precision the data
 * does not have — the full value stays in `network.json`.
 */
const CASAS_EXTENSAO = 1;

export const numero = (valor: number, casas = 0): string =>
  new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  }).format(valor);

export const quilometros = (valor: number): string => `${numero(valor, CASAS_EXTENSAO)} km`;

/** `1974-09-14` → `14/09/1974`. Parsed as a plain date, never shifted by a time zone. */
export const data = (iso: string): string => {
  const partes = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return partes ? `${partes[3]}/${partes[2]}/${partes[1]}` : iso;
};
