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
import time
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

# Screen dimensions - set during client connection
screen_width = None
screen_height = None

# Constants for compression
RECTANGLES_PER_PACKET = 100000  # 100,000 rectangles per packet

def log(message):
    """Print a timestamped log message."""
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}")


def merge_pixels_to_rectangles(changed_pixels):
    """
    Convert changed pixels into minimum number of rectangles.
    Greedy approach: maximize X first, then Y.
    """
    rectangles = []
    visited = set()

    # Process pixels in normal screen order (top to bottom)
    for y in range(screen_height):
        for x in range(screen_width):
            # Direct lookup - no additional flipping needed
            if (x, y) in changed_pixels and (x, y) not in visited:
                color = changed_pixels[(x, y)]

                # Grow rectangle: X first, then Y
                rect = grow_rectangle_greedy(changed_pixels, x, y, color, visited)
                rectangles.append(rect)

    return rectangles


def grow_rectangle_greedy(changed_pixels, start_x, start_y, color, visited):
    """
    Grow rectangle greedily: expand X as far as possible, then Y.
    """
    # Step 1: Expand X (go right as far as possible)
    max_x = start_x
    while (max_x + 1, start_y) in changed_pixels and \
          changed_pixels[(max_x + 1, start_y)] == color and \
          (max_x + 1, start_y) not in visited:
        max_x += 1

    # Step 2: Expand Y (go down as far as possible with the full width)
    max_y = start_y
    can_expand = True

    while can_expand:
        test_y = max_y + 1

        # Check if entire next row has the same color
        for test_x in range(start_x, max_x + 1):
            if (test_x, test_y) not in changed_pixels or \
               changed_pixels[(test_x, test_y)] != color or \
               (test_x, test_y) in visited:
                can_expand = False
                break

        if can_expand:
            max_y = test_y

    # Step 3: Mark all pixels in rectangle as visited
    for y in range(start_y, max_y + 1):
        for x in range(start_x, max_x + 1):
            visited.add((x, y))

    # Step 4: Return the rectangle with compact format
    return {
        'x': start_x,
        'y': start_y,
        'w': max_x - start_x + 1,
        'h': max_y - start_y + 1,
        'r': color[0],
        'g': color[1],
        'b': color[2]
    }

def generate_screenshot_packets(screenshot, pixels_per_packet=100000):
    """Generator that yields screenshot packets."""
    width, height = screenshot.size
    screenshot = screenshot.convert('RGB')
    pixels = screenshot.load()

    pixel_buffer = []

    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            pixel_buffer.append([x, height - 1 - y, r, g, b])

            if len(pixel_buffer) >= pixels_per_packet:
                packet = {
                    'type': 'screenshot_packet',
                    'pixels': pixel_buffer
                }
                yield packet
                pixel_buffer = []

    if pixel_buffer:
        packet = {
            'type': 'screenshot_packet',
            'pixels': pixel_buffer
        }
        yield packet

