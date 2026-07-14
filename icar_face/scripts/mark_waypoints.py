#!/usr/bin/env python3
"""
教室坐标标记脚本 — 在 Jetson 上运行
把小车推到每个教室门口, 按回车记录坐标, 自动生成 classrooms.yaml

用法:
  python3 mark_waypoints.py
  python3 mark_waypoints.py --output classrooms.yaml
"""

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import PoseWithCovarianceStamped
import math
import yaml
import os
import sys

CLASSROOMS = ['501','502','503','504','505','506','507','508','509','510','511','512']

class WaypointMarker(Node):
    def __init__(self):
        super().__init__('waypoint_marker')
        self.latest_x = 0.0
        self.latest_y = 0.0
        self.latest_yaw = 0.0
        self.has_pose = False

        # 订阅 amcl_pose (优先) 或 odom
        self.create_subscription(
            PoseWithCovarianceStamped, '/amcl_pose', self._on_amcl, 10)
        self.create_subscription(
            Odometry, '/odom', self._on_odom, 10)

        print('等待定位数据... (确保 AMCL 已启动)')

    def _on_amcl(self, msg):
        self.latest_x = msg.pose.pose.position.x
        self.latest_y = msg.pose.pose.position.y
        oz = msg.pose.pose.orientation.z
        ow = msg.pose.pose.orientation.w
        self.latest_yaw = math.atan2(2*ow*oz, 1-2*oz*oz)  # quat z/w → yaw
        self.has_pose = True

    def _on_odom(self, msg):
        if not self.has_pose:  # odom as fallback
            self.latest_x = msg.pose.pose.position.x
            self.latest_y = msg.pose.pose.position.y
            oz = msg.pose.pose.orientation.z
            ow = msg.pose.pose.orientation.w
            self.latest_yaw = math.atan2(2*ow*oz, 1-2*oz*oz)
            self.has_pose = True

    def get_pose(self):
        rclpy.spin_once(self, timeout_sec=0.1)
        return self.latest_x, self.latest_y, self.latest_yaw


def main():
    rclpy.init()
    marker = WaypointMarker()

    # 等待定位数据
    while rclpy.ok() and not marker.has_pose:
        rclpy.spin_once(marker, timeout_sec=0.1)
    print('定位数据已就绪!\n')

    results = {}
    print('=' * 55)
    print('  教室坐标标记工具')
    print('  把小车推到教室门口 → 按 Enter 记录坐标')
    print('  输入 q 退出, 输入 s 跳过当前教室')
    print('=' * 55)

    # 先标记充电桩
    print('\n📍 充电桩 (出发点)')
    input('  推到充电桩位置后按 Enter...')
    x, y, yaw = marker.get_pose()
    results['charging_station'] = {
        'x': round(x, 3), 'y': round(y, 3), 'yaw': round(yaw, 3)
    }
    print(f'  ✅ 充电桩: x={x:.3f} y={y:.3f} yaw={yaw:.3f} ({math.degrees(yaw):.0f}°)')

    # 逐教室标记
    classrooms = {}
    for room in CLASSROOMS:
        print(f'\n📍 教室 {room}')
        cmd = input(f'  推到 {room} 门口后按 Enter (s=跳过, q=退出): ').strip().lower()
        if cmd == 'q':
            break
        if cmd == 's':
            continue
        x, y, yaw = marker.get_pose()
        classrooms[room] = {'x': round(x, 3), 'y': round(y, 3), 'yaw': round(yaw, 3)}
        print(f'  ✅ {room}: x={x:.3f} y={y:.3f} yaw={yaw:.3f} ({math.degrees(yaw):.0f}°)')

    results['classrooms'] = classrooms

    # 生成 YAML
    output = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == '--output' else 'classrooms.yaml'

    yaml_text = yaml.dump(results, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # 添加注释头
    header = (
        '# iCar 教室 SLAM 坐标映射\n'
        '# 自动生成于标记脚本\n'
        '# 坐标系: SLAM map frame\n'
        '# 单位: 位置—米(m), 朝向—弧度(rad)\n\n'
    )

    with open(output, 'w', encoding='utf-8') as f:
        f.write(header + yaml_text)

    print(f'\n{"="*55}')
    print(f'✅ 已保存到 {output}')
    print(f'   共 {len(classrooms)} 个教室坐标 + 充电桩')
    print(f'{"="*55}')

    marker.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
