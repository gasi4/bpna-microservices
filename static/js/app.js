let videoWs = null;
let telemetryWs = null;
let wifiWs = null;

let canvas = null;
let ctx = null;
let detectionCanvas = null;
let detectionCtx = null;

let frameCount = 0;
let lastFpsTime = Date.now();
let hasVideoFrame = false;
let sourceFrameWidth = 0;
let sourceFrameHeight = 0;
let videoRenderState = null;

let detectionBoxes = [];
let detectionEnabled = true;
let currentTargetBox = null;

let autopilotEnabled = false;
let selectedAutopilotTargetId = null;
let selectedAutopilotTargetLabel = null;

const motorState = { left: "STOP", right: "STOP" };
const pressedKeys = new Set();
let commandLoop = null;
const COMMAND_INTERVAL_MS = 150;
const DEVICE_HEARTBEAT_INTERVAL_MS = 8000;
const DEVICE_POLL_INTERVAL_MS = 10000;

let currentUser = null;
let availableDevices = [];
let adminUsers = [];
let adminDevices = [];
let devicePollTimer = null;
let controlHeartbeatTimer = null;
let videoStreamDeviceId = null;
let telemetryStreamDeviceId = null;
let wifiStreamDeviceId = null;

let measurements = [];
let currentHeatmap = null;
let isScanning = false;
let droneTrack = [];
let showTrack = true;
let activeScanMode = "manual";
let flashLightEnabled = false;
let activeAdminTab = "users";

function getScanConfig() {

    const widthCm = Math.max(100, Number(document.getElementById("scan-width")?.value || 1000));
    const heightCm = Math.max(100, Number(document.getElementById("scan-height")?.value || 1000));
    const stepCm = Math.max(10, Number(document.getElementById("scan-step")?.value || 100));

    return {
        widthCm,
        heightCm,
        stepCm,
        widthCells: Math.max(1, Math.ceil(widthCm / stepCm)),
        heightCells: Math.max(1, Math.ceil(heightCm / stepCm)),
    };
}


function getAuthToken() {
    return sessionStorage.getItem("access_token");
}

function setAuthToken(token) {
    sessionStorage.setItem("access_token", token);
}

function clearAuthToken() {
    sessionStorage.removeItem("access_token");
}

function getActiveDeviceId() {
    return sessionStorage.getItem("active_device_id");
}

function setActiveDeviceId(deviceId) {
    if (deviceId) {
        sessionStorage.setItem("active_device_id", deviceId);
    } else {
        sessionStorage.removeItem("active_device_id");
    }
}

function getControlledDeviceId() {
    return sessionStorage.getItem("controlled_device_id");
}

function setControlledDeviceId(deviceId) {
    if (deviceId) {
        sessionStorage.setItem("controlled_device_id", deviceId);
    } else {
        sessionStorage.removeItem("controlled_device_id");
    }
}

function isActiveDeviceControlled() {
    const activeDeviceId = getActiveDeviceId();
    return Boolean(activeDeviceId) && getControlledDeviceId() === activeDeviceId;
}

function getActiveDeviceQuery() {
    const deviceId = getActiveDeviceId();
    return deviceId ? `device_id=${encodeURIComponent(deviceId)}` : "";
}

async function apiFetch(url, options = {}, allowUnauthorized = false) {
    const token = getAuthToken();
    if (!token && !allowUnauthorized) {
        throw new Error("Not authenticated");
    }

    const headers = {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {}),
    };

    const res = await fetch(url, { ...options, headers });

    if (res.status === 401 && !allowUnauthorized) {
        performLocalLogout();
    }

    return res;
}

function setText(id, value) {

    const el = document.getElementById(id);
    if (el) {
        el.textContent = value;
    }
}

function updateFlashlightUi() {
    const button = document.getElementById("flashlight-toggle");
    if (!button) {
        return;
    }

    button.textContent = `\u0424\u043e\u043d\u0430\u0440\u044c: ${flashLightEnabled ? "\u0412\u041a\u041b" : "\u0412\u042b\u041a\u041b"}`;
    button.classList.toggle("active", flashLightEnabled);
    button.classList.toggle("is-active", flashLightEnabled);
}

function formatUptime(sec) {
    const total = Number(sec || 0);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    return `${h}h ${m}m ${s}s`;
}

function getRssiColor(rssi) {
    if (rssi >= -50) return "#00ff88";
    if (rssi >= -60) return "#88ff00";
    if (rssi >= -70) return "#cccc00";
    if (rssi >= -80) return "#ff8c42";
    return "#ff5c5c";
}

function getLinkQuality(rssi, ping) {
    if (rssi == null || ping == null || ping < 0) return "Online";
    if (rssi > -55 && ping < 10) return "Excellent";
    if (rssi > -67 && ping < 30) return "Good";
    if (rssi > -75 && ping < 80) return "Fair";
    return "Poor";
}

function getVideoContainer() {
    return document.querySelector(".video-container");
}

function resizeVideoCanvases() {
    if (!canvas || !ctx || !detectionCanvas || !detectionCtx) {
        return null;
    }

    const container = getVideoContainer();
    if (!container) {
        return null;
    }

    const rect = container.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width));
    const height = Math.max(1, Math.round(rect.height));
    const dpr = window.devicePixelRatio || 1;

    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    detectionCanvas.width = Math.round(width * dpr);
    detectionCanvas.height = Math.round(height * dpr);

    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    detectionCanvas.style.width = `${width}px`;
    detectionCanvas.style.height = `${height}px`;

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    detectionCtx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);
    detectionCtx.scale(dpr, dpr);

    return { width, height, dpr };
}

function resizeSquareCanvas(id) {
    const canvasEl = document.getElementById(id);
    if (!canvasEl) {
        return null;
    }

    const rect = canvasEl.getBoundingClientRect();
    const size = Math.max(220, Math.round(rect.width || canvasEl.parentElement?.getBoundingClientRect().width || 320));
    const dpr = window.devicePixelRatio || 1;

    canvasEl.width = Math.round(size * dpr);
    canvasEl.height = Math.round(size * dpr);
    canvasEl.style.height = `${size}px`;

    const context = canvasEl.getContext("2d");
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.scale(dpr, dpr);

    return { canvas: canvasEl, context, size };
}

function resizeHeatmapCanvases() {
    resizeSquareCanvas("heatmap-canvas");
}

function getFitRect(containerWidth, containerHeight, sourceWidth, sourceHeight) {
    const scale = Math.min(containerWidth / sourceWidth, containerHeight / sourceHeight);
    const drawWidth = sourceWidth * scale;
    const drawHeight = sourceHeight * scale;
    const offsetX = (containerWidth - drawWidth) / 2;
    const offsetY = (containerHeight - drawHeight) / 2;

    return { scale, drawWidth, drawHeight, offsetX, offsetY };
}

function clearDetectionCanvas() {
    if (!detectionCtx || !detectionCanvas) {
        return;
    }

    const rect = detectionCanvas.getBoundingClientRect();
    detectionCtx.clearRect(0, 0, rect.width, rect.height);
}

window.addEventListener("DOMContentLoaded", async () => {
    canvas = document.getElementById("video-canvas");
    detectionCanvas = document.getElementById("detection-canvas");

    if (!canvas || !detectionCanvas) {
        console.error("Video canvas elements not found");
        return;
    }

    ctx = canvas.getContext("2d");
    detectionCtx = detectionCanvas.getContext("2d");

    resizeVideoCanvases();
    resizeHeatmapCanvases();

    setupKeyboardControls();
    setupWifiControls();
    updateDetectionUi();
    updateFlashlightUi();
    updateVideoStatus();

    document.getElementById("login-form")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const username = document.getElementById("login-username")?.value?.trim() || "";
        const password = document.getElementById("login-password")?.value || "";
        if (!username || !password) {
            showLoginError("\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043b\u043e\u0433\u0438\u043d \u0438 \u043f\u0430\u0440\u043e\u043b\u044c.");
            return;
        }

        const ok = await login(username, password);
        if (ok) {
            document.getElementById("login-password").value = "";
        }
    });

    document.getElementById("logout-btn")?.addEventListener("click", () => {
        logout();
    });

    document.getElementById("open-device-list-btn")?.addEventListener("click", () => {
        openDeviceList();
    });

    document.getElementById("open-admin-panel-btn")?.addEventListener("click", async () => {
        await openAdminPanel();
    });

    document.getElementById("close-device-list-btn")?.addEventListener("click", () => {
        closeDeviceList();
    });

    document.getElementById("close-admin-panel-btn")?.addEventListener("click", () => {
        closeAdminPanel();
    });

    document.getElementById("refresh-device-list-btn")?.addEventListener("click", async () => {
        try {
            await loadDevices({ preserveView: true });
        } catch (error) {
            console.error("Device list refresh error:", error);
        }
    });

    document.getElementById("release-device-btn")?.addEventListener("click", async () => {
        await releaseCurrentDevice();
    });

    document.getElementById("admin-users-tab")?.addEventListener("click", () => {
        setAdminTab("users");
    });

    document.getElementById("admin-devices-tab")?.addEventListener("click", () => {
        setAdminTab("devices");
    });

    document.getElementById("refresh-admin-users-btn")?.addEventListener("click", async () => {
        await loadAdminUsers();
    });

    document.getElementById("refresh-admin-devices-btn")?.addEventListener("click", async () => {
        await loadAdminDevices();
    });

    document.getElementById("admin-user-form")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        await createAdminUser();
    });

    document.getElementById("admin-device-form")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        await createAdminDevice();
    });

    await bootstrapApp();

    window.addEventListener("resize", () => {
        resizeVideoCanvases();
        resizeHeatmapCanvases();

        if (videoRenderState) {
            renderVideoFrame(videoRenderState.img);
            drawDetections();
        }

        if (currentHeatmap) {
            drawHeatmap(currentHeatmap, "heatmap-canvas");
        } else {
            drawGridOnly("heatmap-canvas");
        }
    });

    setInterval(updateVideoStatus, 5000);
    setInterval(async () => {
        if (showTrack && isScanning && getActiveDeviceId()) {
            await loadDroneTrack();
            if (currentHeatmap) {
                drawHeatmap(currentHeatmap, "heatmap-canvas");
            }
        }
    }, 2000);
});

