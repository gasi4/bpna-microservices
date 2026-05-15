#!/usr/bin/env python3
"""
Р­РјСѓР»СЏС‚РѕСЂ ESP32-CAM РґР»СЏ Р»РѕРєР°Р»СЊРЅРѕРіРѕ СЃРµСЂРІРµСЂР°
РџРѕРґРєР»СЋС‡Р°РµС‚СЃСЏ Рє СЃРµСЂРІРµСЂСѓ С‡РµСЂРµР· WebSocket РЅР° localhost
"""

import asyncio
import json
import cv2
import numpy as np
import websockets
import signal
import sys
import time
import argparse
from typing import Optional
import logging
import ssl
import psutil
import platform

# РќР°СЃС‚СЂРѕР№РєР° Р»РѕРіРёСЂРѕРІР°РЅРёСЏ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ESP32WebcamEmulator:
    def __init__(
        self, 
        server_host: str = "localhost",
        server_port: int = 8000,
        secret: str = "change-me-device",  # Р”РѕР»Р¶РµРЅ СЃРѕРІРїР°РґР°С‚СЊ СЃ device_secret РІ config.py
        camera_id: int = 0,
        width: int = 640,
        height: int = 480,
        fps: int = 15,
        quality: int = 12,
    ):
        """
        Р­РјСѓР»СЏС‚РѕСЂ ESP32-CAM РґР»СЏ Р»РѕРєР°Р»СЊРЅРѕРіРѕ СЃРµСЂРІРµСЂР°
        
        Args:
            server_host: РҐРѕСЃС‚ СЃРµСЂРІРµСЂР° (localhost)
            server_port: РџРѕСЂС‚ СЃРµСЂРІРµСЂР° (8000)
            secret: РЎРµРєСЂРµС‚РЅС‹Р№ РєР»СЋС‡ (РґРѕР»Р¶РµРЅ СЃРѕРІРїР°РґР°С‚СЊ СЃ device_secret)
            camera_id: ID РІРµР±-РєР°РјРµСЂС‹
            width: РЁРёСЂРёРЅР° РєР°РґСЂР°
            height: Р’С‹СЃРѕС‚Р° РєР°РґСЂР°
            fps: РљР°РґСЂРѕРІ РІ СЃРµРєСѓРЅРґСѓ
            quality: РљР°С‡РµСЃС‚РІРѕ JPEG
        """
        self.server_host = server_host
        self.server_port = server_port
        self.secret = secret
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.fps = fps
        self.quality = quality
        
        # Р¤РѕСЂРјРёСЂСѓРµРј URL РґР»СЏ WebSocket (ws://, РЅРµ wss://)
        self.ws_url = f"ws://{self.server_host}:{self.server_port}/ws/esp?secret={self.secret}"
        
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.cap: Optional[cv2.VideoCapture] = None
        self.running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 20
        
        # РўРµР»РµРјРµС‚СЂРёСЏ (РєР°Рє РІ ESP32 РєРѕРґРµ)
        self.device_id = "bpna-01"
        self.battery = 85.0
        self.start_time = time.time()
        self.frame_count = 0
        self.last_fps_time = 0
        self.last_telemetry = 0
        self.last_net_measure = 0
        
        # РЎРµС‚РµРІС‹Рµ РјРµС‚СЂРёРєРё
        self.wifi_rssi_dbm = -45
        self.ping_ms = 5.0
        self.ping_ok = True
        
        # РРЅС‚РµСЂРІР°Р»С‹
        self.TELEMETRY_INTERVAL_MS = 5000
        self.NET_MEASURE_INTERVAL_MS = 1000
        
    def init_camera(self) -> bool:
        """РРЅРёС†РёР°Р»РёР·Р°С†РёСЏ РІРµР±-РєР°РјРµСЂС‹"""
        try:
            self.cap = cv2.VideoCapture(self.camera_id)
            if not self.cap.isOpened():
                logger.error(f"РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РєСЂС‹С‚СЊ РєР°РјРµСЂСѓ {self.camera_id}")
                return False
                
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            
            actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            
            logger.info(f"[CAM] init OK: {actual_width}x{actual_height} @ {actual_fps}fps")
            logger.info(f"[CAM] JPEG quality: {self.quality}")
            return True
            
        except Exception as e:
            logger.error(f"[CAM] init failed: {e}")
            return False
    
    def capture_frame(self) -> Optional[bytes]:
        """Р—Р°С…РІР°С‚ РєР°РґСЂР° Рё СЃР¶Р°С‚РёРµ РІ JPEG"""
        if self.cap is None:
            return None
            
        ret, frame = self.cap.read()
        if not ret:
            logger.warning("[CAM] Failed to capture frame")
            return None
        
        # Р”РѕР±Р°РІР»СЏРµРј РёРЅС„РѕСЂРјР°С†РёРѕРЅРЅСѓСЋ РїР°РЅРµР»СЊ
        frame = self.add_info_overlay(frame)
        
        # РЎР¶Р°С‚РёРµ РІ JPEG
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.quality]
        _, jpeg_bytes = cv2.imencode('.jpg', frame, encode_params)
        
        return jpeg_bytes.tobytes()
    
    def add_info_overlay(self, frame: np.ndarray) -> np.ndarray:
        """РРЅС„РѕСЂРјР°С†РёРѕРЅРЅР°СЏ РїР°РЅРµР»СЊ"""
        frame_rate = 0
        if self.last_fps_time > 0:
            elapsed = time.time() - self.last_fps_time
            if elapsed > 0:
                frame_rate = 30 / elapsed
        
        info_texts = [
            f"ESP32-CAM Emulator | {self.device_id}",
            f"Frame: #{self.frame_count} | FPS: {frame_rate:.1f}",
            f"Heap: {psutil.virtual_memory().available // 1024} KB",
            f"Local server: {self.server_host}:{self.server_port}"
        ]
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 1
        line_height = 20
        padding = 5
        
        max_width = max([cv2.getTextSize(text, font, font_scale, thickness)[0][0] 
                        for text in info_texts]) + 2 * padding
        overlay_height = len(info_texts) * line_height + 2 * padding
        
        cv2.rectangle(frame, (0, 0), (max_width, overlay_height), (0, 0, 0), -1)
        
        for i, text in enumerate(info_texts):
            y_pos = line_height * (i + 1)
            cv2.putText(frame, text, (padding, y_pos), font, font_scale, (0, 255, 0), thickness)
        
        return frame
    
    def update_network_metrics(self):
        """РћР±РЅРѕРІР»РµРЅРёРµ СЃРµС‚РµРІС‹С… РјРµС‚СЂРёРє"""
        self.wifi_rssi_dbm = -45 + np.random.randn() * 8
        self.wifi_rssi_dbm = max(-80, min(-30, self.wifi_rssi_dbm))
        
        self.ping_ms = 5 + np.random.randn() * 3
        self.ping_ms = max(1, min(100, self.ping_ms))
        self.ping_ok = True
    
    def get_cpu_temperature(self) -> float:
        """Р­РјСѓР»СЏС†РёСЏ С‚РµРјРїРµСЂР°С‚СѓСЂС‹"""
        if platform.system() == "Linux":
            try:
                with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                    temp = float(f.read().strip()) / 1000.0
                    return temp
            except:
                pass
        return 45.0 + (time.time() % 100) / 50
    
    def send_telemetry(self):
        """РћС‚РїСЂР°РІРєР° С‚РµР»РµРјРµС‚СЂРёРё"""
        telemetry = {
            "type": "telemetry",
            "device_id": self.device_id,
            "battery": self.battery,
            "temperature": self.get_cpu_temperature(),
            "free_heap": psutil.virtual_memory().available,
            "uptime": int(time.time() - self.start_time),
            "cpu_load": psutil.cpu_percent(),
            "wifi_connected": True,
            "wifi_rssi_dbm": int(self.wifi_rssi_dbm),
            "ping_ms": round(self.ping_ms, 1),
            "ping_ok": self.ping_ok
        }
        
        if self.websocket:
            try:
                asyncio.create_task(self.websocket.send(json.dumps(telemetry)))
                logger.info(f"[TELEMETRY] sent")
            except Exception as e:
                logger.error(f"[TELEMETRY] send error: {e}")
    
    async def handle_websocket_messages(self):
        """РћР±СЂР°Р±РѕС‚РєР° РІС…РѕРґСЏС‰РёС… СЃРѕРѕР±С‰РµРЅРёР№ РѕС‚ СЃРµСЂРІРµСЂР°"""
        if not self.websocket:
            return
            
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")
                    
                    logger.info(f"[WS RX] {message[:100]}")
                    
                    if msg_type == "command":
                        command = data.get("command")
                        if command:
                            logger.info(f"[UART->ESP32] {command}")
                            if command == "forward":
                                logger.info("  рџљ— Р’РїРµСЂС‘Рґ")
                            elif command == "backward":
                                logger.info("  рџ”„ РќР°Р·Р°Рґ")
                            elif command == "stop":
                                logger.info("  рџ›‘ РЎС‚РѕРї")
                            elif "forward" in command:
                                logger.info(f"  рџљ— {command}")
                    
                    elif msg_type == "ping":
                        await self.websocket.send(json.dumps({"type": "pong"}))
                        logger.debug("[WS] pong sent")
                        
                except json.JSONDecodeError:
                    pass
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("[WS] disconnected")
        except Exception as e:
            logger.error(f"[WS] error: {e}")
    
    async def video_stream_loop(self):
        """РћСЃРЅРѕРІРЅРѕР№ С†РёРєР» РѕС‚РїСЂР°РІРєРё РІРёРґРµРѕ"""
        frame_interval = 1.0 / self.fps
        
        while self.running and self.websocket:
            frame_start = time.time()
            
            jpeg_frame = self.capture_frame()
            if jpeg_frame:
                try:
                    await self.websocket.send(jpeg_frame)
                    self.frame_count += 1
                    
                    if self.frame_count % 30 == 0:
                        current_time = time.time()
                        if self.last_fps_time > 0:
                            fps = 30.0 / (current_time - self.last_fps_time)
                            heap_kb = psutil.virtual_memory().available // 1024
                            logger.info(f"[FRAME] #{self.frame_count} | FPS: {fps:.1f} | Heap: {heap_kb} KB")
                        self.last_fps_time = current_time
                        
                except Exception as e:
                    logger.error(f"[FRAME] send error: {e}")
                    break
            
            # РЎРµС‚РµРІС‹Рµ РјРµС‚СЂРёРєРё (СЂР°Р· РІ СЃРµРєСѓРЅРґСѓ)
            current_time_ms = time.time() * 1000
            if current_time_ms - self.last_net_measure >= self.NET_MEASURE_INTERVAL_MS:
                self.update_network_metrics()
                self.last_net_measure = current_time_ms
            
            # РћС‚РїСЂР°РІРєР° С‚РµР»РµРјРµС‚СЂРёРё (СЂР°Р· РІ 5 СЃРµРєСѓРЅРґ)
            if self.websocket and (current_time_ms - self.last_telemetry >= self.TELEMETRY_INTERVAL_MS):
                self.send_telemetry()
                self.last_telemetry = current_time_ms
            
            elapsed = time.time() - frame_start
            sleep_time = max(0, frame_interval - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            else:
                await asyncio.sleep(0.001)
    
    async def connect_and_run(self):
        """РџРѕРґРєР»СЋС‡РµРЅРёРµ Рє Р»РѕРєР°Р»СЊРЅРѕРјСѓ СЃРµСЂРІРµСЂСѓ Рё Р·Р°РїСѓСЃРє"""
        if not self.init_camera():
            logger.error("[CAM] Failed to initialize camera")
            return
        
        logger.info(f"[WiFi] Connecting to network...")
        logger.info(f"[WS] Connecting to {self.ws_url}")
        
        while self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=5,
                    max_size=2**23
                ) as websocket:
                    self.websocket = websocket
                    self.running = True
                    self.reconnect_attempts = 0
                    
                    logger.info(f"[WS] connected! вњ…")
                    logger.info(f"[WS] Server: {self.server_host}:{self.server_port}")
                    logger.info(f"[CAM] Streaming video...")
                    
                    stream_task = asyncio.create_task(self.video_stream_loop())
                    message_task = asyncio.create_task(self.handle_websocket_messages())
                    
                    done, pending = await asyncio.wait(
                        [stream_task, message_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    for task in pending:
                        task.cancel()
                    
            except ConnectionRefusedError:
                logger.error(f"[WS] Connection refused! Make sure server is running on {self.server_host}:{self.server_port}")
                break
            except Exception as e:
                logger.error(f"[WS] Connection error: {e}")
                self.reconnect_attempts += 1
                
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    wait_time = min(3 * self.reconnect_attempts, 30)
                    logger.info(f"[WS] Reconnecting in {wait_time}s (attempt {self.reconnect_attempts}/{self.max_reconnect_attempts})...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("[WS] Max reconnection attempts reached")
        
        self.cleanup()
    
    def cleanup(self):
        """РћС‡РёСЃС‚РєР° СЂРµСЃСѓСЂСЃРѕРІ"""
        self.running = False
        if self.cap:
            self.cap.release()
        logger.info("[CAM] Resources released")


async def main():
    parser = argparse.ArgumentParser(description='ESP32-CAM Emulator for LOCAL server')
    parser.add_argument('--host', 
                       default='localhost',
                       help='Server host (default: localhost)')
    parser.add_argument('--port', 
                       type=int, default=8000,
                       help='Server port (default: 8000)')
    parser.add_argument('--secret', 
                       default='change-me-device',
                       help='Device secret (must match device_secret in config.py)')
    parser.add_argument('--camera', '-c', 
                       type=int, default=0,
                       help='Camera ID (default: 0)')
    parser.add_argument('--width', '-w', 
                       type=int, default=640,
                       help='Frame width (default: 640)')
    parser.add_argument('--height', '-H', 
                       type=int, default=480,
                       help='Frame height (default: 480)')
    parser.add_argument('--fps', '-f', 
                       type=int, default=15,
                       help='Frames per second (default: 15)')
    parser.add_argument('--quality', '-q', 
                       type=int, default=12,
                       help='JPEG quality 1-100 (default: 12)')
    
    args = parser.parse_args()
    
    print("""
    в•”в•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•—
    в•‘                    ESP32-CAM Emulator for LOCAL Server                   в•‘
    в•‘                                                                          в•‘
    в•‘  Make sure your server is running:                                      в•‘
    в•‘    docker compose -f docker-compose.microservices.yml up -d               в•‘
    в•љв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ќ
    """)
    
    logger.info("=" * 60)
    logger.info(f"Server: ws://{args.host}:{args.port}/ws/esp?secret={args.secret}")
    logger.info(f"Camera ID: {args.camera}")
    logger.info(f"Resolution: {args.width}x{args.height}")
    logger.info(f"FPS: {args.fps}")
    logger.info("=" * 60)
    print()
    
    emulator = ESP32WebcamEmulator(
        server_host=args.host,
        server_port=args.port,
        secret=args.secret,
        camera_id=args.camera,
        width=args.width,
        height=args.height,
        fps=args.fps,
        quality=args.quality
    )
    
    def signal_handler(signum, frame):
        logger.info("\nвЏ№пёЏ  Stopping emulator...")
        emulator.running = False
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    await emulator.connect_and_run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nвЏ№пёЏ  Stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
