/**
 * WebSocket Relay Server for Spectacles-Claude (Deno Deploy)
 *
 * A full WebSocket proxy that forwards ALL traffic between Mac server and Spectacles.
 * The relay acts as the middleman for all data - screen content, text, everything.
 *
 * Architecture:
 *   - Mac server connects to: wss://relay/ws/server?device_secret=XXX
 *   - Spectacles connects to: wss://relay/ws/client?device_secret=XXX
 *   - Relay matches them by device_secret and forwards all messages
 *
 * RUNNING LOCALLY:
 *     deno run --allow-net relay_server_deno.ts
 *
 * DEPLOYING TO DENO DEPLOY:
 *     1. Push to GitHub
 *     2. Connect repo at dash.deno.com
 *     3. Select relay_server_deno.ts as entrypoint
 *     4. Deploy! URL: your-project.deno.dev
 */

// Connection types
type ConnectionType = "server" | "client";

interface Connection {
  socket: WebSocket;
  type: ConnectionType;
  deviceSecret: string;
  connectedAt: number;
  messageCount: number;
  bytesTransferred: number;
}

interface DevicePair {
  server: Connection | null;
  client: Connection | null;
  createdAt: number;
}

// Store all device pairs by device_secret
const devicePairs = new Map<string, DevicePair>();

// CORS headers for HTTP responses
const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...corsHeaders,
    },
  });
}

function errorResponse(detail: string, status = 400): Response {
  return jsonResponse({ error: detail }, status);
}

function log(message: string, deviceSecret?: string): void {
  const timestamp = new Date().toISOString();
  const prefix = deviceSecret ? `[${deviceSecret.substring(0, 8)}...]` : "";
  console.log(`${timestamp} ${prefix} ${message}`);
}

function getOrCreatePair(deviceSecret: string): DevicePair {
  let pair = devicePairs.get(deviceSecret);
  if (!pair) {
    pair = {
      server: null,
      client: null,
      createdAt: Date.now(),
    };
    devicePairs.set(deviceSecret, pair);
    log("Created new device pair", deviceSecret);
  }
  return pair;
}

function cleanupConnection(deviceSecret: string, type: ConnectionType): void {
  const pair = devicePairs.get(deviceSecret);
  if (!pair) return;

  if (type === "server") {
    pair.server = null;
    // Notify client that server disconnected
    if (pair.client?.socket.readyState === WebSocket.OPEN) {
      pair.client.socket.send(JSON.stringify({
        type: "relay_notification",
        event: "server_disconnected",
        message: "Mac server has disconnected",
      }));
    }
  } else {
    pair.client = null;
    // Notify server that client disconnected
    if (pair.server?.socket.readyState === WebSocket.OPEN) {
      pair.server.socket.send(JSON.stringify({
        type: "relay_notification",
        event: "client_disconnected",
        message: "Spectacles client has disconnected",
      }));
    }
  }

  // Clean up empty pairs
  if (!pair.server && !pair.client) {
    devicePairs.delete(deviceSecret);
    log("Removed empty device pair", deviceSecret);
  }
}

function handleWebSocket(
  request: Request,
  type: ConnectionType,
  deviceSecret: string
): Response {
  const { socket, response } = Deno.upgradeWebSocket(request);

  const pair = getOrCreatePair(deviceSecret);

  // Close existing connection of same type if present
  const existingConnection = type === "server" ? pair.server : pair.client;
  if (existingConnection?.socket.readyState === WebSocket.OPEN) {
    log(`Closing existing ${type} connection (replaced by new one)`, deviceSecret);
    existingConnection.socket.close(1000, "Replaced by new connection");
  }

  // Create new connection
  const connection: Connection = {
    socket,
    type,
    deviceSecret,
    connectedAt: Date.now(),
    messageCount: 0,
    bytesTransferred: 0,
  };

  // Store connection
  if (type === "server") {
    pair.server = connection;
  } else {
    pair.client = connection;
  }

  socket.onopen = () => {
    log(`${type} connected`, deviceSecret);

    // Notify the other side about the new connection
    const otherConnection = type === "server" ? pair.client : pair.server;
    if (otherConnection?.socket.readyState === WebSocket.OPEN) {
      otherConnection.socket.send(JSON.stringify({
        type: "relay_notification",
        event: type === "server" ? "server_connected" : "client_connected",
        message: `${type === "server" ? "Mac server" : "Spectacles client"} has connected`,
      }));
    }

    // Send confirmation to the connecting party
    socket.send(JSON.stringify({
      type: "relay_notification",
      event: "connected",
      message: `Connected to relay as ${type}`,
      peerConnected: otherConnection?.socket.readyState === WebSocket.OPEN,
    }));
  };

  socket.onmessage = (event) => {
    connection.messageCount++;
    const dataSize = typeof event.data === "string"
      ? event.data.length
      : (event.data as ArrayBuffer).byteLength;
    connection.bytesTransferred += dataSize;

    // Determine the target (forward to the other side)
    const targetConnection = type === "server" ? pair.client : pair.server;

    if (targetConnection?.socket.readyState === WebSocket.OPEN) {
      // Forward the message as-is (supports both text and binary)
      targetConnection.socket.send(event.data);
    } else {
      // No peer connected - optionally notify sender
      // We don't spam with notifications for every message, just log occasionally
      if (connection.messageCount % 100 === 1) {
        log(`No ${type === "server" ? "client" : "server"} connected to receive messages`, deviceSecret);
      }
    }
  };

  socket.onclose = (event) => {
    log(`${type} disconnected (code: ${event.code}, reason: ${event.reason || "none"})`, deviceSecret);
    cleanupConnection(deviceSecret, type);
  };

  socket.onerror = (event) => {
    log(`${type} error: ${event}`, deviceSecret);
  };

  return response;
}

