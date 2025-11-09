#!/usr/bin/env python3
"""
WebSocket server for Spectacles that monitors Claude Code conversations.
Sends latest assistant messages to connected Spectacles in real-time.
"""

import asyncio
import websockets
import datetime
import traceback
import json
import os
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Store connected clients
connected_clients = set()

# Store last sent message to avoid duplicates
last_sent_message = None

def log(message):
    """Print a timestamped log message."""
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}")

def extract_latest_event(file_path):
    """Extract the latest event from a Claude Code .jsonl file."""
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()

        # Get the last non-empty line
        for line in reversed(lines):
            line = line.strip()
            if line:
                # Parse the event
                event = json.loads(line)

                # Extract timestamp (just the time part)
                timestamp = event.get('timestamp', '')
                if timestamp:
                    # Extract HH:MM:SS from ISO timestamp
                    time_part = timestamp.split('T')[1].split('.')[0] if 'T' in timestamp else timestamp
                else:
                    time_part = '??:??:??'

                # Extract role from message
                if 'message' in event:
                    msg = event['message']
                    role = msg.get('role', 'unknown')

                    # Extract content
                    content_parts = []
                    if 'content' in msg:
                        content = msg['content']
                        if isinstance(content, str):
                            content_parts.append(content)
                        elif isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict):
                                    if item.get('type') == 'text':
                                        content_parts.append(item.get('text', ''))
                                    elif item.get('type') == 'tool_use':
                                        content_parts.append(f"[Tool: {item.get('name', 'unknown')}]")
                                    elif item.get('type') == 'tool_result':
                                        content_parts.append(f"[Tool Result]")

                    content_text = ' '.join(content_parts)

                    # Trim to 1000 characters
                    if len(content_text) > 1000:
                        content_text = content_text[:1000] + "..."

                    # Format: [timestamp] role: content
                    return f"[{time_part}] {role}: {content_text}"

                # If no message, just show event type
                return f"[{time_part}] {event.get('type', 'unknown')}"

        return None
    except Exception as e:
        log(f"❌ Error reading conversation file: {e}")
        return None

class ClaudeConversationHandler(FileSystemEventHandler):
    """Handles file system events for Claude Code conversation files."""

    def __init__(self, loop):
        self.loop = loop
        super().__init__()

    def on_modified(self, event):
        """Called when a file is modified."""
        if event.is_directory:
            return

        # Only process .jsonl files
        if not event.src_path.endswith('.jsonl'):
            return

        log(f"📝 Conversation file changed: {Path(event.src_path).name}")

        # Extract latest event
        message = extract_latest_event(event.src_path)

        if message:
            # Schedule sending the message to all clients
            asyncio.run_coroutine_threadsafe(
                broadcast_message(message),
                self.loop
            )

async def broadcast_message(message):
    """Send a message to all connected clients."""
    global last_sent_message

    # Avoid sending duplicate messages
    if message == last_sent_message:
        log("⏭️  Skipping duplicate message")
        return

    last_sent_message = message

    # Print FULL message being sent
    log("=" * 60)
    log("📤 FULL MESSAGE BEING SENT:")
    log("=" * 60)
    log(message)
    log("=" * 60)
    log(f"   Message length: {len(message)} characters")
    log(f"   Sending to {len(connected_clients)} client(s)")

    # Send to all connected clients
    if connected_clients:
        disconnected_clients = set()
        for client in connected_clients:
            try:
                await client.send(message)
                log(f"   ✅ Sent to {client.remote_address}")
            except Exception as e:
                log(f"   ❌ Failed to send to {client.remote_address}: {e}")
                disconnected_clients.add(client)

        # Remove disconnected clients
        for client in disconnected_clients:
            connected_clients.discard(client)

async def handle_client(websocket):
    """Handle a client connection."""
    # Add client to set
    connected_clients.add(websocket)
    client_addr = websocket.remote_address
    log(f"✅ CLIENT CONNECTED: {client_addr}")
    log(f"   Total clients: {len(connected_clients)}")

    try:
        # Send welcome message
        welcome_msg = "Connected! Watching Claude Code conversations..."
        log(f"📤 SENDING to {client_addr}: '{welcome_msg}'")
        await websocket.send(welcome_msg)
        log(f"✅ SENT welcome message successfully")

        # If we have a previous message, send it
        if last_sent_message:
            preview = last_sent_message[:80].replace('\n', ' ')
            log(f"📤 Sending last message to new client: {preview}...")
            await websocket.send(last_sent_message)

        # Listen for messages from client
        log(f"👂 Listening for messages from {client_addr}")
        async for message in websocket:
            log(f"📥 RECEIVED from {client_addr}: '{message}'")
            # Echo back
            response = f"Server received: {message}"
            log(f"📤 SENDING response: '{response}'")
            await websocket.send(response)
            log(f"✅ Response sent successfully")

    except websockets.exceptions.ConnectionClosed as e:
        log(f"🔌 CLIENT DISCONNECTED: {client_addr}")
        log(f"   Reason: {e}")
    except Exception as e:
        log(f"❌ ERROR with {client_addr}: {e}")
        log(f"   Traceback: {traceback.format_exc()}")
    finally:
        # Remove client from set
        connected_clients.discard(websocket)
        log(f"   Remaining clients: {len(connected_clients)}")

async def main():
    """Start the WebSocket server and file watcher."""
    host = "0.0.0.0"  # Listen on all interfaces
    port = 8080

    log("=" * 60)
    log("🚀 STARTING WEBSOCKET SERVER FOR SPECTACLES")
    log("=" * 60)
    log(f"Host: {host}")
    log(f"Port: {port}")
    log(f"Local URL: ws://localhost:{port}")
    log(f"Network URL: ws://[YOUR_MAC_IP]:{port}")
    log("=" * 60)

    # Set up file watcher for Claude Code conversations
    claude_projects_path = Path.home() / '.claude' / 'projects'

    if not claude_projects_path.exists():
        log(f"⚠️  WARNING: Claude Code projects directory not found: {claude_projects_path}")
        log(f"   Conversation monitoring will not work!")
    else:
        log(f"📁 Monitoring Claude Code conversations in:")
        log(f"   {claude_projects_path}")

        # Get the event loop
        loop = asyncio.get_event_loop()

        # Create and start the observer
        event_handler = ClaudeConversationHandler(loop)
        observer = Observer()
        observer.schedule(event_handler, str(claude_projects_path), recursive=True)
        observer.start()
        log(f"👁️  File watcher started successfully")

    log("=" * 60)
    log("⏳ Waiting for connections...")
    log("")

    try:
        async with websockets.serve(handle_client, host, port):
            await asyncio.Future()  # Run forever
    except Exception as e:
        log(f"❌ FATAL ERROR: Server failed to start: {e}")
        log(f"   Traceback: {traceback.format_exc()}")
    finally:
        if 'observer' in locals():
            observer.stop()
            observer.join()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("")
        log("🛑 SERVER STOPPED by user (Ctrl+C)")
    except Exception as e:
        log(f"❌ UNEXPECTED ERROR: {e}")
        log(f"   Traceback: {traceback.format_exc()}")
