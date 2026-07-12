# iCar Face Recognition — Jetson 部署指南

## 系统架构

```
Web 管理端 (Express)
   │
   │ TCP:6001 → face_bridge (接收指令/回传结果)
   │
   ▼
Jetson Orin Nano (ROS2 foxy)
   ├── astra_camera (深度相机驱动)
   │     └── /camera/color/image_raw
   ├── face_detector (MTCNN 检测)
   │     └── /icar/face/detections
   ├── face_recognizer (FaceNet 识别)
   │     └── /icar/face/recognition
   └── face_bridge (TCP ↔ ROS2)
```

## 部署步骤

### 1. 安装依赖 (Jetson 上)

```bash
# PyTorch for Jetson
sudo apt install python3-pip
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# ONNX Runtime GPU
pip3 install onnxruntime-gpu

# 其他依赖
pip3 install facenet-pytorch opencv-python numpy pillow

# ROS2 依赖
sudo apt install ros-foxy-cv-bridge ros-foxy-vision-msgs
```

### 2. 复制文件

```bash
# 从开发机
scp -r icar_face/ jetson@192.168.1.11:~/icar_face

# 在 Jetson 上
cd ~/icar_face
pip3 install -e .
```

### 3. 构建 ROS2 包

```bash
cd ~/icar_face
colcon build --symlink-install
source install/setup.bash
```

### 4. 启动

```bash
# 方式1: Launch 一键启动
ros2 launch icar_face icar_face.launch.py

# 方式2: 单独启动
ros2 run icar_face face_server
```

### 5. 测试 (开发机上)

```bash
# Web 端发送测试指令
echo '{"action":"start_scan","recipient_name":"张明","order_id":1}' | \
  nc 192.168.1.11 6001

# 查看状态文件
cat ~/icar_face_status.json
```

## 配置文件

| 文件 | 说明 |
|------|------|
| `models/face_embed.onnx` | FaceNet ONNX 模型 (0.7 MB) |
| `models/enrolled_embeddings.npz` | 注册用户嵌入向量 |
| `models/face_detect.onnx` | 人脸检测模型 (可选, 默认用 MTCNN) |

## 话题

| 话题 | 方向 | 类型 | 说明 |
|------|------|------|------|
| `/camera/color/image_raw` | 订阅 | Image | Astra 相机 RGB |
| `/icar/face/detections` | 发布 | String(JSON) | 检测到的人脸 |
| `/icar/face/recognition` | 发布 | String(JSON) | 识别结果 |
| `/icar/face/command` | 订阅 | String(JSON) | 控制指令 |

## 识别流程

```
1. Web 端下发订单 → TCP 发送 start_scan 指令
2. face_bridge 接收 → 发布到 /icar/face/command
3. face_recognizer 收到 → 设置目标收件人
4. face_detector 持续检测相机帧 → 发布人脸
5. face_recognizer 收到人脸 → ONNX 提取嵌入 → 比对
6. 连续 3 次匹配成功 → 发布 recognized 事件
7. face_bridge 收到 → 写入状态文件 + 通知 Web
8. 超时 30 秒未匹配 → 发布 timeout 事件
```
