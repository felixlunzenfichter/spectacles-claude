---
name: start-spectacles
description: Start the Spectacles streaming server. Use when asked to start spectacles, launch the server, or begin streaming to glasses.
allowed-tools: Bash, Read
---

# Start Spectacles Server

## Instructions

```bash
cd ~/Documents/spectacles-claude
./start-all.sh
tail -f server.log
```

## Scripts

| Script | Run directly? | Purpose |
|--------|---------------|---------|
| `start-all.sh` | **YES** | Entry point. Kills/starts Tailscale Funnel, calls start-server-in-window.sh |
| `start-server-in-window.sh` | no | Internal. AppleScript types into "spectacles" Terminal. Server must run in persistent window, not Claude's bash. |
| `start-server-and-preview.sh` | no | Internal. Starts websocket_server.py, calls start-lens.sh. Dies when calling bash exits. |
| `start-lens.sh` | no | Internal. Opens Lens Studio, dismisses dialogs, clicks Preview. |

## Logs

Output goes to `server.log`. Watch for:
- "STARTING SPECTACLES SYSTEM" - server initializing
- "Tailscale Funnel" - network tunnel active
- "CONNECTED" - relay connection established
- "SPECTACLES CONNECTED" - glasses joined
- "Sending JPEG" - screen stream active
