"""Tradução entre o vocabulário do dbt-mcp (tipos do ``dbtsl``) e o do MetricFlow.

Quatro regras mantêm o servidor genérico, sem código novo por métrica ou dimensão:

R1  O nome exposto é o ``dunder_name`` (``customer_id__region_name``). O ``name`` puro pode
    repetir entre semantic models, e só o dunder volta resolvível no ``group_by``.
R2  Dimensão de tempo é colapsada pelo ``granularity_free_dunder_name``: ``metric_time`` vira
    uma entrada com ``granularities=[DAY, MONTH, ...]`` em vez de cinco linhas.
R3  ``group_by``/``order_by`` resolvem por lookup no conjunto real de nomes, com a grain em
    minúsculo. O prompt do dbt-mcp ensina ``"MONTH"``; o MetricFlow quer ``metric_time__month``.
R4  Enum mapeia pelo nome do membro, com fallback para ``UNKNOWN``: o MetricFlow usa
    ``'categorical'`` e o ``dbtsl`` ``'CATEGORICAL'``.

Não importa o engine nem toca o warehouse, para poder ser testado offline.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

from dbtsl.models.dimension import DimensionType as SlDimensionType
from dbtsl.models.entity import EntityType as SlEntityType
from dbtsl.models.metric import MetricType as SlMetricType

SlEnum = TypeVar("SlEnum", bound=Enum)

GRAIN_ORDER = ("DAY", "WEEK", "MONTH", "QUARTER", "YEAR")
"""Do mais fino ao mais grosso. Explícito porque a ordem alfabética não é a temporal."""


def map_enum(mf_member: Any, sl_enum: type[SlEnum]) -> SlEnum:
    """R4."""
    name = getattr(mf_member, "name", None) or str(mf_member or "")
    try:
        return sl_enum[name.upper()]
    except KeyError:
        return sl_enum["UNKNOWN"]


def map_dimension_type(mf_type: Any) -> SlDimensionType:
    return map_enum(mf_type, SlDimensionType)


def map_entity_type(mf_type: Any) -> SlEntityType:
    return map_enum(mf_type, SlEntityType)


def map_metric_type_name(mf_type: Any) -> str:
    """String, não membro: o ``list_metrics`` vira CSV com ``str(val)``, que daria
    ``"MetricType.SIMPLE"``."""
    return map_enum(mf_type, SlMetricType).name


@dataclass(frozen=True)
class ResolvedDimension:
    """Uma dimensão como o agente a enxerga, já colapsada (R1 + R2)."""

    name: str
    type: SlDimensionType
    description: str | None = None
    label: str | None = None
    granularities: list[str] = field(default_factory=list)
    grain_to_dunder: dict[str, str] = field(default_factory=dict)
    bare_is_queryable: bool = True
    """Falso para ``metric_time``, que só existe com sufixo de grain."""


def collapse_dimensions(mf_dimensions: Any) -> list[ResolvedDimension]:
    """R1 + R2. Os metadados vêm da primeira entrada do grupo, a que carrega a descrição."""
    grouped: dict[str, list[Any]] = {}
    for dim in mf_dimensions:
        grouped.setdefault(dim.granularity_free_dunder_name, []).append(dim)

    resolved: list[ResolvedDimension] = []
    for base, dims in grouped.items():
        grain_to_dunder: dict[str, str] = {}
        bare = False
        for dim in dims:
            if dim.dunder_name == base:
                bare = True
            else:
                grain_to_dunder[dim.dunder_name[len(base) + 2 :].upper()] = dim.dunder_name
        first = dims[0]
        resolved.append(
            ResolvedDimension(
                name=base,
                type=map_dimension_type(first.type),
                description=first.description,
                label=first.label,
                granularities=[g for g in GRAIN_ORDER if g in grain_to_dunder]
                + sorted(g for g in grain_to_dunder if g not in GRAIN_ORDER),
                grain_to_dunder=grain_to_dunder,
                bare_is_queryable=bare or not grain_to_dunder,
            )
        )
    return sorted(resolved, key=lambda d: d.name)


class UnknownGroupByError(ValueError):
    """Nome de group_by que não existe para as métricas pedidas. A mensagem lista os válidos."""


def resolve_group_by(
    name: str,
    grain: str | None,
    dimensions: list[ResolvedDimension],
    entity_names: set[str],
    *,
    fallback_to_finest_grain: bool = False,
) -> str:
    """R3. Ordem: entidade, dimensão colapsada, nome já com sufixo de grain.

    ``fallback_to_finest_grain`` serve ao ``get_dimension_values``, que não tem parâmetro de
    grain no schema do dbt-mcp e senão nunca conseguiria consultar ``metric_time``.
    """
    if name in entity_names and grain is None:
        return name

    by_name = {d.name: d for d in dimensions}
    dim = by_name.get(name)
    if dim is None:
        if any(name in d.grain_to_dunder.values() for d in dimensions):
            return name
        valid = ", ".join(sorted(by_name) + sorted(entity_names))
        raise UnknownGroupByError(
            f"Group by '{name}' não existe para estas métricas. Válidos: {valid}"
        )

    if grain:
        if grain.upper() in dim.grain_to_dunder:
            return dim.grain_to_dunder[grain.upper()]
        if dim.type is SlDimensionType.TIME:
            return f"{dim.name}__{grain.lower()}"
        raise UnknownGroupByError(f"Dimensão '{name}' não é de tempo; remova o `grain`.")

    if dim.bare_is_queryable:
        return dim.name
    if fallback_to_finest_grain and dim.granularities:
        return dim.grain_to_dunder[dim.granularities[0]]
    raise UnknownGroupByError(
        f"Dimensão '{name}' exige `grain`. Disponíveis: {', '.join(dim.granularities)}"
    )


def resolve_order_by(
    name: str,
    grain: str | None,
    descending: bool,
    metric_names: set[str],
    dimensions: list[ResolvedDimension],
    entity_names: set[str],
) -> str:
    """R3 aplicado a ``order_by``, com o prefixo ``-`` que o MetricFlow usa para descendente."""
    resolved = (
        name
        if name in metric_names
        else resolve_group_by(name, grain, dimensions, entity_names)
    )
    return f"-{resolved}" if descending else resolved


def _normalize(text: str) -> str:
    """Sem caixa e sem acento: "Receita líquida" casa com "receita liquida"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def matches_search(haystack: str | None, search: str | None) -> bool:
    """Busca client-side: nenhum método do MetricFlow aceita ``search``."""
    if not search:
        return True
    return bool(haystack) and _normalize(search) in _normalize(haystack)
