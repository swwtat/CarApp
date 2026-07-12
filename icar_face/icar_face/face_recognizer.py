"""
ROS2 人脸识别节点
=================
接收检测到的人脸, 使用 FaceNet ONNX 提取嵌入向量,
与注册用户比对, 判断是否为收件人。

话题:
  订阅: /icar/face/detections       (检测到的人脸)
  发布: /icar/face/recognition       (识别结果)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import base64
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort

from . import (
    EMBED_MODEL_PATH,
    EMBEDDINGS_PATH,
    RECOGNITION_THRESHOLD,
    SCAN_TIMEOUT_SEC,
    DEBUG_MODE,
)


class FaceRecognizerNode(Node):
    """
    人脸识别 ROS2 节点

    维护一个"目标收件人"状态, 当收到检测结果时,
    提取人脸嵌入并与目标比对, 匹配成功时发布识别结果。
    """

    def __init__(self):
        super().__init__('face_recognizer')

        # ── 订阅检测结果 ──
        self.create_subscription(
            String, '/icar/face/detections', self.on_detection, 10
        )

        # ── 发布识别结果 ──
        self.result_pub = self.create_publisher(
            String, '/icar/face/recognition', 10
        )

        # ── 接收控制指令 (web → 小车 TCP → 此节点) ──
        self.ctrl_sub = self.create_subscription(
            String, '/icar/face/command', self.on_command, 10
        )

        # ── 加载 ONNX 模型 ──
        self._load_model()

        # ── 加载注册用户嵌入 ──
        self._load_enrolled_embeddings()

        # ── 状态机 ──
        self.target_recipient = None     # 当前目标收件人姓名
        self.target_order_id = None      # 当前订单 ID
        self.scan_start_time = None      # 开始扫描的时间
        self.scanning = False            # 是否正在扫描
        self.consecutive_matches = 0     # 连续匹配次数 (防抖)
        self.REQUIRED_MATCHES = 3        # 需要连续匹配多少次才确认

        self.get_logger().info(f'人脸识别节点已启动 (阈值={RECOGNITION_THRESHOLD})')
        self.get_logger().info(f'注册用户: {list(self.enrolled.keys())}')

    def _load_model(self):
        """加载 ONNX 嵌入模型"""
        if not EMBED_MODEL_PATH.exists():
            self.get_logger().fatal(f'模型文件不存在: {EMBED_MODEL_PATH}')
            raise FileNotFoundError(str(EMBED_MODEL_PATH))

        # 尝试使用 CUDA, 如果不可用则 fallback 到 CPU
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        try:
            self.ort_session = ort.InferenceSession(
                str(EMBED_MODEL_PATH), providers=providers
            )
        except Exception:
            self.ort_session = ort.InferenceSession(
                str(EMBED_MODEL_PATH), providers=['CPUExecutionProvider']
            )

        self.input_name = self.ort_session.get_inputs()[0].name
        self.get_logger().info(f'ONNX 模型已加载 ({EMBED_MODEL_PATH.name})')

    def _load_enrolled_embeddings(self):
        """加载注册用户的嵌入向量"""
        if not EMBEDDINGS_PATH.exists():
            self.get_logger().fatal(f'嵌入文件不存在: {EMBEDDINGS_PATH}')
            raise FileNotFoundError(str(EMBEDDINGS_PATH))

        data = np.load(str(EMBEDDINGS_PATH), allow_pickle=True)
        names = data['names']
        self.enrolled = {}
        for name in names:
            self.enrolled[str(name)] = {
                'centroid': data[str(name)],
            }
        self.get_logger().info(f'已加载 {len(self.enrolled)} 个注册用户嵌入')

    def on_detection(self, msg: String):
        """收到检测结果"""
        if not self.scanning:
            return

        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            return

        faces = payload.get('faces', [])
        if not faces:
            return

        # 对每张检测到的人脸进行识别
        for face_info in faces:
            face_b64 = face_info.get('face_crop_base64')
            if not face_b64:
                continue

            # 解码 base64 → 解码 JPEG → numpy 数组
            try:
                img_bytes = base64.b64decode(face_b64)
                img_array = np.frombuffer(img_bytes, dtype=np.uint8)
                import cv2
                face_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if face_bgr is None:
                    continue
                face_rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
            except Exception as e:
                self.get_logger().debug(f'解码人脸失败: {e}')
                continue

            # 提取嵌入
            embedding = self._extract_embedding(face_rgb)
            if embedding is None:
                continue

            # 比对所有注册用户
            best_name, best_sim = self._identify(embedding)

            # 判断是否匹配目标收件人
            if self.target_recipient and best_name == self.target_recipient:
                if best_sim >= RECOGNITION_THRESHOLD:
                    self.consecutive_matches += 1
                    self.get_logger().info(
                        f'匹配! {best_name} (sim={best_sim:.4f}, '
                        f'连续={self.consecutive_matches}/{self.REQUIRED_MATCHES})'
                    )

                    if self.consecutive_matches >= self.REQUIRED_MATCHES:
                        self._on_recognized(best_name, best_sim, face_info['bbox'])
                else:
                    self.consecutive_matches = 0

            elif DEBUG_MODE:
                self.get_logger().debug(
                    f'检测到 {best_name} (sim={best_sim:.4f}), '
                    f'目标={self.target_recipient}'
                )

        # 超时检查
        if self.scan_start_time and self.scanning:
            elapsed = time.time() - self.scan_start_time
            if elapsed > SCAN_TIMEOUT_SEC:
                self._on_timeout()

    def _extract_embedding(self, face_rgb: np.ndarray) -> np.ndarray:
        """
        从 RGB 人脸图像提取嵌入向量

        Args:
            face_rgb: (160, 160, 3) numpy array

        Returns:
            (512,) numpy array
        """
        # 预处理: 归一化到 [-1, 1]
        img = face_rgb.astype(np.float32) / 127.5 - 1.0
        # 转置: HWC -> CHW
        img = np.transpose(img, (2, 0, 1))
        # 添加 batch 维度
        img = np.expand_dims(img, axis=0)

        # ONNX 推理
        output = self.ort_session.run(None, {self.input_name: img})[0]
        return output.flatten()

    def _identify(self, embedding: np.ndarray) -> tuple:
        """
        与所有注册用户比对, 返回最佳匹配

        Returns:
            (name: str, similarity: float)
        """
        best_name = 'unknown'
        best_sim = -1.0

        for name, info in self.enrolled.items():
            sim = self._cosine_similarity(embedding, info['centroid'])
            if sim > best_sim:
                best_sim = sim
                best_name = name

        return best_name, best_sim

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """余弦相似度"""
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

    def on_command(self, msg: String):
        """接收控制指令"""
        try:
            cmd = json.loads(msg.data)
        except json.JSONDecodeError:
            return

        action = cmd.get('action')

        if action == 'start_scan':
            # 开始扫描教室
            self.target_recipient = cmd.get('recipient_name')
            self.target_order_id = cmd.get('order_id')
            self.consecutive_matches = 0
            self.scan_start_time = time.time()
            self.scanning = True
            self.get_logger().info(
                f'开始扫描 — 寻找收件人: {self.target_recipient} '
                f'(订单: {self.target_order_id})'
            )

        elif action == 'stop_scan':
            # 停止扫描
            self.scanning = False
            self.get_logger().info('停止扫描')

        elif action == 'add_recipient':
            # 动态添加注册用户 (接收人脸图片 base64)
            self._add_recipient(cmd)

    def _on_recognized(self, name: str, similarity: float, bbox: list):
        """识别成功回调"""
        self.scanning = False
        self.get_logger().info(f'✅ 收件人已识别: {name} (相似度={similarity:.4f})')

        result = json.dumps({
            'event': 'recognized',
            'recipient_name': name,
            'order_id': self.target_order_id,
            'similarity': float(similarity),
            'bbox': bbox,
            'timestamp': time.time(),
        }, ensure_ascii=False)
        self.result_pub.publish(String(data=result))

    def _on_timeout(self):
        """扫描超时回调"""
        self.scanning = False
        self.get_logger().warn(f'扫描超时 ({SCAN_TIMEOUT_SEC}s), 未找到 {self.target_recipient}')

        result = json.dumps({
            'event': 'timeout',
            'recipient_name': self.target_recipient,
            'order_id': self.target_order_id,
            'timestamp': time.time(),
        }, ensure_ascii=False)
        self.result_pub.publish(String(data=result))

    def _add_recipient(self, cmd: dict):
        """动态添加注册用户 (用于后续批量更新的场景)"""
        name = cmd.get('name')
        face_b64 = cmd.get('face_image_base64')
        if not name or not face_b64:
            return

        try:
            img_bytes = base64.b64decode(face_b64)
            img_array = np.frombuffer(img_bytes, dtype=np.uint8)
            import cv2
            face_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            face_rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
            embedding = self._extract_embedding(face_rgb)
        except Exception:
            return

        self.enrolled[name] = {'centroid': embedding}
        self.get_logger().info(f'动态添加注册用户: {name}')


def main(args=None):
    rclpy.init(args=args)
    node = FaceRecognizerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
