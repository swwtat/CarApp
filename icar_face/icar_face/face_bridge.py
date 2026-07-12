"""
TCP 桥接节点 — Web 管理端 ↔ ROS2 人脸识别
===========================================
监听 TCP 端口, 接收来自 Web 管理端的指令,
转发到 ROS2 话题。同时发布识别结果回 Web。

Web 管理端通过 type=20 协议的 JSON 下发指令:
  {
    "action": "face_scan",
    "order_id": 1,
    "recipient_name": "张明",
    "face_image_base64": "...",    // 目标人脸图片 (base64 JPEG)
    "classroom_no": "501"
  }

此节点将:
  1. 解析 Web 指令 → 发布到 /icar/face/command
  2. 监听 /icar/face/recognition → 转发识别结果回 Web (通过文件/HTTP)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import socket
import threading
import select

from . import TCP_LISTEN_HOST, TCP_LISTEN_PORT, DEBUG_MODE


class FaceBridgeNode(Node):
    """
    TCP ↔ ROS2 双向桥接

    方向1 (Web→ROS): TCP JSON → /icar/face/command
    方向2 (ROS→Web): /icar/face/recognition → 结果写入文件 + 回调 Web
    """

    def __init__(self):
        super().__init__('face_bridge')

        # ── 发布命令到识别节点 ──
        self.cmd_pub = self.create_publisher(
            String, '/icar/face/command', 10
        )

        # ── 订阅识别结果 ──
        self.result_sub = self.create_subscription(
            String, '/icar/face/recognition', self.on_result, 10
        )

        # ── 状态文件 (Web 端轮询此文件获取结果) ──
        from pathlib import Path
        self.status_file = Path.home() / 'icar_face_status.json'

        # ── 启动 TCP 监听线程 ──
        self.running = True
        self.tcp_thread = threading.Thread(target=self._tcp_listen, daemon=True)
        self.tcp_thread.start()

        self.get_logger().info(f'TCP 桥接节点已启动 (监听 {TCP_LISTEN_HOST}:{TCP_LISTEN_PORT})')

    def _tcp_listen(self):
        """TCP 监听线程"""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            server.bind((TCP_LISTEN_HOST, TCP_LISTEN_PORT))
            server.listen(1)
            server.settimeout(1.0)
        except OSError as e:
            self.get_logger().error(f'TCP 绑定失败: {e}')
            return

        self.get_logger().info(f'TCP 服务已启动 0.0.0.0:{TCP_LISTEN_PORT}')

        while self.running:
            try:
                client, addr = server.accept()
                self.get_logger().info(f'TCP 连接: {addr}')
                self._handle_client(client)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.get_logger().error(f'TCP 异常: {e}')

        server.close()

    def _handle_client(self, client: socket.socket):
        """处理 TCP 客户端 (Web 管理端)"""
        client.settimeout(10)
        try:
            # 接收数据
            data = b''
            while True:
                try:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    # 检查是否收到完整帧 ($...#)
                    if b'#' in chunk:
                        break
                except socket.timeout:
                    break

            if not data:
                return

            # 解析 iCar 协议帧: $01<type><size><data><checksum>#
            cmd = self._parse_frame(data.decode('utf-8', errors='ignore'))
            if cmd:
                self.get_logger().info(f'收到指令: action={cmd.get("action")}')
                # 发布到 ROS2 话题
                msg = String(data=json.dumps(cmd, ensure_ascii=False))
                self.cmd_pub.publish(msg)

                # 发送确认
                client.send(b'OK\n')

        except Exception as e:
            self.get_logger().error(f'处理客户端异常: {e}')
        finally:
            client.close()

    def _parse_frame(self, raw: str) -> dict:
        """
        解析 TCP 协议帧
        格式: $01<type><size><data_hex><checksum>#

        type=20 时, data_hex 解码为 UTF-8 JSON
        """
        try:
            if not (raw.startswith('$') and '#' in raw):
                self.get_logger().warn(f'无效帧格式: {raw[:100]}')
                return None

            # 简单解析: 取 $...# 之间的内容
            start = raw.index('$')
            end = raw.index('#', start)
            content = raw[start+1:end]

            # content = 01 + type(2) + size(2) + data_hex + checksum(2)
            if len(content) < 8:
                return None

            frame_type = content[2:4]  # 例如 "20"
            size_hex = content[4:6]
            data_size = int(size_hex, 16)
            data_hex = content[6:6 + (data_size - 2) * 2]  # data 区 (含 data 自身 的 checksum 修正)

            # 简化处理: 直接尝试找 JSON
            import re
            json_match = re.search(r'\{.*\}', raw)
            if json_match:
                return json.loads(json_match.group(0))

            return None
        except Exception as e:
            if DEBUG_MODE:
                self.get_logger().debug(f'帧解析失败: {e}')
            return None

    def on_result(self, msg: String):
        """识别结果回调 — 写入状态文件供 Web 轮询"""
        try:
            result = json.loads(msg.data)
        except json.JSONDecodeError:
            return

        event = result.get('event', 'unknown')
        self.get_logger().info(f'识别结果: {event}')

        # 写入状态文件
        status = {
            'event': event,
            'recipient_name': result.get('recipient_name'),
            'order_id': result.get('order_id'),
            'similarity': result.get('similarity'),
            'timestamp': result.get('timestamp'),
        }
        try:
            self.status_file.write_text(
                json.dumps(status, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
        except Exception as e:
            self.get_logger().error(f'写入状态文件失败: {e}')

    def destroy_node(self):
        self.running = False
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = FaceBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
