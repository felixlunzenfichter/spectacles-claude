#!/bin/bash

# Start Lens Studio preview only (assumes Mac server is already running)

echo "Starting Lens Studio preview..."
echo "================================"

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Open Lens Studio and click Preview
"$SCRIPT_DIR/start-lens.sh"

echo ""
echo "Preview started. Mac server should already be connected to relay."