function toggleDetection() {

    detectionEnabled = !detectionEnabled;

    if (!detectionEnabled) {
        detectionBoxes = [];
        currentTargetBox = null;
        clearDetectionCanvas();
        refreshAutopilotTargetOptions([]);
    }

    updateDetectionUi();
    updateTargetDistanceBadge();
    drawDetections();
}

function updateDetectionUi() {
    const toggle = document.getElementById("detection-toggle");
    if (toggle) {
        toggle.textContent = `\u0414\u0435\u0442\u0435\u043a\u0446\u0438\u044f: ${detectionEnabled ? "\u0412\u041a\u041b" : "\u0412\u042b\u041a\u041b"}`;
        toggle.classList.toggle("active", detectionEnabled);
    }

    const trackedTargets = detectionBoxes.filter((box) => box.track_id !== null && box.track_id !== undefined);
    const summary = document.getElementById("detection-summary");

    if (summary) {
        if (!detectionEnabled) {
            summary.textContent = "\u0414\u0435\u0442\u0435\u043a\u0446\u0438\u044f \u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d\u0430";
        } else if (!detectionBoxes.length) {
            summary.textContent = "\u0414\u0435\u0442\u0435\u043a\u0446\u0438\u044f \u0432\u043a\u043b\u044e\u0447\u0435\u043d\u0430, \u043e\u0436\u0438\u0434\u0430\u043d\u0438\u0435 \u043e\u0431\u044a\u0435\u043a\u0442\u043e\u0432";
        } else {
            summary.textContent = `\u041d\u0430\u0439\u0434\u0435\u043d\u043e \u043e\u0431\u044a\u0435\u043a\u0442\u043e\u0432: ${detectionBoxes.length}`;
        }
    }

    const autopilotButton = document.getElementById("autopilot-toggle");
    if (autopilotButton) {
        autopilotButton.textContent = `\u0410\u0432\u0442\u043e\u043f\u0438\u043b\u043e\u0442: ${autopilotEnabled ? "\u0412\u041a\u041b" : "\u0412\u042b\u041a\u041b"}`;
        autopilotButton.classList.toggle("active", autopilotEnabled);
        autopilotButton.disabled = !detectionEnabled || selectedAutopilotTargetId === null || !selectedAutopilotTargetLabel;
    }
}

function updateAutopilotTarget(value) {
    if (!value) {
        selectedAutopilotTargetId = null;
        selectedAutopilotTargetLabel = null;
        currentTargetBox = null;
        updateDetectionUi();
        updateTargetDistanceBadge();
        return;
    }

    const [label, idRaw] = value.split("|");
    selectedAutopilotTargetLabel = label || null;
    selectedAutopilotTargetId = idRaw ? Number(idRaw) : null;

    currentTargetBox = detectionBoxes.find(
        (box) => box.track_id === selectedAutopilotTargetId && box.label === selectedAutopilotTargetLabel
    ) || null;

    updateDetectionUi();
    updateTargetDistanceBadge();
}

function refreshAutopilotTargetOptions(boxes) {
    const select = document.getElementById("autopilot-target");
    if (!select) {
        return;
    }

    const tracked = (boxes || []).filter((box) => box.track_id !== null && box.track_id !== undefined);
    select.innerHTML = "";

    if (!tracked.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = detectionEnabled ? "\u0422\u0440\u0435\u043a\u0438\u043d\u0433 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d" : "\u0414\u0435\u0442\u0435\u043a\u0446\u0438\u044f \u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d\u0430";
        select.appendChild(option);
        select.disabled = true;
        selectedAutopilotTargetId = null;
        selectedAutopilotTargetLabel = null;
        currentTargetBox = null;
        return;
    }

    select.disabled = false;

    tracked
        .sort((a, b) => {
            if (a.label === b.label) {
                return a.track_id - b.track_id;
            }
            return a.label.localeCompare(b.label);
        })
        .forEach((box, index) => {
            const option = document.createElement("option");
            option.value = `${box.label}|${box.track_id}`;
            option.textContent = `${box.label} #${box.track_id}`;

            const isSelected =
                box.track_id === selectedAutopilotTargetId &&
                box.label === selectedAutopilotTargetLabel;

            if (isSelected || (selectedAutopilotTargetId === null && index === 0)) {
                option.selected = true;
                selectedAutopilotTargetId = box.track_id;
                selectedAutopilotTargetLabel = box.label;
            }

            select.appendChild(option);
        });

    currentTargetBox = detectionBoxes.find(
        (box) => box.track_id === selectedAutopilotTargetId && box.label === selectedAutopilotTargetLabel
    ) || null;
}

async function toggleAutopilot() {
    const deviceId = getActiveDeviceId();
    if (!deviceId || !isActiveDeviceControlled()) {
        window.alert("\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0432\u043e\u0437\u044c\u043c\u0438\u0442\u0435 \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0443 \u043f\u043e\u0434 \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435.");
        return;
    }

    if (selectedAutopilotTargetId === null || !selectedAutopilotTargetLabel) {
        console.warn("[AUTOPILOT] No tracked target selected");
        return;
    }

    const nextState = !autopilotEnabled;

    try {
        const res = await apiFetch(
            `/api/device/autopilot?enabled=${nextState}&device_id=${encodeURIComponent(deviceId)}&target_id=${selectedAutopilotTargetId}&target_label=${encodeURIComponent(selectedAutopilotTargetLabel)}`,
            { method: "POST" }
        );

        if (!res.ok) {
            console.error("[AUTOPILOT] request failed", res.status);
            return;
        }

        autopilotEnabled = nextState;
        if (autopilotEnabled) {
            pressedKeys.clear();
            stopCommandLoop();
            updateMotorStatus("stop");
            document.querySelectorAll(".key-chip").forEach((chip) => chip.classList.remove("active"));
        }

        updateControlAvailability();
        updateDetectionUi();
        updateTargetDistanceBadge();
    } catch (error) {
        console.error("[AUTOPILOT] toggle error:", error);
    }
}

function updateTargetDistanceBadge() {
    const badge = document.getElementById("target-distance-badge");
    if (!badge) {
        return;
    }

    if (!selectedAutopilotTargetLabel || selectedAutopilotTargetId === null) {
        badge.textContent = "\u0426\u0435\u043b\u044c \u043d\u0435 \u0432\u044b\u0431\u0440\u0430\u043d\u0430";
        return;
    }

    const target = detectionBoxes.find(
        (box) => box.track_id === selectedAutopilotTargetId && box.label === selectedAutopilotTargetLabel
    );

    if (!target) {
        badge.textContent = `\u0426\u0435\u043b\u044c ${selectedAutopilotTargetLabel} #${selectedAutopilotTargetId} \u043f\u043e\u0442\u0435\u0440\u044f\u043d\u0430`;
        return;
    }

    const distanceText = target.distance_cm != null
        ? `${(target.distance_cm / 100).toFixed(2)} \u043c`
        : "\u0431\u0435\u0437 \u043e\u0446\u0435\u043d\u043a\u0438 \u0434\u0438\u0441\u0442\u0430\u043d\u0446\u0438\u0438";

    badge.textContent = `${target.label} #${target.track_id} | \u0434\u0438\u0441\u0442\u0430\u043d\u0446\u0438\u044f ${distanceText}${autopilotEnabled ? " | \u0430\u0432\u0442\u043e\u043f\u0438\u043b\u043e\u0442 \u0430\u043a\u0442\u0438\u0432\u0435\u043d" : ""}`;
}

function getDeviceById(deviceId) {
    return availableDevices.find((item) => item.device_id === deviceId) || null;
}

function formatRole(role) {
    if (role === "admin") {
        return "\u0410\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440";
    }
    return "\u041e\u043f\u0435\u0440\u0430\u0442\u043e\u0440";
}

function formatStatus(status) {
    if (status === "busy") {
        return "busy";
    }
    if (status === "online") {
        return "online";
    }
    return "offline";
}

function formatStatusLabel(status) {
    if (status === "busy") {
        return "\u0417\u0430\u043d\u044f\u0442";
    }
    if (status === "online") {
        return "\u041e\u043d\u043b\u0430\u0439\u043d";
    }
    return "\u041e\u0444\u0444\u043b\u0430\u0439\u043d";
}

function formatLastSeen(value) {
    if (!value) {
        return "-";
    }

    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return value;
    }

    return parsed.toLocaleString("ru-RU");
}

function formatCreatedAt(value) {
    if (!value) {
        return "-";
    }

    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return value;
    }

    return parsed.toLocaleString("ru-RU");
}

function showElement(id, visible) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.toggle("hidden", !visible);
    }
}

function setDashboardVisible(visible) {
    showElement("cockpit-dashboard", visible);
}

function isAdminUser() {
    return currentUser?.role === "admin";
}

function openDeviceList() {
    showElement("admin-screen", false);
    showElement("device-selection-screen", true);
    setDashboardVisible(false);
}

function closeDeviceList() {
    if (!getActiveDeviceId()) {
        return;
    }

    showElement("device-selection-screen", false);
    setDashboardVisible(true);
}

function setAdminTab(tab) {
    activeAdminTab = tab === "devices" ? "devices" : "users";
    showElement("admin-users-panel", activeAdminTab === "users");
    showElement("admin-devices-panel", activeAdminTab === "devices");
    document.getElementById("admin-users-tab")?.classList.toggle("is-active", activeAdminTab === "users");
    document.getElementById("admin-devices-tab")?.classList.toggle("is-active", activeAdminTab === "devices");
}

async function openAdminPanel() {
    if (!isAdminUser()) {
        return;
    }

    showElement("device-selection-screen", false);
    setDashboardVisible(false);
    showElement("admin-screen", true);
    setAdminTab(activeAdminTab);
    await Promise.all([loadAdminUsers(), loadAdminDevices()]);
}

function closeAdminPanel() {
    showElement("admin-screen", false);

    if (getActiveDeviceId()) {
        setDashboardVisible(true);
    } else {
        openDeviceList();
    }
}

