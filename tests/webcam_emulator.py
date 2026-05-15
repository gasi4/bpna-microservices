#!/usr/bin/env python3
"""
ESP32-CAM webcam emulator for the local BPNA server.

It connects to the gateway through /ws/esp, sends JPEG frames and telemetry,
and logs commands received from the server.
"""

import argparse
import asyncio
import json
import logging
import platform
import signal
import sys
import time
from typing import Optional

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
DEFAULT_DEVICE_SECRET = "JOOGmlUysuw6_l0-sIFnKCZ6ht3VCnev"


class ESP32WebcamEmulator:
    TELEMETRY_INTERVAL_SEC = 5.0
    NET_MEASURE_INTERVAL_SEC = 1.0

    def __init__(
        self,
        server_host: str = "localhost",
        server_port: int = 8000,
        device_id: str = DEFAULT_DEVICE_ID,
        secret: str = DEFAULT_DEVICE_SECRET,
        camera_id: int = 0,
        width: int = 640,
        height: int = 480,
        fps: int = 15,
        quality: int = 75,
        synthetic_video: bool = False,
    ) -> None:
        self.server_host = server_host
        self.server_port = server_port
        self.device_id = device_id
        self.secret = secret
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.fps = fps
        self.quality = quality
        self.synthetic_video = synthetic_video

        self.ws_url = (
            f"ws://{self.server_host}:{self.server_port}/ws/esp"
            f"?device_id={self.device_id}&secret={self.secret}"
        )

        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.cap: Optional[cv2.VideoCapture] = None
        self.running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 20

        self.battery = 85.0
        self.start_time = time.time()
        self.frame_count = 0
        self.last_fps_checkpoint = 0.0
        self.last_telemetry_sent = 0.0
        self.last_net_measure = 0.0
        self.last_frame_error_log = 0.0

        self.wifi_rssi_dbm = -45
        self.ping_ms = 5.0
        self.ping_ok = True

    def init_camera(self) -> bool:
        if self.synthetic_video:
            logger.info("[CAM] synthetic video mode enabled")
            return True

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
            time.sleep(0.4)

            ok, _frame = cap.read()
            if not ok:
                logger.warning("[CAM] backend %s opened camera but returned no frame", backend_name)
                cap.release()
                continue

            self.cap = cap
            actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            logger.info(
                "[CAM] init OK with %s: %sx%s @ %.1ffps",
                backend_name,
                actual_width,
                actual_height,
                actual_fps,
            )
            logger.info("[CAM] JPEG quality: %s", self.quality)
            return True

        logger.error("[CAM] failed to open camera %s", self.camera_id)
        logger.info("Tip: add --synthetic-video to test without a physical webcam")
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
        self.wifi_rssi_dbm = max(-80, min(-30, int(-45 + np.random.randn() * 8)))
        self.ping_ms = max(1.0, min(100.0, 5.0 + np.random.randn() * 3))
        self.ping_ok = True

    def add_info_overlay(self, frame: np.ndarray) -> np.ndarray:
        fps_value = 0.0
        if self.last_fps_checkpoint > 0 and self.frame_count % 30 == 0:
            elapsed = time.time() - self.last_fps_checkpoint
            if elapsed > 0:
                fps_value = 30.0 / elapsed

        info_lines = [
            f"ESP32-CAM Emulator | {self.device_id}",
            f"Frame: {self.frame_count} | FPS target: {self.fps}",
            f"Server: {self.server_host}:{self.server_port}",
            f"Measured FPS: {fps_value:.1f}" if fps_value else "Measured FPS: warming up",
        ]

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 1
        line_height = 20
        padding = 6
        max_width = max(cv2.getTextSize(text, font, font_scale, thickness)[0][0] for text in info_lines)
        overlay_height = len(info_lines) * line_height + 2 * padding

        cv2.rectangle(frame, (0, 0), (max_width + 2 * padding, overlay_height), (0, 0, 0), -1)
        for index, text in enumerate(info_lines):
            cv2.putText(
                frame,
                text,
                (padding, line_height * (index + 1)),
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
        cv2.putText(
            frame,
            "SYNTHETIC CAMERA",
            (40, self.height - 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
        )
        return self.encode_frame(self.add_info_overlay(frame))

    def encode_frame(self, frame: np.ndarray) -> bytes:
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.quality],
        )
        if not ok:
            raise RuntimeError("Failed to encode frame")
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
        return self.encode_frame(self.add_info_overlay(frame))

    async def send_telemetry(self) -> None:
        if self.websocket is None:
            return

        telemetry = {
            "type": "telemetry",
            "device_id": self.device_id,
            "battery": self.battery,
            "temperature": self.get_cpu_temperature(),
            "free_heap": psutil.virtual_memory().available,
            "uptime": int(time.time() - self.start_time),
            "cpu_load": psutil.cpu_percent(),
            "wifi_connected": True,
            "wifi_rssi_dbm": self.wifi_rssi_dbm,
            "ping_ms": round(self.ping_ms, 1),
            "ping_ok": self.ping_ok,
        }
        await self.websocket.send(json.dumps(telemetry))
        logger.info("[TELEMETRY] sent")

    async def handle_websocket_messages(self) -> None:
        if self.websocket is None:
            return

        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    logger.info("[WS RX] %s", str(message)[:120])
                    continue

                logger.info("[WS RX] %s", json.dumps(data, ensure_ascii=False)[:160])
                msg_type = data.get("type")
                if msg_type == "command":
                    command = data.get("command")
                    if command:
                        logger.info("[UART->ESP32] %s", command)
                elif msg_type == "ping":
                    await self.websocket.send(json.dumps({"type": "pong"}))
        except websockets.exceptions.ConnectionClosed as exc:
            logger.warning("[WS] disconnected: code=%s reason=%s", exc.code, exc.reason or "-")

    async def video_stream_loop(self) -> None:
        frame_interval = 1.0 / max(self.fps, 1)

        while self.running and self.websocket is not None:
            frame_start = time.time()

            frame = self.capture_frame()
            if frame:
                try:
                    await self.websocket.send(frame)
                    self.frame_count += 1
                    if self.frame_count % 30 == 0:
                        now = time.time()
                        if self.last_fps_checkpoint > 0:
                            fps = 30.0 / (now - self.last_fps_checkpoint)
                            heap_kb = psutil.virtual_memory().available // 1024
                            logger.info("[FRAME] #%s | FPS: %.1f | Heap: %s KB", self.frame_count, fps, heap_kb)
                        self.last_fps_checkpoint = now
                except websockets.exceptions.ConnectionClosed as exc:
                    logger.warning("[FRAME] send failed: websocket closed code=%s reason=%s", exc.code, exc.reason or "-")
                    break

            now = time.time()
            if now - self.last_net_measure >= self.NET_MEASURE_INTERVAL_SEC:
                self.update_network_metrics()
                self.last_net_measure = now

            if now - self.last_telemetry_sent >= self.TELEMETRY_INTERVAL_SEC:
                try:
                    await self.send_telemetry()
                    self.last_telemetry_sent = now
                except websockets.exceptions.ConnectionClosed:
                    break

            elapsed = time.time() - frame_start
            await asyncio.sleep(max(0.001, frame_interval - elapsed))

    async def connect_and_run(self) -> None:
        if not self.init_camera():
            return

        logger.info("[WS] connecting to ws://%s:%s/ws/esp?device_id=%s&secret=***", self.server_host, self.server_port, self.device_id)

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

                    logger.info("[WS] connected")
                    logger.info("[CAM] streaming video")

                    stream_task = asyncio.create_task(self.video_stream_loop())
                    message_task = asyncio.create_task(self.handle_websocket_messages())
                    done, pending = await asyncio.wait(
                        [stream_task, message_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    for task in done:
                        task.result()
            except ConnectionRefusedError:
                logger.error("[WS] connection refused on %s:%s", self.server_host, self.server_port)
                break
            except Exception as exc:
                logger.error("[WS] connection error: %s", exc)

            self.websocket = None
            self.reconnect_attempts += 1
            if self.reconnect_attempts < self.max_reconnect_attempts:
                wait_time = min(3 * self.reconnect_attempts, 30)
                logger.info("[WS] reconnecting in %ss (%s/%s)", wait_time, self.reconnect_attempts, self.max_reconnect_attempts)
                await asyncio.sleep(wait_time)

        self.cleanup()


async def main() -> None:
    parser = argparse.ArgumentParser(description="ESP32-CAM emulator for local BPNA server")
    parser.add_argument("--host", default="localhost", help="Gateway host")
    parser.add_argument("--port", type=int, default=8000, help="Gateway port")
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID, help="Device ID from the admin panel")
    parser.add_argument("--secret", default=DEFAULT_DEVICE_SECRET, help="Device secret from the admin panel")
    parser.add_argument("--camera", "-c", type=int, default=0, help="Camera index")
    parser.add_argument("--width", "-w", type=int, default=640, help="Frame width")
    parser.add_argument("--height", "-H", type=int, default=480, help="Frame height")
    parser.add_argument("--fps", "-f", type=int, default=15, help="Frames per second")
    parser.add_argument("--quality", "-q", type=int, default=75, help="JPEG quality from 1 to 100")
    parser.add_argument("--synthetic-video", action="store_true", help="Use generated frames instead of a physical webcam")

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Device ID: %s", args.device_id)
    logger.info("Server: ws://%s:%s/ws/esp?device_id=%s&secret=***", args.host, args.port, args.device_id)
    logger.info("Camera index: %s", args.camera)
    logger.info("Resolution: %sx%s", args.width, args.height)
    logger.info("FPS: %s", args.fps)
    logger.info("JPEG quality: %s", args.quality)
    logger.info("=" * 60)

    emulator = ESP32WebcamEmulator(
        server_host=args.host,
        server_port=args.port,
        device_id=args.device_id,
        secret=args.secret,
        camera_id=args.camera,
        width=args.width,
        height=args.height,
        fps=args.fps,
        quality=args.quality,
        synthetic_video=args.synthetic_video,
    )

    def signal_handler(signum, frame):
        logger.info("Stopping emulator")
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
