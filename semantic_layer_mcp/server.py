"""Servidor MCP da camada semântica, respaldado em MetricFlow local contra o BigQuery.

Registra as mesmas sete tools do dbt-mcp, com os mesmos prompts, schemas e nomes. O agente não
distingue este servidor de um apontado para o dbt Platform; muda só o objeto que atende as
chamadas.

O ponto de injeção é o ``semantic_layer_fetcher`` do contexto: as sete tools passam por ele
(``dbt_mcp/semantic_layer/tools.py``). O ``register_sl_tools`` upstream monta o próprio contexto
e não aceita um fetcher, então chamamos o ``register_tools`` que está por baixo dele.

**Não adicionar ``from __future__ import annotations`` a este módulo.** O ``adapt_with_mapper``
do dbt-mcp casa o parâmetro de contexto comparando ``param.annotation == mapper_return_type``.
Com anotações adiadas, a anotação de ``bind_context`` vira string, a comparação falha em
silêncio e as tools passam a expor ``context`` como parâmetro para o LLM.
"""

import logging
import os

from dbt_mcp.config.config_providers import SemanticLayerConfig, StaticConfigProvider
from dbt_mcp.semantic_layer.tools import SEMANTIC_LAYER_TOOLS, SemanticLayerToolContext
from dbt_mcp.tools.register import register_tools
from mcp.server.fastmcp import FastMCP

from .engine import SemanticLayerEngine, build_engine
from .fetcher import MetricFlowFetcher

_UNUSED = "local-metricflow"


class _StubTokenProvider:
    """Nunca chamado: só o caminho GraphQL do upstream lê token."""

    def get_token(self) -> str:
        return _UNUSED


class _StubHeadersProvider:
    def get_headers(self) -> dict[str, str]:
        return {}


def build_config() -> SemanticLayerConfig:
    """Config que as tools exigem. Só ``metrics_related_max`` e ``max_response_chars`` são lidos."""
    return SemanticLayerConfig(
        url=_UNUSED,
        host=_UNUSED,
        prod_environment_id=1,
        token_provider=_StubTokenProvider(),  # type: ignore[arg-type]
        headers_provider=_StubHeadersProvider(),  # type: ignore[arg-type]
        metrics_related_max=int(os.environ.get("SL_METRICS_RELATED_MAX", "10")),
        max_response_chars=int(os.environ.get("SL_MAX_RESPONSE_CHARS", "16000")),
    )


class LocalSemanticLayerContext(SemanticLayerToolContext):
    """Mesmo contexto do dbt-mcp com o fetcher trocado. Não chama ``super()``, que construiria
    um fetcher apontado para o dbt Platform."""

    def __init__(
        self,
        config_provider: StaticConfigProvider[SemanticLayerConfig],
        fetcher: MetricFlowFetcher,
    ) -> None:
        self.config_provider = config_provider
        self.semantic_layer_fetcher = fetcher


def create_server(engine: SemanticLayerEngine | None = None) -> FastMCP:
    """Monta o servidor. ``engine`` existe para os testes injetarem um engine offline.

    A anotação de retorno de ``bind_context`` é a classe base de propósito, mesmo devolvendo a
    subclasse: é com ela que o ``adapt_with_mapper`` compara.
    """
    engine = engine or build_engine()
    config_provider = StaticConfigProvider(build_config())
    fetcher = MetricFlowFetcher(engine)

    def bind_context() -> SemanticLayerToolContext:
        return LocalSemanticLayerContext(config_provider, fetcher)

    mcp = FastMCP(
        name="tpch-semantic-layer",
        instructions=(
            "Camada semântica do projeto tpch (TPC-H no BigQuery), servida por MetricFlow. "
            "Use list_metrics para descobrir métricas, get_dimensions para os agrupamentos "
            "válidos e query_metrics para consultar. As métricas carregam regras de negócio "
            "próprias: use a definição da camada, nunca recalcule a partir das tabelas."
        ),
    )
    register_tools(
        mcp,
        [tool.adapt_context(bind_context) for tool in SEMANTIC_LAYER_TOOLS],
        disabled_tools=set(),
        enabled_tools=None,
        enabled_toolsets=set(),
        disabled_toolsets=set(),
    )
    return mcp


def quiet_metricflow_logs() -> None:
    """O MetricFlow loga cada etapa do plano em INFO, dezenas de linhas por query."""
    for name in ("metricflow", "metricflow_semantics", "dbt_metricflow", "dbt"):
        logging.getLogger(name).setLevel(os.environ.get("MF_LOG_LEVEL", "WARNING"))


def main() -> None:
    """Sobe em stdio. Todo log vai para stderr: em stdio o stdout é o canal JSON-RPC."""
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    quiet_metricflow_logs()
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
