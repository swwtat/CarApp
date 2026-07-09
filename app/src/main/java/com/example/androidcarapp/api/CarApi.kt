package com.example.androidcarapp.api

import com.example.androidcarapp.tcp.TcpManager

/**
 * 小车控制 API — 封装 TCP 发送逻辑 (1:1 对应 HarmonyOS CarApi)
 */
object CarApi {

    /**
     * 按钮控制小车方向
     */
    fun btnCtrl(d: CarDirection) {
        send(CarEncoder.buttonEncode(d))
    }

    /**
     * 摇杆控制 (speedX, speedY: -100 ~ 100)
     */
    fun rockerCtrl(speedX: Float, speedY: Float) {
        send(CarEncoder.ctrlEncode(speedX, speedY))
    }

    /**
     * 发送原始指令
     */
    fun send(message: String) {
        TcpManager.sendMessage(message)
    }
}
