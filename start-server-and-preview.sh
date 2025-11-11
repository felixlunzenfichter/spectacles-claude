#!/bin/bash

echo "Starting Spectacles development environment..."
echo "=============================================="

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Kill any existing server on port 8080
echo "Checking for existing server on port 8080..."
lsof -ti:8080 | xargs kill -9 2>/dev/null || true

# Start the WebSocket server in the background
echo "Starting WebSocket server..."
python3 "$SCRIPT_DIR/websocket_server.py" &
SERVER_PID=$!
echo "WebSocket server started (PID: $SERVER_PID)"

# Wait a moment for server to start
sleep 2

# Get Mac IP address
MAC_IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -1)
echo ""
echo "WebSocket server running at:"
echo "  - Local:      ws://localhost:8080"
echo "  - Spectacles: ws://$MAC_IP:8080"
echo ""


echo ""
echo "=============================================="
echo "Server is running. Press Ctrl+C to stop."
echo "=============================================="

# Wait for Ctrl+C
trap "echo ''; echo 'Stopping server...'; kill $SERVER_PID 2>/dev/null; exit 0" INT TERM

# Keep script running
wait $SERVER_PID
