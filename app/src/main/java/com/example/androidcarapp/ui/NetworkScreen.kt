package com.example.androidcarapp.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.androidcarapp.tcp.TcpManager
import kotlinx.coroutines.launch

/**
 * 网络设置页面 (1:1 对应 HarmonyOS NetworkSettings)
 *
 * 输入小车 IP 和端口 → 点击连接 → 成功后回调 onConnected
 */
@Composable
fun NetworkScreen(
    onConnected: () -> Unit
) {
    var ip by remember { mutableStateOf(TcpManager.getAddress()) }
    var portText by remember { mutableStateOf(TcpManager.getPort().toString()) }
    var isConnecting by remember { mutableStateOf(false) }
    var errorMsg by remember { mutableStateOf<String?>(null) }

    val scope = rememberCoroutineScope()

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF1A1A2E)),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.widthIn(max = 480.dp)
        ) {
            // ── 标题区域 ──
            Text(
                text = "iCar 智能小车",
                fontSize = 32.sp,
                color = Color.White,
                fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = "网络连接设置",
                fontSize = 18.sp,
                color = Color(0xFFAAAAAA)
            )

            Spacer(Modifier.height(30.dp))

            // ── 输入区域 ──
            Column(
                modifier = Modifier
                    .fillMaxWidth(0.9f)
                    .background(Color(0xFF16213E), RoundedCornerShape(16.dp))
                    .padding(20.dp)
            ) {
                // IP 地址
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        "IP 地址",
                        fontSize = 18.sp,
                        color = Color.White,
                        modifier = Modifier.width(100.dp)
                    )
                    OutlinedTextField(
                        value = ip,
                        onValueChange = { ip = it; errorMsg = null },
                        singleLine = true,
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White,
                            focusedContainerColor = Color(0xFF2D2D44),
                            unfocusedContainerColor = Color(0xFF2D2D44),
                            focusedBorderColor = Color(0xFF4A4A8E),
                            unfocusedBorderColor = Color(0xFF3A3A5E)
                        ),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.weight(1f)
                    )
                }
                Spacer(Modifier.height(16.dp))
                // 端口号
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        "端  口",
                        fontSize = 18.sp,
                        color = Color.White,
                        modifier = Modifier.width(100.dp)
                    )
                    OutlinedTextField(
                        value = portText,
                        onValueChange = { portText = it; errorMsg = null },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White,
                            focusedContainerColor = Color(0xFF2D2D44),
                            unfocusedContainerColor = Color(0xFF2D2D44),
                            focusedBorderColor = Color(0xFF4A4A8E),
                            unfocusedBorderColor = Color(0xFF3A3A5E)
                        ),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.weight(1f)
                    )
                }
            }

            Spacer(Modifier.height(30.dp))

            // ── 连接按钮 ──
            Button(
                onClick = {
                    errorMsg = null
                    isConnecting = true
                    scope.launch {
                        val port = portText.toIntOrNull()
                        if (port == null || port !in 1..65535) {
                            errorMsg = "端口号无效 (1-65535)"
                            isConnecting = false
                            return@launch
                        }
                        if (ip.isBlank()) {
                            errorMsg = "IP 地址不能为空"
                            isConnecting = false
                            return@launch
                        }

                        TcpManager.init(ip, port)
                        val err = TcpManager.connect()
                        isConnecting = false
                        if (err == null) {
                            onConnected()
                        } else {
                            errorMsg = "连接失败: $err"
                        }
                    }
                },
                modifier = Modifier
                    .width(300.dp)
                    .height(50.dp),
                shape = RoundedCornerShape(25.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = Color(0xFFE94560),
                    disabledContainerColor = Color(0xFF884455)
                ),
                enabled = !isConnecting
            ) {
                if (isConnecting) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(22.dp),
                        color = Color.White,
                        strokeWidth = 2.dp
                    )
                    Spacer(Modifier.width(10.dp))
                }
                Text(
                    if (isConnecting) "连接中..." else "连 接 小 车",
                    fontSize = 20.sp,
                    color = Color.White
                )
            }

            // ── 错误提示 ──
            if (errorMsg != null) {
                Spacer(Modifier.height(12.dp))
                Text(errorMsg!!, fontSize = 14.sp, color = Color(0xFFFF6B6B))
            }

            Spacer(Modifier.height(20.dp))
            Text(
                "请确保手机与小车在同一局域网",
                fontSize = 14.sp,
                color = Color(0xFF666666)
            )
        }
    }
}
