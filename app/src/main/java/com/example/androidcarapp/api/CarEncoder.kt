package com.example.androidcarapp.api

/**
 * 小车控制指令编码器 (1:1 对应 HarmonyOS CarEncode)
 *
 * 协议格式: $01<type><size><data><checksum>#
 * 所有数值以十六进制大写字符串表示
 */
object CarEncoder {

    private const val TAG = "CarEncoder"

    /** 按钮控制编码 */
    fun buttonEncode(d: CarDirection): String {
        return baseEncode("15", numberToHex(d.code, 2))
    }

    /** 摇杆控制编码 (speedX, speedY: -100~100) */
    fun ctrlEncode(speedX: Float, speedY: Float): String {
        var x = Math.round(speedX)
        var y = Math.round(speedY)

        if (x < 0) x += 256
        if (y < 0) y += 256

        return baseEncode("10", numberToHex(x, 2) + numberToHex(y, 2))
    }

    /** 启动跟踪 */
    fun trackingOpen(): String = baseEncode("63")

    /** 关闭跟踪 */
    fun trackingClose(): String = baseEncode("64")

    /** 通用编码函数 */
    private fun baseEncode(type: String, vararg datas: String): String {
        val info = datas.joinToString("")
        val size = numberToHex(info.length + 2, 2)
        var code = "01$type$size$info"
        code += numberToHex(checksum(code), 2)
        return "$$code#"
    }

    /** 数值转十六进制字符串 */
    private fun numberToHex(num: Int, len: Int): String {
        val hex = num.toString(16)
        return hex.padStart(len, '0').uppercase()
    }

    /** 计算校验和 */
    private fun checksum(data: String): Int {
        var sum = 0
        var i = 0
        while (i < data.length) {
            sum += data.substring(i, i + 2).toInt(16)
            i += 2
        }
        return sum % 256
    }
}
