#!/usr/bin/env python3
"""
WebSocket client for Spectacles that connects to the relay server.
Sends screen content to connected Spectacles in real-time.
"""

import asyncio
import websockets
import datetime
import traceback
import json
import os
import base64
import io
import hashlib
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import ImageGrab, Image
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Relay server configuration
RELAY_URL = os.environ.get("RELAY_URL", "https://spectacles-relay-qbeff114ve4r.deno.dev")
DEVICE_SECRET = os.environ.get("DEVICE_SECRET", "")
RECONNECT_DELAY = 5  # seconds between reconnection attempts

# Store the WebSocket connection to relay
relay_connection = None

# Store last sent message to avoid duplicates
last_sent_message = None

# Store sun times for color calculation
sun_times_data = None
location_data = None

# Flag to track if Spectacles client is connected (via relay)
spectacles_connected = False

# Path to this repository for git diff
REPO_PATH = Path(__file__).parent.resolve()

# Store last git diff to avoid duplicates
last_git_diff = None


def log(message):
    """Print a timestamped log message."""
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}")


def get_git_diff():
    """Get the git diff output for the spectacles-claude repository.

    Runs the get-diff.sh script which provides comprehensive git status including:
    - Branch status with ahead/behind count
    - Unstaged and staged changes with function context
    - Untracked files with their content
    - Recent commit history with LOCAL/REMOTE markers
    """
    try:
        script_path = REPO_PATH / 'scripts' / 'get-diff.sh'
        log(f"Running script: {script_path}")
        result = subprocess.run(
            [str(script_path)],
            cwd=REPO_PATH,
            capture_output=True,
            text=True,
            timeout=30
        )
        log(f"Script result: returncode={result.returncode}, stdout_len={len(result.stdout)}, stderr={result.stderr[:100] if result.stderr else 'none'}")
        return result.stdout if result.returncode == 0 else None
    except Exception as e:
        log(f"Error getting git diff: {e}")
        return None


async def send_git_diff(force: bool = False):
    """Send the current git diff to Spectacles via relay."""
    global relay_connection, spectacles_connected, last_git_diff

    log(f"send_git_diff called: force={force}, relay_connection={relay_connection is not None}, spectacles_connected={spectacles_connected}")

    if not relay_connection or not spectacles_connected:
        log("Cannot send git diff - no Spectacles connected via relay")
        return

    log("Calling get_git_diff()...")
    diff_output = get_git_diff()
    log(f"get_git_diff returned: {diff_output is not None}, length={len(diff_output) if diff_output else 0}")

    if diff_output is None:
        log("No git diff available")
        return

    # Truncate to prevent overly large messages
    MAX_DIFF_SIZE = 10000
    if len(diff_output) > MAX_DIFF_SIZE:
        original_len = len(diff_output)
        diff_output = diff_output[:MAX_DIFF_SIZE] + "\n\n... (truncated)"
        log(f"Git diff truncated from {original_len} to {MAX_DIFF_SIZE} chars")

    # Skip if diff is the same as last time (unless forced)
    if not force and diff_output == last_git_diff:
        log("Git diff unchanged, skipping")
        return

    last_git_diff = diff_output

    message = {
        'type': 'git_diff',
        'data': diff_output
    }

    log("=" * 60)
    log("SENDING GIT DIFF:")
    log("=" * 60)
    log(f"   Data length: {len(diff_output)} characters")
    if diff_output:
        preview = diff_output[:200].replace('\n', '\\n')
        log(f"   Preview: {preview}...")
    else:
        log("   (empty diff - no uncommitted changes)")
    log("=" * 60)

    try:
        await relay_connection.send(json.dumps(message))
        log("   Git diff sent through relay")
    except Exception as e:
        log(f"   Failed to send git diff: {e}")


