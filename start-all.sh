#!/bin/bash
# Start everything for self-hosted Spectacles relay
#
# This script starts:
# 1. Local relay server (Deno on port 8000)
# 2. Tailscale Funnel (exposes relay to internet)
# 3. Mac server (connects to local relay)

cd "$(dirname "$0")"

echo "=============================================="
echo "STARTING SELF-HOSTED SPECTACLES SYSTEM"
echo "=============================================="
echo ""

# Kill any existing processes
echo "Stopping any existing processes..."
pkill -f "deno.*relay_server" 2>/dev/null
pkill -f "tailscale funnel" 2>/dev/null
sleep 1

# Step 1: Start local relay server
echo ""
echo "[1/3] Starting local relay server on port 8000..."
deno run --allow-net relay_server_deno.ts &
RELAY_PID=$!
sleep 2

# Check if relay started
if curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo "      Relay server running at http://localhost:8000"
else
    echo "      ERROR: Relay server failed to start!"
    exit 1
fi

# Step 2: Start Tailscale Funnel
echo ""
echo "[2/3] Starting Tailscale Funnel..."
tailscale funnel 8000 &
FUNNEL_PID=$!
sleep 2

echo "      Funnel URL: https://felixs-macbook-pro.tailcfdca5.ts.net/"

# Step 3: Start Mac server
echo ""
echo "[3/3] Starting Mac server..."
echo ""
./start-server-in-window.sh

echo ""
echo "=============================================="
echo "ALL SYSTEMS RUNNING"
echo "=============================================="
echo ""
echo "Local relay:  http://localhost:8000"
echo "Public URL:   https://felixs-macbook-pro.tailcfdca5.ts.net/"
echo ""
echo "Spectacles can now connect!"
echo ""
echo "To stop everything: pkill -f 'deno.*relay' && pkill -f 'tailscale funnel'"
echo ""
