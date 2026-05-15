let wifiWs = null;
let measurements = [];
let currentHeatmap = null;
let isScanning = false;
let droneTrack = [];
let showTrack = true;

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
        console.log("[WS] Connected to WiFi measurements");
    };

    wifiWs.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            if (data.type === "wifi_measurement") {
                measurements.push(data);
                updateMeasurementCount();
                if (currentHeatmap) {
                    drawHeatmap(currentHeatmap, 'heatmap-canvas');
                }
                document.getElementById('last-measurement').textContent = `📡 Последний RSSI: ${data.rssi} dBm`;
            } else if (data.type === "scan_complete") {
                document.getElementById('scan-status-text').textContent = '✅ Сканирование завершено!';
                isScanning = false;
                loadHeatmap();
                loadDroneTrack();
            }
        } catch (e) {
            console.error("WS parse error:", e);
        }
    };

    wifiWs.onclose = () => {
        console.log("[WS] Disconnected, reconnecting...");
        setTimeout(connectWiFiWebSocket, 3000);
    };
}

async function loadHeatmap() {
    const width = document.getElementById('scan-width').value;
    const height = document.getElementById('scan-height').value;
    const step = document.getElementById('scan-step').value;

    const res = await apiFetch(`/api/wifi/heatmap?width_cells=${width}&height_cells=${height}&step_cm=${step}`);
    const data = await res.json();

    if (data.error) {
        console.warn(data.error);
        drawGridOnly('heatmap-canvas');
        return;
    }

    drawHeatmap(data, 'heatmap-canvas');
    currentHeatmap = data;

    if (data.total_points) {
        document.getElementById('measurement-count').textContent = `📊 Точек: ${data.total_points}`;
    }
}

function drawHeatmap(data, canvasId) {
    const canvas = document.getElementById(canvasId);
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    if (!data.heatmap || !data.heatmap.z) {
        drawGridOnly(canvasId);
        return;
    }

    const z = data.heatmap.z;
    const rows = z.length;
    const cols = z[0].length;
    const cellW = width / cols;
    const cellH = height / rows;

    for (let i = 0; i < rows; i++) {
        for (let j = 0; j < cols; j++) {
            const rssi = z[i][j];
            if (rssi === null || isNaN(rssi)) continue;
            ctx.fillStyle = getRssiColor(rssi);
            ctx.fillRect(j * cellW, i * cellH, cellW + 1, cellH + 1);
        }
    }

    ctx.beginPath();
    ctx.strokeStyle = 'rgba(255,255,255,0.2)';
    ctx.lineWidth = 1;
    for (let i = 0; i <= cols; i++) {
        ctx.moveTo(i * cellW, 0);
        ctx.lineTo(i * cellW, height);
        ctx.stroke();
    }
    for (let i = 0; i <= rows; i++) {
        ctx.moveTo(0, i * cellH);
        ctx.lineTo(width, i * cellH);
        ctx.stroke();
    }
    
    if (showTrack && droneTrack.length > 0 && canvasId === 'heatmap-canvas') {
        drawDroneTrack();
    }
}

function drawGridOnly(canvasId) {
    const canvas = document.getElementById(canvasId);
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    const cellSize = 40;

    ctx.fillStyle = '#0d0d1a';
    ctx.fillRect(0, 0, width, height);

    ctx.beginPath();
    ctx.strokeStyle = 'rgba(255,255,255,0.1)';
    for (let x = 0; x < width; x += cellSize) {
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
    }
    for (let y = 0; y < height; y += cellSize) {
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
    }
}

function updateMeasurementCount() {
    const el = document.getElementById('measurement-count');
    const current = parseInt(el.textContent.split(': ')[1]) || 0;
    el.textContent = `📊 Точек: ${current + 1}`;
}

async function startScan() {
    const width = document.getElementById('scan-width').value;
    const height = document.getElementById('scan-height').value;
    const step = document.getElementById('scan-step').value;

    document.getElementById('scan-status-text').textContent = '🔄 Сканирование...';
    isScanning = true;

    const res = await apiFetch(`/api/wifi/start?width=${width}&height=${height}&step_cm=${step}`, { method: 'POST' });
    
    if (res.ok) {
        const data = await res.json();
        if (data.status === 'error') {
            alert(data.message);
            document.getElementById('scan-status-text').textContent = '❌ Ошибка';
            isScanning = false;
        }
    } else {
        document.getElementById('scan-status-text').textContent = '❌ Ошибка запуска';
        isScanning = false;
    }
}

async function stopScan() {
    const res = await apiFetch('/api/wifi/stop', { method: 'POST' });
    if (res.ok) {
        document.getElementById('scan-status-text').textContent = '⏸️ Остановлено';
        isScanning = false;
    }
}

async function clearData() {
    if (confirm('Очистить все измерения Wi-Fi?')) {
        await apiFetch('/api/wifi/measurements', { method: 'DELETE' });
        measurements = [];
        currentHeatmap = null;
        document.getElementById('measurement-count').textContent = '📊 Точек: 0';
        drawGridOnly('heatmap-canvas');
    }
}

async function saveHeatmap() {
    const name = document.getElementById('map-name').value;
    if (!name) {
        alert('Введите название карты');
        return;
    }
    
    const res = await apiFetch(`/api/wifi/save?name=${encodeURIComponent(name)}`, { method: 'POST' });
    if (res.ok) {
        alert('Карта сохранена!');
        document.getElementById('map-name').value = '';
        loadSavedMapsList();
    } else {
        alert('Ошибка сохранения');
    }
}

