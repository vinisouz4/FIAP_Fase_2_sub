#!/usr/bin/env bash
# Gera o gráfico lendo direto do Athena.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
python "$ROOT/src/viz/grafico_media_movel.py" --desde 2015 --saida "$ROOT/output/grafico_media_movel.png"
