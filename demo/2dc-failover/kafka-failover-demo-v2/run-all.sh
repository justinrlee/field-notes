#!/usr/bin/env bash
# Starts all four clients and the dashboard page in this one terminal.
# Ctrl-C stops everything. Client output is appended to logs/<client>.log
# (not shown here); the dashboard's own output shows here.
#
#   ./run-all.sh
#
# To kill or restart one client during the demo, run the clients yourself in
# separate terminals with ./run.sh <client> and use ./run-dashboard.sh for the
# page.
set -uo pipefail
cd "$(dirname "$0")"

clients=(producer-tuned producer-fragile consumer-1 consumer-2)

trap 'trap - INT TERM EXIT; kill 0 2>/dev/null; wait 2>/dev/null' INT TERM EXIT

for c in "${clients[@]}"; do
  ./run.sh "$c" >/dev/null 2>&1 &
done
echo "Started: ${clients[*]} (logs in logs/)"
echo "Dashboard on port ${DASHBOARD_PORT:-8090}"

./run-dashboard.sh
