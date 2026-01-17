#!/usr/bin/env python3
"""
WebSocket server for Spectacles that accepts direct connections.
Sends screen content to connected Spectacles in real-time.
"""

import asyncio
import websockets
import aiohttp
import datetime
import traceback
import json
import os
import base64
import io
import time
import hashlib
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import ImageGrab, Image
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Server configuration
SERVER_PORT = int(os.environ.get("SERVER_PORT", "8765"))
RECONNECT_DELAY = 10  # seconds between reconnection attempts

# Store the WebSocket connection to Spectacles client
client_connection = None

# Store last sent message to avoid duplicates
last_sent_message = None

# Store sun times for color calculation
sun_times_data = None
location_data = None

# Flag to track if Spectacles client is connected
spectacles_connected = False

# Columns JSON file (written by realtime-claude mac-server.js)
COLUMNS_JSON_PATH = Path.home() / ".git-diff-columns.json"


LOG_FILE = Path("/tmp/spectacles-server.log")

def log(message):
    """Print a timestamped log message to stdout and file."""
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    line = f"[{timestamp}] {message}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# Cache last hash to avoid sending unchanged diff
_last_columns_hash = None


def columns_to_piped_format(columns):
    """Convert columns array to piped display format for Spectacles."""
    if not columns:
        return ""

    LINE_WIDTH = 100
    rows_per_col = [col.split('\n') for col in columns]
    num_rows = max(len(rows) for rows in rows_per_col)

    for rows in rows_per_col:
        while len(rows) < num_rows:
            rows.append('')

    def format_cell(cell):
        if cell.startswith('===') or cell.startswith('##'):
            return cell.center(LINE_WIDTH)
        return cell.ljust(LINE_WIDTH)

    result_lines = []
    for row_idx in range(num_rows):
        row_parts = [format_cell(rows_per_col[col_idx][row_idx]) for col_idx in range(len(columns))]
        result_lines.append("| " + " | ".join(row_parts) + " |")

    return '\n'.join(result_lines)


async def send_git_diff(force: bool = False):
    """Send git diff from JSON file to Spectacles."""
    global client_connection, spectacles_connected, _last_columns_hash

    log(f"send_git_diff called: force={force}")

    if not COLUMNS_JSON_PATH.exists():
        log(f"No columns JSON file at {COLUMNS_JSON_PATH}")
        return

    try:
        data = json.loads(COLUMNS_JSON_PATH.read_text())
        columns = data.get('columns', [])
        current_hash = data.get('hash', '')
    except Exception as e:
        log(f"Failed to read columns JSON: {e}")
        return

    if not force and current_hash and current_hash == _last_columns_hash:
        return
    _last_columns_hash = current_hash

    formatted_diff = columns_to_piped_format(columns)

    if not client_connection or not spectacles_connected:
        log("Cannot send git diff - no Spectacles connected")
        return

    message = {
        'type': 'git_diff',
        'data': formatted_diff
    }

    log("=" * 60)
    log("SENDING GIT DIFF:")
    log(f"   {len(columns)} columns -> {len(formatted_diff)} chars")
    log("=" * 60)

    try:
        await client_connection.send(json.dumps(message))
        log("   Git diff sent to Spectacles")
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
            asyncio.run_coroutine_threadsafe(
                send_text_message(message),
                self.loop
            )


class ColumnsJsonHandler(FileSystemEventHandler):
    """Handles file system events for the columns JSON file."""

    def __init__(self, loop):
        self.loop = loop
        super().__init__()

    def on_modified(self, event):
        """Called when the columns JSON file is modified."""
        if event.is_directory:
            return

        if Path(event.src_path).name == '.git-diff-columns.json':
            log("Columns JSON file changed")
            asyncio.run_coroutine_threadsafe(
                send_git_diff(force=True),
                self.loop
            )


async def send_text_message(message):
    """Send a text message to Spectacles."""
    global last_sent_message, client_connection, spectacles_connected

    # Avoid sending duplicate messages
    if message == last_sent_message:
        log("Skipping duplicate message")
        return

    last_sent_message = message

    if not client_connection or not spectacles_connected:
        log("Cannot send text - no Spectacles connected")
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
        await client_connection.send(json_string)
        log("   Text message sent to Spectacles")
    except Exception as e:
        log(f"   Failed to send text: {e}")


async def jpeg_screenshot_loop():
    """Capture and send JPEG screenshots, skip if unchanged."""
    global client_connection, spectacles_connected

    prev_hash = None

    while True:
        # Only send if Spectacles is connected
        if not client_connection or not spectacles_connected:
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
            await client_connection.send(message)

            # Wait 1 second before next frame
            await asyncio.sleep(1.0)

        except websockets.exceptions.ConnectionClosed:
            log("Connection to Spectacles lost during screenshot send, waiting for reconnection...")
            await asyncio.sleep(1.0)
            continue
        except Exception as e:
            log(f"Error in screenshot loop: {e}")
            await asyncio.sleep(1.0)


