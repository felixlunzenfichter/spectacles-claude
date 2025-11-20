@component
export class SpectaclesClient extends BaseScriptComponent {
    @input
    textComponent: Text;

    @input
    image: Image;

    @input
    serverUrl: string = "ws://172.20.10.3:8080";  // Mac server IP address

    @input
    autoConnect: boolean = true;

    private startTime: number;
    private socket: WebSocket = null;
    private connected: boolean = false;
    private internetModule: any;
    private rawText: string = "";  // Store raw unformatted text
    private lastReconnectAttempt: number = 0;
    private reconnectDelay: number = 10.0;  // Try reconnecting every 10 seconds
    private lastPrintTime: number = 0;
    private printDelay: number = 1.0;  // Print status every 1 second

    private readonly MAX_ROWS = 50;
    private readonly CONTENT_WIDTH = 64;
    private readonly MAX_CONVERSATION_LINES = 500;
    private completeConversation: string[] = [];

    private screenshotWidth: number = 0;
    private screenshotHeight: number = 0;
    private currentTexture: Texture = null;
    private currentProvider: ProceduralTextureProvider = null;
    private pixelData: Uint8Array = null;

    onAwake() {
        print("ServerTextDisplay: Script initialized");
        this.startTime = getTime();

        // Load the InternetModule for WebSocket support
        this.internetModule = require("LensStudio:InternetModule");

        if (this.autoConnect) {
            this.connectToServer();
        }

        this.createEvent("UpdateEvent").bind(this.onUpdate.bind(this));
        print("ServerTextDisplay: Update event bound");
    }

    handleRectanglePacket(message: any) {
        if (!this.pixelData || !this.currentProvider) return;

        const rectangles = message.rectangles;

        // Draw each rectangle
        for (let i = 0; i < rectangles.length; i++) {
            const rect = rectangles[i];
            const x = rect.x;
            const y = rect.y;
            const w = rect.w;
            const h = rect.h;
            const r = rect.r;
            const g = rect.g;
            const b = rect.b;

            // Fill the rectangle area with the color
            for (let dy = 0; dy < h; dy++) {
                for (let dx = 0; dx < w; dx++) {
                    const pixelX = x + dx;
                    // Flip Y coordinate to fix upside-down display
                    const pixelY = (this.screenshotHeight - 1) - (y + dy);
                    const index = (pixelY * this.screenshotWidth + pixelX) * 4;
                    this.pixelData[index + 0] = r;
                    this.pixelData[index + 1] = g;
                    this.pixelData[index + 2] = b;
                    this.pixelData[index + 3] = 255;
                }
            }
        }

        this.currentProvider.setPixels(0, 0, this.screenshotWidth, this.screenshotHeight, this.pixelData);
        print(`Updated image with ${rectangles.length} rectangles`);
    }


