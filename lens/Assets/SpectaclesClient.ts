import { DEVICE_SECRET, RELAY_URL } from "./secrets";

@component
export class SpectaclesClient extends BaseScriptComponent {
    @input
    textComponent: Text;

    @input
    gitDiffText: Text;

    @input
    image: Image;

    // Build WebSocket URL for relay connection
    private readonly relayWsUrl = `${RELAY_URL.replace('https', 'wss')}/ws/client?device_secret=${DEVICE_SECRET}`;

    private startTime: number;
    private socket: WebSocket = null;
    private connected: boolean = false;
    private internetModule: any;
    private lastReconnectAttempt: number = 0;
    private reconnectDelay: number = 3.0;  // Try reconnecting every 3 seconds
    private lastPrintTime: number = 0;
    private printDelay: number = 1.0;  // Print status every 1 second
    private peerConnected: boolean = false;
    private lastHelloTime: number = 0;
    private helloCount: number = 0;

    private readonly MAX_ROWS_PER_COLUMN = 100;
    private readonly MAX_DISPLAY_ROWS = 500;
    private readonly MAX_CONTENT_WIDTH = 100;
    private completeConversation: string[] = [];

    // Git diff formatting constants
    private readonly GIT_DIFF_LINE_WIDTH = 60;
    private readonly GIT_DIFF_ROWS_PER_COLUMN = 100;
    private readonly MAX_GIT_DIFF_COLUMNS = 20;

    onAwake() {
        print("ServerTextDisplay: Script initialized");
        this.startTime = getTime();

        // Load the InternetModule for WebSocket support
        this.internetModule = require("LensStudio:InternetModule");

        // Set lastReconnectAttempt to current time minus 2 seconds
        // This will trigger connection attempt after 1 second (since reconnectDelay is 3)
        this.lastReconnectAttempt = getTime() - 2.0;

        this.createEvent("UpdateEvent").bind(this.onUpdate.bind(this));
        print("ServerTextDisplay: Update event bound");

        // Update text to show initialized state
        this.updateText("Initialized");
    }

    processJSONMessage(message: any) {
        // Handle message based on type
        switch (message.type) {
            case "relay_notification":
                // Handle relay notifications about peer connection status
                print("SpectaclesClient: Relay notification - " + message.event);
                if (message.event === "peer_connected" || message.event === "server_connected") {
                    this.peerConnected = true;
                    this.updateText("Mac connected to relay!");
                    // Resend hello to trigger handshake
                    if (this.socket && this.connected) {
                        this.socket.send(JSON.stringify({ type: "hello" }));
                        print("SpectaclesClient: Resent hello after peer connected");
                    }
                } else if (message.event === "peer_disconnected") {
                    this.peerConnected = false;
                    this.updateText("Mac disconnected from relay");
                }
                break;

            case "init":
                print("ServerTextDisplay: Received init message");

                // Set color
                const color = message.color;
                this.updateColor(color.r, color.g, color.b, color.a);

                // Display last message if present
                if (message.last_message) {
                    this.updateText(message.last_message);
                }

                // Send acknowledgement
                print("ServerTextDisplay: Sending acknowledgement");
                this.socket.send("ACK");
                break;

            case "text":
                print("ServerTextDisplay: Received text message");
                // Display the text data
                this.updateText(message.data);
                break;

            case "git_diff":
                print("ServerTextDisplay: Received git_diff message");
                this.updateGitDiffText(message.data);
                break;

            case "jpeg":
                print(`ServerTextDisplay: Received JPEG (base64 length: ${message.data.length})`);
                Base64.decodeTextureAsync(
                    message.data,
                    (texture: Texture) => {
                        print("ServerTextDisplay: JPEG decoded successfully");
                        if (this.image) {
                            this.image.mainPass.baseTex = texture;
                        }
                        if (this.socket) {
                            this.socket.send("ACK");
                        }
                    },
                    () => {
                        throw new Error("JPEG decode failed");
                    }
                );
                break;

            default:
                print("ServerTextDisplay: Unknown message type: " + message.type);
                break;
        }
    }

