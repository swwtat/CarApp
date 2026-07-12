package com.example.androidcarapp.ui

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.androidcarapp.camera.CameraStreamClient

/**
 * 摄像头预览 + 拍照组件
 *
 * @param cameraClient 已连接的摄像头流客户端，null 表示未连接
 * @param onCapture 拍照回调
 * @param modifier 布局修饰
 */
@Composable
fun CameraStreamView(
    cameraClient: CameraStreamClient?,
    onCapture: (Bitmap) -> Unit,
    modifier: Modifier = Modifier
) {
    val frame by (cameraClient?.frameFlow?.collectAsState() ?: remember { mutableStateOf(null) })
    var lastCaptureResult by remember { mutableStateOf<String?>(null) }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFF0A0A1A))
    ) {
        if (cameraClient == null) {
            // 未连接状态
            Column(
                modifier = Modifier.align(Alignment.Center),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text("📷", fontSize = 48.sp)
                Spacer(Modifier.height(8.dp))
                Text("摄像头", fontSize = 16.sp, color = Color(0xFF555577))
                Text("待连接", fontSize = 12.sp, color = Color(0xFF444466))
            }
        } else if (frame != null) {
            // 预览画面
            Image(
                bitmap = frame!!.asImageBitmap(),
                contentDescription = "摄像头预览",
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Fit
            )

            // 拍照按钮（右下角悬浮）
            Button(
                onClick = {
                    frame?.let { onCapture(it) }
                    lastCaptureResult = "已保存"
                },
                modifier = Modifier
                    .align(Alignment.BottomEnd)
                    .padding(12.dp)
                    .size(56.dp),
                shape = RoundedCornerShape(28.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = Color(0xFFE94560)
                ),
                contentPadding = PaddingValues(0.dp)
            ) {
                Text("📸", fontSize = 24.sp)
            }

            // 拍照结果提示
            if (lastCaptureResult != null) {
                Text(
                    lastCaptureResult!!,
                    color = Color(0xFF00FF88),
                    fontSize = 12.sp,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(bottom = 76.dp)
                )
            }
        } else {
            // 连接中（等待首帧）
            Column(
                modifier = Modifier.align(Alignment.Center),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                CircularProgressIndicator(color = Color(0xFFE94560), modifier = Modifier.size(32.dp))
                Spacer(Modifier.height(12.dp))
                Text("等待画面...", fontSize = 14.sp, color = Color(0xFF888888))
            }
        }
    }
}
