"""
YOLO 视觉检测节点 — visual_detector
=====================================
订阅 Astra 相机图像, 使用 YOLO 模型进行实时目标检测:
  - 人员检测 (person detection, 使用 COCO 预训练权重)
  - 门牌识别 (door plate detection, 需自定义训练)
  - 道面检测 (road hazard detection, 需自定义训练)

为答辩演示提供 AI 边缘推理视觉辅助功能。

模型:
  默认使用 YOLOv5s (COCO 80类), 可通过参数指定自定义模型。

用法:
  ros2 run icar_face visual_detector
  ros2 run icar_face visual_detector --ros-args -p model_path:=/path/to/model.pt
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String
from cv_bridge import CvBridge

import json
import time
import numpy as np
import os
from pathlib import Path

# ── COCO 类别中对我们有用的 ──
USEFUL_CLASSES = {
    0: 'person',       # 人员检测 ← 核心
    # 以下需自定义训练:
    # 'door_plate',    # 门牌识别
    # 'hazard',         # 道面危险物
    # 'wet_floor',     # 湿滑地面
}

# ── 默认置信度阈值 ──
DEFAULT_CONFIDENCE = 0.45
DETECT_INTERVAL = 0.5  # 检测间隔 (秒), 降低 Jetson 负载


class VisualDetectorNode(Node):
    """
    YOLO 视觉检测 ROS2 节点

    订阅: /camera/color/image_raw
    发布: /icar/visual/detections (JSON)
    """

    def __init__(self):
        super().__init__('visual_detector')

        # ── 参数 ──
        self.declare_parameter('model_path', '')  # 空=使用 torch hub 自动下载
        self.declare_parameter('confidence', DEFAULT_CONFIDENCE)
        self.declare_parameter('detect_interval', DETECT_INTERVAL)

        self.model_path = self.get_parameter('model_path').value or ''
        self.confidence = self.get_parameter('confidence').value
        self.detect_interval = self.get_parameter('detect_interval').value

        # ── 加载 YOLO 模型 ──
        self.model = self._load_model()
        self.has_model = self.model is not None

        # ── 相机订阅 ──
        self.bridge = CvBridge()
        self.create_subscription(
            Image, '/camera/color/image_raw', self.on_frame, 10
        )

        # ── 检测结果发布 ──
        self.detect_pub = self.create_publisher(
            String, '/icar/visual/detections', 10
        )

        # ── 节流 ──
        self.last_detect_time = 0.0

        if self.has_model:
            self.get_logger().info('YOLO 视觉检测节点已启动 (COCO 预训练)')
            self.get_logger().info('检测目标: person (人员)')
            self.get_logger().info('检测间隔: {:.1f}s (保护 Jetson 算力)'.format(self.detect_interval))
        else:
            self.get_logger().warn('YOLO 模型未加载, 节点以旁路模式运行')
            self.get_logger().warn('安装方法: pip install torch ultralytics')

    def _load_model(self):
        """加载 YOLO 模型"""
        try:
            import torch

            # 方式 1: 本地模型文件
            if self.model_path and Path(self.model_path).exists():
                model = torch.hub.load(
                    'ultralytics/yolov5', 'custom',
                    path=self.model_path, force_reload=False
                )
                self.get_logger().info(f'已加载本地模型: {self.model_path}')
                return model

            # 方式 2: torch hub 自动下载 yolov5s
            model = torch.hub.load(
                'ultralytics/yolov5', 'yolov5s',
                pretrained=True, force_reload=False
            )
            model.conf = self.confidence
            model.classes = [0]  # 只检测 person (COCO class 0)
            # 使用 CPU 推理 (Jetson 上如有 CUDA 则自动使用)
            self.get_logger().info('已加载 YOLOv5s (COCO pretrained)')
            return model

        except ImportError:
            self.get_logger().warn('torch 未安装, 尝试 onnxruntime...')
            return self._load_onnx()
        except Exception as e:
            self.get_logger().warn(f'模型加载失败: {e}')
            return None

    def _load_onnx(self):
        """备选: 加载 ONNX YOLO 模型"""
        try:
            import onnxruntime as ort
            if not self.model_path:
                return None
            session = ort.InferenceSession(self.model_path)
            self.get_logger().info(f'已加载 ONNX 模型: {self.model_path}')
            return session
        except ImportError:
            return None
        except Exception as e:
            self.get_logger().warn(f'ONNX 加载失败: {e}')
            return None

    def on_frame(self, msg: Image):
        """相机帧回调 (带节流)"""
        if not self.has_model:
            return

        now = time.time()
        if now - self.last_detect_time < self.detect_interval:
            return
        self.last_detect_time = now

        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            detections = self._detect(frame)
            if detections:
                self._publish(detections, msg.header.stamp)
        except Exception as e:
            self.get_logger().debug(f'检测帧异常: {e}')

    def _detect(self, frame: np.ndarray) -> list:
        """执行 YOLO 检测"""
        try:
            import torch
            # YOLOv5 PyTorch 模型
            if hasattr(self.model, '__call__'):
                results = self.model(frame)
                dets = results.pandas().xyxy[0] if results is not None else None
                if dets is None or dets.empty:
                    return []

                output = []
                for _, row in dets.iterrows():
                    conf = float(row['confidence'])
                    if conf < self.confidence:
                        continue
                    cls_id = int(row['class']) if 'class' in row else int(row.get('name', 0))
                    cls_name = row.get('name', str(cls_id))
                    output.append({
                        'class': cls_name,
                        'confidence': round(conf, 4),
                        'bbox': [
                            int(row['xmin']), int(row['ymin']),
                            int(row['xmax']), int(row['ymax']),
                        ],
                    })
                return output
        except Exception as e:
            self.get_logger().debug(f'推理异常: {e}')

        return []

    def _publish(self, detections: list, stamp):
        """发布检测结果"""
        payload = {
            'timestamp': float(stamp.sec) + stamp.nanosec * 1e-9,
            'count': len(detections),
            'detections': detections,
        }

        # 统计各类别数量
        class_counts = {}
        for d in detections:
            c = d['class']
            class_counts[c] = class_counts.get(c, 0) + 1
        payload['summary'] = class_counts

        msg = String(data=json.dumps(payload, ensure_ascii=False))
        self.detect_pub.publish(msg)

        # 日志 (仅有人时打印)
        if class_counts:
            summary = ', '.join(f'{c}×{n}' for c, n in class_counts.items())
            self.get_logger().info(f'检测: {summary}')

    def destroy_node(self):
        self.get_logger().info('视觉检测节点已停止')
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = VisualDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
