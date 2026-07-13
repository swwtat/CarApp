"""
本机摄像头实时人脸识别测试
============================
使用笔记本摄像头 + MTCNN 检测 + FaceNet ONNX 识别
不需要 ROS2, 不需要 Astra 相机。

用法:
  python webcam_test.py

按键:
  q — 退出
  s — 截图保存
"""

import cv2
import numpy as np
import onnxruntime as ort
from pathlib import Path
import time
import sys

# 尝试加载 MTCNN
try:
    from facenet_pytorch import MTCNN
    HAS_MTCNN = True
except ImportError:
    HAS_MTCNN = False
    print("[WARN] facenet_pytorch 未安装, 使用 OpenCV Haar Cascade")
    sys.exit(1)

# ── 配置 ──
MODEL_DIR = Path("models")
EMBED_MODEL = MODEL_DIR / "face_embed.onnx"
EMBEDDINGS_FILE = MODEL_DIR / "enrolled_embeddings.npz"
THRESHOLD = 0.64
DEVICE = "cpu"  # 本机用 CPU

# ── 加载模型 ──
print("加载 MTCNN 检测器...")
mtcnn = MTCNN(
    image_size=160, margin=20, min_face_size=60,
    thresholds=[0.6, 0.7, 0.7], factor=0.709,
    post_process=True, device=DEVICE, keep_all=True,
)

print("加载 FaceNet ONNX...")
session = ort.InferenceSession(str(EMBED_MODEL), providers=['CPUExecutionProvider'])
input_name = session.get_inputs()[0].name

print("加载注册用户...")
data = np.load(str(EMBEDDINGS_FILE), allow_pickle=True)
enrolled = {}
for name in data['names']:
    enrolled[str(name)] = data[str(name)]
print(f"注册用户: {list(enrolled.keys())}")

# ── 摄像头 ──
print("打开摄像头...")
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("无法打开摄像头! 尝试 index 1...")
    cap = cv2.VideoCapture(1)
if not cap.isOpened():
    print("未找到摄像头, 退出")
    sys.exit(1)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

print("\nReady! Press 'q' to quit, 's' to screenshot\n")

# ── 主循环 ──
fps_counter = []
frame_idx = 0
cached_results = []  # 帧间缓存

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_idx += 1
    t0 = time.time()

    # 每 5 帧检测一次 (降低 CPU 负载)
    if frame_idx % 5 == 0:
        cached_results = []
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        try:
            boxes, probs = mtcnn.detect(rgb)
        except Exception:
            boxes, probs = None, None

        if boxes is not None and len(boxes) > 0:
            for box, prob in zip(boxes, probs):
                if prob < 0.85:
                    continue
                x1, y1, x2, y2 = [max(0, int(v)) for v in box]

                # 裁剪人脸
                face_bgr = frame[y1:y2, x1:x2]
                if face_bgr.size == 0:
                    continue
                face_resized = cv2.resize(face_bgr, (160, 160))
                face_rgb = cv2.cvtColor(face_resized, cv2.COLOR_BGR2RGB)

                # ONNX 推理
                inp = face_rgb.astype(np.float32) / 127.5 - 1.0
                inp = np.transpose(inp, (2, 0, 1))
                inp = np.expand_dims(inp, axis=0)
                emb = session.run(None, {input_name: inp})[0].flatten()

                # 比对
                best_name, best_sim = "unknown", -1
                for name, centroid in enrolled.items():
                    sim = float(np.dot(emb, centroid) /
                                (np.linalg.norm(emb) * np.linalg.norm(centroid) + 1e-8))
                    if sim > best_sim:
                        best_sim, best_name = sim, name

                cached_results.append((x1, y1, x2, y2, best_name, best_sim, prob))

    # ── 绘制 ──
    for x1, y1, x2, y2, name, sim, prob in cached_results:
        is_match = sim >= THRESHOLD and name != "unknown"

        color = (0, 255, 0) if is_match else (0, 0, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        label = f"{name} ({sim:.2f})"
        if is_match:
            label += " PASS"
        cv2.putText(frame, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    # FPS
    dt = time.time() - t0
    fps_counter.append(dt)
    if len(fps_counter) > 20:
        fps_counter.pop(0)
    fps = 1.0 / (sum(fps_counter) / len(fps_counter) + 1e-8)
    cv2.putText(frame, f"FPS: {fps:.0f}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    cv2.putText(frame, f"Threshold: {THRESHOLD}", (10, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    cv2.imshow("Face Recognition Test", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('s'):
        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{ts}.jpg"
        cv2.imwrite(filename, frame)
        print(f"截图已保存: {filename}")

cap.release()
cv2.destroyAllWindows()
print("退出")