function renderCurrentUser() {
    setText("current-user-name", currentUser?.username || "-");
    setText("current-user-role", currentUser ? formatRole(currentUser.role) : "-");
    showElement("open-admin-panel-btn", isAdminUser());
}

function renderActiveDevice(device) {
    const nameEl = document.getElementById("active-device-name");
    const statusEl = document.getElementById("active-device-status");
    if (!nameEl || !statusEl) {
        return;
    }

    if (!device) {
        nameEl.textContent = "\u041d\u0435 \u0432\u044b\u0431\u0440\u0430\u043d\u0430";
        statusEl.textContent = "\u041d\u0435 \u0430\u043a\u0442\u0438\u0432\u043d\u0430";
        statusEl.className = "chip-status offline";
        return;
    }

    nameEl.textContent = device.name || device.device_id;
    statusEl.textContent = formatStatusLabel(device.status);
    statusEl.className = `chip-status ${formatStatus(device.status)}`;
}

function updateControlAvailability() {
    const canControl = isActiveDeviceControlled();

    document.querySelectorAll(".key-chip").forEach((chip) => {
        chip.disabled = !canControl || autopilotEnabled;
    });

    const flashlightButton = document.getElementById("flashlight-toggle");
    if (flashlightButton) {
        flashlightButton.disabled = !canControl;
    }

    const startScanButton = document.getElementById("start-scan-btn");
    if (startScanButton) {
        startScanButton.disabled = !canControl;
    }

    const stopScanButton = document.getElementById("stop-scan-btn");
    if (stopScanButton) {
        stopScanButton.disabled = !canControl;
    }

    const clearTrackButton = document.getElementById("clear-track-btn");
    if (clearTrackButton) {
        clearTrackButton.disabled = !canControl;
    }

    const clearDataButton = document.getElementById("clear-data-btn");
    if (clearDataButton) {
        clearDataButton.disabled = !canControl;
    }

    const releaseButton = document.getElementById("release-device-btn");
    if (releaseButton) {
        releaseButton.disabled = !Boolean(getControlledDeviceId());
    }

    updateScanAutopilotButton();
    updateFlashlightUi();
}

function stopDevicePolling() {
    if (!devicePollTimer) {
        return;
    }

    clearInterval(devicePollTimer);
    devicePollTimer = null;
}

function startDevicePolling() {
    stopDevicePolling();
    devicePollTimer = setInterval(() => {
        if (currentUser) {
            loadDevices({ preserveView: true });
        }
    }, DEVICE_POLL_INTERVAL_MS);
}

function stopControlHeartbeat() {
    if (!controlHeartbeatTimer) {
        return;
    }

    clearInterval(controlHeartbeatTimer);
    controlHeartbeatTimer = null;
}

function startControlHeartbeat() {
    stopControlHeartbeat();
    const deviceId = getControlledDeviceId();
    if (!deviceId) {
        return;
    }

    controlHeartbeatTimer = setInterval(async () => {
        try {
            const res = await apiFetch(`/api/device/devices/${encodeURIComponent(deviceId)}/heartbeat`, { method: "POST" });
            if (!res.ok) {
                setControlledDeviceId(null);
                stopControlHeartbeat();
                await loadDevices({ preserveView: true });
                updateControlAvailability();
            }
        } catch (error) {
            console.error("Heartbeat error:", error);
        }
    }, DEVICE_HEARTBEAT_INTERVAL_MS);
}

function closeRealtimeStreams() {
    if (videoWs) {
        const ws = videoWs;
        videoWs = null;
        ws.onclose = null;
        ws.onerror = null;
        ws.close();
    }

    if (telemetryWs) {
        const ws = telemetryWs;
        telemetryWs = null;
        ws.onclose = null;
        ws.onerror = null;
        ws.close();
    }

    if (wifiWs) {
        const ws = wifiWs;
        wifiWs = null;
        ws.onclose = null;
        ws.onerror = null;
        ws.close();
    }
}

function resetRealtimeState() {
    updateStatus(false);
    setText("esp-status", "Offline");
    hasVideoFrame = false;
    sourceFrameWidth = 0;
    sourceFrameHeight = 0;
    videoRenderState = null;
    detectionBoxes = [];
    currentTargetBox = null;
    clearDetectionCanvas();
    refreshAutopilotTargetOptions([]);
    updateDetectionUi();
    updateTargetDistanceBadge();
    const noSignal = document.getElementById("no-signal");
    if (noSignal) {
        noSignal.style.display = "flex";
    }
}

function applyDeviceSnapshot(device) {
    renderActiveDevice(device);

    if (!device) {
        renderTelemetry({});
        resetRealtimeState();
        return;
    }

    renderTelemetry({
        connected: Boolean(device.connected),
        last_seen: device.last_seen,
        last_data: device.last_data
            ? { ...device.last_data, device_id: device.last_data.device_id || device.device_id }
            : { device_id: device.device_id },
    });

    updateStatus(Boolean(device.connected));
    setText("esp-status", device.connected ? "Connected" : "Offline");
}

function showLoginError(message = "") {
    const errorEl = document.getElementById("login-error");
    if (!errorEl) {
        return;
    }

    errorEl.textContent = message;
    errorEl.classList.toggle("hidden", !message);
}

function renderAuthState() {
    const authenticated = Boolean(currentUser && getAuthToken());
    showElement("auth-screen", !authenticated);
    showElement("app-shell", authenticated);

    if (!authenticated) {
        showElement("admin-screen", false);
        openDeviceList();
        setDashboardVisible(false);
    }
}

function performLocalLogout() {
    clearAuthToken();
    setActiveDeviceId(null);
    setControlledDeviceId(null);
    currentUser = null;
    availableDevices = [];
    adminUsers = [];
    adminDevices = [];
    stopDevicePolling();
    stopControlHeartbeat();
    closeRealtimeStreams();
    resetRealtimeState();
    renderCurrentUser();
    renderActiveDevice(null);
    renderDeviceList();
    updateControlAvailability();
    renderAuthState();
}

async function loadCurrentUser() {
    const res = await apiFetch("/api/auth/me");
    if (!res.ok) {
        throw new Error(`Failed to load profile: ${res.status}`);
    }

    currentUser = await res.json();
    renderCurrentUser();
    renderAuthState();
}

function renderAdminOverview() {
    setText("admin-users-count", String(adminUsers.filter((item) => item.is_active).length));
    setText("admin-admins-count", String(adminUsers.filter((item) => item.is_active && item.role === "admin").length));
    setText("admin-devices-count", String(adminDevices.filter((item) => item.is_active !== false).length));
}

function renderAdminUsers() {
    const root = document.getElementById("admin-users-list");
    if (!root) {
        return;
    }

    if (!adminUsers.length) {
        root.innerHTML = '<div class="empty-state">\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442.</div>';
        renderAdminOverview();
        return;
    }

    root.innerHTML = adminUsers.map((user) => `
        <article class="admin-list-item">
            <div class="admin-list-row">
                <div class="admin-list-title">
                    <strong>${user.username}</strong>
                    <span class="admin-list-subtitle">${formatRole(user.role)}</span>
                </div>
                <span class="chip-status admin-account-state ${user.is_active ? "online" : "offline"}">${user.is_active ? "\u0423\u0447\u0451\u0442\u043d\u0430\u044f \u0437\u0430\u043f\u0438\u0441\u044c \u0434\u0435\u0439\u0441\u0442\u0432\u0443\u0435\u0442" : "\u0423\u0447\u0451\u0442\u043d\u0430\u044f \u0437\u0430\u043f\u0438\u0441\u044c \u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u0430"}</span>
            </div>
            <div class="admin-list-meta">
                <span>ID: ${user.id}</span>
                <span>\u0421\u043e\u0437\u0434\u0430\u043d: ${formatCreatedAt(user.created_at)}</span>
            </div>
            <div class="admin-list-actions">
                <button class="control-btn control-btn-danger" data-admin-user-delete="${user.id}" data-admin-user-purge="${user.is_active ? "false" : "true"}" ${user.username === currentUser?.username ? "disabled" : ""}>
                    ${user.is_active ? "\u0414\u0435\u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u0442\u044c" : "\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0438\u0437 \u0411\u0414"}
                </button>
            </div>
        </article>
    `).join("");

    renderAdminOverview();

    root.querySelectorAll("button[data-admin-user-delete]").forEach((button) => {
        button.addEventListener("click", async () => {
            const id = button.dataset.adminUserDelete;
            if (!id) {
                return;
            }
            const purge = button.dataset.adminUserPurge === "true";
            const message = purge
                ? "\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u044d\u0442\u0443 \u0443\u0447\u0451\u0442\u043d\u0443\u044e \u0437\u0430\u043f\u0438\u0441\u044c \u0438\u0437 \u0411\u0414?"
                : "\u0414\u0435\u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u044d\u0442\u0443 \u0443\u0447\u0451\u0442\u043d\u0443\u044e \u0437\u0430\u043f\u0438\u0441\u044c?";
            if (!window.confirm(message)) {
                return;
            }
            await deleteAdminUser(id, purge);
        });
    });
}

function renderAdminDevices() {
    const root = document.getElementById("admin-devices-list");
    if (!root) {
        return;
    }

    if (!adminDevices.length) {
        root.innerHTML = '<div class="empty-state">\u041f\u043b\u0430\u0442\u0444\u043e\u0440\u043c \u043f\u043e\u043a\u0430 \u043d\u0435\u0442.</div>';
        renderAdminOverview();
        return;
    }

    root.innerHTML = adminDevices.map((device) => `
        <article class="admin-list-item">
            <div class="admin-list-row">
                <div class="admin-list-title">
                    <strong>${device.name || device.device_id}</strong>
                </div>
                <span class="chip-status admin-account-state ${device.is_active ? "online" : "offline"}">${device.is_active ? "\u041f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0430 \u0430\u043a\u0442\u0438\u0432\u043d\u0430" : "\u041f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0430 \u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u0430"}</span>
            </div>
            <div class="admin-list-meta">
                <span>Device ID: ${device.device_id}</span>
                <span>\u0421\u043e\u0437\u0434\u0430\u043d\u0430: ${formatCreatedAt(device.created_at)}</span>
                <span>Secret: <code>${device.device_secret || "-"}</code></span>
            </div>
            <div class="admin-list-actions">
                <button class="control-btn control-btn-danger" data-admin-device-delete="${device.device_id}" data-admin-device-purge="${device.is_active ? "false" : "true"}">
                    ${device.is_active ? "\u0414\u0435\u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u0442\u044c" : "\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0438\u0437 \u0411\u0414"}
                </button>
            </div>
        </article>
    `).join("");

    renderAdminOverview();

    root.querySelectorAll("button[data-admin-device-delete]").forEach((button) => {
        button.addEventListener("click", async () => {
            const deviceId = button.dataset.adminDeviceDelete;
            if (!deviceId) {
                return;
            }
            const purge = button.dataset.adminDevicePurge === "true";
            const message = purge
                ? "\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u044d\u0442\u0443 \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0443 \u0438\u0437 \u0411\u0414?"
                : "\u0414\u0435\u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u044d\u0442\u0443 \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0443?";
            if (!window.confirm(message)) {
                return;
            }
            await deleteAdminDevice(deviceId, purge);
        });
    });
}

