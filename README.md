# iCar Android

Android 端智能小车遥控 APP — 基于 Kotlin + Jetpack Compose 构建，通过 TCP 协议与小车通信，提供摇杆 + D-pad 双模式远程控制。


## 技术栈

| 技术 | 版本 |
|------|------|
| Kotlin | 2.2.10 |
| Jetpack Compose (BOM) | 2026.02.01 |
| Material3 | — |
| AGP | 9.2.1 |
| Min SDK | 24 (Android 7.0) |
| Target SDK | 36 |

## 通信协议

与小车 TCP 服务端通信，帧格式：

```
$01<type><size><data><checksum>#
```

| 字段 | 长度 | 说明 |
|------|------|------|
| `$` | 1 | 帧头 |
| `01` | 2 | 协议版本 |
| `type` | 2 | 指令类型（`10`=摇杆, `15`=按钮, `63`=追踪, `64`=自动） |
| `size` | 2 | 数据区长度（十六进制） |
| `data` | N | 数据载荷（十六进制大写） |
| `checksum` | 2 | 校验和（type+size+data 各字节累加取低 8 位） |
| `#` | 1 | 帧尾 |

**示例指令：**
- 前进（按钮）：`$011502000117#`
- 摇杆（x=50, y=-30）：`$0110040232E28A#`
- 启动追踪：`$016300000063#`

## 快速开始

### 环境要求

- Android Studio Hedgehog (2024.1+) 或 Ladybug (2025.1+)
- JDK 11+
- Android SDK 36

### 构建 & 运行

```bash
# 克隆项目
git clone https://github.com/swwtat/CarApp.git
cd CarApp

# 编译 Debug APK
./gradlew assembleDebug

# 安装到已连接设备
adb install app/build/outputs/apk/debug/app-debug.apk
```

或在 Android Studio 中直接打开项目 → Run。


1. **手机开启热点**
2. **小车连接手机热点**
3. **APP 连接** → 输入 `当前小车ip:6000`，点击连接

> ⚠️ **注意**：Android 模拟器使用 `10.0.2.x` 虚拟网络，无法访问物理局域网。测试 TCP 连接请使用**真机**。

## 界面说明

### 连接页 (NetworkScreen)

输入小车 IP 地址和端口号，点击连接。连接失败时会显示详细错误信息。


