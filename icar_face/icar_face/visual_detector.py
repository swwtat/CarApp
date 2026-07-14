"""
YOLO 视觉检测节点 — visual_detector
=====================================
订阅 Astra 相机图像, 使用 YOLO 模型进行实时目标检测:
  - 人员检测 (person detection, COCO 预训练)
  - 道面检测 (road surface analysis, 传统 CV)
  - 障碍物检测 (bicycle/backpack/suitcase/chair 等 COCO 类别)

为答辩演示提供 AI 边缘推理视觉辅助功能。

模型:
  默认使用 YOLOv5s (COCO 80类), 可通过参数指定自定义模型。

用法:
  ros2 run icar_face visual_detector
  ros2 run icar_face visual_detector --ros-args -p active_classes:="[0,1,56]"
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

# ── COCO 类别 → (中文名, 危险分组) ──
# 只列出配送走廊场景相关的类别
COCO_HAZARD_CLASSES = {
    0:  ('person',         'PERSON'),           # 行人
    1:  ('bicycle',        'VEHICLE'),           # 走廊自行车
    2:  ('car',            'VEHICLE'),           # 车辆
    3:  ('motorcycle',     'VEHICLE'),           # 摩托车/电动车
    24: ('backpack',       'SMALL_OBSTACLE'),    # 地上书包
    28: ('suitcase',       'SMALL_OBSTACLE'),    # 行李箱挡路
    32: ('sports ball',    'SMALL_OBSTACLE'),    # 滚动的球
    39: ('bottle',         'SMALL_OBSTACLE'),    # 地面杂物
    56: ('chair',          'LARGE_OBSTACLE'),    # 走廊椅子
    58: ('potted plant',   'LARGE_OBSTACLE'),    # 走廊绿植
}

# 默认激活的 COCO 类别 ID
DEFAULT_ACTIVE_CLASSES = [0, 1, 2, 3, 24, 28, 32, 39, 56, 58]

# ── 危险等级阈值 ──
DANGER_NEAR_ZONE = 0.4       # 画面底部 40% = 近距危险区
DANGER_MID_ZONE = 0.7        # 画面 40%-70% = 中距警告区
DANGER_PATH_CENTER = 0.5     # 路径中心宽度比例 (30%-70%)
DANGER_PATH_WIDE = 0.6       # 路径宽域 (20%-80%)
SIZE_LARGE = 0.15            # 检测框面积/画面 > 15% = 大型
SIZE_MEDIUM = 0.05           # 检测框面积/画面 > 5% = 中型

# ── 检测 & 分析间隔 ──
DEFAULT_CONFIDENCE = 0.45
DETECT_INTERVAL = 0.5         # YOLO 推理间隔 (秒)
ROAD_ANALYSIS_INTERVAL = 1.0  # 道面分析间隔 (秒)

# ── 去抖动 ──
DEBOUNCE_CONSECUTIVE = 2      # 连续 N 次同等级危险才触发


class VisualDetectorNode(Node):
    """
    YOLO 视觉检测 ROS2 节点

    订阅: /camera/color/image_raw
    发布: /icar/visual/detections (JSON, 含危险评估 + 道面状况)
    """

    def __init__(self):
        super().__init__('visual_detector')

        # ── 参数 ──
        self.declare_parameter('model_path', '')
        self.declare_parameter('confidence', DEFAULT_CONFIDENCE)
        self.declare_parameter('detect_interval', DETECT_INTERVAL)
        self.declare_parameter('active_classes', DEFAULT_ACTIVE_CLASSES)
        self.declare_parameter('road_analysis_interval', ROAD_ANALYSIS_INTERVAL)
        self.declare_parameter('enable_road_analysis', True)
        self.declare_parameter('danger_size_threshold', SIZE_MEDIUM)

        self.model_path = self.get_parameter('model_path').value or ''
        self.confidence = self.get_parameter('confidence').value
        self.detect_interval = self.get_parameter('detect_interval').value
        self.active_classes = self.get_parameter('active_classes').value
        self.road_interval = self.get_parameter('road_analysis_interval').value
        self.enable_road = self.get_parameter('enable_road_analysis').value
        self.danger_size_threshold = self.get_parameter('danger_size_threshold').value

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

        # ── 节流时钟 ──
        self.last_detect_time = 0.0
        self.last_road_analysis_time = 0.0

        # ── 去抖动状态 ──
        self._danger_history = {}      # {level: consecutive_count}
        self._last_alert_level = None

        if self.has_model:
            active_names = [
                COCO_HAZARD_CLASSES[c][0]
                for c in self.active_classes if c in COCO_HAZARD_CLASSES
            ]
            self.get_logger().info('YOLO 视觉检测节点已启动')
            self.get_logger().info(f'检测类别: {", ".join(active_names)}')
            self.get_logger().info(f'检测间隔: {self.detect_interval:.1f}s | '
                                   f'道面分析: {"开启" if self.enable_road else "关闭"} '
                                   f'({self.road_interval:.1f}s)')
        else:
            self.get_logger().warn('YOLO 模型未加载, 节点以旁路模式运行')
            self.get_logger().warn('安装方法: pip install torch ultralytics')

    # ═══════════════════════════════════════════════════════════════
    # 模型加载
    # ═══════════════════════════════════════════════════════════════

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
            # 只检测我们关心的 COCO 类别
            model.classes = [c for c in self.active_classes if c in COCO_HAZARD_CLASSES]
            if not model.classes:
                model.classes = [0]  # 至少保留 person
            self.get_logger().info(
                f'已加载 YOLOv5s (COCO pretrained), 过滤 {len(model.classes)} 个类别'
            )
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

    # ═══════════════════════════════════════════════════════════════
    # 相机帧处理
    # ═══════════════════════════════════════════════════════════════

    def on_frame(self, msg: Image):
        """相机帧回调 (带节流)"""
        if not self.has_model:
            return

        now = time.time()

        # YOLO 检测节流
        if now - self.last_detect_time < self.detect_interval:
            return

        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            h, w = frame.shape[:2]

            # YOLO 推理
            detections = self._detect(frame, w, h)

            # 道面分析 (独立节流)
            road_surface = None
            if self.enable_road and (now - self.last_road_analysis_time >= self.road_interval):
                self.last_road_analysis_time = now
                road_surface = self._analyze_road_surface(frame)

            # 发布结果
            if detections or road_surface:
                self._publish(detections, road_surface, msg.header.stamp, now)
                self.last_detect_time = now

        except Exception as e:
            self.get_logger().debug(f'检测帧异常: {e}')

    # ═══════════════════════════════════════════════════════════════
    # YOLO 检测
    # ═══════════════════════════════════════════════════════════════

    def _detect(self, frame: np.ndarray, img_w: int, img_h: int) -> list:
        """执行 YOLO 检测并评估危险等级"""
        try:
            import torch
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

                    cls_id = int(row.get('class', -1))
                    cls_name = row.get('name', str(cls_id))
                    bbox = [
                        int(row['xmin']), int(row['ymin']),
                        int(row['xmax']), int(row['ymax']),
                    ]

                    # 危险等级评估
                    danger_info = self._assess_danger(bbox, cls_name, img_w, img_h)

                    detection = {
                        'class': cls_name,
                        'category': COCO_HAZARD_CLASSES.get(cls_id, ('', 'UNKNOWN'))[1],
                        'confidence': round(conf, 4),
                        'bbox': bbox,
                        **danger_info,
                    }
                    output.append(detection)

                return output

        except Exception as e:
            self.get_logger().debug(f'推理异常: {e}')

        return []

    # ═══════════════════════════════════════════════════════════════
    # 危险等级评估
    # ═══════════════════════════════════════════════════════════════

    def _assess_danger(self, bbox: list, cls_name: str,
                       img_w: int, img_h: int) -> dict:
        """
        基于检测框位置和尺寸评估危险等级。

        Returns:
            dict with: danger_level, in_path, distance_zone, size_ratio, center_x, center_y
        """
        xmin, ymin, xmax, ymax = bbox
        box_w = xmax - xmin
        box_h = ymax - ymin
        box_area = box_w * box_h
        img_area = img_w * img_h

        center_x = (xmin + xmax) / 2.0 / img_w
        center_y = (ymin + ymax) / 2.0 / img_h
        bottom_y = ymax / img_h  # bbox 底部位置 (越靠近底部越危险)
        size_ratio = box_area / img_area

        # 是否在行驶路径上
        in_path = (1 - DANGER_PATH_WIDE) / 2 < center_x < (1 + DANGER_PATH_WIDE) / 2

        # 距离区域
        if bottom_y > (1 - DANGER_NEAR_ZONE):
            distance_zone = 'near'
        elif bottom_y > (1 - DANGER_MID_ZONE):
            distance_zone = 'mid'
        else:
            distance_zone = 'far'

        # 综合判定危险等级
        size_large = size_ratio > SIZE_LARGE
        size_medium = size_ratio > self.danger_size_threshold
        in_narrow_path = (1 - DANGER_PATH_CENTER) / 2 < center_x < (1 + DANGER_PATH_CENTER) / 2

        if distance_zone == 'near' and size_large and in_narrow_path:
            danger_level = 'immediate'
        elif distance_zone in ('near', 'mid') and size_medium and in_path:
            danger_level = 'warning'
        elif distance_zone == 'far' or not in_path:
            danger_level = 'notice'
        else:
            danger_level = 'info'

        # 人员类别提高一级 (安全优先)
        if cls_name == 'person' and danger_level == 'warning' and in_narrow_path:
            danger_level = 'immediate'

        return {
            'danger_level': danger_level,
            'in_path': in_path,
            'distance_zone': distance_zone,
            'size_ratio': round(size_ratio, 4),
            'center_x': round(center_x, 4),
            'center_y': round(center_y, 4),
        }

    # ═══════════════════════════════════════════════════════════════
    # 道面分析 (传统 CV, 轻量)
    # ═══════════════════════════════════════════════════════════════

    def _analyze_road_surface(self, frame: np.ndarray) -> dict:
        """
        分析画面底部 40% 区域 (路面), 检测异常状况。

        使用降采样到 160×120 以减少 CPU 开销。

        Returns:
            dict or None: road surface condition report
        """
        try:
            h, w = frame.shape[:2]
            # 取画面底部 40% 作为路面区域
            road_region = frame[int(h * 0.6):h, :]

            if road_region.size == 0:
                return None

            # 降采样
            small = road_region[::4, ::4]  # ~1/16 面积

            # 1. 亮度分析 — 检测异常亮斑 (反光/积水)
            gray = np.mean(small, axis=2).astype(np.float32)
            mean_brightness = float(np.mean(gray))
            std_brightness = float(np.std(gray))
            # 高亮度异常区域 (> mean + 2*std)
            bright_mask = gray > (mean_brightness + 2.0 * std_brightness)
            bright_ratio = float(np.sum(bright_mask) / bright_mask.size)

            # 2. 纹理分析 — Laplacian 方差检测粗糙度异常
            lap = np.abs(np.diff(gray, axis=1)[:, :-1]) + \
                  np.abs(np.diff(gray, axis=0)[:-1, :])
            lap = lap[:gray.shape[0] - 1, :gray.shape[1] - 1]
            roughness = float(np.std(lap))

            # 3. 颜色分析 — HSV 异常色调 (油渍/污渍)
            hsv_region = road_region[::4, ::4, :].astype(np.float32)
            # 简单判断: 暗色区域比例 (油渍通常是暗色的)
            dark_mask = np.mean(hsv_region, axis=2) < 50
            dark_ratio = float(np.sum(dark_mask) / dark_mask.size)

            # ── 综合判断 ──
            anomaly_score = 0.0
            condition = 'normal'

            # 反光/积水: 高亮区域 > 15%
            if bright_ratio > 0.15:
                anomaly_score = max(anomaly_score, 0.7 + bright_ratio)
                condition = 'wet'
            # 粗糙异常: roughness 极高
            if roughness > 30:
                anomaly_score = max(anomaly_score, 0.6)
                condition = 'rough' if condition == 'normal' else condition
            # 暗色异常: 大块深色区域 > 20%
            if dark_ratio > 0.2:
                anomaly_score = max(anomaly_score, 0.5 + dark_ratio)
                condition = 'debris'

            anomaly_score = min(anomaly_score, 1.0)

            return {
                'condition': condition,
                'anomaly_score': round(anomaly_score, 3),
                'brightness_mean': round(mean_brightness, 1),
                'brightness_std': round(std_brightness, 1),
                'bright_ratio': round(bright_ratio, 3),
                'roughness': round(roughness, 2),
                'dark_ratio': round(dark_ratio, 3),
            }

        except Exception as e:
            self.get_logger().debug(f'道面分析异常: {e}')
            return None

    # ═══════════════════════════════════════════════════════════════
    # 发布 & 去抖动
    # ═══════════════════════════════════════════════════════════════

    def _publish(self, detections: list, road_surface: dict,
                 stamp, now: float):
        """构建增强 JSON 并发布 (带去抖动)"""
        # 按类别统计
        class_counts = {}
        category_counts = {}
        for d in detections:
            c = d['class']
            cat = d.get('category', 'UNKNOWN')
            class_counts[c] = class_counts.get(c, 0) + 1
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # 生成危险告警列表
        hazard_alerts = []
        for d in detections:
            level = d['danger_level']
            if level in ('immediate', 'warning'):
                alert = {
                    'type': f'{d["class"]}_in_path' if d['in_path'] else f'{d["class"]}_detected',
                    'level': level,
                    'class': d['class'],
                    'in_path': d['in_path'],
                    'message': (
                        f'前方检测到{d["class"]}, 需立即停车'
                        if level == 'immediate' else
                        f'检测到{d["class"]}, 注意避让'
                    ),
                }
                hazard_alerts.append(alert)

        # 道面危险
        if road_surface and road_surface.get('condition') != 'normal':
            if road_surface.get('anomaly_score', 0) > 0.7:
                hazard_alerts.append({
                    'type': 'road_hazard',
                    'level': 'warning',
                    'class': 'road_surface',
                    'in_path': True,
                    'message': f'地面状况异常 ({road_surface["condition"]})',
                })

        # ── 去抖动 ──
        highest_level = 'info'
        if hazard_alerts:
            levels = [a['level'] for a in hazard_alerts]
            if 'immediate' in levels:
                highest_level = 'immediate'
            elif 'warning' in levels:
                highest_level = 'warning'
            elif 'notice' in levels:
                highest_level = 'notice'

        # 更新连续计数
        self._danger_history[highest_level] = \
            self._danger_history.get(highest_level, 0) + 1
        # 清零其他级别
        for k in list(self._danger_history.keys()):
            if k != highest_level:
                del self._danger_history[k]

        # 只有连续 DEBOUNCE_CONSECUTIVE 次才确认告警
        confirmed = (
            highest_level in ('immediate', 'warning') and
            self._danger_history.get(highest_level, 0) >= DEBOUNCE_CONSECUTIVE
        )
        if not confirmed:
            hazard_alerts = [a for a in hazard_alerts if a['level'] == 'notice']

        # ── 构建载荷 ──
        payload = {
            'timestamp': now,
            'count': len(detections),
            'detections': detections,
            'summary': {
                'by_class': class_counts,
                'by_category': category_counts,
            },
            'hazard_alerts': hazard_alerts,
            'highest_danger_level': highest_level,
            'danger_confirmed': confirmed,
        }

        if road_surface:
            payload['road_surface'] = road_surface

        msg = String(data=json.dumps(payload, ensure_ascii=False))
        self.detect_pub.publish(msg)

        # ── 日志 ──
        parts = []
        if class_counts:
            parts.append(', '.join(f'{c}×{n}' for c, n in class_counts.items()))
        if hazard_alerts:
            alert_summary = ' | '.join(
                f'[{a["level"].upper()}] {a["message"]}' for a in hazard_alerts
            )
            parts.append(f'⚠ {alert_summary}')
        if road_surface and road_surface.get('condition') != 'normal':
            parts.append(
                f'🛣 道面: {road_surface["condition"]} '
                f'(异常度={road_surface["anomaly_score"]})'
            )

        if parts:
            self.get_logger().info(' | '.join(parts))

    # ═══════════════════════════════════════════════════════════════

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
