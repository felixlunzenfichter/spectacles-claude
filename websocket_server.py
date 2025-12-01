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
import base64
import aiohttp
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import ImageGrab, Image

# Store THE client (only one allowed)
current_client = None

# Store last sent message to avoid duplicates
last_sent_message = None

# Store sun times for color calculation
sun_times_data = None
location_data = None

def log(message):
    """Print a timestamped log message."""
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}")


async def fetch_sun_times(lat, lon):
    """Fetch sunrise/sunset times from API."""
    try:
        url = f"https://api.sunrise-sunset.org/json?lat={lat}&lng={lon}&formatted=0"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                if data.get('status') == 'OK':
                    results = data.get('results', {})

                    # Convert UTC times to local datetime objects
                    def parse_time(utc_time_str):
                        try:
                            dt = datetime.datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
                            return dt.astimezone()
                        except:
                            return None

                    return {
                        'astronomical_dawn': parse_time(results.get('astronomical_twilight_begin', '')),
                        'sunrise': parse_time(results.get('sunrise', '')),
                        'solar_noon': parse_time(results.get('solar_noon', '')),
                        'sunset': parse_time(results.get('sunset', '')),
                        'astronomical_dusk': parse_time(results.get('astronomical_twilight_end', ''))
                    }
    except Exception as e:
        log(f"❌ Error fetching sun times: {e}")
    return None

def get_sun_phase_color(sun_times):
    """Determine current sun phase and return (color, phase_name)."""
    if not sun_times:
        return ((1.0, 0.0, 0.0, 1.0), "night")  # Default to night (red)

    now = datetime.datetime.now().astimezone()

    astronomical_dawn = sun_times['astronomical_dawn']
    sunrise = sun_times['sunrise']
    solar_noon = sun_times['solar_noon']
    sunset = sun_times['sunset']
    astronomical_dusk = sun_times['astronomical_dusk']

    if astronomical_dawn <= now < sunrise:
        # Dawn: yellow (100% red + 100% green)
        return ((1.0, 1.0, 0.0, 1.0), "dawn")
    elif sunrise <= now < solar_noon:
        # Morning: blue (100% blue)
        return ((0.0, 0.0, 1.0, 1.0), "morning")
    elif solar_noon <= now < sunset:
        # Afternoon: turquoise (100% blue + 100% green)
        return ((0.0, 1.0, 1.0, 1.0), "afternoon")
    elif sunset <= now < astronomical_dusk:
        # Dusk: orange (100% red + 50% green)
        return ((1.0, 0.5, 0.0, 1.0), "dusk")
    else:
        # Night: red (100% red)
        return ((1.0, 0.0, 0.0, 1.0), "night")

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
                                        tool_name = item.get('name', 'unknown')
                                        tool_input = item.get('input', {})
                                        input_str = json.dumps(tool_input, indent=None)
                                        content_parts.append(f"[Tool: {tool_name}] {input_str}")
                                    elif item.get('type') == 'tool_result':
                                        result_content = item.get('content', '')
                                        content_parts.append(f"[Tool Result] {result_content}")

                    content_text = ' '.join(content_parts)

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

    # Wrap text message in consistent JSON format
    json_message = {
        'type': 'text',
        'data': message
    }
    json_string = json.dumps(json_message)

    # Print message being sent
    log("=" * 60)
    log("📤 SENDING TEXT MESSAGE:")
    log("=" * 60)
    log(f"   Type: text")
    log(f"   Data length: {len(message)} characters")
    log(f"   Preview: {message[:100]}..." if len(message) > 100 else f"   Data: {message}")
    log("=" * 60)
    global current_client

    # Send to THE client if connected
    if current_client:
        try:
            await current_client.send(json_string)
            log(f"   ✅ Sent to {current_client.remote_address}")
        except Exception as e:
            log(f"   ❌ Failed to send to client: {e}")
            # Clear the client if sending failed
            current_client = None
            log(f"   Client cleared due to send failure")
    else:
        log(f"   ⚠️  No client connected - message not sent")

async def jpeg_screenshot_loop(websocket):
    """Capture and send JPEG screenshots at 4 FPS, skip if unchanged."""
    import io
    import hashlib

    prev_hash = None

    while True:
        # Take screenshot (max 2048 on Spectacles)
        screenshot = ImageGrab.grab()
        screenshot = screenshot.resize((2048, 1152), Image.LANCZOS)
        screenshot = screenshot.convert('RGB')

        # Encode as JPEG
        buffer = io.BytesIO()
        screenshot.save(buffer, format='JPEG', quality=75)
        jpeg_bytes = buffer.getvalue()

        # Hash check - skip if identical
        current_hash = hashlib.md5(jpeg_bytes).hexdigest()
        if current_hash == prev_hash:
            # Nothing changed, skip
            await asyncio.sleep(0.25)
            continue

        prev_hash = current_hash

        # Convert to Base64 and send
        base64_jpg = base64.b64encode(jpeg_bytes).decode('ascii')
        message = json.dumps({
            'type': 'jpeg',
            'data': base64_jpg
        })

        log(f"📤 Sending JPEG: {screenshot.width}x{screenshot.height}, {len(jpeg_bytes):,} bytes")
        await websocket.send(message)

        # Wait for acknowledgment
        ack = await websocket.recv()
        log(f"✅ Received ack: {ack}")

        # Wait 1 second
        await asyncio.sleep(1.0)

