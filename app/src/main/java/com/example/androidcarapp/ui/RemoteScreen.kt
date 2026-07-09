package com.example.androidcarapp.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import android.os.Handler
import android.os.Looper
import com.example.androidcarapp.api.CarApi
import com.example.androidcarapp.api.CarDirection
import com.example.androidcarapp.tcp.TcpManager
import kotlinx.coroutines.delay

/**
 * 遥控页面 — 摇杆 + 方向按钮混合控制 (1:1 对应 HarmonyOS RemoteControl)
 *
 * 布局: 左侧摇杆 | 右侧操作面板
 */
@Composable
fun RemoteScreen(
    onDisconnect: () -> Unit
) {
    // ── 连接状态 ──
    var isConnected by remember { mutableStateOf(true) }
    // ── 传感器数据 ──
    var sensorData by remember { mutableStateOf("等待数据...") }
    // ── STOP 双击检测 ──
    var lastStopTime by remember { mutableStateOf(0L) }

    // 注册 TCP 回调
    DisposableEffect(Unit) {
        TcpManager.onMessageReceived = { msg ->
            sensorData = msg
        }
        TcpManager.onConnectionStateChanged = { connected ->
            isConnected = connected
        }
        onDispose {
            TcpManager.onMessageReceived = null
            TcpManager.onConnectionStateChanged = null
        }
    }

    // 每 3 秒检测连接状态
    LaunchedEffect(Unit) {
        while (true) {
            delay(3000)
            // TcpManager.onConnectionStateChanged 已在上层更新
        }
    }

    val statusColor = if (isConnected) Color(0xFF00FF88) else Color(0xFFFF4444)
    val statusText = if (isConnected) "已连接" else "已断开"

    /**
     * STOP 按钮 — 双击刹车+停止
     */
    fun handleStop() {
        val now = System.currentTimeMillis()
        if (now - lastStopTime < 400) {
            // 双击: 刹车 + 延迟停止
            CarApi.btnCtrl(CarDirection.Brake)
            Handler(Looper.getMainLooper()).postDelayed({
                CarApi.btnCtrl(CarDirection.Stop)
            }, 150)
            lastStopTime = 0
        } else {
            // 单击: 仅刹车
            CarApi.btnCtrl(CarDirection.Brake)
            lastStopTime = now
        }
    }

    // 根据屏幕高度自适应缩放
    BoxWithConstraints(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF1A1A2E))
    ) {
        // 设计基准: 360dp 横屏高度, 低于此值等比缩小
        val scale = (maxHeight / 360.dp).coerceIn(0.6f, 1.0f)
        // 摇杆大小取屏幕高度的 ~50%, 控制在左下角 ~1/4 屏占比
        val rockerSize = (maxHeight * 0.5f).value

        Column(modifier = Modifier.fillMaxSize()) {
            // ═══ 顶部状态栏 ═══
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = (20 * scale).dp, vertical = (12 * scale).dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Button(
                onClick = {
                    TcpManager.disconnect()
                    onDisconnect()
                },
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF444444)),
                shape = RoundedCornerShape((8 * scale).dp),
                contentPadding = PaddingValues(horizontal = (16 * scale).dp, vertical = (8 * scale).dp)
            ) {
                Text("← 断开", fontSize = (14 * scale).sp, color = Color.White)
            }

            Spacer(Modifier.weight(1f))

            // 状态指示灯
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size((8 * scale).dp),
                    shape = CircleShape,
                    color = statusColor
                ) {}
                Spacer(Modifier.width((8 * scale).dp))
                Text(statusText, fontSize = (15 * scale).sp, color = statusColor)
            }
        }

        // ═══ 主控制区 ═══
        // 摇杆放在左下角, 约占屏幕 1/4; 右侧为 D-pad 操作面板
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
        ) {
            // ── 左下角: 摇杆 (左半屏, 底部对齐) ──
            Column(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxHeight(),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Bottom
            ) {
                RockerComponent(
                    rockerSize = rockerSize,
                    onTilt = { x, y -> CarApi.rockerCtrl(x, y) }
                )
                Spacer(Modifier.height((4 * scale).dp))
                Text("摇杆控制", fontSize = (12 * scale).sp, color = Color(0xFF888888))
                Spacer(Modifier.height((12 * scale).dp))
            }

            // ── 右侧: 操作面板 (右半屏, 居中) ──
            Column(
                modifier = Modifier.weight(1f),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                // 功能按钮行
                Row(horizontalArrangement = Arrangement.spacedBy((12 * scale).dp)) {
                    ActionChip("🎯 追踪", Color(0xFF4A90D9), scale) {
                        CarApi.send("\$016300000063#")
                    }
                    ActionChip("🤖 自动", Color(0xFF9B59B6), scale) {
                        CarApi.send("\$016400000064#")
                    }
                }

                Spacer(Modifier.height((14 * scale).dp))

                // STOP 大按钮
                Button(
                    onClick = { handleStop() },
                    modifier = Modifier
                        .width((150 * scale).dp)
                        .height((52 * scale).dp)
                        .shadow((6 * scale).dp, RoundedCornerShape((14 * scale).dp), ambientColor = Color.Red.copy(alpha = 0.5f)),
                    shape = RoundedCornerShape((14 * scale).dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFFF4444))
                ) {
                    Text("STOP", fontSize = (20 * scale).sp, fontWeight = FontWeight.Bold, color = Color.White)
                }

                Spacer(Modifier.height((14 * scale).dp))

                // ── 迷你 D-pad ──
                Column(verticalArrangement = Arrangement.spacedBy((8 * scale).dp)) {
                    // 上行: 左转 前进 右转
                    Row(horizontalArrangement = Arrangement.spacedBy((8 * scale).dp)) {
                        DirectionButton("↺", "左转", Color(0xFFE94560), width = (70 * scale).toInt(), height = (70 * scale).toInt(),
                            onDown = { CarApi.btnCtrl(CarDirection.LeftRotate) },
                            onUp = { CarApi.btnCtrl(CarDirection.Stop) })
                        DirectionButton("↑", "前进", Color(0xFFE94560), width = (70 * scale).toInt(), height = (70 * scale).toInt(),
                            onDown = { CarApi.btnCtrl(CarDirection.Front) },
                            onUp = { CarApi.btnCtrl(CarDirection.Stop) })
                        DirectionButton("↻", "右转", Color(0xFFE94560), width = (70 * scale).toInt(), height = (70 * scale).toInt(),
                            onDown = { CarApi.btnCtrl(CarDirection.RightRotate) },
                            onUp = { CarApi.btnCtrl(CarDirection.Stop) })
                    }
                    // 下行: 左移 后退 右移
                    Row(horizontalArrangement = Arrangement.spacedBy((8 * scale).dp)) {
                        DirectionButton("←", "左移", Color(0xFFFF8C42), width = (70 * scale).toInt(), height = (70 * scale).toInt(),
                            onDown = { CarApi.btnCtrl(CarDirection.Left) },
                            onUp = { CarApi.btnCtrl(CarDirection.Stop) })
                        DirectionButton("↓", "后退", Color(0xFFE94560), width = (70 * scale).toInt(), height = (70 * scale).toInt(),
                            onDown = { CarApi.btnCtrl(CarDirection.After) },
                            onUp = { CarApi.btnCtrl(CarDirection.Stop) })
                        DirectionButton("→", "右移", Color(0xFFFF8C42), width = (70 * scale).toInt(), height = (70 * scale).toInt(),
                            onDown = { CarApi.btnCtrl(CarDirection.Right) },
                            onUp = { CarApi.btnCtrl(CarDirection.Stop) })
                    }
                }
            }
        }

        // ═══ 底部: 传感器数据面板 ═══
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(Color(0xFF0D0D22))
                .padding(horizontal = (16 * scale).dp, vertical = (12 * scale).dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("📡 ", fontSize = (13 * scale).sp)
            Text(
                sensorData,
                fontSize = (12 * scale).sp,
                color = Color(0xFF00CC66),
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f)
            )
        }
        } // end Column
    } // end BoxWithConstraints
}

/**
 * 功能芯片按钮
 */
@Composable
fun ActionChip(label: String, color: Color, scale: Float = 1f, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        shape = RoundedCornerShape((8 * scale).dp),
        colors = ButtonDefaults.buttonColors(containerColor = color),
        contentPadding = PaddingValues(horizontal = (14 * scale).dp, vertical = (8 * scale).dp)
    ) {
        Text(label, fontSize = (13 * scale).sp, color = Color.White)
    }
}