async def fetch_sun_times(lat, lon):
    """Fetch sunrise/sunset times from API."""
    import aiohttp
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
        log(f"Error fetching sun times: {e}")
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
        log(f"Error reading conversation file: {e}")
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

        log(f"Conversation file changed: {Path(event.src_path).name}")

        # Extract latest event
        message = extract_latest_event(event.src_path)

        if message:
            # Schedule sending the message through relay
            asyncio.run_coroutine_threadsafe(
                send_text_message(message),
                self.loop
            )


class RepoChangeHandler(FileSystemEventHandler):
    """Handles file system events for the spectacles-claude repository."""

    def __init__(self, loop):
        self.loop = loop
        self.debounce_task = None
        super().__init__()

    def on_any_event(self, event):
        """Called on any file system event."""
        if event.is_directory:
            return

        # Ignore .git directory changes
        if '.git' in event.src_path:
            return

        # Ignore __pycache__ and other noise
        if '__pycache__' in event.src_path or event.src_path.endswith('.pyc'):
            return

        log(f"Repo file changed: {Path(event.src_path).name}")

        # Debounce: cancel previous task and schedule new one
        if self.debounce_task:
            self.debounce_task.cancel()

        # Schedule sending git diff after a small delay (debounce)
        self.debounce_task = asyncio.run_coroutine_threadsafe(
            self._delayed_send_git_diff(),
            self.loop
        )

    async def _delayed_send_git_diff(self):
        """Send git diff after a short delay to debounce rapid changes."""
        await asyncio.sleep(0.5)  # Wait 500ms for rapid changes to settle
        await send_git_diff()


async def send_text_message(message):
    """Send a text message through the relay to Spectacles."""
    global last_sent_message, relay_connection, spectacles_connected

    # Avoid sending duplicate messages
    if message == last_sent_message:
        log("Skipping duplicate message")
        return

    last_sent_message = message

    if not relay_connection or not spectacles_connected:
        log("Cannot send text - no Spectacles connected via relay")
        return

    # Wrap text message in consistent JSON format
    json_message = {
        'type': 'text',
        'data': message
    }
    json_string = json.dumps(json_message)

    log("=" * 60)
    log("SENDING TEXT MESSAGE:")
    log("=" * 60)
    log(f"   Type: text")
    log(f"   Data length: {len(message)} characters")
    log(f"   Preview: {message[:100]}..." if len(message) > 100 else f"   Data: {message}")
    log("=" * 60)

    try:
        await relay_connection.send(json_string)
        log("   Text message sent through relay")
    except Exception as e:
        log(f"   Failed to send text: {e}")


async def jpeg_screenshot_loop():
    """Capture and send JPEG screenshots, skip if unchanged."""
    global relay_connection, spectacles_connected

    prev_hash = None

    while True:
        # Only send if Spectacles is connected
        if not relay_connection or not spectacles_connected:
            await asyncio.sleep(1.0)
            continue

        try:
            # Take screenshot at full resolution
            screenshot = ImageGrab.grab()
            # Resize to 2048x1152
            screenshot = screenshot.resize((2048, 1152), Image.LANCZOS)
            screenshot = screenshot.convert('RGB')

            # Encode as JPEG with maximum quality
            buffer = io.BytesIO()
            screenshot.save(buffer, format='JPEG', quality=100)
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

            log(f"Sending JPEG: {screenshot.width}x{screenshot.height}, {len(jpeg_bytes):,} bytes")
            await relay_connection.send(message)

            # Wait for acknowledgment (will come as a message from relay)
            # The relay will forward the ack from Spectacles
            # We handle acks in the message handler

            # Wait 1 second before next frame
            await asyncio.sleep(1.0)

        except websockets.exceptions.ConnectionClosed:
            log("Connection to relay lost during screenshot send, waiting for reconnection...")
            await asyncio.sleep(1.0)
            continue
        except Exception as e:
            log(f"Error in screenshot loop: {e}")
            await asyncio.sleep(1.0)