async function loadSavedMapsList() {
    const res = await apiFetch('/api/wifi/saved');
    const maps = await res.json();
    
    const select = document.getElementById('saved-maps-select');
    select.innerHTML = '<option value="">-- Выберите карту --</option>';
    
    maps.forEach(map => {
        const option = document.createElement('option');
        option.value = map.id;
        option.textContent = `${map.name} (${new Date(map.created_at).toLocaleString()})`;
        select.appendChild(option);
    });
}

async function loadSavedHeatmap() {
    const select = document.getElementById('saved-maps-select');
    const id = select.value;
    if (!id) return;
    
    const res = await apiFetch(`/api/wifi/saved/${id}`);
    const data = await res.json();
    
    if (data.data && data.data.length > 0) {
        const step = data.data[0]?.step_cm || 100;
        const width = Math.max(...data.data.map(m => m.x)) + 1;
        const height = Math.max(...data.data.map(m => m.y)) + 1;
        
        const heatmapData = {
            heatmap: {
                z: [],
                min_rssi: Math.min(...data.data.map(m => m.rssi)),
                max_rssi: Math.max(...data.data.map(m => m.rssi))
            },
            measurements: data.data,
            width_cells: width,
            height_cells: height,
            step_cm: step
        };
        
        const rows = height * 10;
        const cols = width * 10;
        const z = [];
        for (let i = 0; i <= rows; i++) {
            z[i] = [];
            for (let j = 0; j <= cols; j++) {
                z[i][j] = -90;
            }
        }
        
        for (const m of data.data) {
            const xIdx = Math.floor(m.x * 10);
            const yIdx = Math.floor(m.y * 10);
            if (z[yIdx] && z[yIdx][xIdx] !== undefined) {
                z[yIdx][xIdx] = m.rssi;
            }
        }
        
        heatmapData.heatmap.z = z;
        drawHeatmap(heatmapData, 'saved-canvas');
    }
}

async function loadDroneTrack() {
    const res = await apiFetch('/api/wifi/track');
    const data = await res.json();
    droneTrack = data.track || [];
    if (showTrack && currentHeatmap) {
        drawHeatmap(currentHeatmap, 'heatmap-canvas');
    }
}

async function clearDroneTrack() {
    await apiFetch('/api/wifi/track', { method: 'DELETE' });
    droneTrack = [];
    if (currentHeatmap) {
        drawHeatmap(currentHeatmap, 'heatmap-canvas');
    }
}

function drawDroneTrack() {
    const canvas = document.getElementById('heatmap-canvas');
    if (!canvas || !currentHeatmap) return;
    
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    
    const maxX = currentHeatmap.width_cells;
    const maxY = currentHeatmap.height_cells;
    
    if (droneTrack.length > 1) {
        let lastX = null, lastY = null;
        
        for (let i = 0; i < droneTrack.length; i++) {
            const point = droneTrack[i];
            const px = (point.x / maxX) * width;
            const py = (point.y / maxY) * height;
            
            if (point.avoiding) {
                ctx.strokeStyle = '#ff6600';
            } else {
                ctx.strokeStyle = '#00ff88';
            }
            ctx.lineWidth = 2;
            
            if (lastX !== null && lastY !== null && px > 0 && px < width && py > 0 && py < height) {
                ctx.beginPath();
                ctx.moveTo(lastX, lastY);
                ctx.lineTo(px, py);
                ctx.stroke();
            }
            
            lastX = px;
            lastY = py;
        }
    }
    
    for (const point of droneTrack) {
        if (point.command === 'measure') {
            const px = (point.x / maxX) * width;
            const py = (point.y / maxY) * height;
            
            ctx.beginPath();
            ctx.arc(px, py, 4, 0, 2 * Math.PI);
            ctx.fillStyle = '#ffffff';
            ctx.fill();
            
            ctx.fillStyle = '#333333';
            ctx.font = 'bold 8px monospace';
            ctx.fillText('●', px - 3, py - 5);
        }
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    await ensureAuth();
    connectWiFiWebSocket();
    loadHeatmap();
    loadSavedMapsList();

    document.getElementById('start-scan-btn').onclick = startScan;
    document.getElementById('stop-scan-btn').onclick = stopScan;
    document.getElementById('refresh-map-btn').onclick = loadHeatmap;
    document.getElementById('clear-data-btn').onclick = clearData;
    document.getElementById('save-map-btn').onclick = saveHeatmap;
    document.getElementById('load-saved-btn').onclick = loadSavedHeatmap;
    
    const showTrackCheckbox = document.getElementById('show-track-checkbox');
    if (showTrackCheckbox) {
        showTrackCheckbox.onchange = (e) => {
            showTrack = e.target.checked;
            if (currentHeatmap) {
                drawHeatmap(currentHeatmap, 'heatmap-canvas');
            }
            if (showTrack) {
                loadDroneTrack();
            }
        };
    }
    
    const clearTrackBtn = document.getElementById('clear-track-btn');
    if (clearTrackBtn) {
        clearTrackBtn.onclick = clearDroneTrack;
    }
    
    await loadDroneTrack();
    
    setInterval(async () => {
        if (showTrack && isScanning) {
            await loadDroneTrack();
            if (currentHeatmap) {
                drawHeatmap(currentHeatmap, 'heatmap-canvas');
            }
        }
    }, 2000);
});