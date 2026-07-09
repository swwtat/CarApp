package com.example.androidcarapp.ui

import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * 方向控制按钮 (1:1 对应 HarmonyOS DirectionButton)
 *
 * 按下 → 缩放动画 + 振动 + 发送方向指令
 * 松开 → 归位动画 + 发送停止指令
 */
@Composable
fun DirectionButton(
    icon: String,
    label: String = "",
    btnColor: Color = Color(0xFFE94560),
    pressedColor: Color = Color(0xFFFF6B81),
    width: Int = 70,
    height: Int = 70,
    onDown: () -> Unit = {},
    onUp: () -> Unit = {}
) {
    var isPressed by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(
        targetValue = if (isPressed) 0.9f else 1.0f,
        animationSpec = tween(durationMillis = 80),
        label = "pressScale"
    )

    val context = LocalContext.current
    val vibrator: Vibrator? = remember {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val vm = context.getSystemService(VibratorManager::class.java)
            vm?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(android.content.Context.VIBRATOR_SERVICE) as? Vibrator
        }
    }

    fun triggerHaptic() {
        try {
            vibrator?.vibrate(
                VibrationEffect.createOneShot(12, VibrationEffect.DEFAULT_AMPLITUDE)
            )
        } catch (_: Exception) {}
    }

    Button(
        onClick = { /* 由 pointerInput 处理 */ },
        modifier = Modifier
            .width(width.dp)
            .height(height.dp)
            .scale(scale)
            .shadow(
                elevation = if (isPressed) 2.dp else 4.dp,
                shape = RoundedCornerShape(12.dp)
            )
            .pointerInput(Unit) {
                awaitPointerEventScope {
                    while (true) {
                        val event = awaitPointerEvent()
                        when {
                            event.changes.any { it.pressed } -> {
                                if (!isPressed) {
                                    isPressed = true
                                    triggerHaptic()
                                    onDown()
                                }
                            }
                            else -> {
                                if (isPressed) {
                                    isPressed = false
                                    onUp()
                                }
                            }
                        }
                    }
                }
            },
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = if (isPressed) pressedColor else btnColor
        ),
        contentPadding = PaddingValues(0.dp)
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                text = icon,
                fontSize = 26.sp,
                color = Color.White
            )
            if (label.isNotEmpty()) {
                Text(
                    text = label,
                    fontSize = 11.sp,
                    color = Color(0xFFDDDDDD)
                )
            }
        }
    }
}
