# iCar Android

Android 端智能小车遥控 APP — 基于 Kotlin + Jetpack Compose 构建，通过 TCP 协议与 [iCar 智能小车](https://github.com/swwtat/CarApp) 通信，提供摇杆 + D-pad 双模式远程控制。

## 功能特性

| 模块 | 说明 |
|------|------|
| 🕹 **虚拟摇杆** | Canvas 绘制的触摸摇杆，支持拖拽调速（-100 ~ 100），带触觉反馈 |
| 🎮 **D-pad 方向键** | 8 方向按钮：前进/后退/左移/右移/左转/右转/刹车/停止 |
| 🛑 **STOP 急停** | 单击刹车，双击刹车+停止（400ms 间隔检测） |
| 🎯 追踪 / 🤖 自动 | 快捷功能按钮，发送自定义指令 |
| 📡 **传感器数据** | 实时显示小车回传的传感器信息 |
| 📱 **自适应布局** | 根据屏幕高度等比缩放，适配不同尺寸手机 |
| 🔗 **TCP 长连接** | 心跳保活 + 自动重连 |

## 项目结构

```
CarApp/
├── app/
│   ├── build.gradle.kts              # 应用级构建配置
│   └── src/main/
│       ├── AndroidManifest.xml        # 清单（横屏锁定、网络权限）
│       ├── java/com/example/androidcarapp/
│       │   ├── MainActivity.kt        # 入口 Activity，页面导航
│       │   ├── api/
│       │   │   ├── CarApi.kt          # 小车控制 API（摇杆/按钮/原始指令）
│       │   │   ├── CarDirection.kt    # 方向枚举（Stop/Front/After/Left/Right/…）
│       │   │   └── CarEncoder.kt      # 协议编码器（$01 帧格式）
│       │   ├── tcp/
│       │   │   └── TcpManager.kt      # TCP 客户端（连接/心跳/收发）
│       │   └── ui/
│       │       ├── NetworkScreen.kt   # 连接设置页（IP/端口输入）
│       │       ├── RemoteScreen.kt    # 遥控主界面
│       │       ├── RockerComponent.kt # 虚拟摇杆组件
│       │       ├── DirectionButton.kt # 方向按钮组件
│       │       └── theme/             # Material3 主题
│       └── res/                       # 资源文件（图标、字符串等）
├── gradle/
│   └── libs.versions.toml             # 版本目录（统一依赖管理）
├── build.gradle.kts                   # 项目级构建配置
├── settings.gradle.kts
└── gradlew / gradlew.bat              # Gradle Wrapper
```

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

### 网络拓扑

```
┌──────────────┐    TCP (6000)    ┌──────────────────┐
│  Android 手机 │ ←────────────── │  iCar 智能小车      │
│  (热点模式)    │   WiFi 热点     │  (192.168.43.44)  │
│  192.168.43.x │ ──────────────→ │  Jetson Orin Nano │
└──────────────┘                 └──────────────────┘
```

1. **手机开启热点**（子网 `192.168.43.0/24`）
2. **小车连接手机热点**（Hi3861 WiFi 模块，STA 模式）
3. **启动小车 TCP 服务端**（监听端口 `6000`）
4. **APP 连接** → 输入 `192.168.43.44:6000`，点击连接

> ⚠️ **注意**：Android 模拟器使用 `10.0.2.x` 虚拟网络，无法访问物理局域网。测试 TCP 连接请使用**真机**。

## 界面说明

### 连接页 (NetworkScreen)

输入小车 IP 地址和端口号，点击连接。连接失败时会显示详细错误信息。

### 遥控页 (RemoteScreen)

```
┌──────────────────────────────────────────────────┐
│  ← 断开                          ● 已连接         │
├────────────────────┬─────────────────────────────┤
│                    │   🎯追踪    🤖自动           │
│                    │                             │
│     🕹 摇杆        │      [ STOP ]               │
│    (左下角)        │                             │
│                    │   ↺左转   ↑前进   ↻右转     │
│                    │   ←左移   ↓后退   →右移     │
├────────────────────┴─────────────────────────────┤
│  📡 传感器数据...                                  │
└──────────────────────────────────────────────────┘
```

- **左侧**：虚拟摇杆，触摸拖拽控制小车速度与方向
- **右侧**：D-pad 方向键 + STOP 按钮 + 功能按钮
- **底部**：实时传感器数据栏

## 方向定义

| 枚举 | 值 | 说明 |
|------|----|------|
| `Stop` | 0 | 停止 |
| `Front` | 1 | 前进 |
| `After` | 2 | 后退 |
| `Left` | 3 | 左移 |
| `Right` | 4 | 右移 |
| `LeftRotate` | 5 | 左旋转 |
| `RightRotate` | 6 | 右旋转 |
| `Brake` | 7 | 刹车 |

## 许可证

MIT License

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
