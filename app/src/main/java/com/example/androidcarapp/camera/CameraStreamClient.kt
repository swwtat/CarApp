package com.example.androidcarapp.camera

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.net.HttpURLConnection
import java.net.URL

/**
 * 摄像头流客户端 — 通过轮询 /capture 端点获取帧
 *
 * 使用方式:
 *   val client = CameraStreamClient("http://192.168.1.x:8080")
 *   client.start()
 *   client.frameFlow.collect { bitmap -> ... }
 *   client.stop()
 */
class CameraStreamClient(private val baseUrl: String) {

    companion object {
        private const val TAG = "CameraStreamClient"
        private const val CONNECT_TIMEOUT = 3000
        private const val READ_TIMEOUT = 5000
        private const val POLL_INTERVAL_MS = 100L  // ~10 FPS
    }

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val _frameFlow = MutableStateFlow<Bitmap?>(null)
    val frameFlow: StateFlow<Bitmap?> = _frameFlow

    private var isRunning = false

    fun start() {
        if (isRunning) return
        isRunning = true
        scope.launch { pollLoop() }
    }

    fun stop() {
        isRunning = false
        scope.cancel()
    }

    suspend fun captureFrame(): Bitmap? = withContext(Dispatchers.IO) {
        fetchFrame()
    }

    /** 主循环：定时从 /capture 拉取单帧 */
    private suspend fun pollLoop() = withContext(Dispatchers.IO) {
        while (isRunning) {
            try {
                val bitmap = fetchFrame()
                if (bitmap != null) {
                    _frameFlow.value = bitmap
                }
            } catch (e: Exception) {
                Log.w(TAG, "Poll error: ")
            }
            delay(POLL_INTERVAL_MS)
        }
    }

    /** 请求 /capture 端点，返回 JPEG 解码后的 Bitmap */
    private fun fetchFrame(): Bitmap? {
        var conn: HttpURLConnection? = null
        return try {
            val url = URL("/capture")
            conn = (url.openConnection() as HttpURLConnection).apply {
                connectTimeout = CONNECT_TIMEOUT
                readTimeout = READ_TIMEOUT
            }
            if (conn.responseCode != 200) return null
            val bitmap = BitmapFactory.decodeStream(conn.inputStream)
            if (bitmap == null) {
                Log.w(TAG, "Bitmap decode returned null, response code: ")
            }
            bitmap
        } catch (e: Exception) {
            Log.w(TAG, "fetchFrame failed: ")
            null
        } finally {
            try { conn?.disconnect() } catch (_: Exception) {}
        }
    }
}