    connectToServer() {
        print("ServerTextDisplay: Attempting to connect to " + this.serverUrl);

        try {
            // Create WebSocket connection
            this.socket = this.internetModule.createWebSocket(this.serverUrl);

            // Set up event handlers
            this.socket.onopen = (event) => {
                print("ServerTextDisplay: WebSocket connected!");
                this.connected = true;
                this.updateText("Connected to server!");
            };

            this.socket.onmessage = async (event) => {
                print("ServerTextDisplay: Received message");

                // Handle both text and binary messages
                let messageText: string;
                if (event.data instanceof Blob) {
                    // Binary message - convert to text
                    messageText = await event.data.text();
                } else {
                    // Text message
                    messageText = event.data;
                }

                // Try to parse as JSON
                try {
                    const message = JSON.parse(messageText);

                    // Only log non-packet messages to avoid spam
                    if (message.type !== "rectangle_packet") {
                        print("ServerTextDisplay: Received " + message.type);
                    }

                    if (message.type === "init") {
                        print("ServerTextDisplay: Received init message");

                        // Set dimensions
                        this.screenshotWidth = message.width;
                        this.screenshotHeight = message.height;

                        // Set color
                        const color = message.color;
                        this.updateColor(color.r, color.g, color.b, color.a);

                        // Create texture
                        if (this.screenshotWidth > 0 && this.screenshotHeight > 0 && this.image) {
                            print(`Creating texture: ${this.screenshotWidth}x${this.screenshotHeight}`);
                            try {
                                this.currentTexture = ProceduralTextureProvider.createWithFormat(
                                    this.screenshotWidth,
                                    this.screenshotHeight,
                                    TextureFormat.RGBA8Unorm
                                );
                                this.currentProvider = this.currentTexture.control as ProceduralTextureProvider;
                                this.pixelData = new Uint8Array(this.screenshotWidth * this.screenshotHeight * 4);
                                this.image.mainPass.baseTex = this.currentTexture;
                                print("Texture created");
                            } catch (error) {
                                print(`ERROR: ${error}`);
                            }
                        }

                        // Display last message if present
                        if (message.last_message) {
                            this.updateText(message.last_message);
                        }

                        // Send acknowledgement
                        print("ServerTextDisplay: Sending acknowledgement");
                        this.socket.send("ACK");

                        return;
                    }

                    if (message.type === "rectangle_packet") {
                        this.handleRectanglePacket(message);
                        return;
                    }
                } catch (error) {
                    // Not JSON, continue processing as text
                    if (messageText.length < 200) {
                        print("ServerTextDisplay: Non-JSON message: " + messageText.substring(0, 100));
                    }
                }

                // Display as text
                this.updateText(messageText);
            };

            this.socket.onerror = (event) => {
                print("ServerTextDisplay: WebSocket error occurred");
                print("ServerTextDisplay: Error event details: " + JSON.stringify(event));
                print("ServerTextDisplay: Server URL: " + this.serverUrl);
                print("ServerTextDisplay: Socket state: " + (this.socket ? this.socket.readyState : "null"));
                this.connected = false;
                this.updateText("Connection error!");
            };

            this.socket.onclose = (event) => {
                print("ServerTextDisplay: WebSocket closed");
                print("ServerTextDisplay: Close code: " + event.code);
                print("ServerTextDisplay: Close reason: " + event.reason);
                print("ServerTextDisplay: Was clean: " + event.wasClean);
                print("ServerTextDisplay: Server URL: " + this.serverUrl);
                this.connected = false;
                this.socket = null;
                this.updateText("Disconnected - will reconnect...");
            };

        } catch (error) {
            print("ServerTextDisplay: Failed to create WebSocket");
            print("ServerTextDisplay: Error: " + error);
            print("ServerTextDisplay: Error type: " + typeof error);
            print("ServerTextDisplay: Error message: " + (error.message || "No message"));
            print("ServerTextDisplay: Server URL: " + this.serverUrl);
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

            // Update text only once per second
            if (currentTime - this.lastPrintTime >= this.printDelay) {
                const elapsed = currentTime - this.startTime;
                this.updateText(`Waiting for server...\n${elapsed.toFixed(1)}s`);
                this.lastPrintTime = currentTime;
            }

            // Try to reconnect every 10 seconds
            if (currentTime - this.lastReconnectAttempt >= this.reconnectDelay) {
                print("ServerTextDisplay: Attempting to reconnect...");
                this.lastReconnectAttempt = currentTime;
                this.connectToServer();
            }
        }
    }

    updateText(newText: string) {
        print("ServerTextDisplay: updateText called with: " + newText);
        if (this.textComponent) {
            // Split new text by newline and append to conversation
            const newLines = newText.split('\n');
            this.completeConversation.push(...newLines);

            // Keep only the last 500 lines
            if (this.completeConversation.length > this.MAX_CONVERSATION_LINES) {
                this.completeConversation = this.completeConversation.slice(-this.MAX_CONVERSATION_LINES);
            }

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
                if (remaining.length > this.CONTENT_WIDTH) {
                    let breakPoint = this.CONTENT_WIDTH;
                    const segment = remaining.substring(0, this.CONTENT_WIDTH);
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

        // Step 2: Create empty display grid
        const displayRows: string[] = [];
        for (let i = 0; i < this.MAX_ROWS; i++) {
            displayRows.push('');
        }

        // Step 3: Add labels and padding, then prepend to display grid
        for (let i = 0; i < allRows.length; i++) {
            const rowIndex = i % this.MAX_ROWS;
            const label = i.toString() + ' ';
            let formattedRow: string;

            if (isFirstSegment[i]) {
                // First segment: left-aligned (padEnd)
                formattedRow = label + allRows[i].padEnd(this.CONTENT_WIDTH, ' ');
            } else {
                // Continuation: right-aligned (padStart)
                formattedRow = label + allRows[i].padStart(this.CONTENT_WIDTH, ' ');
            }

            displayRows[rowIndex] = displayRows[rowIndex] + ' ' + formattedRow;
        }

        // Step 4: Append empty rows to push older content left
        const emptyRowsNeeded = allRows.length % this.MAX_ROWS;
        if (emptyRowsNeeded > 0) {
            for (let i = emptyRowsNeeded; i < this.MAX_ROWS; i++) {
                const emptyRowIndex = allRows.length + (i - emptyRowsNeeded);
                const label = emptyRowIndex.toString() + ' ';
                const emptyRow = label + ''.padEnd(this.CONTENT_WIDTH, ' ');
                displayRows[i] = displayRows[i] + ' ' + emptyRow;
            }
        }

        // Add bar at the end of each row
        for (let i = 0; i < displayRows.length; i++) {
            displayRows[i] += '|';
        }

        return displayRows.join('\n');
    }

    updateColor(r: number, g: number, b: number, a: number) {
        if (this.textComponent) {
            this.textComponent.textFill.color = new vec4(r, g, b, a);
        }
    }

}
