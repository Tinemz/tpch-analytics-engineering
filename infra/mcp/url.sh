#!/usr/bin/env bash
# Imprime a URL completa do servidor MCP, com a chave no caminho. É ela que vai no
# conector personalizado do claude.ai e no `claude mcp add`. Trate como senha.
set -euo pipefail
PROJECT="${PROJECT:-dbt-learning-tinem}"
REGION="${REGION:-us-central1}"
base="$(gcloud run services describe tpch-semantic-layer --project "$PROJECT" --region "$REGION" --format='value(status.url)')"
secret="$(gcloud secrets versions access latest --secret tpch-mcp-path-secret --project "$PROJECT")"
printf '%s/mcp/%s\n' "$base" "$secret"
