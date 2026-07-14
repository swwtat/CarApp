"""
激光雷达警卫节点 — lidar_guard
================================
订阅 RPLIDAR 激光扫描数据, 结合里程计速度, 实现智能接近检测:

  - 区分「人靠近车」vs「车靠近人」(相对速度判定)
  - 拐角突然相遇宽限期 (防止误报)
  - 三段式蜂鸣器警告 (SAFE/WARNING/DANGER/CRITICAL)
  - 包裹防窃保护 (VERIFIED 状态极近距告警)

依赖:
  - RPLIDAR A1 + rplidar_ros 驱动 → /scan
  - 里程计 → /odom
  - 配送状态 → /icar/delivery/status (包裹保护)

用法:
  ros2 run icar_face lidar_guard
  ros2 run icar_face lidar_guard --ros-args -p buzzer_enabled:=false
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry
from std_msgs.msg import String

import json
import math
import time
import threading
import numpy as np
from pathlib import Path

# ── 默认参数 ──
DEFAULT_SAFE_DISTANCE = 2.0
DEFAULT_WARNING_DISTANCE = 1.0
DEFAULT_DANGER_DISTANCE = 0.5
DEFAULT_CRITICAL_DISTANCE = 0.3
DEFAULT_APPROACH_THRESHOLD = 0.5  # m/s, 人靠近速度阈值
DEFAULT_SUDDEN_GRACE_SEC = 1.5     # 拐角宽限期
DEFAULT_TRACKING_SIZE = 10         # 追踪历史窗口


class GuardNode(Node):
    """
    激光雷达警卫 ROS2 节点

    订阅: /scan, /odom, /icar/delivery/status
    发布: /icar/guard/status (JSON)
    """

    def __init__(self):
        super().__init__('lidar_guard')

        # ── 参数 ──
        self.declare_parameter('safe_distance', DEFAULT_SAFE_DISTANCE)
        self.declare_parameter('warning_distance', DEFAULT_WARNING_DISTANCE)
        self.declare_parameter('danger_distance', DEFAULT_DANGER_DISTANCE)
        self.declare_parameter('critical_distance', DEFAULT_CRITICAL_DISTANCE)
        self.declare_parameter('approach_speed_threshold', DEFAULT_APPROACH_THRESHOLD)
        self.declare_parameter('sudden_appear_grace_sec', DEFAULT_SUDDEN_GRACE_SEC)
        self.declare_parameter('tracking_history_size', DEFAULT_TRACKING_SIZE)
        self.declare_parameter('buzzer_enabled', True)
        self.declare_parameter('buzzer_gpio_pin', 18)
        self.declare_parameter('buzzer_type', 'gpio')

        self.safe_distance = self.get_parameter('safe_distance').value
        self.warning_distance = self.get_parameter('warning_distance').value
        self.danger_distance = self.get_parameter('danger_distance').value
        self.critical_distance = self.get_parameter('critical_distance').value
        self.approach_threshold = self.get_parameter('approach_speed_threshold').value
        self.sudden_grace = self.get_parameter('sudden_appear_grace_sec').value
        self.tracking_size = self.get_parameter('tracking_history_size').value
        self.buzzer_enabled = self.get_parameter('buzzer_enabled').value
        self.buzzer_pin = self.get_parameter('buzzer_gpio_pin').value
        self.buzzer_type = self.get_parameter('buzzer_type').value

        # ── ROS2 订阅 ──
        self.create_subscription(LaserScan, '/scan', self._process_scan, 10)
        self.create_subscription(Odometry, '/odom', self._on_odom, 10)
        self.create_subscription(String, '/icar/delivery/status', self._on_delivery_status, 10)

        # ── ROS2 发布 ──
        self.guard_pub = self.create_publisher(String, '/icar/guard/status', 10)

        # ── 状态 ──
        self._robot_velocity = 0.0        # 小车当前线速度 (m/s)
        self._delivery_state = 'idle'     # 当前配送状态
        self._tracking_history = []       # [(dist, angle, timestamp), ...]
        self._sudden_appear_time = 0.0    # 最近一次突然出现的时间
        self._last_zone = 'safe'          # 上一帧警戒区

        # ── 蜂鸣器 ──
        self._buzzer = None
        self._buzzer_stop_event = threading.Event()
        self._buzzer_thread = None
        if self.buzzer_enabled:
            self._init_buzzer()

        self.get_logger().info(
            f'激光雷达警卫已启动 | '
            f'警戒距: S>{self.safe_distance}m W>{self.warning_distance}m '
            f'D>{self.danger_distance}m C<{self.critical_distance}m | '
            f'接近阈值: {self.approach_threshold}m/s | '
            f'蜂鸣器: {"开启" if self.buzzer_enabled else "关闭"} '
            f'({self.buzzer_type})'
        )

    # ═══════════════════════════════════════════════════════════════
    # 传感器回调
    # ═══════════════════════════════════════════════════════════════

    def _on_odom(self, msg: Odometry):
        """里程计回调 — 提取小车线速度"""
        vx = msg.twist.twist.linear.x
        vy = msg.twist.twist.linear.y
        self._robot_velocity = math.sqrt(vx * vx + vy * vy)

    def _on_delivery_status(self, msg: String):
        """配送状态回调 — 记录当前状态 (包裹保护用)"""
        try:
            data = json.loads(msg.data)
            self._delivery_state = data.get('state', 'idle')
        except json.JSONDecodeError:
            pass

    # ═══════════════════════════════════════════════════════════════
    # 核心判定管线
    # ═══════════════════════════════════════════════════════════════

    def _process_scan(self, msg: LaserScan):
        """激光数据处理 — 核心判定管线"""
        ranges = np.array(msg.ranges, dtype=np.float32)
        now = time.time()

        # 1. 过滤无效值 (inf, nan, 太近可能是自身/地面)
        valid_mask = np.isfinite(ranges) & (ranges > 0.05) & (ranges < 12.0)
        if not np.any(valid_mask):
            self._tracking_history.clear()
            return

        # 2. 找最近有效距离
        valid_indices = np.where(valid_mask)[0]
        valid_ranges = ranges[valid_indices]
        min_in_valid = int(np.argmin(valid_ranges))
        actual_idx = valid_indices[min_in_valid]
        min_dist = float(valid_ranges[min_in_valid])
        min_angle = float(msg.angle_min + actual_idx * msg.angle_increment)

        # 3. 追踪历史 (用于计算速度 + 检测突然出现)
        self._tracking_history.append((min_dist, min_angle, now))
        if len(self._tracking_history) > self.tracking_size:
            self._tracking_history.pop(0)

        # 4. 检测突然出现 (拐角相遇)
        is_sudden = self._is_sudden_appearance(min_dist)

        # 5. 计算人的接近速度
        v_approach = self._calc_approach_speed()

        # 6. 综合判定警戒等级
        zone = self._classify_zone(min_dist, v_approach, is_sudden)

        # 7. 蜂鸣器控制
        if zone != self._last_zone:
            self._control_buzzer(zone)
            self._last_zone = zone

        # 8. 发布状态
        self._publish_guard_status(min_dist, min_angle, zone, v_approach, is_sudden)

    def _is_sudden_appearance(self, min_dist: float) -> bool:
        """
        检测拐角突然相遇:
        前几帧无有效近距数据 → 突然出现 <2m 物体 → 判定为突然出现
        """
        if min_dist > 2.0:
            return False
        if len(self._tracking_history) < 3:
            self._sudden_appear_time = time.time()
            return True

        # 取最近 5 帧 (排除当前帧)
        prev_entries = self._tracking_history[-6:-1] if len(self._tracking_history) >= 6 \
            else self._tracking_history[:-1]
        if not prev_entries:
            return False

        # 前几帧是否都没有近距离物体 (<3m)
        all_far = all(
            d > 3.0 or math.isinf(d) or math.isnan(d)
            for d, _, _ in prev_entries
        )

        if all_far:
            self._sudden_appear_time = time.time()
            return True
        return False

    def _calc_approach_speed(self) -> float:
        """
        计算人主动靠近的速度 (扣除小车自身移动)。

        Returns:
            float: 人的接近速度 (m/s), 正值=靠近, 负值=远离
        """
        if len(self._tracking_history) < 3:
            return 0.0

        # 取窗口首尾帧
        d0, _, t0 = self._tracking_history[0]
        d1, _, t1 = self._tracking_history[-1]
        dt = t1 - t0
        if dt < 0.05:
            return 0.0

        # 距离缩短速率 (正值 = 距离在缩小)
        closing_speed = (d0 - d1) / dt

        # 扣除小车自身前进速度 → 纯「人靠近」速度
        v_robot = abs(self._robot_velocity)
        v_approach = closing_speed - v_robot

        # 限制在合理范围
        return max(-3.0, min(5.0, v_approach))

    def _classify_zone(self, min_dist: float, v_approach: float,
                       is_sudden: bool) -> str:
        """
        综合距离 + 接近速度 + 突然出现 → 警戒等级。

        Returns:
            'safe' | 'warning' | 'danger' | 'critical'
        """
        in_grace = (time.time() - self._sudden_appear_time) < self.sudden_grace

        # ── 包裹保护: VERIFIED/DELIVERING + 极近距离 → 立即 critical ──
        if self._delivery_state in ('verified', 'delivering'):
            if min_dist < self.critical_distance:
                return 'critical'

        # ── 距离分级 ──
        if min_dist < self.critical_distance:
            return 'warning' if (in_grace and is_sudden) else 'critical'

        if min_dist < self.danger_distance:
            if is_sudden and in_grace:
                return 'warning'  # 宽限期降级
            if v_approach > 0.3:
                return 'danger'   # 确认人靠近
            return 'warning'      # 人在近距离但未主动靠近

        if min_dist < self.warning_distance:
            if is_sudden and in_grace:
                return 'safe'     # 宽限期不告警
            if v_approach > self.approach_threshold:
                return 'warning'  # 确认人靠近
            return 'safe'         # 车在靠近人, 不告警

        # min_dist > warning_distance
        return 'safe'

    # ═══════════════════════════════════════════════════════════════
    # 蜂鸣器
    # ═══════════════════════════════════════════════════════════════

    def _init_buzzer(self):
        """初始化蜂鸣器 (auto-detect)"""
        if self.buzzer_type == 'gpio':
            self._init_gpio_buzzer()
        elif self.buzzer_type == 'system_beep':
            self._init_system_beep()
        elif self.buzzer_type == 'pygame':
            self._init_pygame_buzzer()
        else:
            # 自动检测
            if self._init_gpio_buzzer():
                return
            if self._init_system_beep():
                return
            if self._init_pygame_buzzer():
                return
            self.get_logger().warn('未找到可用蜂鸣器, 仅上报告警')

        # 启动蜂鸣器控制线程
        self._buzzer_thread = threading.Thread(
            target=self._buzzer_loop, daemon=True
        )
        self._buzzer_thread.start()

    def _init_gpio_buzzer(self) -> bool:
        """尝试初始化 GPIO 蜂鸣器"""
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.buzzer_pin, GPIO.OUT)
            GPIO.output(self.buzzer_pin, GPIO.LOW)
            self._buzzer = 'gpio'
            self._gpio_module = GPIO
            self.get_logger().info(f'GPIO 蜂鸣器已就绪 (BCM pin {self.buzzer_pin})')
            return True
        except ImportError:
            self.get_logger().debug('RPi.GPIO 不可用 (非树莓派/Jetson?)')
            return False
        except Exception as e:
            self.get_logger().debug(f'GPIO 初始化失败: {e}')
            return False

    def _init_system_beep(self) -> bool:
        """尝试使用 Linux beep 命令"""
        import subprocess
        try:
            result = subprocess.run(
                ['which', 'beep'], capture_output=True, timeout=3
            )
            if result.returncode == 0:
                self._buzzer = 'system_beep'
                self.get_logger().info('system_beep 蜂鸣器已就绪')
                return True
        except Exception:
            pass
        return False

    def _init_pygame_buzzer(self) -> bool:
        """尝试使用 pygame 播放音频"""
        try:
            import pygame
            pygame.mixer.init()
            # 生成简单的蜂鸣音
            self._buzzer = 'pygame'
            self.get_logger().info('pygame 蜂鸣器已就绪')
            return True
        except ImportError:
            return False
        except Exception as e:
            self.get_logger().debug(f'pygame 初始化失败: {e}')
            return False

    def _control_buzzer(self, zone: str):
        """切换蜂鸣器模式 (通过 Event 通知后台线程)"""
        if not self.buzzer_enabled or not self._buzzer:
            return

        if zone == 'safe':
            self._buzzer_stop_event.set()
        else:
            self._buzzer_stop_event.clear()
            self._buzzer_zone = zone

    def _buzzer_loop(self):
        """蜂鸣器后台线程 — 按区域模式间歇控制"""
        pattern = None  # 当前蜂鸣模式

        while rclpy.ok():
            if self._buzzer_stop_event.is_set():
                self._buzzer_off()
                pattern = None
                self._buzzer_stop_event.wait(timeout=0.1)
                continue

            zone = getattr(self, '_buzzer_zone', 'safe')

            if zone == 'critical':
                self._buzzer_on()
                pattern = None
            elif zone == 'danger':
                # 快速间歇: 200ms 响 / 500ms 停
                self._buzzer_on()
                self._buzzer_stop_event.wait(timeout=0.2)
                self._buzzer_off()
                self._buzzer_stop_event.wait(timeout=0.5)
            elif zone == 'warning':
                # 短促间歇: 500ms 响 / 2000ms 停
                self._buzzer_on()
                self._buzzer_stop_event.wait(timeout=0.5)
                self._buzzer_off()
                self._buzzer_stop_event.wait(timeout=2.0)
            else:
                self._buzzer_off()
                self._buzzer_stop_event.wait(timeout=0.5)

    def _buzzer_on(self):
        """打开蜂鸣器"""
        if self._buzzer == 'gpio':
            try:
                self._gpio_module.output(self.buzzer_pin, self._gpio_module.HIGH)
            except Exception:
                pass
        elif self._buzzer == 'system_beep':
            import subprocess
            subprocess.Popen(
                ['beep', '-f', '2000', '-l', '500'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        elif self._buzzer == 'pygame':
            pass  # pygame 方式直接播放, 不用持续开关

    def _buzzer_off(self):
        """关闭蜂鸣器"""
        if self._buzzer == 'gpio':
            try:
                self._gpio_module.output(self.buzzer_pin, self._gpio_module.LOW)
            except Exception:
                pass
        # system_beep 是一次性命令, 无需关闭

    # ═══════════════════════════════════════════════════════════════
    # 状态发布
    # ═══════════════════════════════════════════════════════════════

    def _publish_guard_status(self, min_dist: float, min_angle: float,
                               zone: str, v_approach: float,
                               is_sudden: bool):
        """发布警卫状态 JSON"""
        in_grace = (time.time() - self._sudden_appear_time) < self.sudden_grace

        # 蜂鸣器模式描述
        buzzer_patterns = {
            'safe': '',
            'warning': '短促间歇',
            'danger': '快速间歇',
            'critical': '持续蜂鸣',
        }

        # 包裹保护告警
        package_alert = (
            self._delivery_state in ('verified', 'delivering') and
            min_dist < self.critical_distance
        )

        payload = {
            'timestamp': time.time(),
            'min_distance': round(min_dist, 3),
            'min_angle_deg': round(math.degrees(min_angle), 1),
            'zone': zone,
            'v_approach': round(v_approach, 3),
            'v_robot': round(self._robot_velocity, 3),
            'is_sudden_appearance': is_sudden,
            'in_grace_period': in_grace,
            'buzzer_active': self.buzzer_enabled and zone != 'safe',
            'buzzer_pattern': buzzer_patterns.get(zone, ''),
            'package_alert': package_alert,
            'delivery_state': self._delivery_state,
        }

        self.guard_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))

        # 日志 (仅告警时)
        if zone in ('warning', 'danger', 'critical'):
            extra = []
            if is_sudden:
                extra.append('拐角相遇')
            if in_grace:
                extra.append('宽限中')
            if package_alert:
                extra.append('包裹保护')
            suffix = f' ({", ".join(extra)})' if extra else ''
            self.get_logger().info(
                f'[{zone.upper()}] d={min_dist:.2f}m v_approach={v_approach:+.2f}m/s'
                f' | v_robot={self._robot_velocity:.2f}m/s{suffix}'
            )

    # ═══════════════════════════════════════════════════════════════

    def destroy_node(self):
        self._buzzer_stop_event.set()
        if self._buzzer == 'gpio':
            try:
                self._gpio_module.output(self.buzzer_pin, self._gpio_module.LOW)
                self._gpio_module.cleanup()
            except Exception:
                pass
        self.get_logger().info('激光雷达警卫已停止')
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = GuardNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