async function loadAdminUsers() {
    if (!isAdminUser()) {
        return;
    }
    const res = await apiFetch("/api/auth/users");
    if (!res.ok) {
        throw new Error(`Failed to load admin users: ${res.status}`);
    }
    adminUsers = await res.json();
    renderAdminUsers();
}

async function loadAdminDevices() {
    if (!isAdminUser()) {
        return;
    }
    const res = await apiFetch("/api/auth/admin/devices");
    if (!res.ok) {
        throw new Error(`Failed to load admin devices: ${res.status}`);
    }
    adminDevices = await res.json();
    renderAdminDevices();
}

async function createAdminUser() {
    const username = document.getElementById("admin-user-username")?.value?.trim() || "";
    const password = document.getElementById("admin-user-password")?.value || "";
    const role = document.getElementById("admin-user-role")?.value || "operator";
    if (!username || !password) {
        window.alert("\u0417\u0430\u043f\u043e\u043b\u043d\u0438\u0442\u0435 \u043b\u043e\u0433\u0438\u043d \u0438 \u043f\u0430\u0440\u043e\u043b\u044c.");
        return;
    }

    const res = await apiFetch("/api/auth/users", {
        method: "POST",
        body: JSON.stringify({ username, password, role }),
    });
    if (!res.ok) {
        window.alert("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f.");
        return;
    }

    document.getElementById("admin-user-form")?.reset();
    document.getElementById("admin-user-role").value = "operator";
    await loadAdminUsers();
}

async function deleteAdminUser(userId, purge = false) {
    const suffix = purge ? "/purge" : "";
    const res = await apiFetch(`/api/auth/users/${encodeURIComponent(userId)}${suffix}`, { method: "DELETE" });
    if (!res.ok) {
        window.alert("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0443\u0434\u0430\u043b\u0438\u0442\u044c \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f.");
        return;
    }
    await loadAdminUsers();
}

async function createAdminDevice() {
    const name = document.getElementById("admin-device-name")?.value?.trim() || "";
    const deviceId = document.getElementById("admin-device-id")?.value?.trim() || "";
    if (!name) {
        window.alert("\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u044b.");
        return;
    }

    const res = await apiFetch("/api/auth/admin/devices", {
        method: "POST",
        body: JSON.stringify({ name, device_id: deviceId || null }),
    });
    if (!res.ok) {
        window.alert("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0443.");
        return;
    }

    const created = await res.json();
    document.getElementById("admin-device-form")?.reset();
    const secretBox = document.getElementById("admin-device-secret-box");
    if (secretBox) {
        secretBox.innerHTML = `
            <strong>\u041d\u043e\u0432\u0430\u044f \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0430 \u0441\u043e\u0437\u0434\u0430\u043d\u0430</strong><br>
            Device ID: <code>${created.device_id}</code><br>
            Secret: <code>${created.device_secret}</code>
        `;
        secretBox.classList.remove("hidden");
    }

    await loadAdminDevices();
    await loadDevices({ preserveView: true });
}

async function deleteAdminDevice(deviceId, purge = false) {
    const suffix = purge ? "/purge" : "";
    const res = await apiFetch(`/api/auth/admin/devices/${encodeURIComponent(deviceId)}${suffix}`, { method: "DELETE" });
    if (!res.ok) {
        window.alert("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0443\u0434\u0430\u043b\u0438\u0442\u044c \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0443.");
        return;
    }
    await loadAdminDevices();
    await loadDevices({ preserveView: true });
}

function renderDeviceList() {
    const root = document.getElementById("device-list");
    if (!root) {
        return;
    }

    if (!availableDevices.length) {
        root.innerHTML = '<div class="empty-state">\u0414\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0445 \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c \u043f\u043e\u043a\u0430 \u043d\u0435\u0442.</div>';
        return;
    }

    const activeDeviceId = getActiveDeviceId();

    root.innerHTML = availableDevices.map((device) => {
        const isActive = activeDeviceId === device.device_id;
        const youControl = Boolean(device.you_control);
        const controllerText = device.controller_username ? device.controller_username : "-";

        let primaryAction = "";
        if (device.status === "offline") {
            primaryAction = `<button class="control-btn control-btn-secondary" data-action="view" data-device-id="${device.device_id}">\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u0442\u0435\u043b\u0435\u043c\u0435\u0442\u0440\u0438\u044e</button>`;
        } else if (youControl) {
            primaryAction = `<button class="control-btn" data-action="resume" data-device-id="${device.device_id}">\u041f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u0442\u044c \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435</button>`;
        } else if (device.status === "online") {
            primaryAction = `<button class="control-btn" data-action="claim" data-device-id="${device.device_id}">\u0412\u0437\u044f\u0442\u044c \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435</button>`;
        } else {
            primaryAction = `<button class="control-btn control-btn-secondary" disabled>\u0417\u0430\u043d\u044f\u0442</button>`;
        }

        const secondaryAction = youControl
            ? `<button class="control-btn control-btn-secondary" data-action="release" data-device-id="${device.device_id}">\u041e\u0441\u0432\u043e\u0431\u043e\u0434\u0438\u0442\u044c</button>`
            : "";

        return `
            <article class="device-card ${isActive ? "is-active" : ""}">
                <div class="device-card-head">
                    <div class="device-card-title">
                        <strong>${device.name || device.device_id}</strong>
                        <span class="device-code">${device.device_id}</span>
                    </div>
                    <span class="chip-status ${formatStatus(device.status)}">${formatStatusLabel(device.status)}</span>
                </div>

                <div class="device-meta">
                    <div class="device-meta-row"><span>\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435</span><strong>${device.connected ? "\u0415\u0441\u0442\u044c" : "\u041d\u0435\u0442"}</strong></div>
                    <div class="device-meta-row"><span>\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0439 \u0441\u0438\u0433\u043d\u0430\u043b</span><strong>${formatLastSeen(device.last_seen)}</strong></div>
                    <div class="device-meta-row"><span>\u041e\u043f\u0435\u0440\u0430\u0442\u043e\u0440</span><strong>${controllerText}</strong></div>
                </div>

                <div class="device-actions">
                    ${primaryAction}
                    ${secondaryAction}
                </div>
            </article>
        `;
    }).join("");

    root.querySelectorAll("button[data-action]").forEach((button) => {
        button.addEventListener("click", async () => {
            const action = button.dataset.action;
            const deviceId = button.dataset.deviceId;
            if (!action || !deviceId) {
                return;
            }

            if (action === "view") {
                await selectDeviceForView(deviceId);
                closeDeviceList();
                return;
            }

            if (action === "claim") {
                await claimDevice(deviceId);
                return;
            }

            if (action === "resume") {
                setControlledDeviceId(deviceId);
                startControlHeartbeat();
                await selectDeviceForView(deviceId);
                closeDeviceList();
                return;
            }

            if (action === "release") {
                await releaseDevice(deviceId);
            }
        });
    });
}

async function loadDevices({ preserveView = true } = {}) {
    const res = await apiFetch("/api/device/devices");
    if (!res.ok) {
        throw new Error(`Failed to load devices: ${res.status}`);
    }

    availableDevices = await res.json();
    renderDeviceList();

    const controlledDeviceId = getControlledDeviceId();
    if (controlledDeviceId) {
        const controlled = getDeviceById(controlledDeviceId);
        if (!controlled || !controlled.you_control) {
            setControlledDeviceId(null);
            stopControlHeartbeat();
        } else {
            startControlHeartbeat();
        }
    }

    const activeDeviceId = getActiveDeviceId();
    const activeDevice = activeDeviceId ? getDeviceById(activeDeviceId) : null;
    if (activeDevice) {
        renderActiveDevice(activeDevice);
        applyDeviceSnapshot(activeDevice);
        if (preserveView) {
            updateControlAvailability();
        }
    } else if (activeDeviceId) {
        setActiveDeviceId(null);
        renderActiveDevice(null);
        setDashboardVisible(false);
        openDeviceList();
    }

    updateControlAvailability();
}

async function selectDeviceForView(deviceId) {
    const device = getDeviceById(deviceId);
    if (!device) {
        return;
    }

    setActiveDeviceId(deviceId);
    applyDeviceSnapshot(device);
    renderDeviceList();
    updateControlAvailability();
    setDashboardVisible(true);

    closeRealtimeStreams();
    resetRealtimeState();
    applyDeviceSnapshot(device);
    connectVideoStream();
    connectTelemetryStream();
    connectWiFiWebSocket();
    await loadHeatmap();
    await loadDroneTrack();
    await loadScanStatus();
}

async function claimDevice(deviceId) {
    const currentControlled = getControlledDeviceId();
    if (currentControlled && currentControlled != deviceId) {
        await releaseCurrentDevice({ silent: true });
    }

    const res = await apiFetch(`/api/device/devices/${encodeURIComponent(deviceId)}/claim`, { method: "POST" });
    if (!res.ok) {
        const message = await res.text();
        window.alert(message || "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0432\u0437\u044f\u0442\u044c \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435");
        await loadDevices({ preserveView: true });
        return;
    }

    setControlledDeviceId(deviceId);
    startControlHeartbeat();
    await loadDevices({ preserveView: true });
    await selectDeviceForView(deviceId);
    closeDeviceList();
}