async def handle_client_messages(websocket):
    """Handle incoming messages from Spectacles client."""
    global spectacles_connected, sun_times_data

    async for message in websocket:
        try:
            data = json.loads(message)
            msg_type = data.get('type', '')

            if msg_type == 'hello':
                # Hello message from Spectacles - initiate handshake
                log("")
                log("*" * 60)
                log("*" * 60)
                log("***  HELLO RECEIVED FROM SPECTACLES  ***")
                log("*" * 60)
                log("*" * 60)
                log(f"   Raw message: {message}")
                log(f"   Timestamp: {datetime.datetime.now().isoformat()}")
                log("   INITIATING HANDSHAKE...")
                log("*" * 60)

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

                # Send git diff immediately after init
                await send_git_diff(force=True)

            elif msg_type == 'ack':
                # Acknowledgment from Spectacles
                log(f"Received ack from Spectacles")

            elif msg_type == 'display_stats':
                # Display statistics from Spectacles
                panel = data.get('panel', 'unknown')
                chars = data.get('chars', 0)
                columns = data.get('columns', 0)
                rows = data.get('rows', 0)
                log("=" * 60)
                log(f"DISPLAY STATS FROM SPECTACLES ({panel}):")
                log(f"   Columns: {columns}")
                log(f"   Rows: {rows}")
                log(f"   Total chars: {chars}")
                log("=" * 60)

            else:
                # Other messages from Spectacles
                log(f"Received from Spectacles: {msg_type}")

        except json.JSONDecodeError:
            # Plain text message (like "ACK")
            if message.upper() == "ACK":
                log("Received ACK from Spectacles")
            else:
                log(f"Received non-JSON message: {message[:100]}")
        except Exception as e:
            log(f"Error handling client message: {e}")


async def handle_client(websocket):
    """Handle a single client connection."""
    global client_connection, spectacles_connected, sun_times_data

    client_connection = websocket
    spectacles_connected = True

    log("=" * 60)
    log("SPECTACLES CONNECTED")
    log("=" * 60)
    log(f"   Remote address: {websocket.remote_address}")
    log("=" * 60)

    # Send initialization message immediately
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

    try:
        # Handle incoming messages
        await handle_client_messages(websocket)
    except websockets.exceptions.ConnectionClosed as e:
        log(f"Client connection closed: {e}")
    finally:
        client_connection = None
        spectacles_connected = False
        log("=" * 60)
        log("SPECTACLES DISCONNECTED")
        log("=" * 60)


async def start_server():
    """Start the WebSocket server."""
    log("=" * 60)
    log("STARTING WEBSOCKET SERVER")
    log("=" * 60)
    log(f"   Port: {SERVER_PORT}")
    log("   Waiting for Spectacles to connect...")
    log("=" * 60)

    async with websockets.serve(
        handle_client,
        "0.0.0.0",
        SERVER_PORT,
        ping_interval=None,  # Disable ping - Spectacles doesn't respond to pings
        ping_timeout=None,
    ) as server:
        log(f"WebSocket server listening on port {SERVER_PORT}")
        await asyncio.Future()  # Run forever


async def main():
    """Start the WebSocket server and file watchers."""
    global sun_times_data, location_data

    log("=" * 60)
    log("STARTING MAC SERVER (DIRECT CONNECTION MODE)")
    log("=" * 60)
    log(f"Server Port: {SERVER_PORT}")
    log("=" * 60)

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

    # Start columns JSON watcher (watches ~/.git-diff-columns.json from mac-server)
    columns_observer = None
    columns_json_dir = COLUMNS_JSON_PATH.parent
    if columns_json_dir.exists():
        columns_handler = ColumnsJsonHandler(loop)
        columns_observer = Observer()
        columns_observer.schedule(columns_handler, str(columns_json_dir), recursive=False)
        columns_observer.start()
        log(f"Columns JSON watcher started on {columns_json_dir}")

    # Trigger initial git diff on startup
    log("Triggering initial git diff...")
    asyncio.run_coroutine_threadsafe(send_git_diff(force=True), loop)

    log("=" * 60)
    log("")

    # Main loop - never exit, always retry
    while True:
        try:
            # Start both the server and screenshot loop concurrently
            await asyncio.gather(
                start_server(),
                jpeg_screenshot_loop()
            )
        except asyncio.CancelledError:
            log("Tasks cancelled, shutting down...")
            break
        except Exception as e:
            log(f"ERROR in main loop: {e}")
            log(f"   Traceback: {traceback.format_exc()}")
            log(f"Restarting main loop in {RECONNECT_DELAY} seconds...")
            await asyncio.sleep(RECONNECT_DELAY)
            # Continue the while loop to restart
            continue

    # Cleanup only happens on graceful shutdown
    if claude_observer:
        claude_observer.stop()
        claude_observer.join()
    if columns_observer:
        columns_observer.stop()
        columns_observer.join()


if __name__ == "__main__":
    # Outer loop - never exit unless Ctrl+C
    while True:
        try:
            asyncio.run(main())
            # If main() returns normally, restart
            log("main() returned, restarting in 5 seconds...")
            import time
            time.sleep(5)
        except KeyboardInterrupt:
            log("")
            log("SERVER STOPPED by user (Ctrl+C)")
            break  # Only exit on Ctrl+C
        except Exception as e:
            log(f"UNEXPECTED ERROR: {e}")
            log(f"   Traceback: {traceback.format_exc()}")
            log(f"Restarting entire server in {RECONNECT_DELAY} seconds...")
            import time
            time.sleep(RECONNECT_DELAY)
            # Continue to restart
