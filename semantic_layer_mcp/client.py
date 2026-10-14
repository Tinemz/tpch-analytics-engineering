"""Implementação local do ``SemanticLayerClientProtocol`` do dbt-mcp.

As três tools que passam pelo client (``query_metrics``, ``get_metrics_compiled_sql`` e
``get_dimension_values``) continuam herdando do dbt-mcp o parsing de ``order_by``, a
normalização do ``where`` e o formatter Arrow→JSON. Este módulo cobre três desencontros:

* ``explain()`` não expõe ``.sql``; o SQL sai em ``.sql_statement.sql``.
* ``get_dimension_values()`` devolve ``list[str]`` e o dbt-mcp espera um ``pa.Table``.
* Erro de query do MetricFlow não é ``QueryFailedError``. Sem tradução, ele chegaria ao
  agente como falha operacional, e não como dado que ele consegue ler e corrigir.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pyarrow as pa
from dbtsl.error import QueryFailedError
from dbtsl.models.query import QueryStatus

from . import naming
from .engine import SemanticLayerEngine, SemanticLayerUnavailableError


def _limit(requested: int | None) -> int | None:
    """Default quando o agente não passa ``limit`` e teto quando passa um exagerado.

    O LLM escolhe esse número sozinho, e no BigQuery cada scan é cobrado.
    """
    default = int(os.environ.get("SL_DEFAULT_QUERY_LIMIT", "5000")) or None
    cap = int(os.environ.get("SL_MAX_QUERY_LIMIT", "100000")) or None
    resolved = requested if requested is not None else default
    if cap is not None and (resolved is None or resolved > cap):
        return cap
    return resolved


def _to_arrow(data_table: Any) -> pa.Table:
    """``MetricFlowDataTable`` -> ``pa.Table``. O resultado mora em ``result_df``."""
    if data_table is None:
        return pa.table({})
    return pa.table(
        {
            name: list(data_table.column_values_iterator(idx))
            for idx, name in enumerate(data_table.column_names)
        }
    )


def as_query_failure(error: Exception) -> Exception:
    """Erro de query vira ``QueryFailedError``, que o dbt-mcp devolve ao agente como dado.

    ``SemanticLayerUnavailableError`` passa intacto: é o servidor fora, não a query ruim.
    """
    if isinstance(error, QueryFailedError | SemanticLayerUnavailableError):
        return error
    return QueryFailedError([str(error)], status=QueryStatus.FAILED.value)


class MetricFlowSemanticLayerClient:
    """Satisfaz ``SemanticLayerClientProtocol`` estruturalmente."""

    def __init__(self, engine: SemanticLayerEngine) -> None:
        self._engine = engine

    @contextmanager
    def session(self) -> Iterator[None]:
        """No-op: o cliente oficial abre conexões GraphQL e Arrow Flight aqui."""
        yield None

    def _context(
        self, metrics: list[str]
    ) -> tuple[list[naming.ResolvedDimension], set[str]]:
        engine = self._engine.metadata()
        dimensions = naming.collapse_dimensions(
            engine.simple_dimensions_for_metrics(metrics, without_any_property=())
        )
        entities = {e.name for e in engine.entities_for_metrics(metrics)}
        return dimensions, entities

    def _build_request(
        self,
        metrics: list[str],
        group_by: Any,
        order_by: Any,
        where: list[str] | None,
        limit: int | None,
    ) -> Any:
        """Resolve nomes antes de tocar o adapter: um nome errado não paga a montagem dele."""
        from metricflow.engine.metricflow_engine import MetricFlowQueryRequest

        try:
            dimensions, entities = self._context(metrics)
            group_by_names = [
                naming.resolve_group_by(
                    item if isinstance(item, str) else item.name,
                    None if isinstance(item, str) else item.grain,
                    dimensions,
                    entities,
                )
                for item in group_by or []
            ]
            order_by_names = [
                item
                if isinstance(item, str)
                else naming.resolve_order_by(
                    name=item.name,
                    grain=getattr(item, "grain", None),
                    descending=item.descending,
                    metric_names=set(metrics),
                    dimensions=dimensions,
                    entity_names=entities,
                )
                for item in order_by or []
            ]
            return MetricFlowQueryRequest.create(
                metric_names=metrics,
                group_by_names=group_by_names or None,
                order_by_names=order_by_names or None,
                where_constraints=list(where) if where else None,
                limit=_limit(limit),
            )
        except Exception as e:
            raise as_query_failure(e) from e

    def query(
        self,
        metrics: list[str],
        group_by: Any = None,
        limit: int | None = None,
        order_by: Any = None,
        where: list[str] | None = None,
        read_cache: bool = True,
    ) -> pa.Table:
        request = self._build_request(metrics, group_by, order_by, where, limit)
        with self._engine.querying() as engine:
            try:
                result = engine.query(request)
            except Exception as e:
                raise as_query_failure(e) from e
        return _to_arrow(result.result_df)

    def compile_sql(
        self,
        metrics: list[str],
        group_by: Any = None,
        limit: int | None = None,
        order_by: Any = None,
        where: list[str] | None = None,
        read_cache: bool = True,
    ) -> str:
        """``sql_statement`` levanta ``NotImplementedError`` quando o plano tem mais de uma etapa."""
        request = self._build_request(metrics, group_by, order_by, where, limit)
        with self._engine.querying() as engine:
            try:
                return engine.explain(request).sql_statement.sql
            except NotImplementedError as e:
                raise QueryFailedError(
                    [
                        "Esta consulta compila para mais de uma etapa e não tem um SQL único. "
                        "Simplifique (menos métricas, ou um group by de cada vez)."
                    ],
                    status=QueryStatus.FAILED.value,
                ) from e
            except Exception as e:
                raise as_query_failure(e) from e

    def dimension_values(self, metrics: list[str], group_by: str) -> pa.Table:
        """O dbt-mcp procura a coluna pelo nome da dimensão e trunca do lado dele."""
        try:
            dimensions, entities = self._context(metrics or [])
            resolved = naming.resolve_group_by(
                group_by, None, dimensions, entities, fallback_to_finest_grain=True
            )
        except Exception as e:
            raise as_query_failure(e) from e
        with self._engine.querying() as engine:
            try:
                values = engine.get_dimension_values(
                    metric_names=metrics or [], get_group_by_values=resolved
                )
            except Exception as e:
                raise as_query_failure(e) from e
        return pa.table({group_by: [str(v) for v in values]})


class MetricFlowClientProvider:
    """Provider no formato que o ``SemanticLayerFetcher`` espera."""

    def __init__(self, engine: SemanticLayerEngine) -> None:
        self._client = MetricFlowSemanticLayerClient(engine)

    async def get_client(self, *, config: Any) -> MetricFlowSemanticLayerClient:
        return self._client
