# Servidor MCP da camada semântica, para o Cloud Run.
#
# O semantic_manifest.json é gerado aqui, no build, com o target prod: a imagem
# carrega as definições de métrica do commit que a gerou e consulta as tabelas
# de produção. O parse não conecta no BigQuery, então o build não precisa de
# credencial.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY tpch/requirements.txt tpch/requirements.txt
COPY semantic_layer_mcp/requirements.txt semantic_layer_mcp/requirements.txt
RUN pip install -r semantic_layer_mcp/requirements.txt

COPY tpch tpch
COPY semantic_layer_mcp semantic_layer_mcp
COPY tpch/deploy/profiles.mcp.yml profiles/profiles.yml

ENV DBT_PROJECT_DIR=/app/tpch \
    DBT_PROFILES_DIR=/app/profiles \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    MCP_TRANSPORT=http \
    LOG_LEVEL=WARNING \
    MF_LOG_LEVEL=WARNING

RUN cd tpch && dbt parse --target prod && test -f target/semantic_manifest.json

# Roda como usuário sem privilégio.
RUN useradd --uid 10001 --no-create-home app && chown -R app /app
USER app

CMD ["python", "-m", "semantic_layer_mcp.server"]
