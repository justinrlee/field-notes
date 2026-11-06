#!/bin/bash
# Start the fraud trigger web UI in the background with logging

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
if [ -f "run/fraud-trigger.pid" ]; then
    OLD_PID=$(cat run/fraud-trigger.pid)
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "Fraud trigger is already running with PID $OLD_PID"
        echo "Stop it first with: kill $OLD_PID"
        exit 1
    else
        echo "Removing stale PID file"
        rm run/fraud-trigger.pid
    fi
fi

# Start fraud-trigger in background
echo "Starting fraud trigger web UI..."
cd fraud-trigger
nohup uvicorn app:app --host 0.0.0.0 --port 8080 > ../run/fraud-trigger.log 2>&1 &

# Save PID
echo $! > ../run/fraud-trigger.pid
cd ..

echo "Fraud trigger started with PID $(cat run/fraud-trigger.pid)"
echo "Logs: run/fraud-trigger.log"
echo "Access at: http://localhost:8080"
echo ""
echo "To stop: kill \$(cat run/fraud-trigger.pid)"
