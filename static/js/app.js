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

const AUTO_LOGIN = "operator";
const AUTO_PASSWORD = "operator123";
const DEVICE_ID = "bpna-01";

let measurements = [];
let currentHeatmap = null;
let isScanning = false;
let droneTrack = [];
let showTrack = true;
let activeScanMode = "manual";

function getAuthToken() {
    return sessionStorage.getItem("access_token");
}

function setAuthToken(token) {
    sessionStorage.setItem("access_token", token);
}

async function performAutoLogin() {
    try {
        const res = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: AUTO_LOGIN, password: AUTO_PASSWORD }),
        });

        if (!res.ok) {
            return false;
        }

        const data = await res.json();
        if (data.access_token) {
            setAuthToken(data.access_token);
            console.log("[AUTH] Auto login success");
            return true;
        }
    } catch (error) {
        console.error("[AUTH] Login error:", error);
    }

    return false;
}

async function ensureAuth() {
    if (getAuthToken()) {
        return true;
    }

    return performAutoLogin();
}

async function apiFetch(url, options = {}, retryOn401 = true) {
    await ensureAuth();

    const token = getAuthToken();
    const headers = {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {}),
    };

    const res = await fetch(url, { ...options, headers });

    if (res.status === 401 && retryOn401) {
        const ok = await performAutoLogin();
        if (!ok) {
            return res;
        }

        const refreshedToken = getAuthToken();
        return fetch(url, {
            ...options,
            headers: {
                ...headers,
                Authorization: `Bearer ${refreshedToken}`,
            },
        });
    }

    return res;
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = value;
    }
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

    await ensureAuth();

    resizeVideoCanvases();
    resizeHeatmapCanvases();

    connectVideoStream();
    connectTelemetryStream();
    connectWiFiWebSocket();

    setupKeyboardControls();
    setupWifiControls();
    updateDetectionUi();
    updateVideoStatus();

    await loadHeatmap();
    await loadDroneTrack();
    await loadScanStatus();

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
        if (showTrack && isScanning) {
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
        toggle.textContent = `Детекция: ${detectionEnabled ? "ВКЛ" : "ВЫКЛ"}`;
        toggle.classList.toggle("active", detectionEnabled);
    }

    const trackedTargets = detectionBoxes.filter((box) => box.track_id !== null && box.track_id !== undefined);
    const summary = document.getElementById("detection-summary");

    if (summary) {
        if (!detectionEnabled) {
            summary.textContent = "Детекция выключена";
        } else if (!detectionBoxes.length) {
            summary.textContent = "Детекция включена, ожидание объектов";
        } else {
            summary.textContent = `Найдено объектов: ${detectionBoxes.length}`;
        }
    }

    const autopilotButton = document.getElementById("autopilot-toggle");
    if (autopilotButton) {
        autopilotButton.textContent = `Автопилот: ${autopilotEnabled ? "ВКЛ" : "ВЫКЛ"}`;
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
        option.textContent = detectionEnabled ? "Трекинг недоступен" : "Детекция выключена";
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
    if (selectedAutopilotTargetId === null || !selectedAutopilotTargetLabel) {
        console.warn("[AUTOPILOT] No tracked target selected");
        return;
    }

    const nextState = !autopilotEnabled;

    try {
        const res = await apiFetch(
            `/api/device/autopilot?enabled=${nextState}&target_id=${selectedAutopilotTargetId}&target_label=${encodeURIComponent(selectedAutopilotTargetLabel)}`,
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
        badge.textContent = "Цель не выбрана";
        return;
    }

    const target = detectionBoxes.find(
        (box) => box.track_id === selectedAutopilotTargetId && box.label === selectedAutopilotTargetLabel
    );

    if (!target) {
        badge.textContent = `Цель ${selectedAutopilotTargetLabel} #${selectedAutopilotTargetId} потеряна`;
        return;
    }

    const distanceText = target.distance_cm != null
        ? `${(target.distance_cm / 100).toFixed(2)} м`
        : "без оценки дистанции";

    badge.textContent = `${target.label} #${target.track_id} | дистанция ${distanceText}${autopilotEnabled ? " | автопилот активен" : ""}`;
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
    if (!token) {
        setTimeout(connectVideoStream, 2000);
        return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/view?token=${token}&device_id=${encodeURIComponent(DEVICE_ID)}`;

    videoWs = new WebSocket(wsUrl);
    videoWs.binaryType = "arraybuffer";

    videoWs.onopen = () => {
        updateStatus(true);
        setText("esp-status", "Connected");
    };

    videoWs.onmessage = (event) => {
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

        setTimeout(connectVideoStream, 3000);
    };

    videoWs.onerror = () => {
        setText("esp-status", "Error");
    };
}

function connectTelemetryStream() {
    const token = getAuthToken();
    if (!token) {
        setTimeout(connectTelemetryStream, 2000);
        return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/telemetry?token=${token}&device_id=${encodeURIComponent(DEVICE_ID)}`;

    telemetryWs = new WebSocket(wsUrl);

    telemetryWs.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            renderTelemetry(data);
        } catch (error) {
            console.error("Telemetry parse error:", error);
        }
    };

    telemetryWs.onclose = () => {
        setTimeout(connectTelemetryStream, 3000);
    };
}

