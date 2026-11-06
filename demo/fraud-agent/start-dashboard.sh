#!/bin/bash
# Start the Streamlit dashboard in the background with logging

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
if [ -f "run/dashboard.pid" ]; then
    OLD_PID=$(cat run/dashboard.pid)
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "Dashboard is already running with PID $OLD_PID"
        echo "Stop it first with: kill $OLD_PID"
        exit 1
    else
        echo "Removing stale PID file"
        rm run/dashboard.pid
    fi
fi

# Start dashboard in background
echo "Starting Streamlit dashboard..."
nohup streamlit run dashboard/app.py --server.headless true > run/dashboard.log 2>&1 &

# Save PID
echo $! > run/dashboard.pid

echo "Dashboard started with PID $(cat run/dashboard.pid)"
echo "Logs: run/dashboard.log"
echo "Access at: http://localhost:8501"
echo ""
echo "To stop: kill \$(cat run/dashboard.pid)"
