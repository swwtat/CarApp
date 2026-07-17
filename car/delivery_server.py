#!/usr/bin/env python3
"""
送货桥接 — 单文件，零依赖（仅需 Python 3 stdlib）
部署: 复制到小车 ~/delivery/delivery_server.py，改下面的配置即可运行

工作流程:
  Web后台 → TCP:6001 (type=20) → 解析教室号 → ros2 action 导航
  → 到达后拍照 → 上报 delivered → 返回起点
"""

import socket, json, math, time, subprocess, base64, sys, os, tempfile
from urllib.request import Request, urlopen

# ═══════════════════════════════════════════════════════════
# 配置区 (修改这里)
# ═══════════════════════════════════════════════════════════

TCP_PORT = 6001
WEB_ADMIN = "http://192.168.1.100:3000"   # Web 后台地址
NAV_TIMEOUT = 180        # 导航超时秒
ARRIVE_WAIT = 10         # 到达后等待取货秒
CAMERA_DEV = 0           # 摄像头 /dev/video0
CONTAINER = ""            # 在容器内跑则为空；在宿主机跑则填容器名

# 教室 → 地图坐标 (SLAM建图后填入真实坐标，仅设3个教室做演示)
WAYPOINTS = {
    "origin": {"x": 37.00, "y": 9.40, "yaw": 0.0},   # 起点/充电桩
    "501":   {"x": 20.50, "y": 2.20, "yaw": 0.0},    # 501教室门口
    "505":   {"x": 11.95, "y": 1.50, "yaw": 0.0},    # 505教室门口
    "509":   {"x": 2.20,  "y": 0.95, "yaw": 0.0},    # 509教室门口
}

# ═══════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════

def log(msg):
    t = time.strftime("%H:%M:%S")
    print(f"[{t}] {msg}", flush=True)


def http_patch(path, data):
    """PATCH 请求上报状态"""
    try:
        body = json.dumps(data).encode()
        req = Request(f"{WEB_ADMIN}{path}", data=body,
                       headers={"Content-Type": "application/json"}, method="PATCH")
        urlopen(req, timeout=5)
        return True
    except Exception as e:
        log(f"⚠ HTTP上报失败: {e}")
        return False


def checksum(hex_str):
    """校验和: 每2hex字符一字节累加取低8位"""
    s = 0
    for i in range(0, len(hex_str), 2):
        s += int(hex_str[i:i+2], 16)
    return s % 256


def decode_frame(frame):
    """解析 $01<type(2)><size(2)><data(hex)><checksum(2)>#"""
    frame = frame.strip()
    if not (frame.startswith('$') and frame.endswith('#') and len(frame) >= 10):
        return None
    body = frame[1:-1]
    if body[:2] != "01":
        return None
    typ = body[2:4]
    data_size = (int(body[4:6], 16) - 2) * 2
    data_hex = body[6:6+data_size] if data_size > 0 else ""
    chk = body[6+data_size:8+data_size]

    if checksum(f"01{typ}{body[4:6]}{data_hex}") != int(chk, 16):
        return None

    data_raw = bytes.fromhex(data_hex).decode('utf-8') if data_hex else ""
    return {"type": typ, "data_raw": data_raw}


def capture_photo(save_path):
    """拍照保存，返回 True/False"""
    try:
        import cv2
        cap = cv2.VideoCapture(CAMERA_DEV)
        if not cap.isOpened():
            log("⚠ 无法打开摄像头")
            return False
        ret, frame = cap.read()
        cap.release()
        if ret:
            os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
            cv2.imwrite(save_path, frame)
            log(f"📷 照片已保存: {save_path}")
            return True
    except ImportError:
        log("⚠ OpenCV 未安装，跳过拍照")
    except Exception as e:
        log(f"⚠ 拍照失败: {e}")
    return False


