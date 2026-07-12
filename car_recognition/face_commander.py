"""
小车人脸识别通信模块
====================
Web 管理端 → 小车 TCP 发送人脸扫描指令
小车端 → Web 管理端接收识别结果

协议 (type=20, 与 carEncoder.js 一致):
  下发指令: $0120<size><json_hex><checksum>#
  其中 JSON 格式:
    {
      "action": "face_scan",
      "order_id": 1,
      "recipient_name": "张明",
      "face_image_base64": "...",
      "classroom_no": "501"
    }

  接收结果: HTTP POST (小车 → Web) 或 TCP 回包

用法 (从 Node.js 调用):
  node face_commander.js
"""

import socket
import json
import time
from pathlib import Path

# ── 配置 ──
CAR_HOST = '192.168.1.11'
CAR_FACE_PORT = 6001         # 小车人脸识别 TCP 端口
WEB_CALLBACK_PORT = 3000     # Web 管理端回调地址
TIMEOUT = 10


def number_to_hex(num, length):
    """数字转十六进制字符串"""
    return format(num, f'0{length}x').upper()


def calc_checksum(data):
    """计算校验和 (每 2 字符累加取低 8 位)"""
    total = 0
    for i in range(0, len(data), 2):
        total += int(data[i:i+2], 16)
    return total % 256


def string_to_hex(s):
    """字符串转十六进制"""
    return s.encode('utf-8').hex().upper()


def build_face_scan_frame(order_id, recipient_name, face_image_base64, classroom_no):
    """
    构建人脸扫描 TCP 帧

    Args:
        order_id: 订单 ID
        recipient_name: 收件人姓名
        face_image_base64: 目标人脸 base64 JPEG
        classroom_no: 教室号

    Returns:
        bytes: 完整 TCP 帧
    """
    payload = {
        'action': 'face_scan',
        'order_id': order_id,
        'recipient_name': recipient_name,
        'face_image_base64': face_image_base64,
        'classroom_no': classroom_no,
        'timestamp': time.time(),
    }
    json_str = json.dumps(payload, ensure_ascii=False)
    data_hex = string_to_hex(json_str)

    # 帧格式: $01<type=20><size><data_hex><checksum>#
    frame_type = '20'
    # size = data 总长度 + 校验和 (2 字符)
    size = number_to_hex(len(data_hex) // 2 + 2, 2)
    prefix = f'01{frame_type}{size}{data_hex}'
    cs = number_to_hex(calc_checksum(prefix), 2)
    frame = f'${prefix}{cs}#'

    return frame.encode('utf-8')


def send_face_scan(host, port, order_id, recipient_name, face_image_base64, classroom_no):
    """
    发送人脸扫描指令到小车

    Returns:
        dict: {'ok': bool, 'error': str | None}
    """
    frame = build_face_scan_frame(order_id, recipient_name, face_image_base64, classroom_no)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        sock.connect((host, port))
        sock.sendall(frame)

        # 等待确认
        response = sock.recv(1024)
        sock.close()

        return {
            'ok': True,
            'response': response.decode('utf-8', errors='ignore'),
            'frame_size': len(frame),
        }
    except socket.timeout:
        return {'ok': False, 'error': f'TCP 连接超时 ({host}:{port})'}
    except ConnectionRefusedError:
        return {'ok': False, 'error': f'TCP 连接被拒绝 ({host}:{port})'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# ── 测试入口 ──
if __name__ == '__main__':
    # 模拟发送扫描指令
    import sys

    if len(sys.argv) < 2:
        print("用法: python face_commander.py <image_path> [recipient_name] [classroom_no]")
        sys.exit(1)

    img_path = Path(sys.argv[1])
    if not img_path.exists():
        print(f"文件不存在: {img_path}")
        sys.exit(1)

    import base64
    with open(img_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode('utf-8')

    recipient = sys.argv[2] if len(sys.argv) > 2 else '张明'
    classroom = sys.argv[3] if len(sys.argv) > 3 else '501'

    print(f"发送人脸扫描指令...")
    print(f"  目标: {recipient}")
    print(f"  教室: {classroom}")
    print(f"  人脸: {img_path.name} ({len(img_b64)} bytes base64)")

    result = send_face_scan(
        CAR_HOST, CAR_FACE_PORT,
        order_id=1,
        recipient_name=recipient,
        face_image_base64=img_b64,
        classroom_no=classroom,
    )

    if result['ok']:
        print(f"  发送成功! 帧大小: {result['frame_size']} bytes")
        print(f"  响应: {result['response']}")
    else:
        print(f"  发送失败: {result['error']}")
