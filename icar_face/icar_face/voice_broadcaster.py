"""
语音播报节点 — voice_broadcaster
=================================
监听配送状态变化, 在关键节点进行中文语音播报,
提升答辩演示效果和人机交互体验。

依赖 (按优先级):
  1. espeak-ng (with Mandarin voice) — sudo apt install espeak-ng
  2. pyttsx3 — pip install pyttsx3
  3. gTTS (Google TTS, 需联网) — pip install gtts

用法:
  ros2 run icar_face voice_broadcaster
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import subprocess
import threading
import os

# ── 播报文案模板 ──
VOICE_SCRIPTS = {
    'navigating': '收到新订单，正在前往{recipient}的{classroom}教室',
    'arrived': '已到达{classroom}教室，正在进行人脸核验',
    'scanning': '正在进行人脸核验，请面对摄像头',
    'verified': '身份核验通过，{recipient}，请取走您的快递',
    'returning': '配送完成，正在返回充电桩',
    'done': '已返回充电桩，等待下一个订单',
    'failed': '配送失败，请查看原因',
}


class VoiceBroadcaster(Node):
    """
    语音播报 ROS2 节点

    订阅 /icar/delivery/status, 检测状态变化,
    通过 TTS 引擎播报中文语音。
    """

    def __init__(self):
        super().__init__('voice_broadcaster')

        # ── 检测 TTS 引擎 ──
        self.tts_engine = self._detect_tts()
        if self.tts_engine == 'none':
            self.get_logger().warn('无可用的 TTS 引擎! 语音播报将使用日志输出')
            self.get_logger().info('安装方法: sudo apt install espeak-ng')
        else:
            self.get_logger().info(f'使用 TTS 引擎: {self.tts_engine}')

        # ── 订阅配送状态 ──
        self.create_subscription(
            String, '/icar/delivery/status', self.on_status, 10
        )

        # ── 状态追踪 ──
        self.last_state = None
        self.last_order_info = {}

        self.get_logger().info('语音播报节点已启动')

    def _detect_tts(self) -> str:
        """检测可用的 TTS 引擎"""
        # 1. espeak-ng (本地, 最快)
        try:
            result = subprocess.run(
                ['espeak-ng', '--version'],
                capture_output=True, timeout=3
            )
            if result.returncode == 0:
                # 测试中文支持
                test = subprocess.run(
                    ['espeak-ng', '-v', 'cmn', '测试'],
                    capture_output=True, timeout=5
                )
                if test.returncode == 0:
                    return 'espeak-ng'
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # 2. espeak (旧版)
        try:
            result = subprocess.run(
                ['espeak', '--version'],
                capture_output=True, timeout=3
            )
            if result.returncode == 0:
                return 'espeak'
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # 3. pyttsx3
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            has_chinese = any('chinese' in v.name.lower() or 'mandarin' in v.name.lower() for v in voices)
            engine.stop()
            if has_chinese:
                return 'pyttsx3'
        except ImportError:
            pass

        # 4. festival
        try:
            subprocess.run(['festival', '--version'], capture_output=True, timeout=3)
            return 'festival'
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return 'none'

    def on_status(self, msg: String):
        """配送状态变化回调"""
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            return

        state = data.get('state', '')
        if state == self.last_state:
            return  # 状态未变化, 不重复播报

        prev = self.last_state
        self.last_state = state

        # 提取订单信息
        recipient = data.get('recipient_name', '收件人')
        classroom = data.get('classroom_no', '')
        message = data.get('message', '')

        # 根据状态转换选择播报内容
        script_key = state if state in VOICE_SCRIPTS else None
        if script_key:
            text = VOICE_SCRIPTS[script_key].format(
                recipient=recipient,
                classroom=classroom,
            )
            self.get_logger().info(f'🔊 播报: {text}')
            self._speak(text)

    def _speak(self, text: str):
        """异步播放语音 (不阻塞 ROS2 主线程)"""
        def _do_speak():
            try:
                if self.tts_engine == 'espeak-ng':
                    subprocess.run(
                        ['espeak-ng', '-v', 'cmn', '-s', '140', text],
                        capture_output=True, timeout=15
                    )
                elif self.tts_engine == 'espeak':
                    subprocess.run(
                        ['espeak', '-v', 'zh', '-s', '140', text],
                        capture_output=True, timeout=15
                    )
                elif self.tts_engine == 'pyttsx3':
                    import pyttsx3
                    engine = pyttsx3.init()
                    engine.setProperty('rate', 160)
                    engine.say(text)
                    engine.runAndWait()
                elif self.tts_engine == 'festival':
                    subprocess.run(
                        ['festival', '--tts'],
                        input=text.encode('utf-8'),
                        capture_output=True, timeout=15
                    )
            except Exception as e:
                self.get_logger().debug(f'语音播放异常: {e}')

        threading.Thread(target=_do_speak, daemon=True).start()

    def destroy_node(self):
        self.get_logger().info('语音播报节点已停止')
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = VoiceBroadcaster()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
