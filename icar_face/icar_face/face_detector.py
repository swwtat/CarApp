"""
ROS2 人脸检测节点
=================
订阅 Astra Pro Plus 相机话题, 使用 MTCNN 检测人脸,
发布裁剪后的人脸图像 + 边界框坐标。

话题:
  订阅: /camera/color/image_raw    (sensor_msgs/Image)
  发布: /icar/face/detections       (自定义 JSON)
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import numpy as np
import json
import time

# Try importing MTCNN from facenet_pytorch
try:
    from facenet_pytorch import MTCNN
    HAS_MTCNN = True
except ImportError:
    HAS_MTCNN = False

from std_msgs.msg import String
from . import FACE_MIN_SIZE, DETECTION_CONFIDENCE, DEBUG_MODE


class FaceDetectorNode(Node):
    """
    人脸检测 ROS2 节点

    从 Astra 相机接收 RGB 图像, 检测其中的人脸,
    输出裁剪对齐后的人脸图像 (base64) 和边界框。
    """

    def __init__(self):
        super().__init__('face_detector')

        # ── 订阅相机 ──
        self.subscription = self.create_subscription(
            Image, '/camera/color/image_raw', self.on_image, 10
        )
        self.bridge = CvBridge()

        # ── 发布检测结果 ──
        self.publisher = self.create_publisher(String, '/icar/face/detections', 10)

        # ── 初始化 MTCNN ──
        if HAS_MTCNN:
            use_cuda = self._check_cuda()
            device_str = 'cuda' if use_cuda else 'cpu'
            self.get_logger().info(f'使用 MTCNN 检测器 (device={device_str})')
            self.mtcnn = MTCNN(
                image_size=160,
                margin=20,
                min_face_size=FACE_MIN_SIZE,
                thresholds=[0.6, 0.7, 0.7],
                factor=0.709,
                post_process=True,
                device=device_str,
                keep_all=True,  # 检测所有人脸
            )
        else:
            self.get_logger().warn('MTCNN 不可用, 使用 OpenCV Haar Cascade 降级')
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            self.face_cascade = cv2.CascadeClassifier(cascade_path)

        # ── 统计 ──
        self.frame_count = 0
        self.detect_count = 0
        self.last_log_time = time.time()

        self.get_logger().info('人脸检测节点已启动')

    def _check_cuda(self):
        """检查 CUDA 是否可用"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def on_image(self, msg: Image):
        """相机帧回调"""
        self.frame_count += 1

        # 每 30 帧打印一次统计
        if DEBUG_MODE and self.frame_count % 30 == 0:
            elapsed = time.time() - self.last_log_time
            fps = 30 / (elapsed + 1e-8)
            self.get_logger().debug(
                f'帧率: {fps:.1f} fps | 累计检测: {self.detect_count} 次'
            )
            self.last_log_time = time.time()

        try:
            # ROS Image -> OpenCV BGR
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

            # 检测人脸
            faces = self._detect_faces(frame)

            if faces:
                self.detect_count += 1
                self._publish_detections(faces, msg.header.stamp)
        except Exception as e:
            self.get_logger().error(f'处理帧失败: {e}')

    def _detect_faces(self, frame: np.ndarray) -> list:
        """
        检测帧中的所有人脸

        Returns:
            list of dict: [{
                'bbox': [x1, y1, x2, y2],
                'confidence': float,
                'face_crop_base64': str (160x160 JPEG base64)
            }, ...]
        """
        if HAS_MTCNN:
            return self._detect_mtcnn(frame)
        else:
            return self._detect_opencv(frame)

    def _detect_mtcnn(self, frame: np.ndarray) -> list:
        """使用 MTCNN 检测"""
        # MTCNN 需要 PIL Image
        from PIL import Image
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)

        try:
            # MTCNN 返回: (boxes, probs) 或 None
            # 注意: 调用 detect() 获取原始结果
            boxes, probs = self.mtcnn.detect(pil_img)

            if boxes is None or len(boxes) == 0:
                return []

            results = []
            for box, prob in zip(boxes, probs):
                if prob < DETECTION_CONFIDENCE:
                    continue

                x1, y1, x2, y2 = [int(v) for v in box]
                # 确保坐标在图像范围内
                h, w = frame.shape[:2]
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)

                if x2 <= x1 or y2 <= y1:
                    continue

                # 裁剪并编码
                face_crop = frame[y1:y2, x1:x2]
                face_base64 = self._encode_face(face_crop)

                results.append({
                    'bbox': [x1, y1, x2, y2],
                    'confidence': float(prob),
                    'face_crop_base64': face_base64,
                })

            return results

        except Exception as e:
            if DEBUG_MODE:
                self.get_logger().debug(f'MTCNN 检测异常: {e}')
            return []

    def _detect_opencv(self, frame: np.ndarray) -> list:
        """降级方案: OpenCV Haar Cascade"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5,
            minSize=(FACE_MIN_SIZE, FACE_MIN_SIZE)
        )

        results = []
        for (x, y, w, h) in faces:
            face_crop = frame[y:y+h, x:x+w]
            face_base64 = self._encode_face(face_crop)
            results.append({
                'bbox': [int(x), int(y), int(x+w), int(y+h)],
                'confidence': 1.0,  # Haar cascade 不提供置信度
                'face_crop_base64': face_base64,
            })
        return results

    def _encode_face(self, face_bgr: np.ndarray) -> str:
        """将人脸图像编码为 base64 JPEG"""
        import base64
        # 调整为 160x160
        face_resized = cv2.resize(face_bgr, (160, 160))
        _, buffer = cv2.imencode('.jpg', face_resized, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return base64.b64encode(buffer).decode('utf-8')

    def _publish_detections(self, faces: list, timestamp):
        """发布检测结果"""
        msg = String()
        payload = {
            'timestamp': float(timestamp.sec) + timestamp.nanosec * 1e-9,
            'face_count': len(faces),
            'faces': faces,
        }
        msg.data = json.dumps(payload, ensure_ascii=False)
        self.publisher.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = FaceDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
