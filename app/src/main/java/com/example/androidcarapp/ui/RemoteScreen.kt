package com.example.androidcarapp.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import android.os.Handler
import android.os.Looper
import com.example.androidcarapp.api.CarApi
import com.example.androidcarapp.api.CarDirection
import com.example.androidcarapp.tcp.TcpManager
import kotlinx.coroutines.delay

/**
 * 遥控页面 — 左半屏: 控制区 | 右半屏: 摄像头预览
 *
 * 使用 RemoteViewModel 管理摄像头流和拍照
 */
@Composable
fun RemoteScreen(
    onDisconnect: () -> Unit
) {
    val viewModel: RemoteViewModel = viewModel()
    val sensorData by viewModel.sensorData.collectAsState()

    var isConnected by remember { mutableStateOf(viewModel.isConnected) }
    // ── STOP 双击检测 ──
    var lastStopTime by remember { mutableStateOf(0L) }
    // ── 控制模式: true=摇杆, false=按键 ──
    var useRocker by remember { mutableStateOf(true) }

    // 注册 TCP 状态回调
    DisposableEffect(Unit) {
        TcpManager.onConnectionStateChanged = { connected -> isConnected = connected }
        onDispose { TcpManager.onConnectionStateChanged = null }
    }

    LaunchedEffect(Unit) { while (true) { delay(3000) } }

    val statusColor = if (isConnected) Color(0xFF00FF88) else Color(0xFFFF4444)
    val statusText = if (isConnected) "已连接" else "已断开"

    fun handleStop() {
        val now = System.currentTimeMillis()
        if (now - lastStopTime < 400) {
            CarApi.btnCtrl(CarDirection.Brake)
            Handler(Looper.getMainLooper()).postDelayed({
                CarApi.btnCtrl(CarDirection.Stop)
            }, 150)
            lastStopTime = 0
        } else {
            CarApi.btnCtrl(CarDirection.Brake)
            lastStopTime = now
        }
    }

    BoxWithConstraints(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF1A1A2E))
    ) {
        val scale = (maxHeight / 360.dp).coerceIn(0.6f, 1.2f)
        val rockerSize = (maxHeight * 1.4f).value
        val rockerShift = maxHeight * 0.35f
        val rockerUpShift = maxHeight * 0.12f

        Column(modifier = Modifier.fillMaxSize()) {
            // ═══ 顶部状态栏 ═══
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = (20 * scale).dp, vertical = (10 * scale).dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Button(
                    onClick = {
                        viewModel.stopCamera()
                        TcpManager.disconnect()
                        onDisconnect()
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF444444)),
                    shape = RoundedCornerShape((8 * scale).dp),
                    contentPadding = PaddingValues(horizontal = (16 * scale).dp, vertical = (8 * scale).dp)
                ) { Text("← 断开", fontSize = (14 * scale).sp, color = Color.White) }

                Spacer(Modifier.weight(1f))

                Row(verticalAlignment = Alignment.CenterVertically) {
                    Surface(modifier = Modifier.size((8 * scale).dp), shape = CircleShape, color = statusColor) {}
                    Spacer(Modifier.width((8 * scale).dp))
                    Text(statusText, fontSize = (15 * scale).sp, color = statusColor)
                }
            }

            // ═══ 主区域: 左控制 | 右摄像头 ═══
            Row(modifier = Modifier.fillMaxWidth().weight(1f)) {
                // ── 左半屏: 控制区 ──
                Column(
                    modifier = Modifier.weight(1f).fillMaxHeight().background(Color(0xFF141428)),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(horizontal = (12 * scale).dp, vertical = (8 * scale).dp),
                        horizontalArrangement = Arrangement.Center
                    ) {
                        Button(
                            onClick = { useRocker = true },
                            shape = RoundedCornerShape(topStart = (8 * scale).dp, bottomStart = (8 * scale).dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (useRocker) Color(0xFFE94560) else Color(0xFF333355)
                            ),
                            contentPadding = PaddingValues(horizontal = (20 * scale).dp, vertical = (8 * scale).dp)
                        ) { Text("🕹 摇杆", fontSize = (14 * scale).sp, color = Color.White) }
                        Button(
                            onClick = { useRocker = false },
                            shape = RoundedCornerShape(topEnd = (8 * scale).dp, bottomEnd = (8 * scale).dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (!useRocker) Color(0xFFE94560) else Color(0xFF333355)
                            ),
                            contentPadding = PaddingValues(horizontal = (20 * scale).dp, vertical = (8 * scale).dp)
                        ) { Text("🎮 按键", fontSize = (14 * scale).sp, color = Color.White) }
                    }

                    Spacer(Modifier.height((8 * scale).dp))

                    Box(
                        modifier = Modifier.weight(1f).fillMaxWidth(),
                        contentAlignment = Alignment.Center
                    ) {
                        if (useRocker) {
                            RockerComponent(
                                modifier = Modifier.padding(start = rockerShift, bottom = rockerUpShift),
                                rockerSize = rockerSize,
                                onTilt = { x, y -> CarApi.rockerCtrl(x, y) }
                            )
                        } else {
                            DPadControl(scale = scale, onStop = { handleStop() })
                        }
                    }

                    Button(
                        onClick = { handleStop() },
                        modifier = Modifier.width((100 * scale).dp).height((32 * scale).dp)
                            .shadow((4 * scale).dp, RoundedCornerShape((10 * scale).dp), ambientColor = Color.Red.copy(alpha = 0.5f)),
                        shape = RoundedCornerShape((10 * scale).dp),
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFFF4444))
                    ) { Text("STOP", fontSize = (14 * scale).sp, fontWeight = FontWeight.Bold, color = Color.White) }

                    Spacer(Modifier.height((8 * scale).dp))
                }

                // ── 右半屏: 摄像头预览 (集成 CameraStreamView) ──
                CameraStreamView(
                    cameraClient = viewModel.cameraClientPublic,
                    onCapture = { viewModel.capturePhoto() },
                    modifier = Modifier.weight(1f).fillMaxHeight()
                        .border(1.dp, Color(0xFF2A2A4A))
                )
            }

            // ═══ 底部: 传感器数据面板 ═══
            Row(
                modifier = Modifier.fillMaxWidth().background(Color(0xFF0D0D22))
                    .padding(horizontal = (16 * scale).dp, vertical = (10 * scale).dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("📡 ", fontSize = (13 * scale).sp)
                Text(
                    sensorData,
                    fontSize = (11 * scale).sp, color = Color(0xFF00CC66),
                    maxLines = 2, overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f)
                )
            }
        }
    }
}