async function releaseDevice(deviceId) {
    const res = await apiFetch(`/api/device/devices/${encodeURIComponent(deviceId)}/release`, { method: "POST" });
    if (!res.ok) {
        return;
    }

    if (getControlledDeviceId() === deviceId) {
        setControlledDeviceId(null);
        stopControlHeartbeat();
    }

    await loadDevices({ preserveView: true });
    updateControlAvailability();
}

async function releaseCurrentDevice({ silent = false } = {}) {
    const deviceId = getControlledDeviceId();
    if (!deviceId) {
        return;
    }

    try {
        const res = await apiFetch(`/api/device/devices/${encodeURIComponent(deviceId)}/release`, { method: "POST" });
        if (!res.ok && !silent) {
            const message = await res.text();
            window.alert(message || "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u0441\u0432\u043e\u0431\u043e\u0434\u0438\u0442\u044c \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0443");
        }
    } catch (error) {
        if (!silent) {
            console.error("Release device error:", error);
        }
    }

    setControlledDeviceId(null);
    stopControlHeartbeat();
    await loadDevices({ preserveView: true });
}

async function login(username, password) {
    const submitButton = document.getElementById("login-submit");
    if (submitButton) {
        submitButton.disabled = true;
    }

    showLoginError("");

    try {
        const res = await apiFetch("/api/auth/login", {
            method: "POST",
            body: JSON.stringify({ username, password }),
        }, true);

        if (!res.ok) {
            showLoginError("\u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 \u043b\u043e\u0433\u0438\u043d \u0438\u043b\u0438 \u043f\u0430\u0440\u043e\u043b\u044c.");
            return false;
        }

        const data = await res.json();
        setAuthToken(data.access_token);
        await loadCurrentUser();
        await loadDevices({ preserveView: true });
        startDevicePolling();
        if (isAdminUser()) {
            await openAdminPanel();
        } else {
            openDeviceList();
        }
        return true;
    } catch (error) {
        console.error("Login error:", error);
        showLoginError("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0432\u043e\u0439\u0442\u0438. \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0441\u043e\u0435\u0434\u0438\u043d\u0435\u043d\u0438\u0435 \u0441 \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u043c.");
        return false;
    } finally {
        if (submitButton) {
            submitButton.disabled = false;
        }
    }
}

async function logout() {
    await releaseCurrentDevice({ silent: true });
    performLocalLogout();
}

async function bootstrapApp() {
    renderAuthState();
    updateControlAvailability();

    const token = getAuthToken();
    if (!token) {
        return;
    }

    try {
        await loadCurrentUser();
        await loadDevices({ preserveView: true });
        startDevicePolling();

        if (isAdminUser()) {
            await openAdminPanel();
        } else {
            const activeDeviceId = getActiveDeviceId();
            if (activeDeviceId && getDeviceById(activeDeviceId)) {
                await selectDeviceForView(activeDeviceId);
                closeDeviceList();
            } else {
                openDeviceList();
            }
        }
    } catch (error) {
        console.error("Bootstrap error:", error);
        performLocalLogout();
    }
}

function renderVideoFrame(img) {

    const container = getVideoContainer();
    if (!container || !canvas || !ctx || !detectionCanvas || !detectionCtx) {
        return;
    }

    const rect = container.getBoundingClientRect();
    const containerWidth = Math.max(1, Math.round(rect.width));
    const containerHeight = Math.max(1, Math.round(rect.height));
    const dpr = window.devicePixelRatio || 1;

    canvas.width = Math.round(containerWidth * dpr);
    canvas.height = Math.round(containerHeight * dpr);
    detectionCanvas.width = Math.round(containerWidth * dpr);
    detectionCanvas.height = Math.round(containerHeight * dpr);

    canvas.style.width = `${containerWidth}px`;
    canvas.style.height = `${containerHeight}px`;
    detectionCanvas.style.width = `${containerWidth}px`;
    detectionCanvas.style.height = `${containerHeight}px`;

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    detectionCtx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);
    detectionCtx.scale(dpr, dpr);

    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, containerWidth, containerHeight);
    detectionCtx.clearRect(0, 0, containerWidth, containerHeight);

    const fit = getFitRect(containerWidth, containerHeight, img.width, img.height);

    videoRenderState = {
        img,
        containerWidth,
        containerHeight,
        sourceWidth: img.width,
        sourceHeight: img.height,
        ...fit,
    };

    ctx.drawImage(img, fit.offsetX, fit.offsetY, fit.drawWidth, fit.drawHeight);
}

function drawDetections() {
    if (!detectionCtx || !videoRenderState) {
        return;
    }

    const { offsetX, offsetY, drawWidth, drawHeight, sourceWidth, sourceHeight, containerWidth, containerHeight } = videoRenderState;
    detectionCtx.clearRect(0, 0, containerWidth, containerHeight);

    if (!detectionEnabled) {
        return;
    }

    const scaleX = drawWidth / sourceWidth;
    const scaleY = drawHeight / sourceHeight;

    for (const box of detectionBoxes) {
        const { x1, y1, x2, y2, label, conf, track_id, distance_cm } = box;
        const bx1 = offsetX + x1 * scaleX;
        const by1 = offsetY + y1 * scaleY;
        const bx2 = offsetX + x2 * scaleX;
        const by2 = offsetY + y2 * scaleY;
        const width = bx2 - bx1;
        const height = by2 - by1;

        const isTarget = track_id === selectedAutopilotTargetId && label === selectedAutopilotTargetLabel;
        const color = isTarget ? "#ffb454" : "#35d7a0";

        detectionCtx.strokeStyle = color;
        detectionCtx.lineWidth = isTarget ? 3 : 2;
        detectionCtx.strokeRect(bx1, by1, width, height);

        const meta = [`${label}`, `${Math.round((conf || 0) * 100)}%`];
        if (track_id !== null && track_id !== undefined) {
            meta.push(`#${track_id}`);
        }
        if (distance_cm != null) {
            meta.push(`${(distance_cm / 100).toFixed(1)}m`);
        }

        const text = meta.join(" | ");
        detectionCtx.font = "12px Inter, Arial, sans-serif";
        const textWidth = detectionCtx.measureText(text).width;
        const labelX = bx1;
        const labelY = Math.max(18, by1 - 8);

        detectionCtx.fillStyle = "rgba(6, 12, 22, 0.84)";
        detectionCtx.fillRect(labelX - 1, labelY - 14, textWidth + 10, 18);
        detectionCtx.fillStyle = color;
        detectionCtx.fillText(text, labelX + 4, labelY);
    }
}

