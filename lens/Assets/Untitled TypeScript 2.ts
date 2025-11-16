@component
export class NewScript extends BaseScriptComponent {
    @input
    image: Image;

    private width: number = 256;
    private height: number = 256;

    onAwake() {
        if (!this.image) {
            print("Error: Please assign an Image to the script");
            return;
        }

        this.updatePixels();
    }

    updatePixels() {
        // Create the procedural texture programmatically
        const newTex = ProceduralTextureProvider.createWithFormat(
            this.width,
            this.height,
            TextureFormat.RGBA8Unorm
        );

        // Create RGBA pixel data array (4 values per pixel: R, G, B, A)
        const pixelData = new Uint8Array(this.width * this.height * 4);

        // Set each pixel to a different color
        for (let y = 0; y < this.height; y++) {
            for (let x = 0; x < this.width; x++) {
                const index = (y * this.width + x) * 4;

                // Create a gradient effect
                pixelData[index + 0] = (x / this.width) * 255;      // Red increases left to right
                pixelData[index + 1] = (y / this.height) * 255;     // Green increases bottom to top
                pixelData[index + 2] = 128;                          // Blue constant
                pixelData[index + 3] = 255;                          // Alpha full
            }
        }

        // Apply the pixel data to the texture
        const provider = newTex.control as ProceduralTextureProvider;
        provider.setPixels(0, 0, this.width, this.height, pixelData);

        // Apply the texture to the image
        this.image.mainPass.baseTex = newTex;

        print("Pixels updated successfully!");
    }
}