def ros2_navigate(x, y, yaw, timeout=NAV_TIMEOUT):
    """
    调用 ROS2 CLI 导航到指定坐标
    用临时 JSON 文件传 goal，避免 shell 转义问题
    返回: True=成功到达, False=失败
    """
    log(f"🗺 导航: x={x:.2f}, y={y:.2f}, yaw={yaw:.2f}")

    # 写 goal JSON 到临时文件
    goal = {
        "pose": {
            "header": {"frame_id": "map"},
            "pose": {
                "position": {"x": x, "y": y, "z": 0.0},
                "orientation": {
                    "x": 0.0, "y": 0.0,
                    "z": math.sin(yaw / 2),
                    "w": math.cos(yaw / 2)
                }
            }
        }
    }

    try:
        # 方法1: 尝试用 --goal-file (ROS2 Humble+)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(goal, f)
            tmp = f.name

        # 直接拼 YAML 格式的命令 (最兼容)
        z = math.sin(yaw/2)
        w = math.cos(yaw/2)
        yaml_goal = "{pose: {header: {frame_id: map}, pose: {position: {x: %s, y: %s, z: 0.0}, orientation: {z: %s, w: %s}}}}" % (x, y, z, w)

        cmd = _ros2([
            "ros2", "action", "send_goal", "/navigate_to_pose",
            "nav2_msgs/action/NavigateToPose", yaml_goal
        ])

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # 轮询等待完成
        start = time.time()
        output_lines = []
        while proc.poll() is None:
            if time.time() - start > timeout:
                proc.terminate()
                os.unlink(tmp)
                log("⏰ 导航超时")
                return False
            line = proc.stdout.readline()
            if line:
                output_lines.append(line)
                if len(output_lines) % 10 == 0:
                    log(f"  ...导航中 ({int(time.time()-start)}s)")
            else:
                time.sleep(0.2)

        # 读剩余输出
        remaining = proc.stdout.read()
        full_output = "".join(output_lines) + remaining
        os.unlink(tmp)

        # 检查结果
        if proc.returncode == 0 or "SUCCEEDED" in full_output:
            log("✅ 导航到达")
            return True
        else:
            # 打印最后几行帮助 debug
            for line in output_lines[-3:]:
                log(f"  {line.rstrip()[:100]}")
            log(f"❌ 导航失败 (code={proc.returncode})")
            return False

    except FileNotFoundError:
        log("❌ ros2 命令不可用! 请先 source /opt/ros/humble/setup.bash")
        return False
    except Exception as e:
        log(f"❌ 导航异常: {e}")
        return False


def _ros2(args):
    """构建 ros2 命令，CONTAINER 非空则 docker exec"""
    if CONTAINER:
        return ["docker", "exec", CONTAINER] + args
    return args