    connectToServer() {
        if (global.deviceInfoSystem.isEditor()) {
            print("Running in Lens Studio editor - skipping WebSocket connection");
            return;
        }

        print("SpectaclesClient: Connecting to relay at " + this.relayWsUrl);

        try {
            // Create WebSocket connection directly to relay
            this.socket = this.internetModule.createWebSocket(this.relayWsUrl);

            // Set up event handlers
            this.socket.onopen = (event) => {
                print("SpectaclesClient: Connected to relay!");
                this.connected = true;
                this.updateText("Connected to relay, waiting for Mac...");
                // Send hello message to initiate handshake
                this.socket.send(JSON.stringify({ type: "hello" }));
                print("SpectaclesClient: Sent hello message");
            };

            this.socket.onmessage = async (event) => {
                let messageText: string;
                if (event.data instanceof Blob) {
                    messageText = await event.data.text();
                } else {
                    messageText = event.data;
                }

                try {
                    const message = JSON.parse(messageText);
                    this.processJSONMessage(message);
                } catch (error) {
                    print("SpectaclesClient: Error parsing message: " + error);
                }
            };

            this.socket.onerror = (event) => {
                print("SpectaclesClient: WebSocket error occurred");
                print("SpectaclesClient: Error event details: " + JSON.stringify(event));
                print("SpectaclesClient: Relay URL: " + this.relayWsUrl);
                print("SpectaclesClient: Socket state: " + (this.socket ? this.socket.readyState : "null"));
                this.connected = false;
                this.peerConnected = false;
                this.updateText("Connection error!");
            };

            this.socket.onclose = (event) => {
                print("SpectaclesClient: WebSocket closed");
                print("SpectaclesClient: Close code: " + event.code);
                print("SpectaclesClient: Close reason: " + event.reason);
                print("SpectaclesClient: Was clean: " + event.wasClean);
                this.connected = false;
                this.peerConnected = false;
                this.socket = null;
                this.updateText("Disconnected - will reconnect...");
            };

        } catch (error) {
            print("SpectaclesClient: Failed to create WebSocket");
            print("SpectaclesClient: Error: " + error);
            print("SpectaclesClient: Error type: " + typeof error);
            print("SpectaclesClient: Error message: " + (error.message || "No message"));
            print("SpectaclesClient: Relay URL: " + this.relayWsUrl);
            this.updateText("Failed to connect!");
        }
    }

    sendMessage(message: string) {
        if (this.socket && this.connected) {
            print("ServerTextDisplay: Sending message: " + message);
            this.socket.send(message);
        } else {
            print("ServerTextDisplay: Cannot send message - not connected");
        }
    }

    disconnect() {
        if (this.socket) {
            this.socket.close();
            this.socket = null;
            this.connected = false;
        }
    }

    onUpdate() {
        // If not connected, show waiting message with elapsed time
        if (!this.connected) {
            const currentTime = getTime();

            // Try to reconnect every 3 seconds
            if (currentTime - this.lastReconnectAttempt >= this.reconnectDelay) {
                print("ServerTextDisplay: Attempting to reconnect...");
                const elapsed = currentTime - this.startTime;
                this.updateText(`Reconnecting... (${elapsed.toFixed(0)}s)`);
                this.lastReconnectAttempt = currentTime;
                this.connectToServer();
            }
        }

        // If connected to relay but peer not connected, send hello every 3s
        if (this.connected && !this.peerConnected) {
            const currentTime = getTime();
            if (currentTime - this.lastHelloTime >= 3.0) {
                this.helloCount++;
                this.socket.send(JSON.stringify({ type: "hello" }));
                this.updateText(`Connected to relay\nWaiting for Mac...\nSending hello #${this.helloCount}`);
                print("SpectaclesClient: Sending hello (waiting for Mac)");
                this.lastHelloTime = currentTime;
            }
        }
    }

