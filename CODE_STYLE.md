# Convenções

## Idioma

O **conteúdo** publicado — páginas do site, README, esta documentação — é em português,
porque o público é quem usa a rede de São Paulo. O **código** é em inglês: identificadores,
comentários, mensagens de commit, títulos e descrições de PR. As duas coisas não se
misturam num mesmo arquivo, exceto pelos rótulos de interface, que são dados em português
dentro de código em inglês.

## Pipeline (Python)

- `config.py` é a **fonte única** de qualquer parâmetro: URL, bbox, limiar, caminho. Nada
  de constante espalhada por módulo.
- Um módulo por fonte em `sources/`, todos com a mesma superfície: `fetch()` grava o
  snapshot cru, `stations()`/`lines()` leem o último snapshot. **Nenhuma fonte reconcilia
  nada** — ela relata o que a origem afirma, inclusive quando isso contradiz outra fonte.
- Toda decisão entre fontes vive em `merge/precedence.py`, declarada por campo.
- Comentário só onde explica um **porquê** não óbvio — tipicamente uma armadilha da fonte
  (o `ref` do OSM ser a sigla e não a linha; o Overpass responder 200 com XML de erro).
  O que o código faz deve estar nos nomes.
- Linter e testes antes de qualquer commit:

  ```bash
  cd pipeline
  uv run ruff check .
  uv run pytest
  ```

- Testes **nunca** acessam a rede. Cada fonte é exercitada contra um snapshot de fixture
  escrito à mão em `tests/conftest.py`, que também serve de documentação do formato.
- Cobertura mínima de 80%, verificada pelo próprio `pytest`.

## Site (Astro + Starlight)

- As páginas por linha e por estação são **geradas** por `transporte-sp pages` e
  commitadas. Não edite `site/src/content/docs/linhas/` à mão: a próxima geração sobrescreve.
  Mudou o conteúdo dessas páginas? Mude o gerador em `pipeline/src/transporte_sp/export/pages.py`.
- O site não consulta fonte externa no build. Ele lê `site/src/data/network.json`
  (sem geometria, para renderizar) e serve `site/public/dados/network.geojson` (só
  geometria, simplificada, para o mapa).
- Nada de CDN: dependências de runtime entram por `npm`, não por `<script src>`.
- Verificação antes do commit:

  ```bash
  cd site
  npx astro check
  npm run build
  ```

## Dados

- Todo campo publicado carrega `source` e `confidence`. Um campo novo sem procedência é um
  bug, e `transporte-sp validate` falha por causa dele.
- Divergência acima do limiar não é resolvida em silêncio: vai para `conflicts.json` e
  aparece no site.
- Os payloads crus não são commitados (o GTFS sozinho tem 14 MB por coleta); os manifestos
  são, com URL, SHA-256 e data, o que permite rebaixar e conferir byte a byte.

## Git

Repositório público com proteção de branch: `main` exige CI verde, toda mudança passa por
PR, e o merge é sempre **rebase**. Commits seguem Conventional Commits, em inglês, sem
qualquer menção a ferramentas ou processo interno.
