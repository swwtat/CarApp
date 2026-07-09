package com.example.androidcarapp.api

/**
 * 小车运动方向枚举 (1:1 对应 HarmonyOS CarEnum)
 */
enum class CarDirection(val code: Int) {
    /** 停止 */
    Stop(0),
    /** 前进 */
    Front(1),
    /** 后退 */
    After(2),
    /** 左平移 */
    Left(3),
    /** 右平移 */
    Right(4),
    /** 左旋转 */
    LeftRotate(5),
    /** 右旋转 */
    RightRotate(6),
    /** 刹车 */
    Brake(7)
}