    updateText(newText: string) {
        print("ServerTextDisplay: updateText called with: " + newText);
        if (this.textComponent) {
            // Split new text by newline and append to conversation
            const newLines = newText.split('\n');
            this.completeConversation.push(...newLines);

            // Format complete conversation into columns
            const formatted = this.formatConversation();

            // Set the text
            this.textComponent.text = formatted;

            print("ServerTextDisplay: Text component updated successfully");
        } else {
            print("ServerTextDisplay: ERROR - Text component not assigned!");
        }
    }

    formatConversation(): string {
        const allRows: string[] = [];
        const isFirstSegment: boolean[] = [];

        // Step 1: Convert each conversation line into formatted rows (NO labels, NO padding)
        for (let i = 0; i < this.completeConversation.length; i++) {
            const line = this.completeConversation[i];
            let remaining = line;
            let isFirst = true;

            while (remaining.length > 0) {
                if (remaining.length > this.MAX_CONTENT_WIDTH) {
                    let breakPoint = this.MAX_CONTENT_WIDTH;
                    const segment = remaining.substring(0, this.MAX_CONTENT_WIDTH);
                    const lastSpace = segment.lastIndexOf(' ');
                    if (lastSpace > 0) {
                        breakPoint = lastSpace;
                    }

                    allRows.push(remaining.substring(0, breakPoint));
                    isFirstSegment.push(isFirst);
                    remaining = remaining.substring(breakPoint);
                    isFirst = false;
                } else {
                    allRows.push(remaining);
                    isFirstSegment.push(isFirst);
                    break;
                }
            }
        }

        // Step 2: Take the last N rows to keep display stable when adding rows
        // Take MAX_DISPLAY_ROWS + (allRows.length % MAX_ROWS_PER_COLUMN) to ensure column alignment
        const remainder = allRows.length % this.MAX_ROWS_PER_COLUMN;
        const rowsToTake = Math.min(allRows.length, this.MAX_DISPLAY_ROWS + remainder);
        const startIndex = allRows.length - rowsToTake;
        const displayAllRows = allRows.slice(startIndex);
        const displayIsFirstSegment = isFirstSegment.slice(startIndex);

        // Trim old lines from completeConversation to prevent unbounded growth
        let linesToRemove = 0;
        for (let i = 0; i < startIndex; i++) {
            if (isFirstSegment[i]) {
                linesToRemove++;
            }
        }
        if (linesToRemove > 0) {
            this.completeConversation.splice(0, linesToRemove);
        }

        // Step 3: Calculate width for each column based on longest element
        const numColumns = Math.ceil(displayAllRows.length / this.MAX_ROWS_PER_COLUMN);
        const columnWidths: number[] = [];
        for (let col = 0; col < numColumns; col++) {
            const startIdx = col * this.MAX_ROWS_PER_COLUMN;
            const endIdx = Math.min(startIdx + this.MAX_ROWS_PER_COLUMN, displayAllRows.length);
            let maxWidth = 0;
            for (let i = startIdx; i < endIdx; i++) {
                maxWidth = Math.max(maxWidth, displayAllRows[i].length);
            }
            columnWidths.push(Math.min(maxWidth, this.MAX_CONTENT_WIDTH));
        }

        // Step 4: Create empty display grid
        const displayRows: string[] = [];
        for (let i = 0; i < this.MAX_ROWS_PER_COLUMN; i++) {
            displayRows.push('|');
        }

        // Step 5: Add bars and padding, then prepend to display grid
        for (let i = 0; i < displayAllRows.length; i++) {
            const rowIndex = i % this.MAX_ROWS_PER_COLUMN;
            const colIndex = Math.floor(i / this.MAX_ROWS_PER_COLUMN);
            const colWidth = columnWidths[colIndex];
            let formattedRow: string;

            if (displayIsFirstSegment[i]) {
                // First segment: left-aligned (padEnd)
                formattedRow = '|' + displayAllRows[i].padEnd(colWidth, ' ');
            } else {
                // Continuation: right-aligned (padStart)
                formattedRow = '|' + displayAllRows[i].padStart(colWidth, ' ');
            }

            displayRows[rowIndex] = displayRows[rowIndex] + ' ' + formattedRow;
        }

        // Step 6: Append empty rows to push older content left
        const emptyRowsNeeded = displayAllRows.length % this.MAX_ROWS_PER_COLUMN;
        if (emptyRowsNeeded > 0) {
            const lastColWidth = columnWidths[columnWidths.length - 1];
            for (let i = emptyRowsNeeded; i < this.MAX_ROWS_PER_COLUMN; i++) {
                const emptyRow = '|'.padEnd(lastColWidth + 1, ' ');
                displayRows[i] = displayRows[i] + ' ' + emptyRow;
            }
        }

        // Add bar at the end of each row
        for (let i = 0; i < displayRows.length; i++) {
            displayRows[i] += '|';
        }

        const result = displayRows.join('\n');
        print(`Conversation display: ${numColumns} columns x ${this.MAX_ROWS_PER_COLUMN} rows = ${result.length} chars`);
        return result;
    }

