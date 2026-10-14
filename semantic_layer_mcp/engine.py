"""Ciclo de vida do MetricFlowEngine, em dois estágios.

A CLI do dbt-metricflow monta tudo de uma vez: profile, adapter e manifest. Aqui isso é
partido em dois, para que explorar métricas nunca dependa do warehouse.

**Estágio 1, metadados.** Lê ``target/semantic_manifest.json`` do disco e monta um
``MetricFlowEngine`` com ``sql_client=None``. Basta para ``list_metrics``, ``get_dimensions``,
``get_entities`` e ``list_saved_queries``: sem rede, sem profile, sem credencial.

**Estágio 2, adapter.** Montado na primeira chamada que precisa emitir SQL. O
``dbtProjectMetadata`` do dbt-metricflow lê só o ``dbt_project.yml`` e o ``profiles.yml``, sem
parsear o projeto, então o manifest pode vir do dbt Fusion e o adapter do dbt-core.

**Concorrência.** O dbt-mcp despacha cada tool com ``asyncio.to_thread``. Nem o engine nem a
conexão do adapter são comprovadamente thread-safe, então tudo que emite SQL passa por um lock.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SemanticLayerUnavailableError(RuntimeError):
    """O servidor não consegue atender: manifest ausente ou adapter que não monta.

    Separado de propósito do erro de query. O ``client`` devolve erro de query ao agente como
    dado, para ele corrigir e tentar de novo; este aqui propaga como falha operacional.
    """


class SemanticLayerEngine:
    """Dono do MetricFlowEngine de metadados, do de query e do lock."""

    def __init__(self, project_path: Path, profiles_path: Path) -> None:
        self._project_path = project_path
        self._profiles_path = profiles_path
        self._lock = threading.Lock()
        self._lookup: Any = None
        self._metadata_engine: Any = None
        self._query_engine: Any = None

    @property
    def manifest_path(self) -> Path:
        return self._project_path / "target" / "semantic_manifest.json"

    def load(self) -> None:
        """Estágio 1. Relê o manifest e descarta o engine de query, que pode estar defasado."""
        from metricflow.engine.metricflow_engine import MetricFlowEngine
        from metricflow_semantic_interfaces.implementations.semantic_manifest import (
            PydanticSemanticManifest,
        )
        from metricflow_semantics.model.semantic_manifest_lookup import (
            SemanticManifestLookup,
        )

        if not self.manifest_path.exists():
            raise SemanticLayerUnavailableError(
                f"semantic_manifest.json não encontrado em {self.manifest_path}. "
                "Rode `dbt parse` no projeto."
            )
        manifest = PydanticSemanticManifest.parse_raw(self.manifest_path.read_text())
        with self._lock:
            self._lookup = SemanticManifestLookup(manifest)
            self._metadata_engine = MetricFlowEngine(
                semantic_manifest_lookup=self._lookup, sql_client=None
            )
            self._query_engine = None
        logger.info(
            "Manifest carregado: %d métricas, %d semantic models.",
            len(manifest.metrics),
            len(manifest.semantic_models),
        )

    def metadata(self) -> Any:
        """Engine de metadados. Carrega sob demanda na primeira chamada."""
        if self._metadata_engine is None:
            self.load()
        return self._metadata_engine

    def _ensure_query_engine(self) -> Any:
        """Estágio 2. Idempotente; chamar com o lock já adquirido."""
        if self._query_engine is not None:
            return self._query_engine

        from dbt_metricflow.cli.dbt_connectors.adapter_backed_client import (
            AdapterBackedSqlClient,
        )
        from dbt_metricflow.cli.dbt_connectors.dbt_config_accessor import (
            dbtArtifacts,
            dbtProjectMetadata,
        )
        from metricflow.engine.metricflow_engine import MetricFlowEngine

        try:
            metadata = dbtProjectMetadata.load_from_paths(
                profiles_path=self._profiles_path, project_path=self._project_path
            )
            artifacts = dbtArtifacts.load_from_project_metadata(metadata)
        except Exception as e:
            raise SemanticLayerUnavailableError(
                f"Não foi possível montar o adapter do dbt: {e}. "
                "Metadados continuam consultáveis."
            ) from e

        self._query_engine = MetricFlowEngine(
            semantic_manifest_lookup=self._lookup,
            sql_client=AdapterBackedSqlClient(artifacts.adapter),
        )
        logger.info("Adapter montado.")
        return self._query_engine

    @contextmanager
    def querying(self) -> Iterator[Any]:
        """Engine que emite SQL, segurando o lock durante o uso."""
        self.metadata()
        with self._lock:
            yield self._ensure_query_engine()


def build_engine() -> SemanticLayerEngine:
    """Constrói a partir do ambiente.

    ``DBT_PROJECT_DIR`` aponta para o projeto dbt (default: ``tpch/`` ao lado deste pacote) e
    ``DBT_PROFILES_DIR`` para o diretório do ``profiles.yml`` (default: ``~/.dbt``, o mesmo que
    o dbt usa).
    """
    default_project = Path(__file__).resolve().parent.parent / "tpch"
    project_path = Path(os.environ.get("DBT_PROJECT_DIR", default_project)).resolve()
    profiles_path = Path(
        os.environ.get("DBT_PROFILES_DIR", Path.home() / ".dbt")
    ).expanduser().resolve()
    return SemanticLayerEngine(project_path=project_path, profiles_path=profiles_path)
