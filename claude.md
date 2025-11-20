# Spectacles Claude

WebSocket server that streams Mac screen content to Snap Spectacles.

## Quick Start

Run the server:
```bash
./start-server-in-window.sh
```

This launches the WebSocket server in a new Terminal window and waits for connections from Spectacles at IP 172.20.10.9.

## Scripts

- `start-server-in-window.sh` - Starts the WebSocket server in a new Terminal window
- `start-server-and-preview.sh` - Starts server and opens Lens Studio preview
- `start-lens.sh` - Lens Studio automation only