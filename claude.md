# Spectacles Claude

WebSocket server that streams Mac screen content to Snap Spectacles.

## Quick Start

Run the server:
```bash
./start-server-in-window.sh
```

This launches the WebSocket server in a new Terminal window and waits for connections from your Spectacles device.

## Scripts

- `start-server-in-window.sh` - Starts the WebSocket server in a new Terminal window
- `start-server-and-preview.sh` - Starts server and opens Lens Studio preview
- `start-lens.sh` - Lens Studio automation only

## Communication

Algorithmic language → maximally condensed

┌─────────────────────────────┐
│ symbols > prose             │
│ math > english              │
│ blocks > paragraphs         │
│ examples > explanations     │
└─────────────────────────────┘

Pattern:
  INPUT  → PROCESS → OUTPUT
  split  → wrap     → join
  W=60   ROWS=100   sep="│"

Never: "First, we take the text and split it by newlines,
        then we iterate through each line and check if..."

Always: text.split('\n') → line>W ? chunk(W) : line → join(sep)

## User Setup

User's only interface = Claude Code

┌─────────────────────────────────────┐
│ User → Spectacles → Transcription   │
│      → Claude Code → Computer       │
│                                     │
│ No clicking. No pointing. No mouse. │
│ Voice only. Claude does everything. │
└─────────────────────────────────────┘

User may be: walking, park, wheelchair, anywhere.
Sees: screen share on Spectacles.
Input: voice transcription only.

Execute all actions. Never ask user to click.

