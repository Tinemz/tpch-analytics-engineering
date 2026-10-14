"""Fetcher respaldado em MetricFlow.

No ``SemanticLayerFetcher`` do dbt-mcp, três métodos passam pelo ``client_provider`` e quatro
fazem GraphQL direto contra o dbt Platform. Só os quatro de GraphQL são sobrescritos; os outros
três herdam o comportamento upstream inteiro.

Cada método sobrescrito despacha o trabalho com ``asyncio.to_thread``, como os herdados fazem: a
primeira chamada lê o manifest do disco, e isso não pode rodar no event loop.
"""

from __future__ import annotations

import asyncio
from typing import Any

from dbt_mcp.config.config_providers import SemanticLayerConfig
from dbt_mcp.semantic_layer.client import SemanticLayerFetcher
from dbt_mcp.semantic_layer.types import (
    DimensionToolResponse,
    EntityToolResponse,
    ListMetricsResponse,
    MetricToolResponse,
    SavedQueryToolResponse,
)

from . import naming
from .client import MetricFlowClientProvider
from .engine import SemanticLayerEngine


def _meta(obj: Any) -> dict[str, Any] | None:
    config = getattr(obj, "config", None)
    return (getattr(config, "meta", None) or None) if config else None


class MetricFlowFetcher(SemanticLayerFetcher):
    """Sobrescreve os quatro métodos de metadados; herda os três que usam o client."""

    def __init__(self, engine: SemanticLayerEngine) -> None:
        super().__init__(client_provider=MetricFlowClientProvider(engine))  # type: ignore[arg-type]
        self._sl_engine = engine

    async def list_metrics(
        self, config: SemanticLayerConfig, search: str | list[str] | None = None
    ) -> ListMetricsResponse:
        return await asyncio.to_thread(self._list_metrics, config, search)

    def _list_metrics(
        self, config: SemanticLayerConfig, search: str | list[str] | None
    ) -> ListMetricsResponse:
        """Só enriquece com dimensões e entidades quando o conjunto é pequeno, como o upstream."""
        engine = self._sl_engine.metadata()
        terms = [search] if isinstance(search, str) else (search or [None])
        metrics = sorted(
            (
                m
                for m in engine.list_metrics(include_dimensions=False)
                if any(
                    naming.matches_search(field, t)
                    for t in terms
                    for field in (m.name, m.label, m.description)
                )
            ),
            key=lambda m: m.name,
        )
        include_related = 0 < len(metrics) <= config.metrics_related_max

        responses = []
        for metric in metrics:
            dimensions = entities = None
            if include_related:
                dimensions = [
                    d.name
                    for d in naming.collapse_dimensions(
                        engine.simple_dimensions_for_metrics(
                            [metric.name], without_any_property=()
                        )
                    )
                ]
                entities = sorted(
                    {e.name for e in engine.entities_for_metrics([metric.name])}
                )
            responses.append(
                MetricToolResponse(
                    name=metric.name,
                    type=naming.map_metric_type_name(metric.type),  # type: ignore[arg-type]
                    label=metric.label,
                    description=metric.description,
                    metadata=_meta(metric),
                    dimensions=dimensions,
                    entities=entities,
                )
            )
        return ListMetricsResponse(metrics=responses)

    async def get_dimensions(
        self, config: SemanticLayerConfig, metrics: list[str], search: str | None = None
    ) -> list[DimensionToolResponse]:
        return await asyncio.to_thread(self._get_dimensions, metrics, search)

    def _get_dimensions(
        self, metrics: list[str], search: str | None
    ) -> list[DimensionToolResponse]:
        key = (",".join(sorted(metrics)), search)
        if key not in self.dimensions_cache:
            resolved = naming.collapse_dimensions(
                self._sl_engine.metadata().simple_dimensions_for_metrics(
                    metrics, without_any_property=()
                )
            )
            self.dimensions_cache[key] = [
                DimensionToolResponse(
                    name=d.name,
                    type=d.type,
                    description=d.description,
                    label=d.label,
                    granularities=d.granularities or None,
                )
                for d in resolved
                if naming.matches_search(d.name, search)
                or naming.matches_search(d.description, search)
            ]
        return self.dimensions_cache[key]

    async def get_entities(
        self, config: SemanticLayerConfig, metrics: list[str], search: str | None = None
    ) -> list[EntityToolResponse]:
        return await asyncio.to_thread(self._get_entities, metrics, search)

    def _get_entities(
        self, metrics: list[str], search: str | None
    ) -> list[EntityToolResponse]:
        """Deduplica por nome: o engine devolve uma entrada por semantic model que declara a
        entidade, e ``customer_id`` aparece em ``fct_orders`` e em ``dim_customer``."""
        key = (",".join(sorted(metrics)), search)
        if key not in self.entities_cache:
            seen: dict[str, EntityToolResponse] = {}
            for e in self._sl_engine.metadata().entities_for_metrics(metrics):
                if e.name in seen or not (
                    naming.matches_search(e.name, search)
                    or naming.matches_search(e.description, search)
                ):
                    continue
                seen[e.name] = EntityToolResponse(
                    name=e.name,
                    type=naming.map_entity_type(e.type),
                    description=e.description,
                )
            self.entities_cache[key] = sorted(seen.values(), key=lambda x: x.name)
        return self.entities_cache[key]

    async def list_saved_queries(
        self, config: SemanticLayerConfig, search: str | None = None
    ) -> list[SavedQueryToolResponse]:
        return await asyncio.to_thread(self._list_saved_queries, search)

    def _list_saved_queries(self, search: str | None) -> list[SavedQueryToolResponse]:
        results = []
        for sq in self._sl_engine.metadata().list_saved_queries():
            if not (
                naming.matches_search(sq.name, search)
                or naming.matches_search(sq.description, search)
            ):
                continue
            params = sq.query_params
            where = [
                f.where_sql_template
                for f in (getattr(params.where, "where_filters", None) or [])
            ]
            results.append(
                SavedQueryToolResponse(
                    name=sq.name,
                    label=sq.label,
                    description=sq.description,
                    metrics=[str(m) for m in params.metrics or []],
                    group_by=[str(g) for g in params.group_by or []],
                    where=" AND ".join(f"({w})" for w in where) if where else None,
                )
            )
        return results
