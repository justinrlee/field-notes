#!/bin/bash
# Start all components: producer, fraud trigger, and dashboard

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

# Parse mode argument for producer (default: normal transactions only)
PRODUCER_MODE="${1:-}"

echo "=========================================="
echo "Starting All Components"
echo "=========================================="
echo ""

# Function to check if a component is already running
check_running() {
    local component=$1
    local pid_file="run/${component}.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo "⚠️  $component is already running with PID $pid"
            return 0
        else
            echo "Removing stale PID file for $component"
            rm "$pid_file"
        fi
    fi
    return 1
}

# Start Producer
echo "1. Starting Event Producer..."
if check_running "producer"; then
    echo "   Skipping producer (already running)"
else
    if [ -z "$PRODUCER_MODE" ]; then
        nohup python producer/generate_events.py > run/producer.log 2>&1 &
        echo $! > run/producer.pid
        echo "   ✓ Producer started with PID $(cat run/producer.pid) (mode: normal transactions only)"
    else
        nohup python producer/generate_events.py $PRODUCER_MODE > run/producer.log 2>&1 &
        echo $! > run/producer.pid
        echo "   ✓ Producer started with PID $(cat run/producer.pid) (mode: $PRODUCER_MODE)"
    fi
    echo "   Logs: run/producer.log"
fi
echo ""

# Start Fraud Trigger
echo "2. Starting Fraud Trigger Web UI..."
if check_running "fraud-trigger"; then
    echo "   Skipping fraud trigger (already running)"
else
    cd fraud-trigger
    nohup uvicorn app:app --host 0.0.0.0 --port 8080 > ../run/fraud-trigger.log 2>&1 &
    echo $! > ../run/fraud-trigger.pid
    cd ..
    echo "   ✓ Fraud trigger started with PID $(cat run/fraud-trigger.pid)"
    echo "   Logs: run/fraud-trigger.log"
    echo "   Access at: http://localhost:8080"
fi
echo ""

# Start Dashboard
echo "3. Starting Streamlit Dashboard..."
if check_running "dashboard"; then
    echo "   Skipping dashboard (already running)"
else
    nohup streamlit run dashboard/app.py --server.headless true > run/dashboard.log 2>&1 &
    echo $! > run/dashboard.pid
    echo "   ✓ Dashboard started with PID $(cat run/dashboard.pid)"
    echo "   Logs: run/dashboard.log"
    echo "   Access at: http://localhost:8501"
fi
echo ""

echo "=========================================="
echo "All Components Started"
echo "=========================================="
echo ""
echo "Quick Access:"
echo "  • Dashboard:      http://localhost:8501"
echo "  • Fraud Trigger:  http://localhost:8080"
echo ""
echo "Logs:"
echo "  • Producer:       tail -f run/producer.log"
echo "  • Fraud Trigger:  tail -f run/fraud-trigger.log"
echo "  • Dashboard:      tail -f run/dashboard.log"
echo ""
echo "To stop all components: ./stop-all.sh"
echo ""

# Show producer mode info
if [ -z "$PRODUCER_MODE" ]; then
    echo "Producer Mode: normal transactions only (default)"
else
    echo "Producer Mode: $PRODUCER_MODE"
fi
echo ""
echo "Available producer modes:"
echo "  ./start-all.sh              - Normal user activity only (default)"
echo "  ./start-all.sh --fraud      - Fraud scenarios only"
echo "  ./start-all.sh --single-fraud - Generate one fraud event and exit"
echo "  ./start-all.sh --both       - Normal + fraud after cycle 50"
