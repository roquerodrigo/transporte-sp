/**
 * Resolve every internal link in the built site against the files on disk.
 *
 * The site is almost entirely generated — 380 of its pages come out of the dataset — so a
 * link is never wrong once: an off-by-one in how they are written breaks hundreds at a
 * time, and none of it shows up in a type check or a build. This is the only check that
 * catches it.
 */
import { readFile, readdir, stat } from "node:fs/promises";
import { join, relative, resolve } from "node:path";

const DIST = resolve(process.argv[2] ?? "dist");
const BASE = (process.env.BASE_PATH ?? "/transporte-sp").replace(/\/$/, "");

async function* walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) yield* walk(path);
    else yield path;
  }
}

const exists = async (path) =>
  stat(path).then(
    (info) => info.isFile(),
    () => false,
  );

/** Where a root-relative URL should land in the built output. */
async function resolves(url) {
  const path = url.slice(BASE.length) || "/";
  const target = join(DIST, decodeURIComponent(path));
  if (await exists(target)) return true;
  return exists(join(target, "index.html"));
}

const pages = [];
for await (const path of walk(DIST)) {
  if (path.endsWith(".html")) pages.push(path);
}

const broken = new Map();
let checked = 0;

for (const page of pages) {
  const html = await readFile(page, "utf8");
  const urls = new Set(
    [...html.matchAll(/(?:href|src)="([^"]+)"/g)]
      .map((match) => match[1].split("#")[0].split("?")[0])
      .filter((url) => url.startsWith("/") && !url.startsWith("//")),
  );
  for (const url of urls) {
    checked += 1;
    if (!url.startsWith(`${BASE}/`) && url !== BASE) {
      record(broken, url, page, "fora do base path");
      continue;
    }
    if (!(await resolves(url))) record(broken, url, page, "destino inexistente");
  }
}

function record(map, url, page, reason) {
  const entry = map.get(url) ?? { reason, pages: [] };
  entry.pages.push(relative(DIST, page));
  map.set(url, entry);
}

console.log(`${pages.length} páginas, ${checked} links internos verificados.`);

if (broken.size === 0) {
  console.log("Nenhum link quebrado.");
  process.exit(0);
}

console.error(`\n${broken.size} link(s) quebrado(s):\n`);
for (const [url, { reason, pages: found }] of [...broken].slice(0, 40)) {
  console.error(`  ${url}  — ${reason} (${found.length} página(s), ex.: ${found[0]})`);
}
if (broken.size > 40) console.error(`  … e mais ${broken.size - 40}`);
process.exit(1);
