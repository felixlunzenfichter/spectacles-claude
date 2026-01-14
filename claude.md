# Spectacles Claude

WebSocket server that streams Mac screen content to Snap Spectacles.

## Quick Start

```bash
./start-server-in-window.sh
```

## The Story (told by logs)

### Startup - Mac Server

```
STARTING MAC SERVER (RELAY CLIENT MODE)
Relay URL: wss://...
Device Secret: abc12345...

Fetching sun times...
Location: Berlin, Germany
   Coordinates: 52.5200, 13.4050
   Timezone: Europe/Berlin

Sun Times for Today (local time):
   Astronomical Dawn: 05:23
   Sunrise:           06:15
   Solar Noon:        12:30
   Sunset:            18:45
   Astronomical Dusk: 19:37

Monitoring Claude Code conversations in:
   /Users/.../claude/
Claude conversation watcher started successfully

Monitoring repository for git diff:
   /Users/.../spectacles-claude
Repository watcher started successfully

Connecting to relay: wss://relay.deno.dev/ws/server...
```

### Startup - Relay Server

```
Created new device pair                    → First connection for this secret
server connected                           → Mac arrived
client connected                           → Glasses arrived
```

### Startup - Spectacles

```
ServerTextDisplay: Script initialized      → Lens loaded
ServerTextDisplay: Update event bound      → Ready for frames
SpectaclesClient: Connecting to relay at wss://...
SpectaclesClient: Connected to relay!      → Socket open
```

### Connection Established

Mac sees:
```
CONNECTED TO RELAY SERVER
   Relay URL: wss://relay.deno.dev
   Device Secret: abc12345...
   Waiting for Spectacles to connect...

SPECTACLES CONNECTED (via relay)           → Glasses joined
Sending init: day - #1A1A1A               → Sending config
```

Glasses see:
```
SpectaclesClient: Relay notification - connected
SpectaclesClient: Relay notification - server_connected
ServerTextDisplay: Received init message   → Got config
ServerTextDisplay: Sending acknowledgement
```

Mac confirms:
```
Received ack from Spectacles               → Handshake complete
```

### Running - Screenshot Stream

Mac sends:
```
Sending JPEG: 1920x1080, 245,891 bytes     → Screen captured
Sending JPEG: 1920x1080, 247,103 bytes     → Continuous stream
```

Glasses receive:
```
ServerTextDisplay: Received JPEG (base64 length: 327854)
ServerTextDisplay: JPEG decoded successfully  → Image displayed
```

### Running - Conversation Updates

When Claude Code conversation changes:
```
Conversation file changed: 2024-01-15_abc.json
```

Mac formats and sends text, glasses display it.

### Running - Git Changes

When files in repo change:
```
Repo file changed: websocket_server.py

SENDING GIT DIFF:
   Data length: 1234 characters
   Preview: diff --git a/websocket...

   Git diff sent through relay
```

Glasses receive:
```
ServerTextDisplay: Received git_diff message
ServerTextDisplay: Git diff text component updated successfully
```

### Disconnection

Glasses disconnect:
```
[Relay] client disconnected (code: 1000, reason: none)
[Mac]   SPECTACLES DISCONNECTED (via relay)
```

Mac disconnects:
```
[Relay] server disconnected (code: 1000, reason: none)
[Glasses] SpectaclesClient: Relay notification - server_disconnected
```

### Reconnection

Glasses auto-reconnect:
```
ServerTextDisplay: Attempting to reconnect...
SpectaclesClient: Connecting to relay at wss://...
SpectaclesClient: Connected to relay!
```

Mac auto-reconnect:
```
Connection to relay closed
Reconnecting to relay in 5 seconds...
Connecting to relay: wss://...
CONNECTED TO RELAY SERVER
```

### Errors

Connection issues:
```
SpectaclesClient: WebSocket error occurred
SpectaclesClient: Error event details: {...}
SpectaclesClient: Socket state: 3
```

Missing config:
```
ERROR: DEVICE_SECRET not set in .env file
   Cannot connect to relay without device secret
```

Fatal:
```
FATAL ERROR: <exception>
   Traceback: ...
```

User interrupt:
```
SERVER STOPPED by user (Ctrl+C)
```

## Architecture

```
Mac Server                    Relay                      Spectacles
    |                           |                            |
    |---[connect as server]---->|                            |
    |<--[connected, peer:no]----|                            |
    |                           |<----[connect as client]----|
    |                           |----[connected, peer:yes]-->|
    |<--[client_connected]------|                            |
    |                           |----[server_connected]----->|
    |                           |                            |
    |---[init message]--------->|-------[forward]----------->|
    |<--[ack]-------------------|<------[forward]------------|
    |                           |                            |
    |---[jpeg screenshot]------>|-------[forward]----------->|
    |---[text message]--------->|-------[forward]----------->|
    |---[git_diff]------------->|-------[forward]----------->|
```

## Scripts

| Script | Purpose |
|--------|---------|
| `start-server-in-window.sh` | Start Mac server (USE THIS) |
| `start-lens.sh` | Restart Lens Studio |
| `start-preview.sh` | Open preview panel |
| `start-server-and-preview.sh` | Both server + preview |

## User Setup

User's only interface = Claude Code

```
User -> Spectacles -> Voice Transcription
     -> Claude Code -> Computer

No clicking. No pointing. No mouse.
Voice only. Claude does everything.
```

User may be: walking, anywhere, hands-free.
Sees: screen share on Spectacles.
Input: voice transcription only.

Execute all actions. Never ask user to click.
