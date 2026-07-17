# 🤖 小车送货桥接

轻量级 TCP → ROS2 桥接脚本，接收 Web 后台订单并调用 Nav2 自主导航。

## 文件

| 文件 | 说明 |
|------|------|
| `delivery_server.py` | 主程序 — TCP Server 端口 6001，收订单 → 调 ros2 导航 → 上报状态 |
| `delivery-bridge.service` | systemd 自启配置 |

## 工作原理

```
Web后台 TCP:6001 (type=20) → 解析教室号 → ros2 action send_goal → Nav2 导航
→ 到达 → 拍照 → HTTP 上报 delivered → 返回起点
```

## 部署

```bash
# 容器内
docker exec -it a0e6 bash
python3 /root/delivery_server.py
```

## 配置

编辑脚本顶部的配置区：

- `TCP_PORT` — 监听端口
- `WEB_ADMIN` — Web 后台地址
- `CONTAINER` — Nav2 容器名（容器内跑则留空）
- `WAYPOINTS` — 教室坐标映射表

## 前提

- Nav2 导航栈已启动
- 地图已加载
- 教室航点坐标已标定
