#!/bin/bash
# Start the game trigger web UI in the background with logging

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
if [ -f "run/game-trigger.pid" ]; then
    OLD_PID=$(cat run/game-trigger.pid)
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "Game trigger is already running with PID $OLD_PID"
        echo "Stop it first with: kill $OLD_PID"
        exit 1
    else
        echo "Removing stale PID file"
        rm run/game-trigger.pid
    fi
fi

# Start game-trigger in background
echo "Starting game trigger web UI..."
cd game-trigger
nohup uvicorn app:app --host 0.0.0.0 --port 8080 > ../run/game-trigger.log 2>&1 &

# Save PID
echo $! > ../run/game-trigger.pid
cd ..

echo "Game trigger started with PID $(cat run/game-trigger.pid)"
echo "Logs: run/game-trigger.log"
echo "Access at: http://localhost:8080"
echo ""
echo "To stop: kill \$(cat run/game-trigger.pid)"