def quantize_color(color, levels=16):
    """Quantize color to reduce precision and improve compression."""
    step = 256 // levels
    return tuple((c // step) * step + step // 2 for c in color)

def generate_delta_packets(prev_screenshot, new_screenshot):
    """Generator that yields only changed pixels as rectangles."""
    prev_screenshot = prev_screenshot.convert('RGB')
    new_screenshot = new_screenshot.convert('RGB')
    prev_pixels = prev_screenshot.load()
    new_pixels = new_screenshot.load()

    # Step 1: Find all changed pixels (with color quantization)
    changed_pixels = {}

    for y in range(screen_height):
        for x in range(screen_width):
            prev_r, prev_g, prev_b = prev_pixels[x, y]
            new_r, new_g, new_b = new_pixels[x, y]

            if prev_r != new_r or prev_g != new_g or prev_b != new_b:
                # Quantize the color to reduce variations
                quantized_color = quantize_color((new_r, new_g, new_b))
                # No Y-flipping - use normal coordinates
                changed_pixels[(x, y)] = quantized_color

    # If no changes, don't send anything
    if not changed_pixels:
        return

    # Step 2: Convert changed pixels into rectangles
    rectangles = merge_pixels_to_rectangles(changed_pixels)

    # Log compression stats
    log(f"📊 Compression: {len(changed_pixels)} pixels → {len(rectangles)} rectangles")
    if rectangles:
        compression_ratio = len(changed_pixels) / len(rectangles)
        log(f"   Average rectangle size: {compression_ratio:.1f} pixels")

    # Step 3: Send rectangles in batches using slicing
    total_json_size = 0
    total_binary_size = 0

    for i in range(0, len(rectangles), RECTANGLES_PER_PACKET):
        batch = rectangles[i:i + RECTANGLES_PER_PACKET]
        packet = {
            'type': 'rectangle_packet',
            'rectangles': batch
        }

        # Calculate sizes for comparison
        json_size = len(json.dumps(packet))
        # Binary would be: 11 bytes per rectangle + small header
        binary_size = len(batch) * 11 + 8

        total_json_size += json_size
        total_binary_size += binary_size

        log(f"📦 Packet: {len(batch)} rectangles, JSON: {json_size:,} bytes, Binary would be: {binary_size:,} bytes")
        log(f"   Reduction: {json_size/binary_size:.1f}x smaller with binary")

        yield packet

    if total_json_size > 0:
        log(f"📊 Total: JSON: {total_json_size:,} bytes, Binary: {total_binary_size:,} bytes")
        log(f"   Overall reduction: {total_json_size/total_binary_size:.1f}x with binary")


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

    # Print FULL message being sent
    log("=" * 60)
    log("📤 FULL MESSAGE BEING SENT:")
    log("=" * 60)
    log(message)
    log("=" * 60)
    global current_client

    log(f"   Message length: {len(message)} characters")

    # Send to THE client if connected
    if current_client:
        try:
            await current_client.send(message)
            log(f"   ✅ Sent to {current_client.remote_address}")
        except Exception as e:
            log(f"   ❌ Failed to send to client: {e}")
            # Clear the client if sending failed
            current_client = None
            log(f"   Client cleared due to send failure")
    else:
        log(f"   ⚠️  No client connected - message not sent")

async def continuous_delta_updates(websocket, prev_screenshot):
    """Recursively capture and send delta updates."""
    new_screenshot = ImageGrab.grab()
    # Resize to 1920x1080 for consistent quality
    new_screenshot = new_screenshot.resize((1920, 1080), Image.LANCZOS)

    total_bytes = 0
    packets_sent = 0
    start_time = time.time()

    for packet in generate_delta_packets(prev_screenshot, new_screenshot):
        packet_json = json.dumps(packet)
        packet_size = len(packet_json)
        total_bytes += packet_size
        packets_sent += 1

        log(f"📤 Sending packet {packets_sent}: {packet_size:,} bytes ({len(packet['rectangles'])} rectangles)")
        await websocket.send(packet_json)

    if packets_sent > 0:
        elapsed = time.time() - start_time
        log(f"📊 Frame summary: {packets_sent} packets, {total_bytes:,} bytes total, {elapsed*1000:.1f}ms")
        log(f"   Data rate: {total_bytes/1024:.1f} KB/frame")

    await continuous_delta_updates(websocket, new_screenshot)

async def handle_client(websocket):
    """Handle a client connection."""
    global sun_times_data, location_data, current_client, screen_width, screen_height

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
        # Set fixed dimensions for consistency
        screen_width, screen_height = 1920, 1080
        log(f"📸 Fixed screen dimensions: {screen_width}x{screen_height}")

        # Get color and phase based on sun position
        color, phase = get_sun_phase_color(sun_times_data) if sun_times_data else ((1.0, 0.0, 0.0, 1.0), "night")

        # Create single initialization message
        init_message = {
            'type': 'init',
            'width': screen_width,
            'height': screen_height,
            'color': {
                'r': color[0],
                'g': color[1],
                'b': color[2],
                'a': color[3]
            },
            'last_message': last_sent_message if last_sent_message else None
        }

        log(f"📤 Sending init to {client_addr}: {phase} - {color} - {screen_width}x{screen_height}")
        await websocket.send(json.dumps(init_message))
        log(f"✅ Init message sent successfully")

        # Wait for acknowledgement from client
        log(f"⏳ Waiting for acknowledgement from {client_addr}...")
        ack = await websocket.recv()
        log(f"✅ Received acknowledgement: {ack}")

        # Start with black screen (no initial full screenshot)
        prev_screenshot = Image.new('RGB', (screen_width, screen_height), (0, 0, 0))

        # Start recursive delta updates
        log(f"🔄 Starting recursive delta updates")
        await continuous_delta_updates(websocket, prev_screenshot)

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