function renderTelemetry(state) {
    if (!state.connected) {
        setText("device-id", "-");
        setText("temperature", "-");
        setText("free-heap", "-");
        setText("uptime", "-");
        setText("cpu-load", "-");
        setText("wifi-rssi", "-");
        setText("wifi-ping", "-");
        setText("created-at", "-");
        setText("battery-level", "-");
        setText("link-quality-copy", "-");

        const linkBadge = document.querySelector("#wifi-link .status-badge");
        if (linkBadge) {
            linkBadge.classList.remove("online");
            linkBadge.classList.add("offline");
            linkBadge.textContent = "Offline";
        }
        return;
    }

    const data = state?.last_data || state || {};
    const quality = getLinkQuality(data.wifi_rssi_dbm, data.ping_ms);

    setText("device-id", data.device_id ?? "-");
    setText("temperature", data.temperature != null ? `${Number(data.temperature).toFixed(1)} °C` : "-");
    setText("free-heap", data.free_heap != null ? `${Math.round(data.free_heap / 1024)} KB` : "-");
    setText("uptime", formatUptime(data.uptime ?? 0));
    setText("cpu-load", data.cpu_load != null ? `${data.cpu_load}%` : "-");
    setText("wifi-rssi", data.wifi_rssi_dbm != null ? `${data.wifi_rssi_dbm} dBm` : "-");
    setText("wifi-ping", data.ping_ms != null && data.ping_ms >= 0 ? `${data.ping_ms} ms` : "-");
    setText("created-at", state.last_seen || data.created_at || "-");
    setText("battery-level", data.battery != null ? `${Number(data.battery).toFixed(0)}%` : "-");
    setText("link-quality-copy", quality);

    const linkBadge = document.querySelector("#wifi-link .status-badge");
    if (linkBadge) {
        const online = Boolean(data.wifi_connected);
        linkBadge.classList.toggle("online", online);
        linkBadge.classList.toggle("offline", !online);

        if (!online) {
            linkBadge.textContent = "Offline";
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
    text.textContent = connected ? "Подключено" : "Не подключено";
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
        espStatus.textContent = hasVideoFrame ? "Streaming" : "Connected";
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

async function sendMotorCommand(command) {
    if (autopilotEnabled) {
        return;
    }

    try {
        const res = await apiFetch("/api/device/command", {
            method: "POST",
            body: JSON.stringify({ command }),
        });

        if (!res.ok) {
            console.error("Command failed", res.status);
            return;
        }

        updateMotorStatus(command);
    } catch (error) {
        console.error("Command error:", error);
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
    document.addEventListener("keydown", (event) => {
        if (autopilotEnabled) {
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
    if (!token) {
        setTimeout(connectWiFiWebSocket, 2000);
        return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/wifi-measurements?token=${token}`;
    wifiWs = new WebSocket(wsUrl);

    wifiWs.onopen = () => {
        console.log("[WS] Connected to Wi-Fi measurements");
    };

    wifiWs.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            if (data.type === "wifi_measurement") {
                measurements.push(data);
                updateMeasurementCount();
                setText("last-measurement", `Последний RSSI: ${data.rssi} dBm`);
                if (currentHeatmap) {
                    drawHeatmap(currentHeatmap, "heatmap-canvas");
                }
            } else if (data.type === "scan_status") {
                applyScanStatus(data);
            } else if (data.type === "scan_notice") {
                setText("scan-status-text", data.message || "Сканирование обновлено");
            } else if (data.type === "scan_complete") {
                isScanning = false;
                activeScanMode = "manual";
                autopilotEnabled = false;
                updateScanAutopilotButton();
                setText("scan-mode-text", "Режим: ручной");
                setText("scan-status-text", data.completed ? "Сканирование завершено" : "Сканирование остановлено");
                loadHeatmap();
                loadDroneTrack();
            }
        } catch (error) {
            console.error("Wi-Fi WS parse error:", error);
        }
    };

    wifiWs.onclose = () => {
        setTimeout(connectWiFiWebSocket, 3000);
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
        const width = document.getElementById("scan-width")?.value || 10;
        const height = document.getElementById("scan-height")?.value || 10;
        const step = document.getElementById("scan-step")?.value || 100;

        const res = await apiFetch(`/api/wifi/heatmap?width_cells=${width}&height_cells=${height}&step_cm=${step}`);
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
    const cellSize = Math.max(24, Math.round(width / 10));

    context.fillStyle = "#09111f";
    context.fillRect(0, 0, width, height);
    context.beginPath();
    context.strokeStyle = "rgba(255, 255, 255, 0.08)";

    for (let x = 0; x <= width; x += cellSize) {
        context.moveTo(x, 0);
        context.lineTo(x, height);
    }

    for (let y = 0; y <= height; y += cellSize) {
        context.moveTo(0, y);
        context.lineTo(width, y);
    }

    context.stroke();
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
    setText("measurement-count", `Точек: ${nextValue}`);
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

    button.textContent = `Автозмейка: ${autopilotEnabled ? "ВКЛ" : "ВЫКЛ"}`;
    button.classList.toggle("active", autopilotEnabled);
    button.disabled = !isScanning;
}

async function startScan() {
    try {
        const width = document.getElementById("scan-width")?.value || 10;
        const height = document.getElementById("scan-height")?.value || 10;
        const step = document.getElementById("scan-step")?.value || 100;

        releaseManualControls();
        const res = await apiFetch(`/api/wifi/start?width=${width}&height=${height}&step_cm=${step}&mode=manual`, { method: "POST" });
        if (!res.ok) {
            isScanning = false;
            autopilotEnabled = false;
            updateScanAutopilotButton();
            setText("scan-status-text", "Ошибка запуска");
            return;
        }

        const data = await res.json();
        if (data.status === "error") {
            isScanning = false;
            autopilotEnabled = false;
            updateScanAutopilotButton();
            setText("scan-status-text", "Ошибка запуска");
            window.alert(data.message || "Не удалось запустить сканирование");
            return;
        }

        applyScanStatus(data);
        await loadHeatmap();
        await loadDroneTrack();
    } catch (error) {
        isScanning = false;
        autopilotEnabled = false;
        updateScanAutopilotButton();
        setText("scan-status-text", "Ошибка запуска");
        console.error("Start scan error:", error);
    }
}

async function toggleScanAutopilot() {
    if (!isScanning) {
        window.alert("Сначала запустите сканирование");
        return;
    }

    const nextMode = autopilotEnabled ? "manual" : "autopilot";

    try {
        releaseManualControls();
        const res = await apiFetch(`/api/wifi/mode?mode=${nextMode}`, { method: "POST" });
        if (!res.ok) {
            setText("scan-status-text", "Не удалось переключить режим");
            return;
        }

        const data = await res.json();
        if (data.status === "error") {
            setText("scan-status-text", data.message || "Не удалось переключить режим");
            return;
        }

        applyScanStatus(data);
    } catch (error) {
        console.error("Toggle scan autopilot error:", error);
        setText("scan-status-text", "Ошибка переключения режима");
    }
}

async function stopScan() {
    try {
        const res = await apiFetch("/api/wifi/stop", { method: "POST" });
        if (res.ok) {
            const data = await res.json();
            applyScanStatus(data);
            setText("scan-status-text", "Сканирование остановлено");
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
    setText("scan-mode-text", activeScanMode === "autopilot" ? "Режим: автозмейка" : "Режим: ручной");

    if (!isScanning) {
        setText("scan-status-text", "Ожидание");
        return;
    }

    const coords = `(${data.x ?? 0}, ${data.y ?? 0})`;
    setText(
        "scan-status-text",
        activeScanMode === "autopilot" ? `Автозмейка: ${coords}` : `Ручной сбор: ${coords}`
    );
}

async function clearData() {
    if (!window.confirm("Очистить все Wi-Fi измерения?")) {
        return;
    }

    try {
        await apiFetch("/api/wifi/measurements", { method: "DELETE" });
        measurements = [];
        currentHeatmap = null;
        updateMeasurementCount(0);
        setText("last-measurement", "Последний RSSI: --");
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
        window.alert("Введите название карты");
        return;
    }

    try {
        const res = await apiFetch(`/api/wifi/save?name=${encodeURIComponent(name)}`, { method: "POST" });
        if (!res.ok) {
            window.alert("Не удалось сохранить карту");
            return;
        }

        window.alert("Карта сохранена");
        document.getElementById("map-name").value = "";
    } catch (error) {
        console.error("Save heatmap error:", error);
    }
}

async function loadSavedMapsList() {
    try {
        const res = await apiFetch("/api/wifi/saved");
        if (!res.ok) {
            return;
        }

        const maps = await res.json();
        const select = document.getElementById("saved-maps-select");
        if (!select) {
            return;
        }

        select.innerHTML = '<option value="">-- Выберите карту --</option>';
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
        const res = await apiFetch(`/api/wifi/saved/${id}`);
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
        const res = await apiFetch("/api/wifi/track");
        if (!res.ok) {
            return;
        }

        const data = await res.json();
        droneTrack = data.track || [];
        if (showTrack && currentHeatmap) {
            drawHeatmap(currentHeatmap, "heatmap-canvas");
        }
    } catch (error) {
        console.error("Drone track load error:", error);
    }
}

async function loadScanStatus() {
    try {
        const res = await apiFetch("/api/wifi/status");
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
        await apiFetch("/api/wifi/track", { method: "DELETE" });
        droneTrack = [];
        if (currentHeatmap) {
            drawHeatmap(currentHeatmap, "heatmap-canvas");
        }
    } catch (error) {
        console.error("Clear track error:", error);
    }
}

function drawDroneTrack() {
    const canvasEl = document.getElementById("heatmap-canvas");
    if (!canvasEl || !currentHeatmap || !droneTrack.length) {
        return;
    }

    const context = canvasEl.getContext("2d");
    const width = canvasEl.width / (window.devicePixelRatio || 1);
    const height = canvasEl.height / (window.devicePixelRatio || 1);
    const maxX = Math.max(1, currentHeatmap.width_cells || 1);
    const maxY = Math.max(1, currentHeatmap.height_cells || 1);

    if (droneTrack.length > 1) {
        let lastX = null;
        let lastY = null;

        for (const point of droneTrack) {
            const px = (point.x / maxX) * width;
            const py = (point.y / maxY) * height;

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

        const px = (point.x / maxX) * width;
        const py = (point.y / maxY) * height;
        context.beginPath();
        context.arc(px, py, 4, 0, Math.PI * 2);
        context.fillStyle = "#ffffff";
        context.fill();
    }
}




