#!/usr/bin/env bash
# Prepara o GCP para o servidor MCP da camada semântica e faz o primeiro deploy.
# Rodar uma vez, da raiz do repositório, logado no gcloud como dono do projeto:
#
#   bash infra/mcp/setup_gcp.sh
#
# Pode rodar de novo: cada passo confere se já foi feito. Depois disso, os deploys
# seguintes saem do CD a cada merge na main.
#
# O que fica criado, e por quê:
#   - Conta de serviço mcp-semantic-layer: só lê tpch_prod_marts e tpch_prod_utils.
#   - Secret tpch-mcp-path-secret: a chave que vai no caminho da URL. Gerada aqui e
#     nunca impressa; para ver a URL completa, use infra/mcp/url.sh.
#   - Cloud Run tpch-semantic-layer: escala até zero, no máximo 2 instâncias.
#   - Cota de BigQuery: cada identidade lê no máximo 30 GiB por dia no projeto.
#   - Alerta de orçamento: e-mail quando o gasto do mês passar do limite.
set -euo pipefail

PROJECT="${PROJECT:-dbt-learning-tinem}"
REGION="${REGION:-us-central1}"
SERVICE="tpch-semantic-layer"
SA_NAME="mcp-semantic-layer"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
SECRET="tpch-mcp-path-secret"
# Conta de serviço da CI/CD (a do secret GCP_SA_KEY), que passa a fazer o deploy.
CD_SA="${CD_SA:-fintech-pipeline-sa@${PROJECT}.iam.gserviceaccount.com}"
QUERY_MIB_PER_USER_DAY="${QUERY_MIB_PER_USER_DAY:-30720}"   # 30 GiB
BUDGET="${BUDGET:-5}"
CURRENCY="${CURRENCY:-BRL}"

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
step() { printf '\n== %s\n' "$*"; }

step "APIs"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com secretmanager.googleapis.com cloudquotas.googleapis.com \
  billingbudgets.googleapis.com --project "$PROJECT"

step "Conta de serviço do servidor: $SA"
if ! gcloud iam service-accounts describe "$SA" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SA_NAME" --project "$PROJECT" \
    --display-name "MCP da camada semântica (Cloud Run)" \
    --description "Só lê tpch_prod_marts e tpch_prod_utils para o servidor MCP"
  sleep 10   # a conta leva alguns segundos para aparecer no IAM
fi
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SA" \
  --role roles/bigquery.jobUser --condition=None --format=none

step "Leitura só nos datasets que a camada semântica usa"
for ds in tpch_prod_marts tpch_prod_utils; do
  tmp="$(mktemp)"
  bq show --format=prettyjson "$PROJECT:$ds" > "$tmp"
  python3 - "$tmp" "$SA" <<'EOF'
import json, sys
path, sa = sys.argv[1], sys.argv[2]
access = json.load(open(path)).get("access", [])
if not any(a.get("userByEmail") == sa for a in access):
    access.append({"role": "READER", "userByEmail": sa})
json.dump({"access": access}, open(path, "w"))
EOF
  bq update --source "$tmp" "$PROJECT:$ds" >/dev/null
  rm -f "$tmp"
  echo "READER em $ds"
done

step "Chave do caminho da URL (Secret Manager)"
if ! gcloud secrets describe "$SECRET" --project "$PROJECT" >/dev/null 2>&1; then
  python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")' \
    | gcloud secrets create "$SECRET" --project "$PROJECT" \
        --replication-policy automatic --data-file=-
fi
gcloud secrets add-iam-policy-binding "$SECRET" --project "$PROJECT" \
  --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor --format=none

step "Build a partir do código-fonte (Cloud Build usa a conta padrão do Compute)"
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$COMPUTE_SA" \
  --role roles/run.builder --condition=None --format=none

step "CD pode fazer deploy: $CD_SA"
for role in roles/run.sourceDeveloper roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$CD_SA" \
    --role "$role" --condition=None --format=none
done
gcloud iam service-accounts add-iam-policy-binding "$SA" --project "$PROJECT" \
  --member "serviceAccount:$CD_SA" --role roles/iam.serviceAccountUser --format=none

step "Cota de BigQuery: ${QUERY_MIB_PER_USER_DAY} MiB por identidade por dia"
curl -sS -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "x-goog-user-project: $PROJECT" -H "Content-Type: application/json" \
  "https://cloudquotas.googleapis.com/v1/projects/$PROJECT/locations/global/quotaPreferences?quotaPreferenceId=bq-query-per-user-day" \
  -d "{\"service\":\"bigquery.googleapis.com\",\"quotaId\":\"QueryUsagePerUserPerDay\",\"quotaConfig\":{\"preferredValue\":\"$QUERY_MIB_PER_USER_DAY\"},\"dimensions\":{}}" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("error",{}).get("message") or "cota pedida: " + d["quotaConfig"]["preferredValue"] + " MiB")'

step "Alerta de orçamento: ${BUDGET} ${CURRENCY} por mês"
BILLING="$(gcloud billing projects describe "$PROJECT" --format='value(billingAccountName)' | sed 's#billingAccounts/##')"
if ! gcloud billing budgets list --billing-account "$BILLING" --format='value(displayName)' | grep -qx "$SERVICE"; then
  gcloud billing budgets create --billing-account "$BILLING" --display-name "$SERVICE" \
    --budget-amount "${BUDGET}${CURRENCY}" --filter-projects "projects/$PROJECT" \
    --threshold-rule percent=0.5 --threshold-rule percent=1.0 \
    || echo "Aviso: o alerta não foi criado. Confira a moeda da conta de faturamento (CURRENCY=USD)."
fi

step "Primeiro deploy no Cloud Run"
gcloud run deploy "$SERVICE" --source . --project "$PROJECT" --region "$REGION" \
  --service-account "$SA" \
  --set-secrets "MCP_PATH_SECRET=${SECRET}:latest" \
  --set-env-vars "GCP_PROJECT=$PROJECT" \
  --allow-unauthenticated \
  --min-instances 0 --max-instances 2 \
  --cpu 1 --memory 1Gi --concurrency 4 --timeout 180 \
  --cpu-throttling --quiet

step "Imagens antigas: guarda só as 2 mais recentes"
cleanup="$(mktemp)"
cat > "$cleanup" <<'EOF'
[
  {"name": "guarda-2-recentes", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 2}},
  {"name": "apaga-o-resto", "action": {"type": "Delete"}, "condition": {"tagState": "any", "olderThan": "1d"}}
]
EOF
gcloud artifacts repositories set-cleanup-policies cloud-run-source-deploy \
  --project "$PROJECT" --location "$REGION" --policy "$cleanup" --no-dry-run --format=none
rm -f "$cleanup"

step "Pronto. Para ver a URL completa (com a chave): bash infra/mcp/url.sh"
