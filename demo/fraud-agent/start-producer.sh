#!/bin/bash
# Start the event producer in the background with logging

set -e

# Get the directory where this script is located (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create run directory if it doesn't exist
mkdir -p run

# Activate virtual environment
if [ ! -f "venv/bin/activate" ]; then
    echo "Error: Virtual environment not found at venv/bin/activate"
    echo "Please run: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 1
fi

source venv/bin/activate

# Check if already running
if [ -f "run/producer.pid" ]; then
    OLD_PID=$(cat run/producer.pid)
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "Producer is already running with PID $OLD_PID"
        echo "Stop it first with: kill $OLD_PID"
        exit 1
    else
        echo "Removing stale PID file"
        rm run/producer.pid
    fi
fi

# Parse mode argument (default: normal transactions only)
MODE="${1:-}"

# Start producer in background
if [ -z "$MODE" ]; then
    echo "Starting event producer (mode: normal transactions only)..."
    nohup python producer/generate_events.py > run/producer.log 2>&1 &
else
    echo "Starting event producer (mode: $MODE)..."
    nohup python producer/generate_events.py $MODE > run/producer.log 2>&1 &
fi

# Save PID
echo $! > run/producer.pid

echo "Producer started with PID $(cat run/producer.pid)"
if [ -z "$MODE" ]; then
    echo "Mode: normal transactions only"
else
    echo "Mode: $MODE"
fi
echo "Logs: run/producer.log"
echo ""
echo "Available modes:"
echo "  (no argument)  - Normal user activity only (default)"
echo "  --fraud        - Fraud scenarios only"
echo "  --single-fraud - Generate one fraud event and exit"
echo "  --both         - Normal + fraud after cycle 50"
echo ""
echo "To stop: kill \$(cat run/producer.pid)"
