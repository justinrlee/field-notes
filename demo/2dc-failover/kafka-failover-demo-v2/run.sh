#!/usr/bin/env bash
# Runs one demo client in the foreground, in this terminal. Ctrl-C stops it.
#
#   ./run.sh producer-tuned      UI on port 8081 (PRODUCER_TUNED_PORT)
#   ./run.sh producer-fragile    UI on port 8082 (PRODUCER_FRAGILE_PORT)
#   ./run.sh consumer-1          UI on port 8083 (CONSUMER_1_PORT)
#   ./run.sh consumer-2          UI on port 8084 (CONSUMER_2_PORT)
#   ./run.sh preflight           checks the gateway and topic, then exits
#
# Settings come from .env (see .env.example). A variable already set in the
# shell wins over .env, so one-off overrides work:
#   DEBUG_STATS=1 ./run.sh producer-tuned
#   TOPIC=other GROUP_ID=other CLIENT_ID=check PORT=8089 ./run.sh consumer-1
#
# Client output shows here and is appended to logs/<client id>.log.
set -euo pipefail
cd "$(dirname "$0")"

usage() { sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
[[ $# -eq 1 ]] || usage
name=$1

if [[ ! -x .venv/bin/python ]]; then
  echo "No virtualenv in .venv. Create it first:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install --only-binary=:all: -r client/requirements.txt" >&2
  exit 1
fi

# KEY=value lines; blank lines and # comments are skipped. No quotes needed.
if [[ -f .env ]]; then
  while IFS= read -r line || [[ -n $line ]]; do
    [[ $line =~ ^[[:space:]]*(#|$) ]] && continue
    key=${line%%=*}
    [[ -v $key ]] || export "$key=${line#*=}"
  done < .env
fi

case $name in
  producer-tuned)   role=producer profile=tuned   port=${PRODUCER_TUNED_PORT:-8081} ;;
  producer-fragile) role=producer profile=fragile port=${PRODUCER_FRAGILE_PORT:-8082} ;;
  consumer-1)       role=consumer profile=tuned   port=${CONSUMER_1_PORT:-8083} ;;
  consumer-2)       role=consumer profile=tuned   port=${CONSUMER_2_PORT:-8084} ;;
  preflight)        cd client && exec ../.venv/bin/python preflight.py ;;
  *)                usage ;;
esac

export ROLE=$role PROFILE=$profile CLIENT_ID=${CLIENT_ID:-$name} PYTHONUNBUFFERED=1
mkdir -p logs
cd client
# Open SSE streams never end on their own: give them 2 s on Ctrl-C, then close
# them. tee -i ignores Ctrl-C, so it keeps logging until uvicorn has finished.
../.venv/bin/uvicorn app:app --host "${UI_BIND:-0.0.0.0}" --port "${PORT:-$port}" \
  --timeout-graceful-shutdown 2 2>&1 | tee -ai "../logs/$CLIENT_ID.log"
