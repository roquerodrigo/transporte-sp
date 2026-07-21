# transporte-sp

Base de dados aberta e auditável do **transporte de massa metropolitano de São Paulo** —
metrô, monotrilho, trens metropolitanos, intercidades, VLT, BRT e corredores — com uma
página por linha e por estação, um mapa com o traçado real e um JSON estruturado.

Cada campo publicado diz **de onde veio** e **com que nível de confiança**. Nenhum dado
aqui é afirmado sem fonte.

## Por que existe

O dado sobre a rede de São Paulo está espalhado e cada pedaço tem um buraco diferente:

- o **GeoSampa** tem a geometria e a rede projetada, mas para no limite do município;
- o **GTFS da SPTrans** tem a ordem das estações e o traçado, mas não tem as Linhas 6 e 17;
- o **OpenStreetMap** cobre a região inteira, mas é fraco em acessibilidade e não tem BRT;
- o **Wikidata** tem a sigla oficial das estações, mas erra a linha da maioria dos trens;
- as **expansões futuras** só existem em PDF, notícia e página institucional.

Nenhuma fonte sozinha responde "quais são todas as linhas e estações da região, onde
ficam, e o que vem depois". Este repositório reúne todas, reconcilia as divergências de
forma explícita e publica o resultado.

## O que o repositório produz

| Saída | Onde |
|---|---|
| Dataset reconciliado | `data/dist/network.json` |
| Geometria da rede | `data/dist/network.geojson` |
| Divergências entre fontes | `data/dist/conflicts.json` |
| Snapshots crus, datados e com hash | `data/raw/<fonte>/<AAAA-MM-DD>/` |
| Site (uma página por linha e por estação) | `site/` |

## Estrutura

```
pipeline/   coleta, reconciliação e exportação (Python)
data/raw/   snapshot cru de cada fonte, com manifest (url, sha256, data)
data/dist/  dataset publicado
site/       site estático (Astro + Starlight)
```

O site **nunca** consulta uma fonte externa durante o build: ele lê `data/dist/`. Só o
pipeline fala com a internet, e sempre grava o snapshot cru antes de processar — assim um
build continua reprodutível mesmo quando um portal sai do ar, o que acontece com
frequência.

## Uso

```bash
cd pipeline
uv sync

uv run transporte-sp fetch            # baixa e versiona um snapshot de cada fonte
uv run transporte-sp fetch geosampa   # ou só de uma
uv run transporte-sp inspect osm      # o que a última coleta de uma fonte produz
uv run transporte-sp build            # reconcilia e escreve data/dist/
uv run transporte-sp validate         # invariantes do dataset
uv run transporte-sp pages            # gera as páginas do site a partir do dataset
```

```bash
cd site
npm ci
npm run dev                           # http://localhost:4321
npm run build
```

As páginas por linha e por estação em `site/src/content/docs/linhas/` são **geradas** e
commitadas — editá-las à mão não adianta, a próxima geração sobrescreve. Para mudar o que
elas mostram, mude o gerador em `pipeline/src/transporte_sp/export/pages.py`.

Os **payloads** crus não são commitados (só o GTFS já tem 14 MB por coleta); os
**manifestos** são, com URL, SHA-256 e data — o que permite rebaixar qualquer snapshot e
conferi-lo byte a byte.

## Níveis de confiança

| Nível | Significado | Exemplos |
|---|---|---|
| **A** | Oficial primária, estruturada | GeoSampa, GTFS SPTrans, transparência do Metrô |
| **B** | Oficial secundária ou não estruturada | páginas do metro.sp.gov.br, sites das concessionárias |
| **C** | Colaborativa | OpenStreetMap, Wikidata |
| **D** | Imprensa | datas de obras sem fonte oficial |
| **E** | Inferido por este pipeline | interpolação, dedução por proximidade |

A precedência entre fontes é declarada **por campo**, não globalmente: a coordenada de uma
estação no município vem do GeoSampa, a sigla oficial vem do Wikidata, a ordem das
estações vem do GTFS e a geometria fora do município vem do OSM. Divergência acima do
limiar não é resolvida em silêncio — vai para `conflicts.json`.

## Fontes

Ver [`NOTICE.md`](./NOTICE.md) para a lista completa, com licença e atribuição de cada uma.

## Licença

Código sob [MIT](./LICENSE). **Dados e conteúdo sob [ODbL 1.0](./LICENSE-DATA)** — o
dataset deriva do OpenStreetMap (share-alike) e do GeoSampa (CC-BY-SA), o que torna uma
licença permissiva incompatível.

## Contribuindo

Ver [`CODE_STYLE.md`](./CODE_STYLE.md). Em resumo: conteúdo em português, código em inglês,
toda mudança por PR com CI verde, e nenhum campo publicado sem procedência.
