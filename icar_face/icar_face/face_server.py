"""
人脸识别服务 — 一站式启动
==========================
同时启动人脸检测 + 识别 + TCP 桥接三个节点。

用法:
  ros2 run icar_face face_server

或在 launch 文件中使用:
  ros2 launch icar_face icar_face.launch.py
"""

import rclpy
from rclpy.executors import MultiThreadedExecutor
from .face_detector import FaceDetectorNode
from .face_recognizer import FaceRecognizerNode
from .face_bridge import FaceBridgeNode


def main(args=None):
    rclpy.init(args=args)

    executor = MultiThreadedExecutor()

    detector = FaceDetectorNode()
    recognizer = FaceRecognizerNode()
    bridge = FaceBridgeNode()

    executor.add_node(detector)
    executor.add_node(recognizer)
    executor.add_node(bridge)

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        detector.destroy_node()
        recognizer.destroy_node()
        bridge.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