    updateColor(r: number, g: number, b: number, a: number) {
        const color = new vec4(r, g, b, a);
        if (this.textComponent) {
            this.textComponent.textFill.color = color;
        }
        if (this.gitDiffText) {
            this.gitDiffText.textFill.color = color;
        }
    }

    updateGitDiffText(newText: string) {
        print("ServerTextDisplay: updateGitDiffText called with: " + newText);
        if (this.gitDiffText) {
            const { formatted, numCols, numRows } = this.formatGitDiff(newText);
            this.gitDiffText.text = formatted;
            print("ServerTextDisplay: Git diff text component updated successfully");

            // Send display stats back to Mac
            if (this.socket && this.connected) {
                const stats = {
                    type: "display_stats",
                    panel: "git_diff",
                    chars: formatted.length,
                    columns: numCols,
                    rows: numRows
                };
                this.socket.send(JSON.stringify(stats));
                print("ServerTextDisplay: Sent display_stats to Mac");
            }
        } else {
            print("ServerTextDisplay: ERROR - Git diff text component not assigned!");
        }
    }

    formatGitDiff(text: string): { formatted: string, numCols: number, numRows: number } {
        const W = this.GIT_DIFF_LINE_WIDTH;
        const ROWS = this.GIT_DIFF_ROWS_PER_COLUMN;

        // Split text into lines
        const lines = text.split('\n');

        // Wrap each line that exceeds width
        const wrapped: string[] = [];
        for (const line of lines) {
            if (line.length > W) {
                // Chunk the line into pieces of width W
                for (let i = 0; i < line.length; i += W) {
                    wrapped.push(line.substring(i, i + W));
                }
            } else {
                wrapped.push(line);
            }
        }

        // Calculate number of columns needed, capped at max
        const numCols = Math.min(Math.ceil(wrapped.length / ROWS), this.MAX_GIT_DIFF_COLUMNS);

        // Only take the first (numCols * ROWS) wrapped lines
        const displayWrapped = wrapped.slice(0, numCols * ROWS);

        // Split wrapped lines into columns
        const cols: string[][] = [];
        for (let i = 0; i < numCols; i++) {
            cols.push(displayWrapped.slice(i * ROWS, (i + 1) * ROWS));
        }

        // Pad each column to ROWS length with empty strings
        for (const col of cols) {
            while (col.length < ROWS) {
                col.push("");
            }
        }

        // Build result by joining columns row by row
        const resultLines: string[] = [];
        for (let row = 0; row < ROWS; row++) {
            const rowParts = cols.map(col => col[row].padEnd(W));
            const rowWidths = rowParts.map(p => p.length);
            if (row < 5) {
                print(`Row ${row}: widths=[${rowWidths.join(',')}] total=${rowParts.join('  ').length}`);
            }
            resultLines.push(rowParts.join("  "));
        }

        const result = resultLines.join('\n');
        print(`GitDiff display: ${numCols} columns x ${ROWS} rows = ${result.length} chars`);
        return { formatted: result, numCols: numCols, numRows: ROWS };
    }

}