function handleHealth(): Response {
  const pairs = Array.from(devicePairs.entries());
  const activePairs = pairs.filter(([_, p]) => p.server && p.client).length;

  return jsonResponse({
    status: "healthy",
    timestamp: new Date().toISOString(),
    connections: {
      totalPairs: devicePairs.size,
      activePairs,
      totalServers: pairs.filter(([_, p]) => p.server).length,
      totalClients: pairs.filter(([_, p]) => p.client).length,
    },
  });
}

function handleStatus(): Response {
  const pairs: Record<string, unknown> = {};

  for (const [deviceSecret, pair] of devicePairs) {
    const maskedSecret = deviceSecret.substring(0, 8) + "...";
    pairs[maskedSecret] = {
      server: pair.server ? {
        connected: pair.server.socket.readyState === WebSocket.OPEN,
        connectedAt: new Date(pair.server.connectedAt).toISOString(),
        messageCount: pair.server.messageCount,
        bytesTransferred: pair.server.bytesTransferred,
      } : null,
      client: pair.client ? {
        connected: pair.client.socket.readyState === WebSocket.OPEN,
        connectedAt: new Date(pair.client.connectedAt).toISOString(),
        messageCount: pair.client.messageCount,
        bytesTransferred: pair.client.bytesTransferred,
      } : null,
      paired: !!(pair.server?.socket.readyState === WebSocket.OPEN &&
                 pair.client?.socket.readyState === WebSocket.OPEN),
      createdAt: new Date(pair.createdAt).toISOString(),
    };
  }

  return jsonResponse({
    pairs,
    summary: {
      totalPairs: devicePairs.size,
      activePairs: Object.values(pairs).filter((p: any) => p.paired).length,
    },
  });
}

function handleRoot(): Response {
  return jsonResponse({
    name: "Spectacles WebSocket Relay",
    version: "2.0.0",
    description: "Full WebSocket proxy that forwards all traffic between Mac server and Spectacles",
    endpoints: {
      "GET /": "This info page",
      "GET /health": "Health check with connection counts",
      "GET /status": "Detailed status of all connected pairs",
      "WS /ws/server?device_secret=XXX": "WebSocket endpoint for Mac server",
      "WS /ws/client?device_secret=XXX": "WebSocket endpoint for Spectacles client",
    },
    usage: {
      step1: "Mac server connects to: wss://relay/ws/server?device_secret=YOUR_SECRET",
      step2: "Spectacles connects to: wss://relay/ws/client?device_secret=YOUR_SECRET",
      step3: "All messages are automatically forwarded between them",
    },
  });
}

Deno.serve({ port: 8000 }, (request: Request): Response => {
  const url = new URL(request.url);
  const path = url.pathname;
  const method = request.method;

  // Handle CORS preflight
  if (method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders });
  }

  // WebSocket endpoints
  if (path === "/ws/server" || path === "/ws/client") {
    const deviceSecret = url.searchParams.get("device_secret");

    if (!deviceSecret) {
      return errorResponse("Missing required query parameter: device_secret", 400);
    }

    if (deviceSecret.length < 8) {
      return errorResponse("device_secret must be at least 8 characters", 400);
    }

    // Check for WebSocket upgrade request
    const upgrade = request.headers.get("upgrade") || "";
    if (upgrade.toLowerCase() !== "websocket") {
      return errorResponse("Expected WebSocket upgrade request", 400);
    }

    const type: ConnectionType = path === "/ws/server" ? "server" : "client";
    return handleWebSocket(request, type, deviceSecret);
  }

  // HTTP endpoints
  if (path === "/" && method === "GET") {
    return handleRoot();
  }

  if (path === "/health" && method === "GET") {
    return handleHealth();
  }

  if (path === "/status" && method === "GET") {
    return handleStatus();
  }

  return errorResponse("Not found", 404);
});
