#!/bin/bash
# ============================================
# 将训练好的模型文件复制到 icar_face 包中
# 在开发机上运行此脚本
# ============================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SOURCE_DIR="$PROJECT_DIR/../face_recognition/models"

echo "复制模型文件..."
echo "  源目录: $SOURCE_DIR"
echo "  目标:   $PROJECT_DIR/models"

mkdir -p "$PROJECT_DIR/models"

# 复制必要文件
cp -v "$SOURCE_DIR/face_embed.onnx" "$PROJECT_DIR/models/"
cp -v "$SOURCE_DIR/enrolled_embeddings.npz" "$PROJECT_DIR/models/"

echo ""
echo "完成! 模型已就绪"
echo "下一步: 将整个 icar_face/ 目录复制到 Jetson"
echo ""
echo "  scp -r $PROJECT_DIR jetson@icar:~/icar_face"
