#!/bin/bash
# Stop all running services

set -e

# Get the directory where this script is located (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

STOPPED=0

# Stop dashboard
if [ -f "run/dashboard.pid" ]; then
    PID=$(cat run/dashboard.pid)
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping dashboard (PID $PID)..."
        kill "$PID"
        rm run/dashboard.pid
        STOPPED=$((STOPPED + 1))
    else
        echo "Dashboard PID file exists but process not running, removing stale file"
        rm run/dashboard.pid
    fi
fi

# Stop fraud-trigger
if [ -f "run/fraud-trigger.pid" ]; then
    PID=$(cat run/fraud-trigger.pid)
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping fraud-trigger (PID $PID)..."
        kill "$PID"
        rm run/fraud-trigger.pid
        STOPPED=$((STOPPED + 1))
    else
        echo "Fraud-trigger PID file exists but process not running, removing stale file"
        rm run/fraud-trigger.pid
    fi
fi

# Stop producer
if [ -f "run/producer.pid" ]; then
    PID=$(cat run/producer.pid)
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping producer (PID $PID)..."
        kill "$PID"
        rm run/producer.pid
        STOPPED=$((STOPPED + 1))
    else
        echo "Producer PID file exists but process not running, removing stale file"
        rm run/producer.pid
    fi
fi

if [ $STOPPED -eq 0 ]; then
    echo "No services were running"
else
    echo ""
    echo "Stopped $STOPPED service(s)"
fi
