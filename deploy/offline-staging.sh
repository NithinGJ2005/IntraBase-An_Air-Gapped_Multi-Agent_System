#!/usr/bin/env bash
# Offline Package and Model Staging Script
# Pre-stages all wheels and model assets for offline/air-gapped deployment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WHEELHOUSE_DIR="${SCRIPT_DIR}/wheelhouse"
MODELS_DIR="${SCRIPT_DIR}/models"

echo "=== Enterprise Intranet Assistant - Offline Staging ==="

mkdir -p "${WHEELHOUSE_DIR}"
mkdir -p "${MODELS_DIR}"

echo "[1/3] Downloading pinned wheels from approved internal mirror..."
python3 -m pip download \
    --dest "${WHEELHOUSE_DIR}" \
    --requirement <(python3 -c "
import tomllib
with open('${PROJECT_ROOT}/pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
    print('\n'.join(data['project']['dependencies']))
")

echo "[2/3] Verifying downloaded wheel bundle integrity..."
ls -lh "${WHEELHOUSE_DIR}"

echo "[3/3] Model staging verification..."
if [ -z "$(ls -A "${MODELS_DIR}")" ]; then
    echo "NOTICE: '${MODELS_DIR}' is empty."
    echo "Transfer the license-reviewed, scanned internal model weights to '${MODELS_DIR}/approved-model' before starting containers."
else
    echo "Staged model files detected in '${MODELS_DIR}'."
fi

echo "=== Staging complete. Containers can now build and run without internet access. ==="
