#!/usr/bin/env bash
# Put the corpus on main live, without stopping the API:
# pull main, rebuild the image, re-ingest beside the running API, and check the result.
# Run on the server from the deployment checkout: ./scripts/ingest.sh [--force]
set -euo pipefail

cd "$(dirname "$0")/.."

force=()
if [[ "${1:-}" == "--force" ]]; then
  force=(--force)
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--force]" >&2
  exit 2
fi

docker_cmd=(docker)
if ! docker info >/dev/null 2>&1; then
  docker_cmd=(sudo -n docker)
fi
compose=("${docker_cmd[@]}" compose)

if ! grep -qE '^DATABASE_URL=.+' .env; then
  echo "Ingestion runs as the operator database role: set DATABASE_URL in .env." >&2
  exit 1
fi

echo "[1/4] Pulling main"
git fetch -q origin +refs/heads/main:refs/remotes/origin/main
git merge --ff-only -q origin/main
commit="$(git rev-parse --short HEAD)"

echo "[2/4] Building the image with the corpus at $commit"
"${compose[@]}" build -q api

echo "[3/4] Ingesting beside the running API"
"${compose[@]}" --profile tools run --rm ingest \
  python -m app.ingest --corpus /app/corpus --reason "re-ingest at $commit" "${force[@]}"

echo "[4/4] Checking the live API"
# The API's loopback port, not a public URL from .env, which can go stale.
curl --fail --silent --show-error http://127.0.0.1:18080/v1/health
echo
