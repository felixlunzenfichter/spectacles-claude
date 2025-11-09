@component
export class NewScript extends BaseScriptComponent {
    @input
    textComponent: Text3D;

    private startTime: number;

    onAwake() {
        print("ServerTextDisplay: Script initialized");
        this.startTime = getTime();
        this.createEvent("UpdateEvent").bind(this.onUpdate.bind(this));
        print("ServerTextDisplay: Update event bound");
    }

    onUpdate() {
        const elapsed = getTime() - this.startTime;
        this.updateText(`Waiting for server...\n${elapsed.toFixed(1)}s`);
    }

    updateText(newText: string) {
        print("ServerTextDisplay: updateText called with: " + newText);
        if (this.textComponent) {
            this.textComponent.text = newText;
            print("ServerTextDisplay: Text component updated successfully");
        } else {
            print("ServerTextDisplay: ERROR - Text component not assigned!");
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