function connectVideoStream() {
    const token = getAuthToken();
    const deviceId = getActiveDeviceId();
    if (!token || !deviceId) {
        return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/view?token=${token}&device_id=${encodeURIComponent(deviceId)}`;
    videoStreamDeviceId = deviceId;
    videoWs = new WebSocket(wsUrl);
    videoWs.binaryType = "arraybuffer";

    videoWs.onopen = () => {
        if (getActiveDeviceId() !== deviceId) {
            return;
        }
        updateStatus(true);
        setText("esp-status", "Connected");
    };

    videoWs.onmessage = (event) => {
        if (getActiveDeviceId() !== deviceId) {
            return;
        }

        if (event.data instanceof ArrayBuffer) {
            const blob = new Blob([event.data], { type: "image/jpeg" });
            const img = new Image();

            img.onload = () => {
                sourceFrameWidth = img.width;
                sourceFrameHeight = img.height;

                renderVideoFrame(img);
                drawDetections();

                frameCount += 1;
                updateFps();
                hasVideoFrame = true;

                const noSignal = document.getElementById("no-signal");
                if (noSignal) {
                    noSignal.style.display = "none";
                }

                URL.revokeObjectURL(img.src);
            };

            img.src = URL.createObjectURL(blob);
            return;
        }

        if (typeof event.data === "string") {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "detections") {
                    detectionBoxes = detectionEnabled ? data.boxes || [] : [];
                    currentTargetBox = data.target || null;
                    refreshAutopilotTargetOptions(detectionBoxes);
                    updateDetectionUi();
                    updateTargetDistanceBadge();
                    drawDetections();
                }
            } catch (error) {
                console.error("[WS] text parse error:", error);
            }
        }
    };

    videoWs.onclose = () => {
        if (getActiveDeviceId() !== deviceId) {
            return;
        }

        updateStatus(false);
        setText("esp-status", "Offline");
        hasVideoFrame = false;
        sourceFrameWidth = 0;
        sourceFrameHeight = 0;
        videoRenderState = null;
        detectionBoxes = [];
        currentTargetBox = null;
        clearDetectionCanvas();
        refreshAutopilotTargetOptions([]);
        updateDetectionUi();
        updateTargetDistanceBadge();

        const noSignal = document.getElementById("no-signal");
        if (noSignal) {
            noSignal.style.display = "flex";
        }

        if (currentUser && getActiveDeviceId() === deviceId) {
            setTimeout(connectVideoStream, 3000);
        }
    };

    videoWs.onerror = () => {
        if (getActiveDeviceId() === deviceId) {
            setText("esp-status", "Error");
        }
    };
}

function connectTelemetryStream() {
    const token = getAuthToken();
    const deviceId = getActiveDeviceId();
    if (!token || !deviceId) {
        return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/telemetry?token=${token}&device_id=${encodeURIComponent(deviceId)}`;
    telemetryStreamDeviceId = deviceId;
    telemetryWs = new WebSocket(wsUrl);

    telemetryWs.onmessage = (event) => {
        if (getActiveDeviceId() !== deviceId) {
            return;
        }

        try {
            const data = JSON.parse(event.data);
            renderTelemetry(data);
        } catch (error) {
            console.error("Telemetry parse error:", error);
        }
    };

    telemetryWs.onclose = () => {
        if (currentUser && getActiveDeviceId() === deviceId) {
            setTimeout(connectTelemetryStream, 3000);
        }
    };
}

function renderTelemetry(state) {
    const snapshot = state?.last_data || state || {};
    const hasSnapshot = Boolean(snapshot && Object.keys(snapshot).length);

    if (!state?.connected && !hasSnapshot) {
        setText("device-id", getActiveDeviceId() || "-");
        setText("temperature", "-");
        setText("free-heap", "-");
        setText("uptime", "-");
        setText("cpu-load", "-");
        setText("wifi-rssi", "-");
        setText("wifi-ping", "-");
        setText("created-at", "-");
        setText("battery-level", "-");
        setText("link-quality-copy", "-");
        flashLightEnabled = false;
        updateFlashlightUi();

        const linkBadge = document.querySelector("#wifi-link .status-badge");
        if (linkBadge) {
            linkBadge.classList.remove("online");
            linkBadge.classList.add("offline");
            linkBadge.textContent = "Offline";
        }
        return;
    }

    const data = snapshot;
    const quality = getLinkQuality(data.wifi_rssi_dbm, data.ping_ms);

    setText("device-id", data.device_id ?? getActiveDeviceId() ?? "-");
    setText("temperature", data.temperature != null ? `${Number(data.temperature).toFixed(1)} \u00b0C` : "-");
    setText("free-heap", data.free_heap != null ? `${Math.round(data.free_heap / 1024)} KB` : "-");
    setText("uptime", data.uptime != null ? formatUptime(data.uptime ?? 0) : "-");
    setText("cpu-load", data.cpu_load != null ? `${data.cpu_load}%` : "-");
    setText("wifi-rssi", data.wifi_rssi_dbm != null ? `${data.wifi_rssi_dbm} dBm` : "-");
    setText("wifi-ping", data.ping_ms != null && data.ping_ms >= 0 ? `${data.ping_ms} ms` : "-");
    setText("created-at", state?.last_seen || data.created_at || "-");
    setText("battery-level", data.battery != null ? `${Number(data.battery).toFixed(0)}%` : "-");
    setText("link-quality-copy", quality === "Online" && !state?.connected ? "\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u0434\u0430\u043d\u043d\u044b\u0435" : quality);
    flashLightEnabled = Boolean(data.flash_led);
    updateFlashlightUi();

    const linkBadge = document.querySelector("#wifi-link .status-badge");
    if (linkBadge) {
        const online = Boolean(data.wifi_connected);
        linkBadge.classList.toggle("online", online);
        linkBadge.classList.toggle("offline", !online);

        if (!online) {
            linkBadge.textContent = state?.connected ? "Offline" : "\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u0434\u0430\u043d\u043d\u044b\u0435";
        } else if (data.ping_ok === false) {
            linkBadge.textContent = "Unstable";
        } else {
            linkBadge.textContent = quality;
        }
    }
}

function updateStatus(connected) {
    const indicator = document.getElementById("status-indicator");
    const text = document.getElementById("status-text");

    if (!indicator || !text) {
        return;
    }

    indicator.classList.toggle("offline", !connected);
    indicator.classList.toggle("online", connected);
    text.textContent = connected ? "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u043e" : "\u041d\u0435 \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u043e";
}

function updateFps() {
    if (frameCount % 30 !== 0) {
        return;
    }

    const now = Date.now();
    const elapsed = (now - lastFpsTime) / 1000;
    const fps = elapsed > 0 ? (30 / elapsed).toFixed(1) : "0.0";
    lastFpsTime = now;
    setText("fps", fps);
}

function updateVideoStatus() {
    const espStatus = document.getElementById("esp-status");
    if (!espStatus) {
        return;
    }

    if (videoWs && videoWs.readyState === WebSocket.OPEN) {
        espStatus.textContent = hasVideoFrame ? "\u0418\u0434\u0451\u0442 \u043f\u043e\u0442\u043e\u043a" : "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u043e";
    } else {
        espStatus.textContent = "Offline";
    }
}

function commandByKey(key) {
    const commands = {
        arrowup: "forward",
        arrowdown: "backward",
        arrowleft: "left-forward",
        arrowright: "right-forward",
        w: "forward",
        s: "backward",
        a: "left-forward",
        d: "right-forward",
    };

    return commands[key];
}

async function sendDeviceCommand(command) {
    const deviceId = getActiveDeviceId();
    if (!deviceId) {
        return false;
    }

    const res = await apiFetch("/api/device/command", {
        method: "POST",
        body: JSON.stringify({ device_id: deviceId, command }),
    });

    if (!res.ok) {
        console.error("Command failed", res.status);
        return false;
    }

    return true;
}

async function sendMotorCommand(command) {
    if (autopilotEnabled || !isActiveDeviceControlled()) {
        return;
    }

    try {
        const ok = await sendDeviceCommand(command);
        if (!ok) {
            return;
        }

        updateMotorStatus(command);
    } catch (error) {
        console.error("Command error:", error);
    }
}

async function toggleFlashlight() {
    if (!isActiveDeviceControlled()) {
        window.alert("\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0432\u043e\u0437\u044c\u043c\u0438\u0442\u0435 \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0443 \u043f\u043e\u0434 \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435.");
        return;
    }

    try {
        const ok = await sendDeviceCommand("flashlight-toggle");
        if (!ok) {
            return;
        }

        flashLightEnabled = !flashLightEnabled;
        updateFlashlightUi();
    } catch (error) {
        console.error("Flashlight command error:", error);
    }
}

function updateMotorStatus(command) {
    const leftEl = document.getElementById("motor-left");
    const rightEl = document.getElementById("motor-right");
    if (!leftEl || !rightEl) {
        return;
    }

    leftEl.classList.remove("active");
    rightEl.classList.remove("active");

    switch (command) {
        case "forward":
            motorState.left = "FWD";
            motorState.right = "FWD";
            leftEl.classList.add("active");
            rightEl.classList.add("active");
            break;
        case "backward":
            motorState.left = "BWD";
            motorState.right = "BWD";
            leftEl.classList.add("active");
            rightEl.classList.add("active");
            break;
        case "left-forward":
            motorState.left = "FWD";
            motorState.right = "STOP";
            leftEl.classList.add("active");
            break;
        case "right-forward":
            motorState.left = "STOP";
            motorState.right = "FWD";
            rightEl.classList.add("active");
            break;
        default:
            motorState.left = "STOP";
            motorState.right = "STOP";
    }

    leftEl.textContent = motorState.left;
    rightEl.textContent = motorState.right;
}

function highlightKey(key) {
    const chip = document.querySelector(`.key-chip[data-key="${key}"]`);
    if (chip) {
        chip.classList.add("active");
    }
}

function unhighlightKey(key) {
    const chip = document.querySelector(`.key-chip[data-key="${key}"]`);
    if (chip) {
        chip.classList.remove("active");
    }
}

function getActiveCommand() {
    if (pressedKeys.has("arrowleft") || pressedKeys.has("a")) return "left-forward";
    if (pressedKeys.has("arrowright") || pressedKeys.has("d")) return "right-forward";
    if (pressedKeys.has("arrowup") || pressedKeys.has("w")) return "forward";
    if (pressedKeys.has("arrowdown") || pressedKeys.has("s")) return "backward";
    return "stop";
}

function startCommandLoop() {
    if (commandLoop) {
        return;
    }

    commandLoop = setInterval(() => {
        const command = getActiveCommand();
        if (command !== "stop") {
            sendMotorCommand(command);
        }
    }, COMMAND_INTERVAL_MS);
}

function stopCommandLoop() {
    if (!commandLoop) {
        return;
    }

    clearInterval(commandLoop);
    commandLoop = null;
}

function handlePress(key, command) {
    if (autopilotEnabled || pressedKeys.has(key)) {
        return;
    }

    pressedKeys.add(key);
    highlightKey(key);
    sendMotorCommand(command);
    startCommandLoop();
}

function handleRelease(key) {
    if (!pressedKeys.has(key)) {
        return;
    }

    pressedKeys.delete(key);
    unhighlightKey(key);

    if (pressedKeys.size === 0) {
        stopCommandLoop();
        sendMotorCommand("stop");
    }
}

function setupKeyboardControls() {
    const isTypingTarget = (target) => {
        if (!(target instanceof HTMLElement)) {
            return false;
        }

        const tag = target.tagName;
        return target.isContentEditable || tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
    };

    document.addEventListener("keydown", (event) => {
        if (autopilotEnabled || isTypingTarget(event.target)) {
            return;
        }

        const key = event.key.toLowerCase();
        const command = commandByKey(key);
        if (!command) {
            return;
        }

        event.preventDefault();
        if (pressedKeys.has(key)) {
            return;
        }

        handlePress(key, command);
    });

    document.addEventListener("keyup", (event) => {
        if (isTypingTarget(event.target)) {
            return;
        }

        const key = event.key.toLowerCase();
        if (!commandByKey(key)) {
            return;
        }

        event.preventDefault();
        handleRelease(key);
    });

    window.addEventListener("blur", () => {
        pressedKeys.clear();
        document.querySelectorAll(".key-chip").forEach((chip) => chip.classList.remove("active"));
        stopCommandLoop();
        sendMotorCommand("stop");
        updateMotorStatus("stop");
    });

    document.querySelectorAll(".key-chip[data-command]").forEach((chip) => {
        const key = chip.dataset.key;
        const command = chip.dataset.command;
        if (!key || !command) {
            return;
        }

        const press = (event) => {
            event.preventDefault();
            handlePress(key, command);
        };

        const release = (event) => {
            event.preventDefault();
            handleRelease(key);
        };

        chip.addEventListener("mousedown", press);
        chip.addEventListener("mouseup", release);
        chip.addEventListener("mouseleave", release);
        chip.addEventListener("touchstart", press, { passive: false });
        chip.addEventListener("touchend", release, { passive: false });
        chip.addEventListener("touchcancel", release, { passive: false });
    });
}

function connectWiFiWebSocket() {
    const token = getAuthToken();
    const deviceId = getActiveDeviceId();
    if (!token || !deviceId) {
        return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/wifi-measurements?token=${token}&device_id=${encodeURIComponent(deviceId)}`;
    wifiStreamDeviceId = deviceId;
    wifiWs = new WebSocket(wsUrl);

    wifiWs.onopen = () => {
        console.log("[WS] Connected to Wi-Fi measurements", deviceId);
    };

    wifiWs.onmessage = async (event) => {
        if (getActiveDeviceId() !== deviceId) {
            return;
        }

        try {
            const data = JSON.parse(event.data);

            if (data.type === "wifi_measurement") {
                measurements.push(data);
                updateMeasurementCount();
                setText("last-measurement", `\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0439 RSSI: ${data.rssi} dBm`);
                await loadHeatmap();
                await loadDroneTrack();
            } else if (data.type === "scan_status") {
                applyScanStatus(data);
                await loadDroneTrack();
            } else if (data.type === "scan_notice") {
                setText("scan-status-text", data.message || "\u0421\u043a\u0430\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442\u0441\u044f");
                await loadDroneTrack();
            } else if (data.type === "scan_complete") {
                isScanning = false;
                activeScanMode = "manual";
                autopilotEnabled = false;
                updateScanAutopilotButton();
                setText("scan-mode-text", "\u0420\u0435\u0436\u0438\u043c: \u0440\u0443\u0447\u043d\u043e\u0439");
                setText("scan-status-text", data.completed ? "\u0421\u043a\u0430\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e" : "\u0421\u043a\u0430\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e");
                await loadHeatmap();
                await loadDroneTrack();
            }
        } catch (error) {
            console.error("Wi-Fi WS parse error:", error);
        }
    };

    wifiWs.onclose = () => {
        if (currentUser && getActiveDeviceId() === deviceId) {
            setTimeout(connectWiFiWebSocket, 3000);
        }
    };
}

function setupWifiControls() {
    const showTrackCheckbox = document.getElementById("show-track-checkbox");
    if (showTrackCheckbox) {
        showTrackCheckbox.addEventListener("change", (event) => {
            showTrack = event.target.checked;
            if (currentHeatmap) {
                drawHeatmap(currentHeatmap, "heatmap-canvas");
            }
            if (showTrack) {
                loadDroneTrack();
            }
        });
    }

    const startButton = document.getElementById("start-scan-btn");
    if (startButton) startButton.onclick = startScan;

    const stopButton = document.getElementById("stop-scan-btn");
    if (stopButton) stopButton.onclick = stopScan;

    const refreshButton = document.getElementById("refresh-map-btn");
    if (refreshButton) refreshButton.onclick = loadHeatmap;

    const clearButton = document.getElementById("clear-data-btn");
    if (clearButton) clearButton.onclick = clearData;

    const saveButton = document.getElementById("save-map-btn");
    if (saveButton) saveButton.onclick = saveHeatmap;

    const loadSavedButton = document.getElementById("load-saved-btn");
    if (loadSavedButton) loadSavedButton.onclick = loadSavedHeatmap;

    const clearTrackButton = document.getElementById("clear-track-btn");
    if (clearTrackButton) clearTrackButton.onclick = clearDroneTrack;

    const toggleScanAutopilotButton = document.getElementById("toggle-scan-autopilot-btn");
    if (toggleScanAutopilotButton) toggleScanAutopilotButton.onclick = toggleScanAutopilot;

    const downloadButton = document.getElementById("download-heatmap-btn");
    if (downloadButton) downloadButton.onclick = downloadHeatmapImage;

    updateScanAutopilotButton();
}

async function loadHeatmap() {
    try {
        const { widthCells, heightCells, stepCm } = getScanConfig();

        const deviceQuery = getActiveDeviceQuery();
        if (!deviceQuery) {
            currentHeatmap = null;
            drawGridOnly("heatmap-canvas");
            updateMeasurementCount(0);
            return;
        }

        const res = await apiFetch(`/api/wifi/heatmap?${deviceQuery}&width_cells=${widthCells}&height_cells=${heightCells}&step_cm=${stepCm}`);
        const data = await res.json();

        if (data.error) {
            console.warn(data.error);
            currentHeatmap = null;
            drawGridOnly("heatmap-canvas");
            updateMeasurementCount(0);
            return;
        }

        currentHeatmap = data;
        if (Array.isArray(data.measurements)) {
            measurements = data.measurements;
        }

        drawHeatmap(data, "heatmap-canvas");
        updateMeasurementCount(data.total_points || 0);
    } catch (error) {
        console.error("Heatmap load error:", error);
        drawGridOnly("heatmap-canvas");
    }
}

function drawHeatmap(data, canvasId) {
    const canvasEl = document.getElementById(canvasId);
    if (!canvasEl) {
        return;
    }

    const context = canvasEl.getContext("2d");
    const width = canvasEl.width / (window.devicePixelRatio || 1);
    const height = canvasEl.height / (window.devicePixelRatio || 1);

    context.fillStyle = "#09111f";
    context.fillRect(0, 0, width, height);

    if (!data.heatmap || !data.heatmap.z) {
        drawGridOnly(canvasId);
        return;
    }

    const z = data.heatmap.z;
    const rows = z.length;
    const cols = z[0].length;
    const cellW = width / cols;
    const cellH = height / rows;

    for (let y = 0; y < rows; y += 1) {
        for (let x = 0; x < cols; x += 1) {
            const rssi = z[y][x];
            if (rssi === null || Number.isNaN(rssi)) {
                continue;
            }

            context.fillStyle = getRssiColor(rssi);
            context.fillRect(x * cellW, y * cellH, cellW + 1, cellH + 1);
        }
    }

    context.beginPath();
    context.strokeStyle = "rgba(255, 255, 255, 0.18)";
    context.lineWidth = 1;

    for (let x = 0; x <= cols; x += 1) {
        context.moveTo(x * cellW, 0);
        context.lineTo(x * cellW, height);
    }

    for (let y = 0; y <= rows; y += 1) {
        context.moveTo(0, y * cellH);
        context.lineTo(width, y * cellH);
    }

    context.stroke();

    if (showTrack && droneTrack.length > 0 && canvasId === "heatmap-canvas") {
        drawDroneTrack();
    }
}

function drawGridOnly(canvasId) {
    const canvasEl = document.getElementById(canvasId);
    if (!canvasEl) {
        return;
    }

    const context = canvasEl.getContext("2d");
    const width = canvasEl.width / (window.devicePixelRatio || 1);
    const height = canvasEl.height / (window.devicePixelRatio || 1);
    const { widthCells: gridCols, heightCells: gridRows } = getScanConfig();
    const cellW = width / Math.max(1, gridCols);
    const cellH = height / Math.max(1, gridRows);

    context.fillStyle = "#09111f";
    context.fillRect(0, 0, width, height);
    context.beginPath();
    context.strokeStyle = "rgba(255, 255, 255, 0.08)";

    for (let x = 0; x <= gridCols; x += 1) {
        context.moveTo(x * cellW, 0);
        context.lineTo(x * cellW, height);
    }

    for (let y = 0; y <= gridRows; y += 1) {
        context.moveTo(0, y * cellH);
        context.lineTo(width, y * cellH);
    }

    context.stroke();

    if (showTrack && droneTrack.length > 0 && canvasId === "heatmap-canvas") {
        drawDroneTrack();
    }
}

function getDisplayedMeasurementCount() {
    const el = document.getElementById("measurement-count");
    if (!el) {
        return 0;
    }

    const match = el.textContent.match(/(\d+)/);
    return match ? Number(match[1]) : 0;
}

function updateMeasurementCount(exactValue = null) {
    const nextValue = typeof exactValue === "number" ? exactValue : getDisplayedMeasurementCount() + 1;
    setText("measurement-count", `\u0422\u043e\u0447\u0435\u043a: ${nextValue}`);
}

function releaseManualControls() {
    pressedKeys.clear();
    document.querySelectorAll(".key-chip").forEach((chip) => chip.classList.remove("active"));
    stopCommandLoop();
    updateMotorStatus("stop");
}

function updateScanAutopilotButton() {
    const button = document.getElementById("toggle-scan-autopilot-btn");
    if (!button) {
        return;
    }

    button.textContent = `\u0410\u0432\u0442\u043e\u043f\u0440\u043e\u0445\u043e\u0434: ${autopilotEnabled ? "\u0412\u041a\u041b" : "\u0412\u042b\u041a\u041b"}`;
    button.classList.toggle("active", autopilotEnabled);
    button.disabled = !isScanning || !isActiveDeviceControlled();
}

async function startScan() {
    try {
        const { widthCells, heightCells, stepCm } = getScanConfig();

        releaseManualControls();
        if (!isActiveDeviceControlled()) {
            window.alert("\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0432\u043e\u0437\u044c\u043c\u0438\u0442\u0435 \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0443 \u043f\u043e\u0434 \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435.");
            return;
        }

        const deviceQuery = getActiveDeviceQuery();
        const res = await apiFetch(`/api/wifi/start?${deviceQuery}&width=${widthCells}&height=${heightCells}&step_cm=${stepCm}&mode=manual`, { method: "POST" });
        if (!res.ok) {
            isScanning = false;
            autopilotEnabled = false;
            updateScanAutopilotButton();
            setText("scan-status-text", "\u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u043f\u0443\u0441\u043a\u0430");
            return;
        }

        const data = await res.json();
        if (data.status === "error") {
            isScanning = false;
            autopilotEnabled = false;
            updateScanAutopilotButton();
            setText("scan-status-text", "\u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u043f\u0443\u0441\u043a\u0430");
            window.alert(data.message || "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c \u0441\u043a\u0430\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435");
            return;
        }

        applyScanStatus(data);
        await loadHeatmap();
        await loadDroneTrack();
    } catch (error) {
        isScanning = false;
        autopilotEnabled = false;
        updateScanAutopilotButton();
        setText("scan-status-text", "\u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u043f\u0443\u0441\u043a\u0430");
        console.error("Start scan error:", error);
    }
}

async function toggleScanAutopilot() {
    if (!isScanning) {
        window.alert("\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u0435 \u0441\u043a\u0430\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435");
        return;
    }

    const nextMode = autopilotEnabled ? "manual" : "autopilot";

    try {
        releaseManualControls();
        if (!isActiveDeviceControlled()) {
            window.alert("\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0432\u043e\u0437\u044c\u043c\u0438\u0442\u0435 \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0443 \u043f\u043e\u0434 \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435.");
            return;
        }

        const deviceQuery = getActiveDeviceQuery();
        const res = await apiFetch(`/api/wifi/mode?${deviceQuery}&mode=${nextMode}`, { method: "POST" });
        if (!res.ok) {
            setText("scan-status-text", "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u0435\u0440\u0435\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u0440\u0435\u0436\u0438\u043c");
            return;
        }

        const data = await res.json();
        if (data.status === "error") {
            setText("scan-status-text", data.message || "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u0435\u0440\u0435\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u0440\u0435\u0436\u0438\u043c");
            return;
        }

        applyScanStatus(data);
    } catch (error) {
        console.error("Toggle scan autopilot error:", error);
        setText("scan-status-text", "\u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u0435\u0440\u0435\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f \u0440\u0435\u0436\u0438\u043c\u0430");
    }
}

async function stopScan() {
    try {
        if (!isActiveDeviceControlled()) {
            window.alert("\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0432\u043e\u0437\u044c\u043c\u0438\u0442\u0435 \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0443 \u043f\u043e\u0434 \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435.");
            return;
        }

        const deviceQuery = getActiveDeviceQuery();
        const res = await apiFetch(`/api/wifi/stop?${deviceQuery}`, { method: "POST" });
        if (res.ok) {
            const data = await res.json();
            applyScanStatus(data);
            setText("scan-status-text", "\u0421\u043a\u0430\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e");
        }
    } catch (error) {
        console.error("Stop scan error:", error);
    }
}

function applyScanStatus(data) {
    activeScanMode = data.mode || "manual";
    isScanning = Boolean(data.running);
    autopilotEnabled = isScanning && activeScanMode === "autopilot";
    updateScanAutopilotButton();
    setText("scan-mode-text", activeScanMode === "autopilot" ? "\u0420\u0435\u0436\u0438\u043c: \u0430\u0432\u0442\u043e\u043f\u0440\u043e\u0445\u043e\u0434" : "\u0420\u0435\u0436\u0438\u043c: \u0440\u0443\u0447\u043d\u043e\u0439");

    if (!isScanning) {
        setText("scan-status-text", "\u041e\u0436\u0438\u0434\u0430\u043d\u0438\u0435");
        return;
    }

    const coords = `(${data.x ?? 0}, ${data.y ?? 0})`;
    setText(
        "scan-status-text",
        activeScanMode === "autopilot" ? `\u0410\u0432\u0442\u043e\u043f\u0440\u043e\u0445\u043e\u0434: ${coords}` : `\u0420\u0443\u0447\u043d\u043e\u0439 \u043f\u0440\u043e\u0445\u043e\u0434: ${coords}`
    );
}

async function clearData() {
    if (!window.confirm("\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c \u0432\u0441\u0435 Wi-Fi \u0438\u0437\u043c\u0435\u0440\u0435\u043d\u0438\u044f?")) {
        return;
    }

    try {
        if (!isActiveDeviceControlled()) {
            window.alert("\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0432\u043e\u0437\u044c\u043c\u0438\u0442\u0435 \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0443 \u043f\u043e\u0434 \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435.");
            return;
        }

        const deviceQuery = getActiveDeviceQuery();
        await apiFetch(`/api/wifi/measurements?${deviceQuery}`, { method: "DELETE" });
        measurements = [];
        currentHeatmap = null;
        updateMeasurementCount(0);
        setText("last-measurement", "\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0439 RSSI: --");
        drawGridOnly("heatmap-canvas");
    } catch (error) {
        console.error("Clear data error:", error);
    }
}

function downloadHeatmapImage() {
    const canvasEl = document.getElementById("heatmap-canvas");
    if (!canvasEl) {
        return;
    }

    const link = document.createElement("a");
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    link.href = canvasEl.toDataURL("image/png");
    link.download = `wifi-heatmap-${stamp}.png`;
    link.click();
}
async function saveHeatmap() {
    const name = document.getElementById("map-name")?.value?.trim();
    if (!name) {
        window.alert("\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u043a\u0430\u0440\u0442\u044b");
        return;
    }

    try {
        const deviceQuery = getActiveDeviceQuery();
        const res = await apiFetch(`/api/wifi/save?${deviceQuery}&name=${encodeURIComponent(name)}`, { method: "POST" });
        if (!res.ok) {
            window.alert("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u043a\u0430\u0440\u0442\u0443");
            return;
        }

        window.alert("\u041a\u0430\u0440\u0442\u0430 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0430");
        document.getElementById("map-name").value = "";
    } catch (error) {
        console.error("Save heatmap error:", error);
    }
}

async function loadSavedMapsList() {
    try {
        const deviceQuery = getActiveDeviceQuery();
        const res = await apiFetch(`/api/wifi/saved?${deviceQuery}`);
        if (!res.ok) {
            return;
        }

        const maps = await res.json();
        const select = document.getElementById("saved-maps-select");
        if (!select) {
            return;
        }

        select.innerHTML = '<option value="">-- \u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043a\u0430\u0440\u0442\u0443 --</option>';
        maps.forEach((map) => {
            const option = document.createElement("option");
            option.value = map.id;
            option.textContent = `${map.name} (${new Date(map.created_at).toLocaleString()})`;
            select.appendChild(option);
        });
    } catch (error) {
        console.error("Saved maps load error:", error);
    }
}

async function loadSavedHeatmap() {
    const select = document.getElementById("saved-maps-select");
    const id = select?.value;
    if (!id) {
        return;
    }

    try {
        const deviceQuery = getActiveDeviceQuery();
        const res = await apiFetch(`/api/wifi/saved/${id}?${deviceQuery}`);
        if (!res.ok) {
            return;
        }

        const data = await res.json();
        if (!data.data || !data.data.length) {
            drawGridOnly("saved-canvas");
            return;
        }

        const step = data.data[0]?.step_cm || 100;
        const widthCells = Math.max(...data.data.map((item) => item.x)) + 1;
        const heightCells = Math.max(...data.data.map((item) => item.y)) + 1;
        const rows = heightCells * 10 + 1;
        const cols = widthCells * 10 + 1;
        const z = Array.from({ length: rows }, () => Array.from({ length: cols }, () => -90));

        for (const item of data.data) {
            const xIndex = Math.floor(item.x * 10);
            const yIndex = Math.floor(item.y * 10);
            if (z[yIndex] && z[yIndex][xIndex] !== undefined) {
                z[yIndex][xIndex] = item.rssi;
            }
        }

        drawHeatmap({
            heatmap: {
                z,
                min_rssi: Math.min(...data.data.map((item) => item.rssi)),
                max_rssi: Math.max(...data.data.map((item) => item.rssi)),
            },
            measurements: data.data,
            width_cells: widthCells,
            height_cells: heightCells,
            step_cm: step,
            total_points: data.data.length,
        }, "saved-canvas");
    } catch (error) {
        console.error("Saved heatmap load error:", error);
    }
}

async function loadDroneTrack() {
    try {
        const deviceQuery = getActiveDeviceQuery();
        if (!deviceQuery) {
            droneTrack = [];
            return;
        }
        const res = await apiFetch(`/api/wifi/track?${deviceQuery}`);
        if (!res.ok) {
            return;
        }

        const data = await res.json();
        droneTrack = data.track || [];
        if (showTrack) {
            if (currentHeatmap) {
                drawHeatmap(currentHeatmap, "heatmap-canvas");
            } else {
                drawGridOnly("heatmap-canvas");
            }
        }
    } catch (error) {
        console.error("Drone track load error:", error);
    }
}

async function loadScanStatus() {
    try {
        const deviceQuery = getActiveDeviceQuery();
        if (!deviceQuery) {
            applyScanStatus({ running: false, mode: "manual" });
            return;
        }
        const res = await apiFetch(`/api/wifi/status?${deviceQuery}`);
        if (!res.ok) {
            return;
        }
        const data = await res.json();
        applyScanStatus(data);
    } catch (error) {
        console.error("Scan status load error:", error);
    }
}

async function clearDroneTrack() {
    try {
        if (!isActiveDeviceControlled()) {
            window.alert("\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0432\u043e\u0437\u044c\u043c\u0438\u0442\u0435 \u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0443 \u043f\u043e\u0434 \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435.");
            return;
        }

        const deviceQuery = getActiveDeviceQuery();
        await apiFetch(`/api/wifi/track?${deviceQuery}`, { method: "DELETE" });
        droneTrack = [];
        if (currentHeatmap) {
            drawHeatmap(currentHeatmap, "heatmap-canvas");
        } else {
            drawGridOnly("heatmap-canvas");
        }
    } catch (error) {
        console.error("Clear track error:", error);
    }
}

function drawDroneTrack() {
    const canvasEl = document.getElementById("heatmap-canvas");
    if (!canvasEl || !droneTrack.length) {
        return;
    }

    const context = canvasEl.getContext("2d");
    const width = canvasEl.width / (window.devicePixelRatio || 1);
    const height = canvasEl.height / (window.devicePixelRatio || 1);
    const { widthCells, heightCells } = getScanConfig();
    const maxX = Math.max(1, Number(currentHeatmap?.width_cells || widthCells));
    const maxY = Math.max(1, Number(currentHeatmap?.height_cells || heightCells));

    if (droneTrack.length > 1) {
        let lastX = null;
        let lastY = null;

        for (const point of droneTrack) {
            const px = ((Number(point.x) + 0.5) / maxX) * width;
            const py = ((Number(point.y) + 0.5) / maxY) * height;

            context.strokeStyle = point.avoiding ? "#ff8c42" : "#35d7a0";
            context.lineWidth = 2;

            if (lastX !== null && lastY !== null) {
                context.beginPath();
                context.moveTo(lastX, lastY);
                context.lineTo(px, py);
                context.stroke();
            }

            lastX = px;
            lastY = py;
        }
    }

    for (const point of droneTrack) {
        if (point.command !== "measure") {
            continue;
        }

        const px = ((Number(point.x) + 0.5) / maxX) * width;
        const py = ((Number(point.y) + 0.5) / maxY) * height;
        context.beginPath();
        context.arc(px, py, 4, 0, Math.PI * 2);
        context.fillStyle = "#ffffff";
        context.fill();
    }
}





