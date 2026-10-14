# Servidor MCP da camada semântica

Serve as métricas do projeto `tpch` para agentes via MCP, usando o MetricFlow local contra o
BigQuery, sem dbt Platform. Um agente pergunta "receita por região" e recebe o número que a
camada semântica define: a regra mora no YAML, não em quem consulta.

## O problema

As sete ferramentas de camada semântica do [`dbt-mcp`](https://github.com/dbt-labs/dbt-mcp)
(`list_metrics`, `get_dimensions`, `get_entities`, `list_saved_queries`, `query_metrics`,
`get_metrics_compiled_sql`, `get_dimension_values`) falam com o dbt Platform: Arrow Flight SQL
para executar e GraphQL para metadados, com `DBT_HOST` + `DBT_TOKEN` obrigatórios. Não há
caminho para dbt Core.

## Como funciona

Não é um fork. O `dbt-mcp` segue como dependência e o servidor troca um único objeto: todas as
sete tools passam por `context.semantic_layer_fetcher`, então substituir esse atributo troca o
backend inteiro sem tocar em nome, schema ou prompt de ferramenta. O agente não distingue este
servidor de um apontado para o dbt Platform.

```
FastMCP
 └── LocalSemanticLayerContext          server.py   contexto com o fetcher trocado
       └── MetricFlowFetcher            fetcher.py  4 tools de metadados (eram GraphQL)
             └── MetricFlowSemanticLayerClient  client.py  3 tools que emitem SQL
                   └── SemanticLayerEngine      engine.py  MetricFlowEngine + dbt-bigquery
```

| Arquivo | Responsabilidade |
|---|---|
| `engine.py` | Carga em dois estágios e lock de execução |
| `client.py` | `SemanticLayerClientProtocol`: query, SQL compilado, valores de dimensão |
| `fetcher.py` | As quatro tools de metadados |
| `naming.py` | Tradução de nomes e enums entre `dbtsl` e MetricFlow |
| `server.py` | Registro das tools e entrypoint stdio |

**Carga em dois estágios.** Metadados vêm só do `tpch/target/semantic_manifest.json`, sem rede
nem credencial. O adapter do BigQuery é montado na primeira chamada que emite SQL. Explorar
métricas nunca depende do warehouse.

**Fusion gera, dbt-core consome.** O manifest sai do `dbt parse` do dbt Fusion. O adapter vem
do dbt-core + dbt-bigquery deste ambiente, que lê só o `dbt_project.yml` e o `profiles.yml`,
sem reparsear o projeto. Uma diferença entre os dois mordeu: o dbt-core reescreve
`agg: count` para `sum` durante o parse e o Fusion não, e o MetricFlow recusa `count` cru.
Por isso as métricas de contagem são `agg: sum` com `expr: "1"`.

**Erro de query volta como dado.** Group by inexistente ou SQL inválido chegam ao agente como
mensagem com os nomes válidos, para ele corrigir. Só "o servidor não está em pé" propaga como
falha operacional.

## Rodar

Python 3.12, a partir da raiz do repositório:

```bash
uv venv --python 3.12 .venv-sl
VIRTUAL_ENV=.venv-sl uv pip install -r semantic_layer_mcp/requirements.txt
(cd tpch && dbt parse)
```

Testes, offline:

```bash
PYTHONPATH=. .venv-sl/bin/pytest semantic_layer_mcp/tests -q
```

Registrar no Claude Code (stdio). A autenticação é a do `profiles.yml` do projeto: OAuth via
`gcloud auth application-default login`, sem chave de service account.

```bash
claude mcp add tpch-semantic-layer --scope user -e PYTHONPATH=$(pwd) -e LOG_LEVEL=WARNING -- $(pwd)/.venv-sl/bin/python -m semantic_layer_mcp.server
```

| Variável | Default | Observação |
|---|---|---|
| `DBT_PROJECT_DIR` | `tpch/` ao lado do pacote | Projeto dbt |
| `DBT_PROFILES_DIR` | `~/.dbt` | Onde está o `profiles.yml` |
| `SL_DEFAULT_QUERY_LIMIT` | `5000` | Teto quando o agente não passa `limit`. `0` desliga |
| `SL_MAX_QUERY_LIMIT` | `100000` | Teto absoluto, também para `limit` explícito |
| `MF_LOG_LEVEL` | `WARNING` | Log do MetricFlow, que em INFO escreve o plano inteiro |

**Qual ambiente ele lê** é decidido pelo manifest, não pelo servidor: as tabelas de cada
semantic model saem do target usado no `dbt parse`. Com o `dev` do profile, são as de
`tpch_dev_marts`.

## A métrica `receita`

Existe para demonstrar que quem consome a camada não define a métrica. `receita` soma a receita
líquida **apenas dos pedidos cujo `order_id` começa com 1**: o filtro está em
`tpch/models/marts/_fct_orders.yml` e vai no SQL que o MetricFlow compila. Um dashboard ou um
agente que pede "receita" recebe esse número, e não um `SUM` direto da tabela.

## Antes de subir a versão do dbt-mcp

O servidor importa símbolos internos (`SemanticLayerFetcher`, `SemanticLayerToolContext`,
`register_tools`), porque o dbt-mcp não oferece API de extensão. A versão é pinada exata. Para
subir: atualize o pin, rode os testes e confira o diff de `dbt_mcp/semantic_layer/` e
`dbt_mcp/tools/`. Não adicione `from __future__ import annotations` ao `server.py`: a injeção de
contexto do dbt-mcp compara anotações por igualdade e falha em silêncio com anotações adiadas
(há teste travando isso).
