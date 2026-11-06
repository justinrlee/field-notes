#!/bin/bash
# Check status of all services

# Get the directory where this script is located (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Service Status ==="
echo ""

RUNNING=0

# Check dashboard
echo -n "Dashboard:      "
if [ -f "run/dashboard.pid" ]; then
    PID=$(cat run/dashboard.pid)
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "RUNNING (PID $PID) - http://localhost:8501"
        RUNNING=$((RUNNING + 1))
    else
        echo "STOPPED (stale PID file)"
    fi
else
    echo "STOPPED"
fi

# Check game-trigger
echo -n "Game Trigger:  "
if [ -f "run/game-trigger.pid" ]; then
    PID=$(cat run/game-trigger.pid)
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "RUNNING (PID $PID) - http://localhost:8080"
        RUNNING=$((RUNNING + 1))
    else
        echo "STOPPED (stale PID file)"
    fi
else
    echo "STOPPED"
fi

# Check producer
echo -n "Producer:       "
if [ -f "run/producer.pid" ]; then
    PID=$(cat run/producer.pid)
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "RUNNING (PID $PID)"
        RUNNING=$((RUNNING + 1))
    else
        echo "STOPPED (stale PID file)"
    fi
else
    echo "STOPPED"
fi

echo ""
echo "$RUNNING of 3 services running"
echo ""

# Show recent log entries if services are running
if [ $RUNNING -gt 0 ]; then
    echo "=== Recent Logs ==="
    echo ""

    if [ -f "run/dashboard.pid" ] && ps -p "$(cat run/dashboard.pid)" > /dev/null 2>&1; then
        echo "--- Dashboard (last 3 lines) ---"
        tail -n 3 run/dashboard.log 2>/dev/null || echo "(no logs yet)"
        echo ""
    fi

    if [ -f "run/game-trigger.pid" ] && ps -p "$(cat run/game-trigger.pid)" > /dev/null 2>&1; then
        echo "--- Game Trigger (last 3 lines) ---"
        tail -n 3 run/game-trigger.log 2>/dev/null || echo "(no logs yet)"
        echo ""
    fi

    if [ -f "run/producer.pid" ] && ps -p "$(cat run/producer.pid)" > /dev/null 2>&1; then
        echo "--- Producer (last 3 lines) ---"
        tail -n 3 run/producer.log 2>/dev/null || echo "(no logs yet)"
        echo ""
    fi
fi

echo "Commands:"
echo "  Start:  ./start-dashboard.sh | ./start-game-trigger.sh | ./start-producer.sh"
echo "  Stop:   ./stop-all.sh"
echo "  Logs:   tail -f run/dashboard.log | run/game-trigger.log | run/producer.log"
