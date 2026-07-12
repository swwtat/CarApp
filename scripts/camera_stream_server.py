#!/usr/bin/env python3
"""
iCar 摄像头 HTTP 流服务
=======================
运行在小车 Jetson Orin Nano 上，读取深度相机 /dev/video0，
通过 HTTP 提供 MJPEG 实时流和单帧抓取。

启动方式:
    python3 camera_stream_server.py

端点:
    /stream   — MJPEG 实时流 (APP 预览用)
    /capture  — 单帧 JPEG (拍照用)
    /photo    — 拍照并保存到小车本地
    /status   — 服务状态检查

依赖:
    sudo apt install -y python3-opencv
"""

import cv2
import threading
import time
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

# ═══ 配置 ═══
CAMERA_DEVICE = 0          # AstraProPlus 一般映射为 /dev/video0
PORT = 8080                # HTTP 服务端口
JPEG_QUALITY = 80          # JPEG 压缩质量 (0-100)
FRAME_WIDTH = 640          # 采集分辨率宽
FRAME_HEIGHT = 480         # 采集分辨率高
SAVE_DIR = "/home/yahboom/photos"  # 拍照保存目录

# ═══ 全局帧缓存 (线程安全) ═══
latest_frame = None
frame_lock = threading.Lock()


class CameraHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器"""

    def log_message(self, format, *args):
        pass  # 静默模式，减少终端输出

    def do_GET(self):
        if self.path == "/stream":
            self._serve_stream()
        elif self.path == "/capture":
            self._serve_capture()
        elif self.path == "/photo":
            self._serve_photo()
        elif self.path == "/status":
            self._serve_status()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_stream(self):
        """MJPEG 实时流 — APP 预览画面"""
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            while True:
                with frame_lock:
                    if latest_frame is not None:
                        _, jpeg = cv2.imencode(
                            ".jpg", latest_frame,
                            [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
                        )
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n\r\n")
                        self.wfile.write(jpeg.tobytes())
                        self.wfile.write(b"\r\n")
                time.sleep(0.05)  # ~20 FPS
        except (BrokenPipeError, ConnectionResetError):
            pass  # 客户端断开，正常退出

    def _serve_capture(self):
        """单帧抓取 — APP 拍照用"""
        with frame_lock:
            if latest_frame is not None:
                _, jpeg = cv2.imencode(
                    ".jpg", latest_frame,
                    [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
                )
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(jpeg)))
                self.end_headers()
                self.wfile.write(jpeg.tobytes())
            else:
                self.send_response(204)
                self.end_headers()

    def _serve_photo(self):
        """拍照并保存到小车本地磁盘"""
        with frame_lock:
            if latest_frame is not None:
                filename = f"iCar_{int(time.time())}.jpg"
                filepath = os.path.join(SAVE_DIR, filename)
                cv2.imwrite(filepath, latest_frame)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(f"Saved: {filepath}".encode())
            else:
                self.send_response(204)
                self.end_headers()

    def _serve_status(self):
        """服务状态"""
        with frame_lock:
            status = "ok" if latest_frame is not None else "no_frame"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(status.encode())


def capture_loop():
    """摄像头采集线程 — 持续从 /dev/video0 读帧"""
    global latest_frame
    cap = cv2.VideoCapture(CAMERA_DEVICE)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

    if not cap.isOpened():
        print(f"[ERROR] Cannot open camera device {CAMERA_DEVICE}")
        print("        Try: ls /dev/video* to check available devices")
        return

    print(f"[INFO] Camera opened: {FRAME_WIDTH}x{FRAME_HEIGHT}")
    while True:
        ret, frame = cap.read()
        if ret:
            with frame_lock:
                latest_frame = frame
        time.sleep(0.03)  # ~30 FPS


if __name__ == "__main__":
    # 确保保存目录存在
    os.makedirs(SAVE_DIR, exist_ok=True)

    # 启动摄像头采集线程
    capture_thread = threading.Thread(target=capture_loop, daemon=True)
    capture_thread.start()

    # 启动 HTTP 服务
    server = HTTPServer(("0.0.0.0", PORT), CameraHandler)
    print(f"[INFO] Camera stream server running on http://0.0.0.0:{PORT}")
    print(f"        Stream: http://<car-ip>:{PORT}/stream")
    print(f"        Capture: http://<car-ip>:{PORT}/capture")
    print(f"        Photo:   http://<car-ip>:{PORT}/photo")
    print(f"        Status:  http://<car-ip>:{PORT}/status")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Server stopped.")
