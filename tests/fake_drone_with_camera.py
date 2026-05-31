#!/usr/bin/env python3
"""
Stationary fake drone with camera for the local BPNA server.

What it does:
- connects to the local gateway through `/ws/esp`
- sends binary JPEG frames from a webcam
- sends telemetry messages in the format expected by device-service
- stays in one place and only logs commands from the server
"""

import argparse
import asyncio
import json
import logging
import platform
import signal
import sys
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode, urlparse, urlunparse

import cv2
import numpy as np
import psutil
import websockets


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_DEVICE_ID = "bpna-001"
DEFAULT_DEVICE_SECRET = "nzHqU5RkZEgGHypiCTzSeMPc3av0eizQ"
DEFAULT_SERVER_URL = "https://bpna-production.up.railway.app/"
LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


def is_local_host(host: str) -> bool:
    raw_host = host.strip()
    parsed = urlparse(raw_host if "://" in raw_host else f"//{raw_host}", scheme="http")
    hostname = (parsed.hostname or raw_host).strip("[]").lower()
    return hostname in LOCAL_HOSTNAMES


def build_gateway_ws_url(host: str, port: Optional[int], device_id: str, secret: str) -> str:
    raw_host = host.strip()
    parsed = urlparse(raw_host if "://" in raw_host else f"//{raw_host}", scheme="http")

    scheme = "wss" if parsed.scheme == "https" else "ws"
    hostname = parsed.hostname or raw_host.strip("/")
    netloc = hostname

    selected_port = parsed.port or port
    if selected_port and not (
        (scheme == "ws" and selected_port == 80)
        or (scheme == "wss" and selected_port == 443)
    ):
        netloc = f"{hostname}:{selected_port}"

    query = urlencode({"device_id": device_id, "secret": secret})
    return urlunparse((scheme, netloc, "/ws/esp", "", query, ""))


@dataclass
class DroneState:
    device_id: str = DEFAULT_DEVICE_ID
    battery: float = 85.0
    x: float = 0.0
    y: float = 0.0
    z: float = 1.2
    yaw: float = 0.0
    last_command: str = "idle"
    command_count: int = 0


