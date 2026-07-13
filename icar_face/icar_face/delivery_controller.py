"""
订单调度引擎 — delivery_controller
===================================
ROS2 节点, 监听 TCP 端口 6000, 接收 Web 管理端的配送订单,
编排完整配送流程: 自主导航 → 人脸核验 → 交付 → 返回。

依赖:
  - Nav2 (navigate_to_pose action)
  - icar_face 人脸识别管线 (face_detector + face_recognizer)

用法:
  ros2 run icar_face delivery_controller
  ros2 run icar_face delivery_controller --ros-args -p classrooms_config:=./classrooms.yaml
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from std_msgs.msg import String

import json
import socket
import threading
import time
import yaml
import urllib.request
import urllib.error
from pathlib import Path

from .protocol import parse_frame, build_frame
from .delivery_status import (
    DeliveryState, STATE_LABELS,
    TERMINAL_STATES, ACTIVE_STATES,
    build_status_msg,
)

# ── Nav2 导入 (可选, 测试环境可能没有安装) ──
try:
    from nav2_msgs.action import NavigateToPose
    from geometry_msgs.msg import PoseStamped, Quaternion
    HAS_NAV2 = True
except ImportError:
    HAS_NAV2 = False

# ── 默认配置 ──
DEFAULT_TCP_PORT = 6000
DEFAULT_CLASSROOMS_CONFIG = 'classrooms.yaml'
NAV_ACTION_NAME = 'navigate_to_pose'
NAV_TIMEOUT_SEC = 120  # 导航超时 (秒)
FACE_SCAN_TIMEOUT_SEC = 30  # 人脸核验超时 (秒)


class DeliveryController(Node):
    """
    订单调度引擎 ROS2 节点

    状态机:
      IDLE → NAVIGATING → ARRIVED → SCANNING → VERIFIED → RETURNING → DONE
        │                    │         │          │
        └── (超时/取消) ──→ FAILED  ←────────────┘
    """

    def __init__(self):
        super().__init__('delivery_controller')

        # ── 参数 ──
        self.declare_parameter('tcp_port', DEFAULT_TCP_PORT)
        self.declare_parameter('classrooms_config', DEFAULT_CLASSROOMS_CONFIG)
        self.declare_parameter('nav_timeout', NAV_TIMEOUT_SEC)
        self.declare_parameter('face_scan_timeout', FACE_SCAN_TIMEOUT_SEC)
        self.declare_parameter('web_admin_url', '')  # 如 http://192.168.1.100:3000

        self.tcp_port = self.get_parameter('tcp_port').value
        self.classrooms_config_path = self.get_parameter('classrooms_config').value
        self.nav_timeout = self.get_parameter('nav_timeout').value
        self.face_scan_timeout = self.get_parameter('face_scan_timeout').value
        self.web_admin_url = (self.get_parameter('web_admin_url').value or '').rstrip('/')

        # ── 加载教室坐标 ──
        self.classrooms = self._load_classrooms()

        # ── ROS2 通信 ──
        callback_group = ReentrantCallbackGroup()

        # 发布: 人脸扫描指令
        self.face_cmd_pub = self.create_publisher(
            String, '/icar/face/command', 10
        )

        # 发布: 配送状态
        self.status_pub = self.create_publisher(
            String, '/icar/delivery/status', 10
        )

        # 订阅: 人脸识别结果
        self.face_result_sub = self.create_subscription(
            String, '/icar/face/recognition', self.on_face_result, 10,
            callback_group=callback_group
        )

        # ── Nav2 导航 Action Client ──
        self.nav_client = None
        if HAS_NAV2:
            self.nav_client = ActionClient(self, NavigateToPose, NAV_ACTION_NAME)
            self.get_logger().info(f'Nav2 action client 已创建 ({NAV_ACTION_NAME})')
        else:
            self.get_logger().warn('nav2_msgs 不可用, 导航功能将被模拟')

        # ── 状态机 ──
        self.state = DeliveryState.IDLE
        self.current_order = None  # 当前处理的订单 dict
        self.nav_goal_handle = None
        self.face_scan_timer = None
        self._cancel_requested = False

        # ── 状态文件 ──
        self.status_file = Path.home() / 'icar_delivery_status.json'

        # ── TCP 监听线程 ──
        self.running = True
        self.tcp_thread = threading.Thread(target=self._tcp_listen, daemon=True)
        self.tcp_thread.start()

        self.get_logger().info(f'配送调度引擎已启动 (TCP :{self.tcp_port})')
        self.get_logger().info(f'已加载 {len(self.classrooms)} 个教室坐标')
        self._publish_status()

    # ═══════════════════════════════════════════════════════════════
    # 教室坐标加载
    # ═══════════════════════════════════════════════════════════════

    def _load_classrooms(self) -> dict:
        """从 YAML 文件加载教室坐标映射"""
        # 搜索路径
        search_paths = [
            Path(self.classrooms_config_path),
            Path(__file__).parent.parent / 'config' / 'classrooms.yaml',
            Path(__file__).parent / 'classrooms.yaml',
        ]

        for path in search_paths:
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                    rooms = data.get('classrooms', {})
                    charging = data.get('charging_station', {})
                    self.get_logger().info(f'已加载教室坐标: {path}')
                    return {
                        'charging_station': charging,
                        'classrooms': {str(k): v for k, v in rooms.items()},
                    }
                except Exception as e:
                    self.get_logger().error(f'解析教室坐标失败 ({path}): {e}')

        # 未找到配置文件, 使用空映射
        self.get_logger().warn(
            f'教室坐标配置文件未找到, 请创建 classrooms.yaml\n'
            f'  搜索路径: {[str(p) for p in search_paths]}'
        )
        return {'charging_station': {}, 'classrooms': {}}

    # ═══════════════════════════════════════════════════════════════
    # TCP 监听
    # ═══════════════════════════════════════════════════════════════

    def _tcp_listen(self):
        """TCP 监听线程 — 接收 Web 端配送订单 (type=20) 和取消指令 (type=21)"""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            server.bind(('0.0.0.0', self.tcp_port))
            server.listen(5)
            server.settimeout(1.0)
        except OSError as e:
            self.get_logger().error(f'TCP 端口 {self.tcp_port} 绑定失败: {e}')
            self.get_logger().error('请检查端口是否被占用 (如小车自带的上位机服务)')
            return

        self.get_logger().info(f'TCP 配送服务已启动 0.0.0.0:{self.tcp_port}')

        while self.running:
            try:
                client, addr = server.accept()
                self.get_logger().info(f'TCP 连接: {addr}')
                self._handle_client(client, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.get_logger().error(f'TCP 异常: {e}')

        server.close()
        self.get_logger().info('TCP 服务已关闭')

    def _handle_client(self, client: socket.socket, addr: tuple):
        """处理 TCP 客户端连接"""
        client.settimeout(10)
        try:
            data = b''
            while True:
                try:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b'#' in chunk:
                        break
                except socket.timeout:
                    break

            if not data:
                return

            raw = data.decode('utf-8', errors='ignore')
            cmd = parse_frame(raw)

            if not cmd:
                self.get_logger().warn(f'无法解析帧: {raw[:120]}')
                return

            action = cmd.get('action', '')
            self.get_logger().info(f'收到指令: action={action}')

            if action == 'delivery_order':
                self._on_delivery_order(cmd)
            elif action == 'cancel':
                self._on_cancel_order(cmd)
            elif action == 'face_scan':
                # 转发给 face_recognizer
                self._forward_face_scan(cmd)
            else:
                self.get_logger().warn(f'未知 action: {action}')

            # 发送确认
            client.send(b'OK\n')

        except Exception as e:
            self.get_logger().error(f'处理客户端异常: {e}')
        finally:
            client.close()

    # ═══════════════════════════════════════════════════════════════
    # 指令处理
    # ═══════════════════════════════════════════════════════════════

    def _on_delivery_order(self, cmd: dict):
        """收到配送订单"""
        if self.state not in (DeliveryState.IDLE, DeliveryState.DONE, DeliveryState.FAILED):
            self.get_logger().warn(
                f'当前状态 {STATE_LABELS[self.state]}, 无法接收新订单'
            )
            # 发送忙状态回执
            self._publish_status(
                message=f'小车正忙 ({STATE_LABELS[self.state]}), 请稍后再试'
            )
            return

        order_id = cmd.get('order_id')
        order_no = cmd.get('order_no', 'N/A')
        classroom_no = str(cmd.get('classroom_no', ''))
        recipient_name = cmd.get('recipient_name', '')

        self.get_logger().info(
            f'收到配送订单: {order_no} → {classroom_no} ({recipient_name})'
        )

        # 查找教室坐标
        classroom_coords = self.classrooms['classrooms'].get(classroom_no)
        if not classroom_coords:
            self.get_logger().error(
                f'教室 {classroom_no} 无 SLAM 坐标! 请在 classrooms.yaml 中配置'
            )
            self._set_state(DeliveryState.FAILED)
            self._publish_status(
                order_id=order_id, order_no=order_no,
                message=f'教室 {classroom_no} 坐标未配置'
            )
            return

        # 保存当前订单
        self.current_order = {
            'order_id': order_id,
            'order_no': order_no,
            'classroom_no': classroom_no,
            'recipient_name': recipient_name,
            'classroom_coords': classroom_coords,
            'face_image_base64': cmd.get('face_image_base64'),
        }

        self._cancel_requested = False

        # 开始导航
        self._start_navigation(classroom_coords)

    def _on_cancel_order(self, cmd: dict):
        """收到取消订单指令"""
        order_no = cmd.get('order_no', '')
        self.get_logger().info(f'收到取消指令: {order_no}')

        if self.state in ACTIVE_STATES:
            self._cancel_requested = True
            self._cancel_navigation()
            self._set_state(DeliveryState.FAILED)
            self._publish_status(message=f'订单 {order_no} 已取消')
        else:
            self._publish_status(message=f'订单 {order_no} 无需取消 (当前状态: {STATE_LABELS.get(self.state, "未知")})')

    def _forward_face_scan(self, cmd: dict):
        """转发人脸扫描指令到 face_recognizer (用于手动触发)"""
        # 将 Web 端的 "face_scan" action 转为 face_recognizer 能理解的 "start_scan"
        scan_cmd = {
            'action': 'start_scan',
            'order_id': cmd.get('order_id'),
            'recipient_name': cmd.get('recipient_name'),
        }
        msg = String(data=json.dumps(scan_cmd, ensure_ascii=False))
        self.face_cmd_pub.publish(msg)
        self.get_logger().info(f'已转发人脸扫描指令: {scan_cmd["recipient_name"]}')

    # ═══════════════════════════════════════════════════════════════
    # 导航控制
    # ═══════════════════════════════════════════════════════════════

    def _start_navigation(self, coords: dict):
        """启动 Nav2 导航到目标坐标"""
        x = coords.get('x', 0.0)
        y = coords.get('y', 0.0)
        yaw = coords.get('yaw', 0.0)

        self._set_state(DeliveryState.NAVIGATING)
        self._publish_status(message=f'正在前往教室 {self.current_order["classroom_no"]}')

        if not HAS_NAV2 or self.nav_client is None:
            self.get_logger().warn(
                f'[SIM] 模拟导航到 classroom {self.current_order["classroom_no"]} '
                f'(x={x}, y={y}, yaw={yaw})'
            )
            # 模拟: 延迟后直接标记到达
            self._on_navigation_done(success=True)
            return

        # 等待 Nav2 action server
        if not self.nav_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error('Nav2 action server 无响应! 请确认导航 Docker 已启动')
            self._set_state(DeliveryState.FAILED)
            self._publish_status(message='导航服务不可用')
            return

        # 构建目标位姿
        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = PoseStamped()
        goal_msg.pose.header.frame_id = 'map'
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()
        goal_msg.pose.pose.position.x = float(x)
        goal_msg.pose.pose.position.y = float(y)
        goal_msg.pose.pose.position.z = 0.0

        # 欧拉角 yaw → 四元数
        import math
        goal_msg.pose.pose.orientation = Quaternion()
        goal_msg.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal_msg.pose.pose.orientation.w = math.cos(yaw / 2.0)

        self.get_logger().info(
            f'Nav2 导航目标: ({x:.2f}, {y:.2f}, yaw={yaw:.2f})'
        )

        send_goal_future = self.nav_client.send_goal_async(
            goal_msg,
            feedback_callback=self._on_nav_feedback,
        )
        send_goal_future.add_done_callback(self._on_nav_goal_response)

    def _on_nav_goal_response(self, future):
        """导航目标发送回调"""
        goal_handle = future.result()
        if not goal_handle or not goal_handle.accepted:
            self.get_logger().error('Nav2 导航目标被拒绝')
            self._on_navigation_done(success=False)
            return

        self.nav_goal_handle = goal_handle
        self.get_logger().info('Nav2 导航目标已接受, 开始行驶...')

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._on_nav_result)

    def _on_nav_feedback(self, feedback_msg):
        """导航反馈回调"""
        feedback = feedback_msg.feedback
        dist = feedback.distance_remaining
        eta = getattr(feedback, 'estimated_time_remaining', None)
        eta_str = f'{eta:.0f}s' if eta and eta > 0 else '--'
        self.get_logger().info(f'导航中... 剩余距离: {dist:.2f}m, 预计: {eta_str}')

    def _on_nav_result(self, future):
        """导航结果回调"""
        result = future.result()
        if result is None:
            self._on_navigation_done(success=False)
            return

        status = result.status
        # Nav2 状态码: 0=SUCCEEDED, 其他为各种失败状态
        nav2_succeeded = getattr(status, 'status', -1) if hasattr(status, 'status') else -1
        success = (nav2_succeeded == 0)

        self.get_logger().info(
            f'导航完成: {"成功" if success else "失败"} (status={nav2_succeeded})'
        )
        self._on_navigation_done(success=success)

    def _on_navigation_done(self, success: bool):
        """导航完成处理"""
        if self._cancel_requested:
            self.get_logger().info('导航已被取消')
            return

        if not success:
            self.get_logger().error('导航失败!')
            self._set_state(DeliveryState.FAILED)
            self._publish_status(message='导航失败, 未能到达目标教室')
            return

        # 到达教室
        self._set_state(DeliveryState.ARRIVED)
        classroom = self.current_order['classroom_no']
        self._publish_status(message=f'已到达教室 {classroom}')
        self.get_logger().info(f'已到达教室 {classroom}, 开始人脸核验...')

        # 启动人脸扫描
        self._start_face_scan()

    def _cancel_navigation(self):
        """取消当前导航"""
        if self.nav_goal_handle:
            self.get_logger().info('取消 Nav2 导航...')
            cancel_future = self.nav_goal_handle.cancel_goal_async()
            # 不等待取消结果
        self.nav_goal_handle = None

    # ═══════════════════════════════════════════════════════════════
    # 人脸扫描
    # ═══════════════════════════════════════════════════════════════

    def _start_face_scan(self):
        """触发人脸核验"""
        if self.current_order is None:
            return

        self._set_state(DeliveryState.SCANNING)
        self._publish_status(message='正在进行人脸核验...')

        # 发送 start_scan 到 face_recognizer (注意: face_recognizer 处理的是 "start_scan", 不是 "face_scan")
        scan_cmd = {
            'action': 'start_scan',
            'order_id': self.current_order['order_id'],
            'recipient_name': self.current_order['recipient_name'],
        }
        msg = String(data=json.dumps(scan_cmd, ensure_ascii=False))
        self.face_cmd_pub.publish(msg)
        self.get_logger().info(
            f'人脸扫描已触发: {self.current_order["recipient_name"]}'
        )

        # 设置超时定时器
        self.face_scan_timer = self.create_timer(
            self.face_scan_timeout, self._on_face_scan_timeout
        )

    def on_face_result(self, msg: String):
        """人脸识别结果回调"""
        if self.state != DeliveryState.SCANNING:
            return

        try:
            result = json.loads(msg.data)
        except json.JSONDecodeError:
            return

        event = result.get('event', '')
        if event not in ('recognized', 'timeout'):
            return

        # 验证是否匹配当前订单
        order_id = result.get('order_id')
        if self.current_order and order_id != self.current_order['order_id']:
            self.get_logger().debug(
                f'忽略其他订单的识别结果 (order_id={order_id})'
            )
            return

        # 取消超时定时器
        if self.face_scan_timer:
            self.destroy_timer(self.face_scan_timer)
            self.face_scan_timer = None

        if event == 'recognized':
            recipient = result.get('recipient_name', '')
            similarity = result.get('similarity', 0.0)
            self.get_logger().info(
                f'人脸核验通过: {recipient} (相似度={similarity:.4f})'
            )
            self._set_state(DeliveryState.VERIFIED)
            self._publish_status(
                message=f'人脸核验通过: {recipient}',
                extra={'similarity': similarity}
            )
            # 核验通过, 开始返回
            self._start_return()

        elif event == 'timeout':
            self.get_logger().warn('人脸核验超时')
            self._set_state(DeliveryState.FAILED)
            self._publish_status(message='人脸核验超时, 未找到收件人')

    def _on_face_scan_timeout(self):
        """人脸扫描超时回调"""
        self.get_logger().warn(f'人脸扫描超时 ({self.face_scan_timeout}s)')
        self.face_scan_timer = None

        if self.state == DeliveryState.SCANNING:
            self._set_state(DeliveryState.FAILED)
            self._publish_status(message='人脸核验超时')

            # 发送停止扫描指令
            stop_cmd = {'action': 'stop_scan'}
            msg = String(data=json.dumps(stop_cmd, ensure_ascii=False))
            self.face_cmd_pub.publish(msg)

    # ═══════════════════════════════════════════════════════════════
    # 返回充电桩
    # ═══════════════════════════════════════════════════════════════

    def _start_return(self):
        """启动返回充电桩导航"""
        charging = self.classrooms.get('charging_station', {})
        if not charging:
            self.get_logger().info('无充电桩坐标, 配送完成 (不返回)')
            self._set_state(DeliveryState.DONE)
            self._publish_status(message='配送完成')
            return

        self._set_state(DeliveryState.RETURNING)
        classroom = self.current_order['classroom_no']
        self._publish_status(message=f'正在从教室 {classroom} 返回充电桩')

        if not HAS_NAV2 or self.nav_client is None:
            self.get_logger().info('[SIM] 模拟返回充电桩')
            self._set_state(DeliveryState.DONE)
            self._publish_status(message='配送完成, 已返回充电桩')
            return

        if not self.nav_client.wait_for_server(timeout_sec=3.0):
            self.get_logger().warn('Nav2 不可用, 跳过返回')
            self._set_state(DeliveryState.DONE)
            self._publish_status(message='配送完成 (未返回)')
            return

        x = charging.get('x', 0.0)
        y = charging.get('y', 0.0)
        yaw = charging.get('yaw', 0.0)

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = PoseStamped()
        goal_msg.pose.header.frame_id = 'map'
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()
        goal_msg.pose.pose.position.x = float(x)
        goal_msg.pose.pose.position.y = float(y)
        goal_msg.pose.pose.position.z = 0.0

        import math
        goal_msg.pose.pose.orientation = Quaternion()
        goal_msg.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal_msg.pose.pose.orientation.w = math.cos(yaw / 2.0)

        self.get_logger().info(f'返回充电桩: ({x:.2f}, {y:.2f})')

        send_goal_future = self.nav_client.send_goal_async(goal_msg)
        send_goal_future.add_done_callback(self._on_return_goal_response)

    def _on_return_goal_response(self, future):
        """返回充电桩 — 目标响应"""
        goal_handle = future.result()
        if not goal_handle or not goal_handle.accepted:
            self.get_logger().warn('返回导航被拒绝')
            self._set_state(DeliveryState.DONE)
            self._publish_status(message='配送完成')
            return

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._on_return_result)

    def _on_return_result(self, future):
        """返回充电桩 — 结果"""
        result = future.result()
        success = result and getattr(result.status, 'status', -1) == 0

        self.get_logger().info(f'返回充电桩: {"成功" if success else "完成"}')
        self._set_state(DeliveryState.DONE)
        self._publish_status(
            message='配送完成, 已返回充电桩' if success else '配送完成'
        )

    # ═══════════════════════════════════════════════════════════════
    # 状态管理
    # ═══════════════════════════════════════════════════════════════

    def _set_state(self, new_state: DeliveryState):
        """切换状态并记录日志"""
        old = self.state
        self.state = new_state
        self.get_logger().info(
            f'状态变更: {STATE_LABELS.get(old, old.value)} → {STATE_LABELS[new_state]}'
        )

    def _publish_status(self, message: str = None, order_id: int = None,
                        order_no: str = None, extra: dict = None):
        """发布配送状态到 ROS2 话题、写入文件、HTTP 上报 Web 管理端"""
        order = self.current_order or {}

        msg_data = build_status_msg(
            state=self.state,
            order_id=order_id or order.get('order_id'),
            order_no=order_no or order.get('order_no'),
            classroom_no=order.get('classroom_no'),
            recipient_name=order.get('recipient_name'),
            message=message,
            extra=extra,
        )
        msg_data['timestamp'] = time.time()

        # 发布到 ROS2
        self.status_pub.publish(String(data=json.dumps(msg_data, ensure_ascii=False)))

        # 写入文件 (供 Web 端轮询)
        try:
            self.status_file.write_text(
                json.dumps(msg_data, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
        except Exception as e:
            self.get_logger().debug(f'写入状态文件失败: {e}')

        # HTTP 上报到 Web 管理端
        if self.web_admin_url:
            self._http_post_status(msg_data)

    def _http_post_status(self, msg_data: dict):
        """HTTP POST 配送状态到 Web 管理端 (后台线程, 不阻塞)"""
        def _post():
            try:
                url = f'{self.web_admin_url}/api/delivery/status'
                data = json.dumps(msg_data, ensure_ascii=False).encode('utf-8')
                req = urllib.request.Request(
                    url, data=data,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                urllib.request.urlopen(req, timeout=3)
            except urllib.error.URLError:
                self.get_logger().debug(f'HTTP 上报失败 (Web 管理端不可达)')
            except Exception as e:
                self.get_logger().debug(f'HTTP 上报异常: {e}')

        threading.Thread(target=_post, daemon=True).start()

    # ═══════════════════════════════════════════════════════════════
    # 生命周期
    # ═══════════════════════════════════════════════════════════════

    def destroy_node(self):
        self.running = False
        # 取消导航
        if self.nav_goal_handle:
            self._cancel_navigation()
        # 写入最终状态
        self._set_state(DeliveryState.IDLE)
        self._publish_status(message='调度引擎已关闭')
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = DeliveryController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
