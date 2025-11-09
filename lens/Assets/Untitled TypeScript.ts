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
            const formatted = this.formatMultiColumn(newText);
            this.textComponent.text = formatted;
            print("ServerTextDisplay: Text component updated successfully");
        } else {
            print("ServerTextDisplay: ERROR - Text component not assigned!");
        }
    }

    formatMultiColumn(text: string): string {
        const MAX_LINE_WIDTH = 100;  // Maximum characters per line
        const MAX_LINES_PER_COLUMN = 50;  // Maximum lines per column

        // Split text into lines and wrap long lines
        const allLines: string[] = [];
        const rawLines = text.split('\n');

        for (const line of rawLines) {
            if (line.length <= MAX_LINE_WIDTH) {
                allLines.push(line);
            } else {
                // Wrap long lines
                let remaining = line;
                while (remaining.length > 0) {
                    allLines.push(remaining.substring(0, MAX_LINE_WIDTH));
                    remaining = remaining.substring(MAX_LINE_WIDTH);
                }
            }
        }

        // Split lines into columns
        const columns: string[][] = [];
        for (let i = 0; i < allLines.length; i += MAX_LINES_PER_COLUMN) {
            columns.push(allLines.slice(i, i + MAX_LINES_PER_COLUMN));
        }

        // If only one column, return as-is
        if (columns.length === 1) {
            return allLines.join('\n');
        }

        // Find max width needed for each column
        const columnWidths: number[] = [];
        for (const column of columns) {
            let maxWidth = 0;
            for (const line of column) {
                if (line.length > maxWidth) {
                    maxWidth = line.length;
                }
            }
            columnWidths.push(Math.min(maxWidth, MAX_LINE_WIDTH));
        }

        // Build multi-column output
        const maxLinesInAnyColumn = Math.max(...columns.map(c => c.length));
        const result: string[] = [];

        for (let lineIdx = 0; lineIdx < maxLinesInAnyColumn; lineIdx++) {
            const rowParts: string[] = [];

            for (let colIdx = 0; colIdx < columns.length; colIdx++) {
                const column = columns[colIdx];
                const line = lineIdx < column.length ? column[lineIdx] : '';

                // Pad line to column width for alignment
                const padded = line.padEnd(columnWidths[colIdx], ' ');
                rowParts.push(padded);
            }

            result.push(rowParts.join(' | '));
        }

        return result.join('\n');
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