@Composable
private fun DPadControl(scale: Float, onStop: () -> Unit) {
    Column(
        verticalArrangement = Arrangement.spacedBy((8 * scale).dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy((8 * scale).dp)) {
            DirectionButton("↺", "左转", Color(0xFFE94560), width = (56 * scale).toInt(), height = (56 * scale).toInt(),
                onDown = { CarApi.btnCtrl(CarDirection.LeftRotate) },
                onUp = { CarApi.btnCtrl(CarDirection.Stop) })
            DirectionButton("↑", "前进", Color(0xFFE94560), width = (56 * scale).toInt(), height = (56 * scale).toInt(),
                onDown = { CarApi.btnCtrl(CarDirection.Front) },
                onUp = { CarApi.btnCtrl(CarDirection.Stop) })
            DirectionButton("↻", "右转", Color(0xFFE94560), width = (56 * scale).toInt(), height = (56 * scale).toInt(),
                onDown = { CarApi.btnCtrl(CarDirection.RightRotate) },
                onUp = { CarApi.btnCtrl(CarDirection.Stop) })
        }
        Row(horizontalArrangement = Arrangement.spacedBy((8 * scale).dp)) {
            DirectionButton("←", "左移", Color(0xFFFF8C42), width = (56 * scale).toInt(), height = (56 * scale).toInt(),
                onDown = { CarApi.btnCtrl(CarDirection.Left) },
                onUp = { CarApi.btnCtrl(CarDirection.Stop) })
            DirectionButton("↓", "后退", Color(0xFFE94560), width = (56 * scale).toInt(), height = (56 * scale).toInt(),
                onDown = { CarApi.btnCtrl(CarDirection.After) },
                onUp = { CarApi.btnCtrl(CarDirection.Stop) })
            DirectionButton("→", "右移", Color(0xFFFF8C42), width = (56 * scale).toInt(), height = (56 * scale).toInt(),
                onDown = { CarApi.btnCtrl(CarDirection.Right) },
                onUp = { CarApi.btnCtrl(CarDirection.Stop) })
        }
    }
}

@Composable
fun ActionChip(label: String, color: Color, scale: Float = 1f, onClick: () -> Unit) {
    Button(
        onClick = onClick, shape = RoundedCornerShape((8 * scale).dp),
        colors = ButtonDefaults.buttonColors(containerColor = color),
        contentPadding = PaddingValues(horizontal = (14 * scale).dp, vertical = (8 * scale).dp)
    ) { Text(label, fontSize = (13 * scale).sp, color = Color.White) }
}
