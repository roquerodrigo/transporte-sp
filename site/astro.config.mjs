import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

// `site` and `base` follow the GitHub Pages project URL. Both are overridable so a fork
// can publish under its own account without editing the config.
const site = process.env.SITE_URL ?? "https://roquerodrigo.github.io";
const base = process.env.BASE_PATH ?? "/transporte-sp";

export default defineConfig({
  site,
  base,
  trailingSlash: "always",
  integrations: [
    starlight({
      title: "Transporte SP",
      description:
        "Base de dados aberta e auditável do transporte de massa metropolitano de São Paulo.",
      defaultLocale: "root",
      locales: { root: { label: "Português", lang: "pt-BR" } },
      social: {
        github: "https://github.com/roquerodrigo/transporte-sp",
      },
      customCss: ["./src/styles/custom.css"],
      sidebar: [
        { label: "Mapa da rede", link: "/mapa/" },
        { label: "Todas as linhas", link: "/linhas/" },
        { label: "Linhas e estações", autogenerate: { directory: "linhas" } },
        {
          label: "Sobre os dados",
          items: [
            { label: "Metodologia", link: "/metodologia/" },
            { label: "Fontes", link: "/fontes/" },
            { label: "Divergências", link: "/divergencias/" },
          ],
        },
      ],
    }),
  ],
});
