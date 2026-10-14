"""Testes offline: leem o semantic_manifest.json, sem BigQuery e sem credencial.

Rodar ``dbt parse`` em ``tpch/`` antes, para que o manifest seja o do código atual.
"""

import asyncio
from pathlib import Path

import pytest

from semantic_layer_mcp.client import MetricFlowSemanticLayerClient
from semantic_layer_mcp.engine import SemanticLayerEngine
from semantic_layer_mcp.fetcher import MetricFlowFetcher
from semantic_layer_mcp.server import build_config, create_server

PROJECT = Path(__file__).resolve().parents[2] / "tpch"


@pytest.fixture(scope="module")
def engine() -> SemanticLayerEngine:
    engine = SemanticLayerEngine(project_path=PROJECT, profiles_path=PROJECT)
    engine.load()
    return engine


def _metric_names(engine: SemanticLayerEngine) -> list[str]:
    return [m.name for m in engine.metadata().list_metrics(include_dimensions=False)]


def test_tools_nao_expoem_context_ao_llm(engine: SemanticLayerEngine) -> None:
    """Trava a injeção: com anotação adiada no server.py, ``context`` vira parâmetro do LLM."""
    tools = asyncio.run(create_server(engine).list_tools())
    assert len(tools) == 7
    for tool in tools:
        assert "context" not in tool.inputSchema.get("properties", {}), tool.name


def test_toda_dimensao_listada_volta_como_group_by(engine: SemanticLayerEngine) -> None:
    """Todo nome servido por ``get_dimensions`` precisa ser aceito no ``query_metrics``.

    Métrica nova que quebre a resolução de nomes falha aqui, não no agente.
    """
    fetcher = MetricFlowFetcher(engine)
    client = MetricFlowSemanticLayerClient(engine)
    for metric in _metric_names(engine):
        dims = asyncio.run(fetcher.get_dimensions(build_config(), [metric]))
        for dim in dims:
            grains = dim.granularities or [None]
            for grain in grains:
                group_by = [type("G", (), {"name": dim.name, "grain": grain})()]
                client._build_request([metric], group_by, None, None, None)


def test_receita_carrega_a_regra_do_primeiro_digito(engine: SemanticLayerEngine) -> None:
    """A regra de negócio mora na camada semântica, não em quem consome a métrica."""
    metric = next(
        m
        for m in engine.metadata().list_metrics(include_dimensions=False)
        if m.name == "receita"
    )
    sql = [f.where_sql_template for f in metric.filter.where_filters]
    assert any("order_id__order_id_first_digit" in s and "'1'" in s for s in sql)
