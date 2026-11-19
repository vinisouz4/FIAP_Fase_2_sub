#!/usr/bin/env bash
# Cria bucket, sobe o script do Glue e cria/atualiza o Glue Job.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"

echo ">> Bucket"
aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null || {
  if [[ "$AWS_REGION" == "us-east-1" ]]; then aws s3api create-bucket --bucket "$BUCKET"
  else aws s3api create-bucket --bucket "$BUCKET" --create-bucket-configuration LocationConstraint="$AWS_REGION"; fi
}

echo ">> Database default no Glue Catalog (cria só se não existir)"
aws glue create-database --database-input '{"Name":"default"}' 2>/dev/null || echo "   já existe"

echo ">> Upload do script Glue"
aws s3 cp "$ROOT/src/glue/transform_media_movel.py" "s3://$BUCKET/scripts/transform_media_movel.py"

echo ">> Glue Job"
aws glue delete-job --job-name "$GLUE_JOB_NAME" >/dev/null 2>&1 || true
aws glue create-job \
  --name "$GLUE_JOB_NAME" \
  --role "$ROLE_ARN" \
  --glue-version "4.0" \
  --worker-type G.1X --number-of-workers 2 \
  --command "Name=glueetl,ScriptLocation=s3://$BUCKET/scripts/transform_media_movel.py,PythonVersion=3" \
  --default-arguments "{
    \"--RAW_PATH\":\"s3://$BUCKET/raw/petroleo_brent/\",
    \"--REFINED_PATH\":\"s3://$BUCKET/refined/petroleo_media_movel/\",
    \"--DATABASE\":\"$GLUE_DATABASE\",
    \"--TABLE\":\"$GLUE_TABLE\",
    \"--WINDOW_DAYS\":\"$WINDOW_DAYS\",
    \"--enable-glue-datacatalog\":\"true\",
    \"--job-bookmark-option\":\"job-bookmark-disable\",
    \"--enable-continuous-cloudwatch-log\":\"true\"
  }" >/dev/null
echo "Deploy ok."
