# 🌐 智能送货 Web 后台

订单管理 + 小车调度，Express + SQLite，浏览器直接操作。

## 技术栈

| 技术 | 用途 |
|------|------|
| Express.js | HTTP 服务 |
| SQLite (sql.js) | 数据库，零安装 |
| 原生 HTML/CSS/JS | 前端，无框架 |

## 功能

- **📊 数据概览** — 订单统计看板
- **📦 订单管理** — 创建/查看/取消/状态跟踪
- **👥 收件人管理** — 人脸照片录入
- **🏫 楼层教室** — 教室分布可视
- **🤖 小车状态** — 小车 IP/端口配置

## 配送流程

```
创建订单 → TCP推送小车 → 小车自动导航 → 到达核验 → 送达
```

## 启动

```bash
cd web-admin
npm install
npm start        # http://localhost:3000
```

## 小车下发协议

订单通过 TCP 推送到小车 `端口 6001`，帧格式同 APP 端，type `20`：

```
$01<20><size><JSON十六进制><checksum>#
```

小车端 `delivery_server.py` 接收后调用 ROS2 Nav2 自动导航。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/orders` | 订单列表 |
| POST | `/api/orders` | 创建订单 |
| PATCH | `/api/orders/:id` | 更新状态 |
| GET | `/api/recipients` | 收件人列表 |
| POST | `/api/recipients` | 录入收件人（含人脸） |
| GET | `/api/car` | 小车配置 |
| PATCH | `/api/car` | 修改小车 IP/端口 |
| GET | `/api/robot/task` | 获取当前任务 |