async def handle_relay_messages(websocket):
    """Handle incoming messages from the relay (forwarded from Spectacles)."""
    global spectacles_connected, sun_times_data

    async for message in websocket:
        try:
            data = json.loads(message)
            msg_type = data.get('type', '')

            if msg_type == 'relay_notification':
                # Handle relay notifications
                event = data.get('event', '')

                if event == 'client_connected':
                    # Spectacles client connected to relay
                    spectacles_connected = True
                    log("=" * 60)
                    log("SPECTACLES CONNECTED (via relay)")
                    log("=" * 60)

                    # Send initialization message
                    color, phase = get_sun_phase_color(sun_times_data) if sun_times_data else ((1.0, 0.0, 0.0, 1.0), "night")
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
                    log(f"Sending init: {phase} - {color}")
                    await websocket.send(json.dumps(init_message))

                    # Wait for handshake to complete before sending git diff
                    await asyncio.sleep(1)
                    await send_git_diff(force=True)

                elif event == 'client_disconnected':
                    # Spectacles client disconnected from relay
                    spectacles_connected = False
                    log("=" * 60)
                    log("SPECTACLES DISCONNECTED (via relay)")
                    log("=" * 60)

                elif event == 'connected':
                    # Our own connection confirmation
                    peer_connected = data.get('peerConnected', False)
                    log(f"Connected to relay (peer already connected: {peer_connected})")
                    if peer_connected:
                        # Spectacles was already connected before we joined
                        spectacles_connected = True
                        log("=" * 60)
                        log("SPECTACLES ALREADY CONNECTED (via relay)")
                        log("=" * 60)

                        # Send initialization message
                        color, phase = get_sun_phase_color(sun_times_data) if sun_times_data else ((1.0, 0.0, 0.0, 1.0), "night")
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
                        log(f"Sending init: {phase} - {color}")
                        await websocket.send(json.dumps(init_message))

                        # Wait for handshake to complete before sending git diff
                        await asyncio.sleep(1)
                        await send_git_diff(force=True)

                elif event == 'server_disconnected':
                    log("Received server_disconnected (shouldn't happen, we are the server)")

                else:
                    log(f"Unknown relay notification event: {event}")

            elif msg_type == 'ack':
                # Acknowledgment from Spectacles (forwarded by relay)
                log(f"Received ack from Spectacles")

            elif msg_type == 'error':
                log(f"Error from relay: {data.get('message', 'Unknown error')}")

            else:
                # Other messages from Spectacles (forwarded by relay)
                log(f"Received from Spectacles: {msg_type}")

        except json.JSONDecodeError:
            # Plain text message (like "ack")
            if message == "ack":
                log("Received ack from Spectacles")
            else:
                log(f"Received non-JSON message: {message[:100]}")
        except Exception as e:
            log(f"Error handling relay message: {e}")


async def connect_to_relay():
    """Connect to the relay server as a WebSocket client."""
    global relay_connection, spectacles_connected

    if not DEVICE_SECRET:
        log("ERROR: DEVICE_SECRET not set in .env file")
        log("   Cannot connect to relay without device secret")
        return

    # Build WebSocket URL for server endpoint
    ws_url = RELAY_URL.replace('https://', 'wss://').replace('http://', 'ws://')
    ws_url = f"{ws_url}/ws/server?device_secret={DEVICE_SECRET}"

    log(f"Connecting to relay: {ws_url[:50]}...")

    while True:
        try:
            async with websockets.connect(
                ws_url,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5
            ) as websocket:
                relay_connection = websocket
                log("=" * 60)
                log("CONNECTED TO RELAY SERVER")
                log("=" * 60)
                log(f"   Relay URL: {RELAY_URL}")
                log(f"   Device Secret: {DEVICE_SECRET[:8]}...")
                log("   Waiting for Spectacles to connect...")
                log("=" * 60)

                # Handle incoming messages from relay
                await handle_relay_messages(websocket)

        except websockets.exceptions.ConnectionClosed as e:
            log(f"Connection to relay closed: {e}")
        except Exception as e:
            log(f"Error connecting to relay: {e}")

        # Reset state
        relay_connection = None
        spectacles_connected = False

        # Wait before reconnecting
        log(f"Reconnecting to relay in {RECONNECT_DELAY} seconds...")
        await asyncio.sleep(RECONNECT_DELAY)


