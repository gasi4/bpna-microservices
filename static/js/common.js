// static/js/common.js

// ===== Auth helpers =====
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
            body: JSON.stringify({ username: "operator", password: "operator123" }),
        });

        if (!res.ok) return false;
        const data = await res.json();
        if (data.access_token) {
            setAuthToken(data.access_token);
            console.log("[AUTH] Auto login success");
            return true;
        }
    } catch (e) {
        console.error("[AUTH] Login error:", e);
    }
    return false;
}

async function ensureAuth() {
    if (getAuthToken()) return true;
    return await performAutoLogin();
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
        if (!ok) return res;
        const token2 = getAuthToken();
        return fetch(url, {
            ...options,
            headers: { ...headers, Authorization: `Bearer ${token2}` },
        });
    }
    return res;
}

// ===== Общие утилиты =====
function formatUptime(sec) {
    sec = Number(sec || 0);
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    return `${h}h ${m}m ${s}s`;
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function getRssiColor(rssi) {
    if (rssi >= -50) return '#00ff00';
    if (rssi >= -60) return '#88ff00';
    if (rssi >= -70) return '#cccc00';
    if (rssi >= -80) return '#ff6600';
    return '#ff0000';
}

// Добавить в common.js, если её там нет
function getRssiColor(rssi) {
    if (rssi >= -50) return '#00ff00';
    if (rssi >= -60) return '#88ff00';
    if (rssi >= -70) return '#cccc00';
    if (rssi >= -80) return '#ff6600';
    return '#ff0000';
}