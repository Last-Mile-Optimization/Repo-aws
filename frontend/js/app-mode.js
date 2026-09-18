const APP_MODE_STORAGE_KEY = "predictDeliveryAppMode";

function currentMode() {
    return localStorage.getItem(APP_MODE_STORAGE_KEY) || "test";
}

function renderMode() {
    const testMode = currentMode() === "test";
    const switchButton = document.getElementById("appModeSwitch");
    const label = document.getElementById("appModeLabel");

    if (switchButton) {
        switchButton.setAttribute("aria-checked", String(testMode));
    }

    if (label) {
        label.textContent = testMode ? "Modo teste" : "Usar API";
    }
}

window.AppMode = {
    isTestMode: () => currentMode() === "test"
};

document.getElementById("appModeSwitch")?.addEventListener("click", () => {
    localStorage.setItem(
        APP_MODE_STORAGE_KEY,
        currentMode() === "test" ? "api" : "test"
    );
    renderMode();
    window.dispatchEvent(new Event("appmodechange"));
});

renderMode();