async def main():
    """Start the relay client and file watcher."""
    global sun_times_data, location_data

    log("=" * 60)
    log("STARTING MAC SERVER (RELAY CLIENT MODE)")
    log("=" * 60)
    log(f"Relay URL: {RELAY_URL}")
    log(f"Device Secret: {DEVICE_SECRET[:8]}..." if DEVICE_SECRET else "Device Secret: NOT SET")
    log("=" * 60)

    if not DEVICE_SECRET:
        log("")
        log("ERROR: DEVICE_SECRET not configured!")
        log("   Please set DEVICE_SECRET in .env file")
        log("   Both Mac server and Spectacles need the same secret")
        log("")
        return

    # Fetch and log location and sun times
    log("")
    log("Fetching sun times...")
    # Hardcoded to Vienna, 1st District (Innere Stadt)
    location = {
        'city': 'Vienna',
        'country': 'Austria',
        'lat': 48.2082,
        'lon': 16.3738,
        'timezone': 'Europe/Vienna'
    }
    location_data = location  # Store globally
    log(f"Location: {location['city']}, {location['country']}")
    log(f"   Coordinates: {location['lat']:.4f}, {location['lon']:.4f}")
    log(f"   Timezone: {location['timezone']}")

    sun_times = await fetch_sun_times(location['lat'], location['lon'])
    if sun_times:
        sun_times_data = sun_times  # Store globally
        log("")
        log("Sun Times for Today (local time):")
        log(f"   Astronomical Dawn: {sun_times['astronomical_dawn']}")
        log(f"   Sunrise:           {sun_times['sunrise']}")
        log(f"   Solar Noon:        {sun_times['solar_noon']}")
        log(f"   Sunset:            {sun_times['sunset']}")
        log(f"   Astronomical Dusk: {sun_times['astronomical_dusk']}")
    else:
        log("Failed to fetch sun times")
    log("")
    log("=" * 60)

    # Get the event loop for file watchers
    loop = asyncio.get_event_loop()

    # Set up file watcher for Claude Code conversations
    claude_projects_path = Path.home() / '.claude' / 'projects'
    claude_observer = None

    if not claude_projects_path.exists():
        log(f"WARNING: Claude Code projects directory not found: {claude_projects_path}")
        log(f"   Conversation monitoring will not work!")
    else:
        log(f"Monitoring Claude Code conversations in:")
        log(f"   {claude_projects_path}")

        # Create and start the observer
        event_handler = ClaudeConversationHandler(loop)
        claude_observer = Observer()
        claude_observer.schedule(event_handler, str(claude_projects_path), recursive=True)
        claude_observer.start()
        log(f"Claude conversation watcher started successfully")

    # Set up file watcher for repository changes (git diff)
    repo_observer = None
    log(f"Monitoring repository for git diff:")
    log(f"   {REPO_PATH}")
    repo_handler = RepoChangeHandler(loop)
    repo_observer = Observer()
    repo_observer.schedule(repo_handler, str(REPO_PATH), recursive=True)
    repo_observer.start()
    log(f"Repository watcher started successfully")

    log("=" * 60)
    log("")

    try:
        # Start both the relay connection and screenshot loop concurrently
        await asyncio.gather(
            connect_to_relay(),
            jpeg_screenshot_loop()
        )
    except Exception as e:
        log(f"FATAL ERROR: {e}")
        log(f"   Traceback: {traceback.format_exc()}")
    finally:
        if claude_observer:
            claude_observer.stop()
            claude_observer.join()
        if repo_observer:
            repo_observer.stop()
            repo_observer.join()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("")
        log("SERVER STOPPED by user (Ctrl+C)")
    except Exception as e:
        log(f"UNEXPECTED ERROR: {e}")
        log(f"   Traceback: {traceback.format_exc()}")
