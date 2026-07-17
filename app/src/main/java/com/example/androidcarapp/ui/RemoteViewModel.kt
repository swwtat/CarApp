package com.example.androidcarapp.ui

import android.app.Application
import android.graphics.Bitmap
import android.util.Log
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.androidcarapp.camera.CameraCaptureManager
import com.example.androidcarapp.camera.CameraConfig
import com.example.androidcarapp.camera.CameraStreamClient
import com.example.androidcarapp.tcp.TcpManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * 遥控页面 ViewModel — 管理 TCP 连接状态 + 摄像头流 + 拍照
 */
class RemoteViewModel(application: Application) : AndroidViewModel(application) {

    companion object {
        private const val TAG = "RemoteViewModel"
    }

    /** TCP 连接状态 */
    val isConnected: Boolean get() = TcpManager.isConnected()

    /** 摄像头客户端 (null = 未连接或未配置) — Compose 响应式状态 */
    var cameraClient by mutableStateOf<CameraStreamClient?>(null)
        private set

    /** 拍照结果 */
    private val _captureResult = MutableStateFlow<String?>(null)
    val captureResult: StateFlow<String?> = _captureResult

    /** 传感器数据 */
    private val _sensorData = MutableStateFlow("等待数据...")
    val sensorData: StateFlow<String> = _sensorData

    init {
        // 监听 TCP 回调
        TcpManager.onMessageReceived = { msg -> _sensorData.value = msg }
        startCameraIfReady()
    }

    /** 连接/重连摄像头流 */
    fun startCameraIfReady() {
        if (!isConnected) return
        val host = TcpManager.getAddress()
        val port = CameraConfig.getPort(getApplication())
        val url = "http://$host:$port"

        stopCamera()
        cameraClient = CameraStreamClient(url).also {
            it.start()
            Log.d(TAG, "Camera stream started: url")
        }
    }

    /** 停止摄像头流 */
    fun stopCamera() {
        cameraClient?.stop()
        cameraClient = null
    }

    /** 拍照并保存到相册 */
    fun capturePhoto() {
        viewModelScope.launch {
            val bitmap: Bitmap? = try {
                cameraClient?.captureFrame()
                    ?: cameraClient?.frameFlow?.value
            } catch (e: Exception) {
                Log.e(TAG, "Capture failed: {e.message}")
                null
            }

            if (bitmap == null) {
                _captureResult.value = "拍照失败：无画面"
                return@launch
            }

            val path = withContext(Dispatchers.IO) {
                CameraCaptureManager.savePhoto(getApplication(), bitmap)
            }

            _captureResult.value = if (path != null) "已保存" else "保存失败"
            Log.d(TAG, "Photo captured: path")
        }
    }

    override fun onCleared() {
        super.onCleared()
        stopCamera()
    }
}
