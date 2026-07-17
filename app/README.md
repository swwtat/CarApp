# 📱 iCar Android APP

小车遥控端 — Kotlin + Jetpack Compose，TCP 通信，摇杆/D-pad 双模式。

## 技术栈

| 技术 | 版本 |
|------|------|
| Kotlin | 2.2.10 |
| Jetpack Compose BOM | 2026.02.01 |
| Material3 | — |
| AGP | 9.2.1 |
| Min SDK | 24 |

## 功能

- **摇杆遥控** — 模拟摇杆，前后左右灵活控制
- **D-pad 方向键** — 按钮式方向控制（前进/后退/左转/右转）
- **摄像头预览** — MJPEG 实时画面
- **拍照** — 抓取单帧保存到相册

## 通信协议

TCP 连接小车 `端口 6000`，帧格式：

```
$01<type><size><data><checksum>#
```

| type | 功能 | 示例 |
|------|------|------|
| `10` | 摇杆 | `$0110040232E28A#` |
| `15` | 按钮 | `$011502000117#` |
| `63` | 追踪开 | `$016300000063#` |
| `64` | 追踪关 | — |

## 连接方法

1. 手机开热点
2. 小车连手机热点
3. APP 输入 `小车IP:6000` 点连接

> Android 模拟器无法访问物理局域网，请用真机测试。

## 构建

```bash
./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```