async def handle_client(websocket):
    """Handle a client connection."""
    global sun_times_data, location_data, current_client

    client_addr = websocket.remote_address
    client_ip = client_addr[0] if client_addr else "unknown"

    # HARDCODED: Only accept connections from Spectacles
    SPECTACLES_IP = "172.20.10.9"

    # Check if this is the Spectacles
    if client_ip != SPECTACLES_IP:
        log(f"❌ REJECTED CONNECTION from {client_addr} - Not Spectacles IP")
        log(f"   Expected: {SPECTACLES_IP}, Got: {client_ip}")
        await websocket.close()
        return

    # Replace any existing client with this new one
    if current_client:
        log(f"⚠️  Replacing existing client with new connection from {client_addr}")
        try:
            await current_client.close()
        except:
            pass

    # Set this as THE client
    current_client = websocket
    log(f"✅ CLIENT CONNECTED: {client_addr}")
    log(f"   This is THE client - all data will be sent here")

    try:
        # Get color and phase based on sun position
        color, phase = get_sun_phase_color(sun_times_data) if sun_times_data else ((1.0, 0.0, 0.0, 1.0), "night")

        # Create single initialization message
        init_message = {
            'type': 'init',
            'width': 2048,
            'height': 1152,
            'color': {
                'r': color[0],
                'g': color[1],
                'b': color[2],
                'a': color[3]
            },
            'last_message': last_sent_message if last_sent_message else None
        }

        log(f"📤 Sending init to {client_addr}: {phase} - {color}")
        await websocket.send(json.dumps(init_message))
        log(f"✅ Init message sent successfully")

        # Wait for acknowledgement from client
        log(f"⏳ Waiting for acknowledgement from {client_addr}...")
        ack = await websocket.recv()
        log(f"✅ Received acknowledgement: {ack}")

        # Start JPEG screenshot loop
        log(f"🔄 Starting JPEG screenshot loop (1 FPS)")
        await jpeg_screenshot_loop(websocket)

    except websockets.exceptions.ConnectionClosed as e:
        log(f"🔌 CLIENT DISCONNECTED: {client_addr}")
        log(f"   Reason: {e}")
    except Exception as e:
        log(f"❌ ERROR with {client_addr}: {e}")
        log(f"   Traceback: {traceback.format_exc()}")
    finally:
        # Clear the client if it's this one
        if current_client == websocket:
            current_client = None
            log(f"   Client disconnected - slot now empty")

async def main():
    """Start the WebSocket server and file watcher."""
    global sun_times_data, location_data

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

    # Fetch and log location and sun times
    log("")
    log("☀️  Fetching sun times...")
    # Hardcoded to Vienna, 1st District (Innere Stadt)
    location = {
        'city': 'Vienna',
        'country': 'Austria',
        'lat': 48.2082,
        'lon': 16.3738,
        'timezone': 'Europe/Vienna'
    }
    location_data = location  # Store globally
    log(f"📍 Location: {location['city']}, {location['country']}")
    log(f"   Coordinates: {location['lat']:.4f}, {location['lon']:.4f}")
    log(f"   Timezone: {location['timezone']}")

    sun_times = await fetch_sun_times(location['lat'], location['lon'])
    if sun_times:
        sun_times_data = sun_times  # Store globally
        log("")
        log("🌅 Sun Times for Today (local time):")
        log(f"   Astronomical Dawn: {sun_times['astronomical_dawn']}")
        log(f"   Sunrise:           {sun_times['sunrise']}")
        log(f"   Solar Noon:        {sun_times['solar_noon']}")
        log(f"   Sunset:            {sun_times['sunset']}")
        log(f"   Astronomical Dusk: {sun_times['astronomical_dusk']}")
    else:
        log("❌ Failed to fetch sun times")
    log("")
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
    log("⏳ Waiting for Spectacles connection...")
    log("   📱 Only accepting connections from: 172.20.10.9")
    log("   🚫 Blocking all other connections (Lens Studio, localhost, etc.)")
    log("   ⚠️  Only one client allowed at a time")
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
