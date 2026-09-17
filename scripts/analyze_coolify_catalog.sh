#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${COOLIFY_WORK_DIR:-$(mktemp -d)}"
REPO_DIR="${WORK_DIR}/coolify"
REPORT_PATH="${COOLIFY_REPORT_PATH:-${ROOT_DIR}/coolify_catalog_compatibility.json}"
REF="${COOLIFY_REF:-main}"

cleanup() {
  if [[ -z "${COOLIFY_WORK_DIR:-}" ]]; then
    rm -rf "${WORK_DIR}"
  fi
}
trap cleanup EXIT

if [[ ! -d "${REPO_DIR}/.git" ]]; then
  git clone --depth 1 --branch "${REF}" https://github.com/coollabsio/coolify.git "${REPO_DIR}"
fi

python "${ROOT_DIR}/scripts/analyze_catalog_compatibility.py" \
  "${REPO_DIR}/templates/compose" \
  --json "${REPORT_PATH}"
