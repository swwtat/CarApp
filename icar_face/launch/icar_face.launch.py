"""
iCar 人脸识别 Launch 文件
==========================
启动完整的人脸识别管线:
  - 相机驱动 (astra_camera)
  - 人脸检测
  - 人脸识别
  - TCP 桥接
"""

from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import LogInfo, TimerAction


def generate_launch_description():
    return LaunchDescription([

        LogInfo(msg='=== iCar Face Recognition ==='),

        # ── 1. Astra 相机驱动 (如果未启动) ──
        # 注释: 通常相机驱动由其他 launch 文件启动
        # 如果需要, 取消注释:
        # Node(
        #     package='astra_camera',
        #     executable='astra_camera_node',
        #     name='astra_camera',
        #     output='screen',
        # ),

        # ── 2. 人脸检测 ──
        Node(
            package='icar_face',
            executable='face_detector',
            name='face_detector',
            output='screen',
            parameters=[{
                'use_sim_time': False,
            }],
        ),

        # ── 3. 人脸识别 (稍后启动, 等检测节点就绪) ──
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

        # ── 4. TCP 桥接 (再等 1 秒) ──
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

        LogInfo(msg='人脸识别管线已启动'),
    ])
