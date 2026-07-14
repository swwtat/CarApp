"""iCar face recognition & delivery — configuration & constants"""

import os
from pathlib import Path

# ── Paths (resolve install/share layout) ────────────
try:
    from ament_index_python.packages import get_package_share_directory
    _SHARE_DIR = Path(get_package_share_directory('icar_face'))
except ImportError:
    # fallback: running from source tree
    _SHARE_DIR = Path(__file__).parent.parent.resolve()

MODELS_DIR = _SHARE_DIR / 'models'
CONFIG_DIR = _SHARE_DIR / 'config'
EMBED_MODEL_PATH = MODELS_DIR / 'face_embed.onnx'
EMBEDDINGS_PATH = MODELS_DIR / 'enrolled_embeddings.npz'
CLASSROOMS_CONFIG = CONFIG_DIR / 'classrooms.yaml'

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
# Publish face commands (from web / delivery_controller)
FACE_COMMAND_TOPIC = '/icar/face/command'
# Publish delivery status
DELIVERY_STATUS_TOPIC = '/icar/delivery/status'

# ── TCP settings (receive from web admin) ──────────
TCP_LISTEN_HOST = '0.0.0.0'
TCP_LISTEN_PORT = 6001       # face bridge (face scan commands)
TCP_DELIVERY_PORT = 6000     # delivery controller (order dispatch)

# ── Navigation settings ────────────────────────────
NAV_ACTION_NAME = 'navigate_to_pose'
NAV_TIMEOUT_SEC = 120        # navigation timeout
DELIVERY_FACE_TIMEOUT_SEC = 30  # face scan timeout during delivery

# ── Debug ──────────────────────────────────────────
DEBUG_MODE = os.environ.get('ICAR_FACE_DEBUG', '0') == '1'

# ── YOLO 视觉检测 ──────────────────────────────────
VISUAL_DETECT_TOPIC = '/icar/visual/detections'
# 激活的 COCO 类别 (person + vehicle + obstacles)
VISUAL_DEFAULT_CLASSES = [0, 1, 2, 3, 24, 28, 32, 39, 56, 58]
# 危险等级关键字
VISUAL_DANGER_IMMEDIATE = 'immediate'
VISUAL_DANGER_WARNING = 'warning'
# CAUTION 状态下最大重试次数 & 等待秒数
VISUAL_CAUTION_RETRY_MAX = 3
VISUAL_CAUTION_WAIT_SEC = 3.0

# ── LiDAR 警卫模式 ────────────────────────────────
GUARD_STATUS_TOPIC = '/icar/guard/status'
GUARD_SAFE_DISTANCE = 2.0        # 安全距离 (m)
GUARD_WARNING_DISTANCE = 1.0     # 警告距离 (m)
GUARD_DANGER_DISTANCE = 0.5      # 危险距离 (m)
GUARD_CRITICAL_DISTANCE = 0.3    # 极危距离 (包裹保护)
GUARD_APPROACH_THRESHOLD = 0.5   # 人靠近速度阈值 (m/s)
GUARD_SUDDEN_GRACE_SEC = 1.5     # 拐角相遇宽限期 (s)
