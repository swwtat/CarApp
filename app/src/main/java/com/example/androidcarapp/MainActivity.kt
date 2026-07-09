package com.example.androidcarapp

import android.content.pm.ActivityInfo
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.*
import com.example.androidcarapp.ui.NetworkScreen
import com.example.androidcarapp.ui.RemoteScreen

/**
 * 应用入口 — 管理 NetworkScreen ↔ RemoteScreen 导航
 *
 * 横屏锁定 + 暗色主题
 */
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 强制横屏
        requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE

        enableEdgeToEdge()
        setContent {
            var currentScreen by remember { mutableStateOf<Screen>(Screen.Remote) }

            when (currentScreen) {
                Screen.Network -> NetworkScreen(
                    onConnected = { currentScreen = Screen.Remote }
                )
                Screen.Remote -> RemoteScreen(
                    onDisconnect = { currentScreen = Screen.Network }
                )
            }
        }
    }
}

/** 页面枚举 */
private enum class Screen {
    Network,
    Remote
}
