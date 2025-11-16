@component
export class NewScript extends BaseScriptComponent {
    @input
    image: Image;

    @input
    serverUrl: string = "ws://172.20.10.3:8080";

    private socket: WebSocket = null;
    private internetModule: any;

    onAwake() {
        if (!this.image) {
            print("Error: Please assign an Image to the script");
            return;
        }

        this.internetModule = require("LensStudio:InternetModule");
        this.connectWebSocket();
    }

    connectWebSocket() {
        try {
            this.socket = this.internetModule.createWebSocket(this.serverUrl);

            this.socket.onmessage = async (event) => {
                let messageText: string;
                if (event.data instanceof Blob) {
                    messageText = await event.data.text();
                } else {
                    messageText = event.data;
                }

                try {
                    const message = JSON.parse(messageText);
                    if (message.type === "screenshot") {
                        this.updatePixels(message.pixels);
                    }
                } catch (error) {
                    // Not screenshot JSON, ignore
                }
            };
        } catch (error) {
            print("Failed to connect: " + error);
        }
    }

    updatePixels(pixels: number[][]) {
        const width = 256;
        const height = 256;

        const newTex = ProceduralTextureProvider.createWithFormat(
            width,
            height,
            TextureFormat.RGBA8Unorm
        );

        const pixelData = new Uint8Array(width * height * 4);

        // Fill with screenshot pixels
        for (let i = 0; i < pixels.length; i++) {
            const [x, y, r, g, b] = pixels[i];
            const index = (y * width + x) * 4;
            pixelData[index + 0] = r;
            pixelData[index + 1] = g;
            pixelData[index + 2] = b;
            pixelData[index + 3] = 255;
        }

        const provider = newTex.control as ProceduralTextureProvider;
        provider.setPixels(0, 0, width, height, pixelData);
        this.image.mainPass.baseTex = newTex;

        print("Screenshot displayed!");
    }
}
