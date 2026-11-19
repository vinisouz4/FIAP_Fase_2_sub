#!/usr/bin/env bash
# Executa a pipeline ponta a ponta: scraper -> Glue -> Athena.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"

echo ">> 1/3 Scraper -> S3 raw"
python "$ROOT/src/scraper/ipea_scraper.py" --bucket "$BUCKET"

echo ">> 2/3 Glue Job"
RUN_ID=$(aws glue start-job-run --job-name "$GLUE_JOB_NAME" --query JobRunId --output text)
echo "   JobRunId=$RUN_ID"
while :; do
  STATE=$(aws glue get-job-run --job-name "$GLUE_JOB_NAME" --run-id "$RUN_ID" --query JobRun.JobRunState --output text)
  echo "   estado: $STATE"
  case "$STATE" in
    SUCCEEDED) break;;
    FAILED|ERROR|TIMEOUT|STOPPED) aws glue get-job-run --job-name "$GLUE_JOB_NAME" --run-id "$RUN_ID" --query JobRun.ErrorMessage; exit 1;;
  esac
  sleep 20
done

echo ">> 3/3 Athena (amostra)"
QID=$(aws athena start-query-execution \
  --query-string "SELECT data, preco_brent_usd, media_movel_7d FROM $GLUE_DATABASE.$GLUE_TABLE ORDER BY data DESC LIMIT 10" \
  --query-execution-context Database="$GLUE_DATABASE" \
  --result-configuration OutputLocation="s3://$BUCKET/athena-results/" \
  --query QueryExecutionId --output text)
until [[ "$(aws athena get-query-execution --query-execution-id "$QID" --query QueryExecution.Status.State --output text)" =~ ^(SUCCEEDED|FAILED|CANCELLED)$ ]]; do sleep 2; done
aws athena get-query-results --query-execution-id "$QID" --output table \
  --query 'ResultSet.Rows[*].Data[*].VarCharValue'
