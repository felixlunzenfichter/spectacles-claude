@component
export class NewScript extends BaseScriptComponent {
    @input
    textComponent: Text3D;

    @input
    serverUrl: string = "ws://172.20.10.3:8080";  // Mac server IP address

    @input
    autoConnect: boolean = true;

    private startTime: number;
    private socket: WebSocket = null;
    private connected: boolean = false;
    private internetModule: any;
    private rawText: string = "";  // Store raw unformatted text

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

                print("ServerTextDisplay: Message content: " + messageText);
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
                this.updateText("Disconnected from server");
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
            const elapsed = getTime() - this.startTime;
            this.updateText(`Waiting for server...\n${elapsed.toFixed(1)}s`);
        }
    }

    updateText(newText: string) {
        print("ServerTextDisplay: updateText called with: " + newText);
        if (this.textComponent) {
            // Accumulate raw text
            if (this.rawText) {
                this.rawText += "\n\n" + newText;
            } else {
                this.rawText = newText;
            }

            // Format the ENTIRE accumulated text
            const formatted = this.formatMultiColumn(this.rawText);

            // Set the text (not append)
            this.textComponent.text = formatted;

            print("ServerTextDisplay: Text component updated successfully");
        } else {
            print("ServerTextDisplay: ERROR - Text component not assigned!");
        }
    }

    formatMultiColumn(text: string): string {
        const MAX_ROWS = 32;
        const CONTENT_WIDTH = 64;

        const allLines: string[] = [];
        const rawLines = text.split('\n');
        let lineNumber = 0;

        for (const line of rawLines) {
            // Prepend line number first
            const label = lineNumber.toString() + ' ';
            const lineWithLabel = label + line;

            if (lineWithLabel.length <= CONTENT_WIDTH) {
                // Fits - pad end (left-aligned)
                allLines.push(lineWithLabel.padEnd(CONTENT_WIDTH, ' '));
            } else {
                // Too long - split it
                const availableWidth = CONTENT_WIDTH - label.length;

                // Find break point for first segment
                let breakPoint = availableWidth;
                const segment = line.substring(0, availableWidth);
                const lastSpace = segment.lastIndexOf(' ');
                if (lastSpace > 0) {
                    breakPoint = lastSpace;
                }

                // First segment with label (pad end)
                const firstPart = line.substring(0, breakPoint);
                allLines.push((label + firstPart).padEnd(CONTENT_WIDTH, ' '));

                // Continuation segments (right-aligned, no label)
                let remaining = line.substring(breakPoint).trimStart();
                while (remaining.length > 0) {
                    if (remaining.length <= CONTENT_WIDTH) {
                        allLines.push(remaining.padStart(CONTENT_WIDTH, ' '));
                        break;
                    }

                    // Find break point
                    breakPoint = CONTENT_WIDTH;
                    const seg = remaining.substring(0, CONTENT_WIDTH);
                    const space = seg.lastIndexOf(' ');
                    if (space > 0) {
                        breakPoint = space;
                    }

                    allLines.push(remaining.substring(0, breakPoint).padStart(CONTENT_WIDTH, ' '));
                    remaining = remaining.substring(breakPoint).trimStart();
                }
            }

            lineNumber++;
        }

        // Multi-column layout
        if (allLines.length > MAX_ROWS) {
            const outputLines: string[] = new Array(MAX_ROWS).fill('');

            for (let i = 0; i < allLines.length; i++) {
                const rowIndex = i % MAX_ROWS;
                const colIndex = Math.floor(i / MAX_ROWS);

                if (colIndex === 0) {
                    outputLines[rowIndex] = allLines[i];
                } else {
                    outputLines[rowIndex] += allLines[i];
                }
            }

            return outputLines.join('\n');
        } else {
            return allLines.join('\n');
        }
    }

    updateColor(r: number, g: number, b: number, a: number) {
        if (this.textComponent) {
            this.textComponent.mainMaterial.mainPass.baseColor = new vec4(r, g, b, a);
        }
    }

    updateSize(scale: number) {
        if (this.textComponent) {
            const transform = this.textComponent.getSceneObject().getTransform();
            transform.setLocalScale(new vec3(scale, scale, scale));
        }
    }
}
