#!/bin/bash
# ============================================
# iCar 人脸识别 — 一键部署脚本
# 在开发机上运行, 自动打包并上传到 Jetson
# ============================================
set -e

JETSON_HOST="${JETSON_HOST:-192.168.1.11}"
JETSON_USER="${JETSON_USER:-jetson}"
JETSON_DIR="/home/${JETSON_USER}/icar_face"
LOCAL_DIR="$(cd "$(dirname "$0")/../icar_face" && pwd)"

echo "========================================="
echo " iCar 人脸识别 — 一键部署"
echo "========================================="
echo ""
echo "  本地目录: $LOCAL_DIR"
echo "  目标主机: ${JETSON_USER}@${JETSON_HOST}"
echo "  目标路径: $JETSON_DIR"
echo ""

# 1. 检查本地文件
echo "[1/4] 检查本地文件..."
for f in models/face_embed.onnx models/enrolled_embeddings.npz; do
    if [ ! -f "$LOCAL_DIR/$f" ]; then
        echo "  [ERROR] 缺少文件: $f"
        echo "  请先运行: cd ../face_recognition && python export_models.py"
        exit 1
    fi
done
echo "  本地文件完整"
echo ""

# 2. 测试 Jetson 连通性
echo "[2/4] 测试 Jetson 连通性..."
if ping -c 1 -W 2 "$JETSON_HOST" > /dev/null 2>&1; then
    echo "  Jetson 可达 ($JETSON_HOST)"
else
    echo "  [WARNING] 无法 ping 通 $JETSON_HOST, 继续尝试..."
fi
echo ""

# 3. 上传文件
echo "[3/4] 上传文件到 Jetson..."
ssh "${JETSON_USER}@${JETSON_HOST}" "mkdir -p $JETSON_DIR"
rsync -avz --exclude='__pycache__' --exclude='*.pyc' \
    "$LOCAL_DIR/" "${JETSON_USER}@${JETSON_HOST}:${JETSON_DIR}/"
echo "  上传完成"
echo ""

# 4. 在 Jetson 上构建
echo "[4/4] 在 Jetson 上安装..."
ssh "${JETSON_USER}@${JETSON_HOST}" << 'EOF'
    cd ~/icar_face

    # 安装 Python 依赖
    pip3 install --user -q onnxruntime-gpu facenet-pytorch opencv-python numpy pillow 2>/dev/null || true

    # ROS2 构建
    if [ -d ~/ros2_ws ]; then
        cp -r ~/icar_face ~/ros2_ws/src/ 2>/dev/null || true
        cd ~/ros2_ws
        colcon build --symlink-install --packages-select icar_face 2>/dev/null || \
            echo "  [INFO] colcon build 跳过 (可能未安装 ROS2 构建工具)"
    fi

    echo "  Jetson 端安装完成"
EOF

echo ""
echo "========================================="
echo "  部署完成!"
echo "========================================="
echo ""
echo "在 Jetson 上启动:"
echo "  ssh ${JETSON_USER}@${JETSON_HOST}"
echo "  cd ~/icar_face"
echo "  ros2 run icar_face face_server"
echo ""
echo "或在开发机测试 TCP 连接:"
echo "  python car_recognition/face_commander.py <image_path> 张明 501"
