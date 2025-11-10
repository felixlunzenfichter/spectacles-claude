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

    private readonly MAX_ROWS = 32;
    private readonly CONTENT_WIDTH = 64;
    private completeConversation: string[] = [];

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
