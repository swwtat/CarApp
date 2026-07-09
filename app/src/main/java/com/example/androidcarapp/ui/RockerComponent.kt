package com.example.androidcarapp.ui

import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlin.math.*

/**
 * 摇杆组件 — Canvas + 触摸拖拽 (1:1 对应 HarmonyOS RockerComponent)
 *
 * 使用方式:
 *   RockerComponent(
 *     rockerSize = 240.dp,
 *     onTilt = { x, y -> carApi.rockerCtrl(x, y) }
 *   )
 */
@Composable
fun RockerComponent(
    modifier: Modifier = Modifier,
    rockerSize: Float = 260f,
    backgroundColor: Color = Color(0xFF1A1A4E),
    strokeColor: Color = Color(0xFF4A4A8E),
    thumbColor: Color = Color(0xFFE94560),
    thumbHighlight: Color = Color(0xFFFF6B81),
    thumbRadius: Float = rockerSize * 0.15f,
    deadZone: Float = rockerSize * 0.03f,
    sensitivity: Float = 1.0f,
    onTilt: (x: Float, y: Float) -> Unit = { _, _ -> }
) {
    // 拇指球偏移 (相对圆心)
    var thumbOffsetX by remember { mutableStateOf(0f) }
    var thumbOffsetY by remember { mutableStateOf(0f) }
    var lastSendTime by remember { mutableStateOf(0L) }
    var isDragging by remember { mutableStateOf(false) }

    val centerX = rockerSize / 2f
    val centerY = rockerSize / 2f
    val maxRadius = min(rockerSize, rockerSize) / 2f - thumbRadius - 4f

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

    /** 触觉反馈 */
    fun triggerHaptic() {
        try {
            vibrator?.vibrate(
                VibrationEffect.createOneShot(12, VibrationEffect.DEFAULT_AMPLITUDE)
            )
        } catch (_: Exception) {}
    }

    /** 偏移归一化为速度值 (-100~100) */
    fun normalizeOutput(dx: Float, dy: Float): Pair<Float, Float> {
        val dist = sqrt(dx * dx + dy * dy)
        if (dist <= deadZone) return 0f to 0f
        val effectiveDist = dist.coerceAtMost(maxRadius)
        val normalized = (effectiveDist - deadZone) / (maxRadius - deadZone)
        val speed = (normalized * 100f * sensitivity)
        val angle = atan2(dy, dx)
        val sx = round(cos(angle) * speed)
        val sy = -round(sin(angle) * speed)  // Y轴取反: 屏幕Y向下, 小车前进需正Y
        return sx to sy
    }

    Canvas(
        modifier = modifier
            .size(rockerSize.dp)
            .pointerInput(Unit) {
                awaitPointerEventScope {
                    while (true) {
                        val event = awaitPointerEvent()
                        when {
                            event.changes.any { it.pressed } -> {
                                val pos = event.changes.firstOrNull()?.position ?: continue
                                val dx = pos.x - centerX
                                val dy = pos.y - centerY

                                if (!isDragging) {
                                    isDragging = true
                                    triggerHaptic()
                                }

                                // 约束在背景圆内
                                val dist = sqrt(dx * dx + dy * dy)
                                val (cdx, cdy) = if (dist > maxRadius) {
                                    dx * (maxRadius / dist) to dy * (maxRadius / dist)
                                } else {
                                    dx to dy
                                }

                                thumbOffsetX = cdx
                                thumbOffsetY = cdy

                                // 50ms 节流发送
                                val now = System.currentTimeMillis()
                                if (now - lastSendTime >= 50) {
                                    lastSendTime = now
                                    val (sx, sy) = normalizeOutput(cdx, cdy)
                                    onTilt(sx, sy)
                                }
                            }
                            else -> {
                                // Up / Cancel — 回中
                                isDragging = false
                                thumbOffsetX = 0f
                                thumbOffsetY = 0f
                                onTilt(0f, 0f)
                            }
                        }
                    }
                }
            }
    ) {
        drawBackground(
            centerX, centerY, maxRadius,
            backgroundColor, strokeColor
        )
        drawThumb(
            centerX + thumbOffsetX,
            centerY + thumbOffsetY,
            thumbRadius, thumbColor, thumbHighlight
        )
    }
}

// ─── 绘制函数 (1:1 对应 RockerDrawUtils) ───────────────

private fun DrawScope.drawBackground(
    cx: Float, cy: Float, outerRadius: Float,
    bgColor: Color, strokeColor: Color
) {
    // 外层背景圆
    drawCircle(bgColor, outerRadius, Offset(cx, cy))
    drawCircle(strokeColor, outerRadius, Offset(cx, cy),
        style = Stroke(width = 3f))

    // 33% 参考环 (虚线)
    drawCircle(
        Color.White.copy(alpha = 0.12f), outerRadius * 0.33f, Offset(cx, cy),
        style = Stroke(width = 1f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 8f)))
    )
    // 66% 参考环 (虚线)
    drawCircle(
        Color.White.copy(alpha = 0.12f), outerRadius * 0.66f, Offset(cx, cy),
        style = Stroke(width = 1f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 8f)))
    )

    // 十字参考线
    val lineColor = Color.White.copy(alpha = 0.08f)
    drawLine(lineColor, Offset(cx - outerRadius, cy), Offset(cx + outerRadius, cy), 1f)
    drawLine(lineColor, Offset(cx, cy - outerRadius), Offset(cx, cy + outerRadius), 1f)
}

private fun DrawScope.drawThumb(
    tx: Float, ty: Float, radius: Float,
    thumbColor: Color, highlight: Color
) {
    // 外发光
    drawCircle(
        Color(0x33E94560), radius + 6f, Offset(tx, ty)
    )

    // 球体 (径向渐变模拟 3D)
    val gradient = Brush.radialGradient(
        colors = listOf(highlight, thumbColor, Color(0xFF8B1A2B)),
        center = Offset(tx - radius * 0.3f, ty - radius * 0.3f),
        radius = radius
    )
    drawCircle(gradient, radius, Offset(tx, ty))

    // 边框
    drawCircle(highlight, radius, Offset(tx, ty),
        style = Stroke(width = 2f))
}
