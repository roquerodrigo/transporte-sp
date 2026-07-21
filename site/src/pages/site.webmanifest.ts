import type { APIRoute } from "astro";

/**
 * The PWA manifest, generated so its internal paths carry the site's base — a fork
 * publishing under a different prefix gets a correct manifest without editing this file.
 */
export const GET: APIRoute = () => {
  const base = import.meta.env.BASE_URL;
  return new Response(
    JSON.stringify({
      name: "Transporte SP",
      short_name: "Transporte SP",
      description: "Base de dados aberta do transporte de massa metropolitano de São Paulo.",
      lang: "pt-BR",
      start_url: base,
      scope: base,
      display: "standalone",
      background_color: "#0f172a",
      theme_color: "#0f172a",
      icons: [
        { src: `${base}favicon-192.png`, sizes: "192x192", type: "image/png" },
        { src: `${base}favicon-512.png`, sizes: "512x512", type: "image/png" },
      ],
    }),
    { headers: { "content-type": "application/manifest+json" } },
  );
};
