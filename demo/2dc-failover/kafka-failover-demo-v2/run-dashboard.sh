#!/usr/bin/env bash
# Serves the single-page dashboard (dashboard/index.html) in the foreground.
# Ctrl-C stops it. Default port 8090; override with DASHBOARD_PORT.
#
# The page connects straight from your browser to the four client UIs on
# the ports set in .env (PRODUCER_TUNED_PORT etc., default 8081-8084) of the same host, so those ports must be reachable from your
# workstation too. Start the clients with ./run.sh or ./run-all.sh.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -x .venv/bin/python ]]; then
  echo "No virtualenv in .venv. Create it first:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install --only-binary=:all: -r client/requirements.txt" >&2
  exit 1
fi

if [[ -f .env ]]; then
  while IFS= read -r line || [[ -n $line ]]; do
    [[ $line =~ ^[[:space:]]*(#|$) ]] && continue
    key=${line%%=*}
    [[ -v $key ]] || export "$key=${line#*=}"
  done < .env
fi

# The page can't read .env, so hand it the client ports as a generated script.
cat > dashboard/ports.js <<JS
window.DEMO_PORTS = {
  "producer-tuned": ${PRODUCER_TUNED_PORT:-8081},
  "producer-fragile": ${PRODUCER_FRAGILE_PORT:-8082},
  "consumer-1": ${CONSUMER_1_PORT:-8083},
  "consumer-2": ${CONSUMER_2_PORT:-8084},
};
JS

exec .venv/bin/python -m http.server "${DASHBOARD_PORT:-8090}" \
  --bind "${UI_BIND:-0.0.0.0}" --directory dashboard
