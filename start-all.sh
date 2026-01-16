#!/bin/bash
# Start everything for self-hosted Spectacles system (direct connection)
#
# This script starts:
# 1. Tailscale Funnel (exposes Mac server to internet on port 8765)
# 2. Mac server (WebSocket server on port 8765)

cd "$(dirname "$0")"

echo "=============================================="
echo "STARTING SPECTACLES SYSTEM (DIRECT CONNECTION)"
echo "=============================================="
echo ""

# Kill any existing processes
echo "Stopping any existing processes..."
pkill -f "tailscale funnel" 2>/dev/null
sleep 1

# Step 1: Start Tailscale Funnel on port 8765
echo ""
echo "[1/2] Starting Tailscale Funnel on port 8765..."
tailscale funnel 8765 &
FUNNEL_PID=$!
sleep 2

echo "      Funnel URL: https://felixs-macbook-pro.tailcfdca5.ts.net/"

# Step 2: Start Mac server
echo ""
echo "[2/2] Starting Mac server on port 8765..."
echo ""
./start-server-in-window.sh

echo ""
echo "=============================================="
echo "ALL SYSTEMS RUNNING"
echo "=============================================="
echo ""
echo "Mac server:   localhost:8765"
echo "Public URL:   https://felixs-macbook-pro.tailcfdca5.ts.net/"
echo ""
echo "Spectacles can now connect directly!"
echo ""
echo "To stop everything: pkill -f 'tailscale funnel'"
echo ""
