package com.example.androidcarapp.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

/** iCar 暗色主题 — 深蓝黑基调 */
private val CarColorScheme = darkColorScheme(
    primary = CarAccent,
    secondary = BtnFuncBlue,
    tertiary = BtnFuncPurple,
    background = CarBackground,
    surface = CarSurface,
    onPrimary = androidx.compose.ui.graphics.Color.White,
    onSecondary = androidx.compose.ui.graphics.Color.White,
    onTertiary = androidx.compose.ui.graphics.Color.White,
    onBackground = androidx.compose.ui.graphics.Color.White,
    onSurface = androidx.compose.ui.graphics.Color.White,
    error = CarError,
    onError = androidx.compose.ui.graphics.Color.White
)

@Composable
fun AndroidCarAppTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = CarColorScheme,
        typography = Typography,
        content = content
    )
}
