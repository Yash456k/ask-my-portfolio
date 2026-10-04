#!/usr/bin/env bash
# Put the corpus on main live from a development machine, in one command:
#   1. main must be clean and pushed, so the server gets exactly what was tested
#   2. gate: every test question still maps onto the corpus, and Jev passes its gates
#      (evaluation/gates.json) on the 276-question challenge-v3 set
#   3. the server pulls main and ingests beside the running API; only passages whose
#      text changed are embedded
#   4. the server's commit and the live API are checked
#
# Settings come from the environment or from .env.deploy in the repository root (not in Git):
#   DEPLOY_SSH         the ssh command that reaches the server, e.g. "ssh deploy@my-server"
#   DEPLOY_PATH        the deployment checkout on the server (default /opt/rag-playground)
#   DEPLOY_API_URL     the public API, checked at the end (optional)
#   TYPESAFE_API_KEY   for the Jev gate, or TYPESAFE_ENV_FILE naming a file that holds it
#
# Usage: ./scripts/deploy_corpus.sh [--force]     (--force re-embeds every passage)
set -euo pipefail

cd "$(dirname "$0")/.."

force=""
if [[ "${1:-}" == "--force" ]]; then
  force="--force"
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--force]" >&2
  exit 2
fi

# Read KEY=VALUE from a file without running it, and without a stray carriage return.
setting() {
  [[ -f "$2" ]] || return 0
  grep -E "^$1=" "$2" | head -1 | cut -d= -f2- | tr -d '\r' | sed -E 's/^"(.*)"$/\1/'
}
: "${DEPLOY_SSH:=$(setting DEPLOY_SSH .env.deploy)}"
: "${DEPLOY_PATH:=$(setting DEPLOY_PATH .env.deploy)}"
: "${DEPLOY_API_URL:=$(setting DEPLOY_API_URL .env.deploy)}"
: "${TYPESAFE_ENV_FILE:=$(setting TYPESAFE_ENV_FILE .env.deploy)}"
: "${TYPESAFE_API_KEY:=$(setting TYPESAFE_API_KEY "${TYPESAFE_ENV_FILE:-.env.deploy}")}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/rag-playground}"
export TYPESAFE_API_KEY
if [[ -z "$DEPLOY_SSH" || -z "$TYPESAFE_API_KEY" ]]; then
  echo "Set DEPLOY_SSH and TYPESAFE_API_KEY (or TYPESAFE_ENV_FILE); see the top of $0." >&2
  exit 1
fi
read -r -a ssh_cmd <<<"$DEPLOY_SSH"
python=python
[[ -x .venv/bin/python ]] && python=.venv/bin/python
started=$SECONDS

echo "[1/4] Checking main is clean and pushed"
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "There are uncommitted changes. Commit or stash them first." >&2
  exit 1
fi
git fetch -q origin main
commit="$(git rev-parse HEAD)"
if [[ "$commit" != "$(git rev-parse origin/main)" ]]; then
  echo "This checkout is not at origin/main. Push or pull first." >&2
  exit 1
fi

echo "[2/4] Gate: test questions against the corpus, then Jev on challenge-v3"
"$python" -m pytest -q tests/test_evaluation_data.py
results="evaluation/results/deploy/$(date -u +%Y%m%dT%H%M%SZ)-${commit:0:7}"
mkdir -p "$results"
if "$python" -m scripts.evaluate_jev_retrieval --split challenge-v3 --method hybrid --gate \
  --output-dir "$results" >"$results/jev.log" 2>&1; then
  gate=passed
else
  gate=failed
fi
"$python" - "$results/jev.log" <<'PY'
import json, sys
done = [json.loads(line) for line in open(sys.argv[1]) if line.startswith('{"event": "complete"')]
if not done:
    sys.exit("The evaluation did not finish; see " + sys.argv[1])
measured = done[-1]["measured"]
print(f"      right passage first {measured['hitAt1']:.3f}, MRR {measured['mrrAt5']:.3f}, "
      f"must-refuse refused {measured['mustRefuseRefusedShare']:.2f}, "
      f"answerable refused {measured['answerableRefusedShare']:.3f}")
if done[-1]["failures"]:
    print("      below the gate:", ", ".join(done[-1]["failures"]))
PY
if [[ "$gate" != passed ]]; then
  echo "The gate failed, so nothing was deployed. Results are in $results." >&2
  exit 1
fi

echo "[3/4] Ingesting on the server"
"${ssh_cmd[@]}" "cd '$DEPLOY_PATH' && ./scripts/ingest.sh $force" 2>&1 | tr -d '\r' | sed 's/^/      /'

echo "[4/4] Checking what is live"
live="$("${ssh_cmd[@]}" "git -C '$DEPLOY_PATH' rev-parse HEAD" | tr -d '\r')"
if [[ "$live" != "$commit" ]]; then
  echo "The server is at ${live:0:7}, not ${commit:0:7}." >&2
  exit 1
fi
if [[ -n "$DEPLOY_API_URL" ]]; then
  curl --fail --silent --show-error --max-time 20 "$DEPLOY_API_URL/v1/health" | sed 's/^/      /'
  echo
fi
echo "Corpus at ${commit:0:7} is live. Took $((SECONDS - started)) s."
