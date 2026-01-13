#!/bin/bash

echo "Starting Spectacles development environment..."
echo "=============================================="

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Kill any existing server
pkill -f websocket_server.py 2>/dev/null

# Activate virtual environment and start the server in background
echo "Connecting to relay server..."
source "$SCRIPT_DIR/venv/bin/activate"
python3 "$SCRIPT_DIR/websocket_server.py" &
SERVER_PID=$!
echo "Server started (PID: $SERVER_PID)"

# Wait for relay connection
sleep 3

# Check relay status
echo ""
echo "Checking relay connection..."
curl -s https://spectacles-relay-xd16d6rhq1nd.deno.dev/status | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Relay: {d[\"summary\"][\"totalPairs\"]} pairs, {d[\"summary\"][\"activePairs\"]} active')" 2>/dev/null || echo "Could not check relay status"

# Start Lens Studio preview
echo ""
echo "Starting Lens Studio preview..."
"$SCRIPT_DIR/start-lens.sh"

echo ""
echo "=============================================="
echo "Server running. Press Ctrl+C to stop."
echo "=============================================="

# Wait for Ctrl+C
trap "echo ''; echo 'Stopping server...'; kill $SERVER_PID 2>/dev/null; exit 0" INT TERM

# Keep script running
wait $SERVER_PID