def ros2_init_pose(x, y, yaw):
    """
    设置 AMCL 初始位姿 — 告诉小车"你在哪"
    每次 Nav2 启动后只需调用一次
    """
    z = math.sin(yaw / 2)
    w = math.cos(yaw / 2)
    yaml_pose = (
        "{header: {frame_id: map}, "
        "pose: {pose: {position: {x: %s, y: %s, z: 0.0}, "
        "orientation: {z: %s, w: %s}}}}" % (x, y, z, w)
    )
    cmd = _ros2([
        "ros2", "topic", "pub", "-1", "/initialpose",
        "geometry_msgs/msg/PoseWithCovarianceStamped", yaml_pose
    ])

    log(f"📍 设定初始位姿: x={x:.2f}, y={y:.2f}, yaw={yaw:.2f}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            log("✅ 初始位姿已设定")
            return True
        else:
            log(f"⚠ 设定位姿失败: {result.stderr.strip()[:100]}")
            return False
    except FileNotFoundError:
        log("❌ ros2/docker 命令不可用")
        return False
    except Exception as e:
        log(f"⚠ 设定位姿异常: {e}")
        return False


# ═══════════════════════════════════════════════════════════
# 订单处理
# ═══════════════════════════════════════════════════════════

def process_order(order):
    """处理单个订单：导航→拍照→上报→返回"""
    oid = order.get("order_id", "?")
    ono = order.get("order_no", "?")
    room = order.get("classroom_no", "")
    face_b64 = order.get("face_image_base64")

    log(f"\n{'='*50}")
    log(f"📦 开始配送: {ono}")
    log(f"   教室: {room}  收件人: {order.get('recipient_name','?')}")
    log(f"   物品: {order.get('package_desc','?')}")
    log(f"{'='*50}")

    # 查航点
    wp = WAYPOINTS.get(str(room))
    if not wp:
        log(f"❌ 教室 {room} 无航点坐标!")
        http_patch(f"/api/orders/{oid}", {"status": "failed"})
        return False

    origin = WAYPOINTS.get("origin", {"x": 0, "y": 0, "yaw": 0})

    # ── Step 1: 导航去教室 ──
    http_patch(f"/api/orders/{oid}", {"status": "navigating"})
    if not ros2_navigate(wp["x"], wp["y"], wp.get("yaw", 0)):
        http_patch(f"/api/orders/{oid}", {"status": "failed"})
        return False

    # ── Step 2: 到达，拍照 ──
    http_patch(f"/api/orders/{oid}", {"status": "scanning"})
    photo_path = f"/home/jetson/delivery/photos/{ono}_{int(time.time())}.jpg"
    capture_photo(photo_path)

    # ── Step 3: 等待取货 ──
    log(f"⏳ 等待 {ARRIVE_WAIT}s 让收件人取货...")
    time.sleep(ARRIVE_WAIT)

    # ── Step 4: 上报已送达 ──
    http_patch(f"/api/orders/{oid}", {"status": "delivered"})
    log(f"✅ 订单 {ono} 已送达")

    # ── Step 5: 返回起点 ──
    log("🔙 返回起点...")
    ros2_navigate(origin["x"], origin["y"], origin.get("yaw", 0))

    return True


# ═══════════════════════════════════════════════════════════
# TCP 服务器
# ═══════════════════════════════════════════════════════════

def run_server():
    log("=" * 50)
    log("🤖 送货桥接服务启动")
    log(f"   TCP 监听: 0.0.0.0:{TCP_PORT}")
    log(f"   Web 后台: {WEB_ADMIN}")
    log(f"   已加载 {len(WAYPOINTS)-1} 个教室航点")
    log("=" * 50)

    # 启动时设一次初始位姿
    origin = WAYPOINTS.get("origin", {})
    ros2_init_pose(origin.get("x", 0), origin.get("y", 0), origin.get("yaw", 0))

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", TCP_PORT))
    sock.listen(1)
    sock.settimeout(1.0)

    running = True
    buf = ""

    while running:
        try:
            conn, addr = sock.accept()
            log(f"📨 收到连接: {addr}")
            conn.settimeout(10.0)

            try:
                while True:
                    data = conn.recv(4096)
                    if not data:
                        break
                    buf += data.decode('utf-8', errors='ignore')

                    # 提取 $...# 帧
                    while True:
                        s = buf.find('$')
                        if s == -1:
                            buf = ""
                            break
                        buf = buf[s:]
                        e = buf.find('#')
                        if e == -1:
                            break
                        frame = buf[:e+1]
                        buf = buf[e+1:]

                        result = decode_frame(frame)
                        if not result:
                            continue

                        typ = result["type"]

                        if typ == "20":
                            try:
                                order = json.loads(result["data_raw"])
                                log(f"📦 收到订单: {order.get('order_no')} → {order.get('classroom_no')}教室")

                                # 回确认
                                ack = f"$0122020C7B226F6B223A317D37#"  # {"ok":1} 预编码
                                try:
                                    conn.sendall(ack.encode())
                                except:
                                    pass

                                # 处理订单（阻塞，一单一单来）
                                process_order(order)

                            except json.JSONDecodeError:
                                log(f"⚠ 无效JSON: {result['data_raw'][:80]}")

                        elif typ == "21":
                            log(f"❌ 收到取消帧 (当前不支持中途取消)")

            except socket.timeout:
                pass
            except Exception as e:
                log(f"⚠ 连接异常: {e}")
            finally:
                conn.close()

        except socket.timeout:
            continue
        except KeyboardInterrupt:
            running = False
        except Exception as e:
            log(f"⚠ TCP异常: {e}")
            time.sleep(0.5)

    sock.close()
    log("服务已停止")


if __name__ == "__main__":
    run_server()
