"""iCar face recognition — configuration & constants"""

import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────
PACKAGE_DIR = Path(__file__).parent.parent.resolve()
MODELS_DIR = PACKAGE_DIR / 'models'
EMBED_MODEL_PATH = MODELS_DIR / 'face_embed.onnx'
EMBEDDINGS_PATH = MODELS_DIR / 'enrolled_embeddings.npz'

# ── Recognition settings ───────────────────────────
RECOGNITION_THRESHOLD = 0.64  # cosine similarity threshold
FACE_MIN_SIZE = 60             # minimum face size in pixels
DETECTION_CONFIDENCE = 0.85    # MTCNN detection confidence
SCAN_TIMEOUT_SEC = 30          # how long to scan before giving up

# ── ROS2 topics ────────────────────────────────────
# Subscribe to camera (from Astra Pro Plus)
CAMERA_TOPIC = '/camera/color/image_raw'
# Publish face detection results
FACE_DETECT_TOPIC = '/icar/face/detections'
# Publish recognition results
FACE_RECOGNITION_TOPIC = '/icar/face/recognition'

# ── TCP settings (receive from web admin) ──────────
TCP_LISTEN_HOST = '0.0.0.0'
TCP_LISTEN_PORT = 6001  # dedicated port for face commands

# ── Debug ──────────────────────────────────────────
DEBUG_MODE = os.environ.get('ICAR_FACE_DEBUG', '0') == '1'
