# transporte-sp

Base de dados aberta do transporte de massa metropolitano de São Paulo. Um **pipeline**
Python coleta fontes públicas, reconcilia as divergências e publica um dataset onde todo
campo declara sua procedência; um **site** Astro + Starlight gera uma página por linha e por
estação a partir desse dataset, mais um mapa com o traçado real.

Convenções de escrita, lint e fluxo de trabalho: [`CODE_STYLE.md`](./CODE_STYLE.md).

---

## Regra que organiza tudo

**O site nunca fala com a internet; o pipeline nunca renderiza.** O pipeline é a única
coisa que acessa as fontes, e grava o snapshot cru *antes* de interpretar qualquer byte. O
site lê apenas `site/src/data/` e `site/public/dados/`. Isso é o que mantém o build
reprodutível quando um portal público sai do ar — o que acontece com frequência.

## Comandos

```bash
cd pipeline
uv run transporte-sp fetch [fonte...]   # snapshot cru datado em data/raw/
uv run transporte-sp build              # reconcilia -> data/dist/
uv run transporte-sp validate           # invariantes; falha o CI
uv run transporte-sp pages              # gera o conteúdo do site
uv run ruff check . && uv run pytest

cd site
npx astro check && npm run build
```

## Onde mexer

| Quero mudar | Mexo em |
|---|---|
| Qualquer URL, limiar, bbox, caminho | `pipeline/src/transporte_sp/config.py` — **fonte única**, nada disperso |
| Como uma fonte é lida | `pipeline/src/transporte_sp/sources/<fonte>.py` |
| Qual fonte ganha em qual campo | `pipeline/src/transporte_sp/merge/precedence.py` |
| Como estações são agrupadas entre fontes | `pipeline/src/transporte_sp/merge/matching.py` |
| O que aparece nas páginas de linha/estação | `pipeline/src/transporte_sp/export/pages.py` |
| Aparência, mapa, páginas fixas | `site/src/` |

## Armadilhas das fontes (custaram tempo, não repita)

- **`ref` de estação no OSM é a sigla oficial** (`VMD`, `BAS`), **não a linha**. Lê-lo como
  linha gruda a estação em qualquer linha que compartilhe o dígito.
- **Overpass responde `406` sem `User-Agent`** e devolve **HTTP 200 com XML de erro** quando
  está sobrecarregado. Toda resposta é validada como JSON e os mirrors são tentados em ordem.
- **GeoSampa entrega EPSG:31983 por padrão**; `srsName=EPSG:4326` faz o servidor reprojetar,
  e é por isso que o pipeline não precisa de biblioteca de projeção.
- **O GTFS da SPTrans tem trilhos**, ao contrário do que se repete — e é a única fonte que
  declara a ordem das estações. Falta nele: Linhas 6-Laranja e 17-Ouro.
- **GeoSampa para na divisa do município.** Um traçado dele mais curto que o do OSM é
  cobertura, não divergência, e não deve virar conflito.
- **`P81` do Wikidata erra a linha dos trens metropolitanos** (aponta para a ferrovia
  histórica). Referência de linha vinda de lá é pista, nunca atribuição.
- **O casamento de estações é transitivo** — sem um corte por raio, duas estações homônimas
  distantes acabam no mesmo cluster.
- **Wikidata: SPARQL por GET.** POST estoura timeout; `wdt:P131*` não funciona para a
  hierarquia administrativa, use `wikibase:around`.

## Invariantes

`transporte-sp validate` falha se: uma linha férrea tiver menos de duas estações; uma linha
em operação não tiver traçado; uma estação cair fora do bbox; um campo publicado não tiver
`source`; ou a associação estação↔linha for assimétrica. Também avisa quando as contagens
divergem em mais de 25% do que as fontes traziam quando cada adaptador foi escrito — sinal
de que a fonte mudou de forma, não de que a rede mudou.

## Fora de escopo, de propósito

Horários e previsão de chegada (não há GTFS-Realtime público em SP), tarifas, e as linhas de
ônibus municipais e metropolitanas.