class FakeDroneWithCamera:
    TELEMETRY_INTERVAL_SEC = 5.0

    def __init__(
        self,
        host: str = DEFAULT_SERVER_URL,
        port: Optional[int] = None,
        device_id: str = DEFAULT_DEVICE_ID,
        secret: str = DEFAULT_DEVICE_SECRET,
        camera_id: int = 0,
        width: int = 640,
        height: int = 480,
        fps: int = 5,
        jpeg_quality: int = 75,
        synthetic_video: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.device_id = device_id
        self.secret = secret
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.fps = fps
        self.jpeg_quality = jpeg_quality
        self.synthetic_video = synthetic_video

        self.ws_url = build_gateway_ws_url(self.host, self.port, self.device_id, self.secret)

        self.state = DroneState(device_id=device_id)
        self.cap: Optional[cv2.VideoCapture] = None
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 20
        self.start_time = time.time()
        self.frame_count = 0
        self.last_fps_checkpoint = 0.0
        self.last_telemetry_sent = 0.0
        self.wifi_rssi_dbm = -45
        self.ping_ms = 5.0
        self.ping_ok = True
        self.last_frame_error_log = 0.0

    def init_camera(self) -> bool:
        if self.synthetic_video:
            logger.info("[CAM] synthetic video mode enabled")
            return True

        try:
            backend_candidates = []
            if platform.system() == "Windows":
                backend_candidates = [
                    ("DirectShow", cv2.CAP_DSHOW),
                    ("MSMF", cv2.CAP_MSMF),
                    ("Any", cv2.CAP_ANY),
                ]
            else:
                backend_candidates = [("Any", cv2.CAP_ANY)]

            for backend_name, backend_id in backend_candidates:
                logger.info("[CAM] trying backend %s", backend_name)
                cap = cv2.VideoCapture(self.camera_id, backend_id)
                if not cap.isOpened():
                    cap.release()
                    continue

                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                cap.set(cv2.CAP_PROP_FPS, self.fps)
                time.sleep(0.5)

                ok, _frame = cap.read()
                if not ok:
                    logger.warning("[CAM] backend %s opened camera but did not return a frame", backend_name)
                    cap.release()
                    continue

                self.cap = cap
                actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                actual_fps = self.cap.get(cv2.CAP_PROP_FPS)

                logger.info(
                    "[CAM] init ok with %s: %sx%s @ %.1ffps",
                    backend_name,
                    actual_width,
                    actual_height,
                    actual_fps,
                )
                logger.info("[CAM] jpeg quality: %s", self.jpeg_quality)
                return True

            logger.error("Failed to open camera %s with all backends", self.camera_id)
            logger.info("Tip: run with --synthetic-video to test without a physical camera")
            return False
        except Exception as exc:
            logger.error("[CAM] init failed: %s", exc)
            return False

    def cleanup(self) -> None:
        self.running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        logger.info("[CAM] resources released")

    def get_cpu_temperature(self) -> float:
        if platform.system() == "Linux":
            try:
                with open("/sys/class/thermal/thermal_zone0/temp", "r", encoding="utf-8") as file:
                    return float(file.read().strip()) / 1000.0
            except Exception:
                pass
        return 45.0 + (time.time() % 100) / 50

    def update_network_metrics(self) -> None:
        self.wifi_rssi_dbm = max(-80, min(-30, int(-45 + np.random.randn() * 6)))
        self.ping_ms = max(1.0, min(50.0, 5.0 + np.random.randn() * 2.0))
        self.ping_ok = True

    def add_info_overlay(self, frame: np.ndarray) -> np.ndarray:
        fps_value = 0.0
        if self.last_fps_checkpoint > 0 and self.frame_count % 30 == 0:
            elapsed = time.time() - self.last_fps_checkpoint
            if elapsed > 0:
                fps_value = 30.0 / elapsed

        info_lines = [
            f"Fake Drone | {self.state.device_id}",
            f"Frame: {self.frame_count} | FPS target: {self.fps}",
            f"Last command: {self.state.last_command}",
            f"Position: x={self.state.x:.1f} y={self.state.y:.1f} z={self.state.z:.1f}",
            f"Server: {self.host}:{self.port}",
            f"Measured FPS: {fps_value:.1f}" if fps_value else "Measured FPS: warming up",
        ]

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 1
        line_height = 20
        padding = 6

        max_width = max(
            cv2.getTextSize(text, font, font_scale, thickness)[0][0]
            for text in info_lines
        ) + 2 * padding
        overlay_height = len(info_lines) * line_height + 2 * padding

        cv2.rectangle(frame, (0, 0), (max_width, overlay_height), (0, 0, 0), -1)
        for index, text in enumerate(info_lines):
            y_pos = line_height * (index + 1)
            cv2.putText(
                frame,
                text,
                (padding, y_pos),
                font,
                font_scale,
                (0, 255, 0),
                thickness,
            )

        return frame

    def generate_synthetic_frame(self) -> bytes:
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        frame[:, :] = (20, 20, 20)

        now = time.time() - self.start_time
        circle_x = int((self.width * 0.5) + np.sin(now) * self.width * 0.2)
        circle_y = int((self.height * 0.5) + np.cos(now * 0.8) * self.height * 0.15)
        cv2.circle(frame, (circle_x, circle_y), 50, (0, 180, 255), -1)
        cv2.rectangle(frame, (40, self.height - 120), (220, self.height - 40), (60, 120, 60), -1)
        cv2.putText(
            frame,
            "SYNTHETIC CAMERA",
            (40, self.height - 140),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
        )

        frame = self.add_info_overlay(frame)
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
        )
        if not ok:
            raise RuntimeError("Failed to encode synthetic frame")
        return encoded.tobytes()

    def capture_frame(self) -> Optional[bytes]:
        if self.synthetic_video:
            return self.generate_synthetic_frame()

        if self.cap is None:
            return None

        ok, frame = self.cap.read()
        if not ok:
            now = time.time()
            if now - self.last_frame_error_log >= 2:
                logger.warning("[CAM] failed to capture frame")
                self.last_frame_error_log = now
            return None

        frame = self.add_info_overlay(frame)
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
        )
        if not ok:
            logger.warning("[CAM] failed to encode frame")
            return None
        return encoded.tobytes()

    def build_telemetry(self) -> dict:
        uptime = int(time.time() - self.start_time)
        self.update_network_metrics()

        return {
            "type": "telemetry",
            "device_id": self.state.device_id,
            "battery": self.state.battery,
            "temperature": self.get_cpu_temperature(),
            "free_heap": psutil.virtual_memory().available,
            "uptime": uptime,
            "cpu_load": psutil.cpu_percent(),
            "wifi_connected": True,
            "wifi_rssi_dbm": int(self.wifi_rssi_dbm),
            "ping_ms": round(self.ping_ms, 1),
            "ping_ok": self.ping_ok,
            "x": self.state.x,
            "y": self.state.y,
            "z": self.state.z,
            "yaw": self.state.yaw,
            "armed": True,
            "mode": "SIMULATION",
            "is_fake": True,
        }

    async def send_telemetry(self) -> None:
        if self.websocket is None:
            return
        payload = self.build_telemetry()
        await self.websocket.send(json.dumps(payload))
        logger.info(
            "[TELEMETRY] sent x=%.1f y=%.1f battery=%.1f%% cmd=%s",
            self.state.x,
            self.state.y,
            self.state.battery,
            self.state.last_command,
        )

    async def handle_websocket_messages(self) -> None:
        if self.websocket is None:
            return

        try:
            async for message in self.websocket:
                if isinstance(message, bytes):
                    continue

                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    logger.info("[WS RX] text=%s", message[:120])
                    continue

                msg_type = data.get("type")
                if msg_type == "command":
                    command = data.get("command", "unknown")
                    self.state.last_command = command
                    self.state.command_count += 1
                    logger.info("[COMMAND] #%s %s", self.state.command_count, command)
                elif msg_type == "ping":
                    await self.websocket.send(json.dumps({"type": "pong"}))
                    logger.debug("[WS] pong sent")
                else:
                    logger.info("[WS RX] %s", json.dumps(data)[:160])
        except websockets.exceptions.ConnectionClosed:
            logger.warning("[WS] disconnected")
        except Exception as exc:
            logger.error("[WS] receive error: %s", exc)

    async def stream_loop(self) -> None:
        frame_interval = 1.0 / max(self.fps, 1)

        while self.running and self.websocket is not None:
            frame_start = time.time()

            frame = self.capture_frame()
            if frame is not None:
                try:
                    await self.websocket.send(frame)
                    self.frame_count += 1

                    if self.frame_count % 30 == 0:
                        now = time.time()
                        if self.last_fps_checkpoint > 0:
                            fps_value = 30.0 / (now - self.last_fps_checkpoint)
                            logger.info("[FRAME] #%s | fps=%.1f", self.frame_count, fps_value)
                        self.last_fps_checkpoint = now
                except Exception as exc:
                    logger.error("[FRAME] send error: %s", exc)
                    break

            now = time.time()
            if now - self.last_telemetry_sent >= self.TELEMETRY_INTERVAL_SEC:
                await self.send_telemetry()
                self.last_telemetry_sent = now

            elapsed = time.time() - frame_start
            await asyncio.sleep(max(0.001, frame_interval - elapsed))

    async def connect_and_run(self) -> None:
        if not self.init_camera():
            logger.error("[CAM] camera init failed")
            return

        logger.info("[WS] connecting to %s", self.ws_url)

        while self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=5,
                    max_size=2**23,
                ) as websocket:
                    self.websocket = websocket
                    self.running = True
                    self.reconnect_attempts = 0
                    self.last_telemetry_sent = 0.0

                    logger.info("[WS] connected")
                    await self.send_telemetry()

                    stream_task = asyncio.create_task(self.stream_loop())
                    message_task = asyncio.create_task(self.handle_websocket_messages())

                    done, pending = await asyncio.wait(
                        [stream_task, message_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    for task in done:
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

            except ConnectionRefusedError:
                logger.error(
                    "[WS] connection refused, make sure the server is running on %s:%s",
                    self.host,
                    self.port,
                )
                break
            except Exception as exc:
                self.reconnect_attempts += 1
                wait_time = min(3 * self.reconnect_attempts, 30)
                logger.error("[WS] connection error: %s", exc)
                logger.info(
                    "[WS] reconnecting in %ss (%s/%s)",
                    wait_time,
                    self.reconnect_attempts,
                    self.max_reconnect_attempts,
                )
                await asyncio.sleep(wait_time)

        self.cleanup()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Stationary fake drone with camera")
    parser.add_argument(
        "--server-url",
        default=DEFAULT_SERVER_URL,
        help="Gateway URL. Default: https://bpna-production.up.railway.app/",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Deprecated gateway host override. Use --server-url for Railway.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Gateway port. Omit it for https/wss Railway hosts.",
    )
    parser.add_argument(
        "--allow-localhost",
        action="store_true",
        help="Allow localhost/127.0.0.1 for local debugging.",
    )
    parser.add_argument(
        "--device-id",
        default=DEFAULT_DEVICE_ID,
        help="Device ID registered in the admin panel",
    )
    parser.add_argument(
        "--secret",
        default=DEFAULT_DEVICE_SECRET,
        help="Secret for the selected device_id from the admin panel",
    )
    parser.add_argument("--camera", "-c", type=int, default=0, help="Camera index")
    parser.add_argument("--width", "-w", type=int, default=640, help="Frame width")
    parser.add_argument("--height", "-H", type=int, default=480, help="Frame height")
    parser.add_argument("--fps", "-f", type=int, default=5, help="Frames per second")
    parser.add_argument(
        "--quality",
        "-q",
        type=int,
        default=75,
        help="JPEG quality from 1 to 100",
    )
    parser.add_argument(
        "--synthetic-video",
        action="store_true",
        help="Use generated frames instead of a physical webcam",
    )

    args = parser.parse_args()
    gateway_host = args.host or args.server_url
    gateway_port = args.port

    if is_local_host(gateway_host) and not args.allow_localhost:
        logger.warning(
            "Localhost target was requested, but this emulator is configured for the cloud server. "
            "Using %s instead. Add --allow-localhost only for local debugging.",
            DEFAULT_SERVER_URL,
        )
        gateway_host = DEFAULT_SERVER_URL
        gateway_port = None

    logger.info("=" * 60)
    ws_url = build_gateway_ws_url(gateway_host, gateway_port, args.device_id, "***")
    logger.info("Fake drone will connect to: %s", ws_url)
    logger.info("Device ID: %s", args.device_id)
    logger.info("Camera index: %s", args.camera)
    logger.info("Resolution: %sx%s", args.width, args.height)
    logger.info("FPS: %s", args.fps)
    logger.info("JPEG quality: %s", args.quality)
    logger.info("=" * 60)

    emulator = FakeDroneWithCamera(
        host=gateway_host,
        port=gateway_port,
        device_id=args.device_id,
        secret=args.secret,
        camera_id=args.camera,
        width=args.width,
        height=args.height,
        fps=args.fps,
        jpeg_quality=args.quality,
        synthetic_video=args.synthetic_video,
    )

    def signal_handler(signum, frame):
        logger.info("Stopping fake drone...")
        emulator.running = False
        emulator.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    await emulator.connect_and_run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as exc:
        logger.error("Fatal error: %s", exc)
        sys.exit(1)
