"""
iCar 完整配送 Launch 文件
===========================
启动配送所需全部 ROS2 节点:
  1. 人脸检测 (face_detector)
  2. 人脸识别 (face_recognizer)
  3. TCP 桥接 (face_bridge)
  4. 订单调度引擎 (delivery_controller)
  5. 语音播报 (voice_broadcaster)
  6. YOLO 视觉检测 (visual_detector)
  7. 激光雷达警卫 (lidar_guard)

前置条件:
  - 相机驱动已启动 (/camera/color/image_raw)
  - Nav2 自动导航 Docker 已启动 (或跳过)
  - 底盘驱动已启动

用法:
  ros2 launch icar_face delivery.launch.py
  ros2 launch icar_face delivery.launch.py classrooms_config:=/path/to/classrooms.yaml
"""

import os
from pathlib import Path

from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import LogInfo, TimerAction, DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition, UnlessCondition


def generate_launch_description():
    # ── 参数 ──
    classrooms_config = LaunchConfiguration('classrooms_config', default=(
        os.path.join(os.path.dirname(__file__), '..', 'config', 'classrooms.yaml')
    ))
    tcp_delivery_port = LaunchConfiguration('tcp_delivery_port', default='6000')
    tcp_face_port = LaunchConfiguration('tcp_face_port', default='6001')
    nav_timeout = LaunchConfiguration('nav_timeout', default='120')
    face_scan_timeout = LaunchConfiguration('face_scan_timeout', default='30')

    declare_classrooms = DeclareLaunchArgument(
        'classrooms_config', default_value=classrooms_config,
        description='教室 SLAM 坐标 YAML 文件路径'
    )
    declare_delivery_port = DeclareLaunchArgument(
        'tcp_delivery_port', default_value=tcp_delivery_port,
        description='配送订单 TCP 端口'
    )
    declare_face_port = DeclareLaunchArgument(
        'tcp_face_port', default_value=tcp_face_port,
        description='人脸扫描 TCP 端口'
    )
    declare_nav_timeout = DeclareLaunchArgument(
        'nav_timeout', default_value=nav_timeout,
        description='导航超时 (秒)'
    )
    declare_face_timeout = DeclareLaunchArgument(
        'face_scan_timeout', default_value=face_scan_timeout,
        description='人脸扫描超时 (秒)'
    )

    return LaunchDescription([
        declare_classrooms,
        declare_delivery_port,
        declare_face_port,
        declare_nav_timeout,
        declare_face_timeout,

        LogInfo(msg='========== iCar 配送系统启动 =========='),
        LogInfo(msg='前置条件: 相机驱动、Nav2、底盘驱动应已启动'),

        # ── 1. 人脸检测节点 ──
        Node(
            package='icar_face',
            executable='face_detector',
            name='face_detector',
            output='screen',
            parameters=[{'use_sim_time': False}],
        ),

        # ── 2. 人脸识别节点 (等待检测节点就绪) ──
        TimerAction(
            period=2.0,
            actions=[
                Node(
                    package='icar_face',
                    executable='face_recognizer',
                    name='face_recognizer',
                    output='screen',
                ),
            ],
        ),

        # ── 3. TCP 桥接 (等待识别节点就绪) ──
        TimerAction(
            period=3.0,
            actions=[
                Node(
                    package='icar_face',
                    executable='face_bridge',
                    name='face_bridge',
                    output='screen',
                ),
            ],
        ),

        # ── 4. 订单调度引擎 (等待其他节点就绪) ──
        TimerAction(
            period=4.0,
            actions=[
                Node(
                    package='icar_face',
                    executable='delivery_controller',
                    name='delivery_controller',
                    output='screen',
                    parameters=[{
                        'tcp_port': 6000,
                        'classrooms_config': Path(__file__).parent.parent / 'config' / 'classrooms.yaml',
                        'nav_timeout': 120,
                        'face_scan_timeout': 30,
                        'web_admin_url': '',  # 设为 Web 管理端地址
                    }],
                ),
            ],
        ),

        # ── 5. 语音播报 ──
        TimerAction(
            period=5.0,
            actions=[
                Node(
                    package='icar_face',
                    executable='voice_broadcaster',
                    name='voice_broadcaster',
                    output='screen',
                ),
            ],
        ),

        # ── 6. YOLO 视觉检测 ──
        TimerAction(
            period=5.0,
            actions=[
                Node(
                    package='icar_face',
                    executable='visual_detector',
                    name='visual_detector',
                    output='screen',
                ),
            ],
        ),

        LogInfo(msg='========== 配送系统启动完成 =========='),
        LogInfo(msg='配送订单 TCP: 端口 6000'),

        LogInfo(msg='人脸扫描 TCP: 端口 6001'),
        LogInfo(msg='配送状态文件: ~/icar_delivery_status.json'),
        LogInfo(msg='语音播报: 已启动'),
        # ── 7. 激光雷达警卫 ──
        TimerAction(
            period=6.0,
            actions=[
                Node(
                    package='icar_face',
                    executable='lidar_guard',
                    name='lidar_guard',
                    output='screen',
                    parameters=[{
                        'safe_distance': 2.0,
                        'warning_distance': 1.0,
                        'danger_distance': 0.5,
                        'critical_distance': 0.3,
                        'approach_speed_threshold': 0.5,
                        'sudden_appear_grace_sec': 1.5,
                        'buzzer_enabled': True,
                        'buzzer_gpio_pin': 18,
                        'buzzer_type': 'gpio',
                    }],
                ),
            ],
        ),

        LogInfo(msg='YOLO视觉检测: 已启动'),
        LogInfo(msg='激光雷达警卫: 已启动'),
        LogInfo(msg='确保 Nav2 Docker 已启动后即可接收订单'),
    ])
