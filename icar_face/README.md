# 🧠 icar_face — 小车智能配送系统

运行在 Jetson Orin Nano (ROS2) 上的完整配送执行系统，包含：
自主导航、人脸核验、避障警卫、语音播报、TCP 桥接、相机工具。

## 目录结构

```
icar_face/
├── icar_face/               ROS2 核心模块
│   ├── delivery_controller.py   配送调度引擎（状态机编排全流程）
│   ├── face_detector.py         人脸检测（MTCNN）
│   ├── face_recognizer.py       人脸识别（FaceNet ONNX）
│   ├── face_bridge.py           TCP ↔ ROS2 桥接
│   ├── face_server.py           人脸服务入口
│   ├── lidar_guard.py           激光雷达避障警卫
│   ├── visual_detector.py       视觉目标检测
│   ├── voice_broadcaster.py     语音播报
│   ├── protocol.py              TCP 帧协议编解码
│   └── delivery_status.py       配送状态定义
├── launch/                 ROS2 Launch 文件
│   ├── delivery.launch.py       配送系统完整启动
│   └── icar_face.launch.py      人脸识别独立启动
├── scripts/                工具脚本
│   ├── mark_waypoints.py        地图航点标定工具
│   ├── face_commander.py        人脸扫描指令发送（Web → 小车）
│   ├── camera_stream_server.py  MJPEG HTTP 相机流服务
│   ├── cam.py                   简化版相机服务
│   ├── fix_capture_frame.py     底盘固件补丁
│   └── copy_models.sh           模型部署脚本
├── config/                 配置
│   ├── classrooms.yaml          教室坐标映射
│   └── yahboomcar 2026714.yaml  地图配置
├── models/                 ONNX 模型
├── delivery_server.py     轻量级送货桥接（subprocess 方案，零依赖）
└── delivery-bridge.service systemd 自启配置
```

## 配送流程

```
Web后台 TCP → 解析订单 → Nav2 自主导航 → 到达教室
→ 人脸检测+识别 → 核验通过 → 语音播报 → 交付 → 返回起点
```

## 两种桥接方式

| 方式 | 文件 | 适用场景 |
|------|------|----------|
| ROS2 节点 | `icar_face/delivery_controller.py` | 需要完整配送流程（人脸+语音+避障）|
| subprocess 调用 | `delivery_server.py` | 仅需导航，零 Python 依赖 |

## 启动

```bash
# 完整配送系统
ros2 launch icar_face delivery.launch.py

# 仅人脸识别
ros2 launch icar_face icar_face.launch.py

# 轻量桥接（容器内）
python3 delivery_server.py
```

## 前提

- ROS2 Humble
- Nav2 导航栈 + 地图
- 教室航点坐标已标定（用 `scripts/mark_waypoints.py`）
