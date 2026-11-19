#!/usr/bin/env bash
# Carrega .env e valida credenciais. Use: source scripts/00_env.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -a; source "$ROOT/.env"; set +a
export AWS_DEFAULT_REGION="$AWS_REGION"
if [[ "$BUCKET" == *CHANGE-ME* || "$ROLE_ARN" == *"<ACCOUNT_ID>"* ]]; then
  echo "Edite o .env (BUCKET e ROLE_ARN) antes de continuar." >&2; return 1 2>/dev/null || exit 1
fi
aws sts get-caller-identity >/dev/null || { echo "Credenciais AWS inválidas/expiradas (cole de novo do AWS Details)." >&2; return 1 2>/dev/null || exit 1; }
export ROOT
echo "Conta: $(aws sts get-caller-identity --query Account --output text) | Região: $AWS_REGION | Bucket: $BUCKET"
