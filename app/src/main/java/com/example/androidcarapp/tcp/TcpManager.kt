package com.example.androidcarapp.tcp

import android.util.Log
import kotlinx.coroutines.*
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.InetSocketAddress
import java.net.Socket

/**
 * TCP 客户端管理器 — 单例 (1:1 对应 HarmonyOS TCPClientManager)
 *
 * 负责建立/断开 TCP 连接、发送消息、接收消息、心跳保活
 */
object TcpManager {

    private const val TAG = "TcpManager"
    private const val CONNECT_TIMEOUT = 3000      // 连接超时 ms
    private const val HEARTBEAT_INTERVAL = 5000L  // 心跳间隔 ms

    private var socket: Socket? = null
    private var writer: OutputStreamWriter? = null

    private var address: String = "192.168.1.11"
    private var port: Int = 6000

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var heartbeatJob: Job? = null
    private var receiveJob: Job? = null

    /** 消息接收回调 */
    var onMessageReceived: ((String) -> Unit)? = null

    /** 连接状态变化回调 */
    var onConnectionStateChanged: ((Boolean) -> Unit)? = null

    // ─── 配置 ─────────────────────────────────────────

    fun init(address: String, port: Int) {
        Log.d(TAG, "init: address=$address, port=$port")
        this.address = address
        this.port = port
    }

    fun getAddress(): String = address
    fun getPort(): Int = port

    // ─── 连接管理 ─────────────────────────────────────

    /**
     * 建立 TCP 连接
     */
    /**
     * @return null 表示成功, 否则返回错误描述
     */
    suspend fun connect(): String? = withContext(Dispatchers.IO) {
        stopHeartbeat()
        // 如果已连接先断开
        if (isConnected()) {
            disconnectInternal()
        }

        try {
            val s = Socket()
            s.connect(InetSocketAddress(address, port), CONNECT_TIMEOUT)

            socket = s
            writer = OutputStreamWriter(s.getOutputStream(), Charsets.UTF_8)

            Log.d(TAG, "connect success: $address:$port")
            withContext(Dispatchers.Main) {
                onConnectionStateChanged?.invoke(true)
            }

            // 启动接收线程
            startReceiver()

            // 启动心跳
            startHeartbeat()

            null
        } catch (e: Exception) {
            val msg = e.message ?: "未知错误"
            Log.e(TAG, "connect failed: $msg")
            disconnectInternal()
            withContext(Dispatchers.Main) {
                onConnectionStateChanged?.invoke(false)
            }
            msg
        }
    }

    /**
     * 判断当前是否已连接
     */
    fun isConnected(): Boolean {
        val s = socket ?: return false
        return !s.isClosed && s.isConnected
    }

    // ─── 发送消息 ─────────────────────────────────────

    /**
     * 发送消息 (异步, 断连自动重连)
     */
    fun sendMessage(message: String) {
        scope.launch {
            Log.d(TAG, "sendMessage: $message")
            try {
                if (!isConnected()) {
                    Log.d(TAG, "连接已断开，尝试重连...")
                    if (connect() == null) {
                        writeMessage(message)
                    }
                } else {
                    writeMessage(message)
                }
            } catch (e: Exception) {
                Log.e(TAG, "sendMessage failed: ${e.message}")
            }
        }
    }

    private fun writeMessage(message: String) {
        try {
            writer?.apply {
                write(message)
                flush()
            }
        } catch (e: Exception) {
            Log.e(TAG, "write error: ${e.message}")
        }
    }

    // ─── 接收消息 ─────────────────────────────────────

    private fun startReceiver() {
        receiveJob?.cancel()
        receiveJob = scope.launch {
            try {
                val reader = BufferedReader(
                    InputStreamReader(socket!!.getInputStream(), Charsets.UTF_8)
                )
                val buffer = CharArray(256)
                while (isActive && isConnected()) {
                    val count = reader.read(buffer)
                    if (count == -1) break
                    val msg = String(buffer, 0, count)
                    Log.d(TAG, "receive: $msg")
                    withContext(Dispatchers.Main) {
                        onMessageReceived?.invoke(msg)
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "receiver error: ${e.message}")
            }
            Log.d(TAG, "receiver stopped")
        }
    }

    // ─── 心跳 ─────────────────────────────────────────

    private fun startHeartbeat() {
        stopHeartbeat()
        heartbeatJob = scope.launch {
            while (isActive && isConnected()) {
                delay(HEARTBEAT_INTERVAL)
                if (isConnected()) {
                    writeMessage(HEARTBEAT_MSG)
                    Log.d(TAG, "heartbeat sent")
                }
            }
        }
    }

    private fun stopHeartbeat() {
        heartbeatJob?.cancel()
        heartbeatJob = null
    }

    // ─── 断开连接 ─────────────────────────────────────

    fun disconnect() {
        scope.launch {
            disconnectInternal()
            withContext(Dispatchers.Main) {
                onConnectionStateChanged?.invoke(false)
            }
        }
    }

    private fun disconnectInternal() {
        stopHeartbeat()
        receiveJob?.cancel()
        receiveJob = null
        try {
            writer?.close()
        } catch (_: Exception) {}
        try {
            socket?.close()
        } catch (_: Exception) {}
        writer = null
        socket = null
        Log.d(TAG, "disconnected")
    }

    /** 心跳包 */
    const val HEARTBEAT_MSG = "\$010000000000#"
}
