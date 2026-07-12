package com.example.androidcarapp.camera

import android.content.Context

object CameraConfig {
    private const val PREFS_NAME = "camera_prefs"
    private const val KEY_PORT = "camera_port"
    const val DEFAULT_PORT = 8080

    fun getPort(context: Context): Int {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getInt(KEY_PORT, DEFAULT_PORT)
    }

    fun setPort(context: Context, port: Int) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putInt(KEY_PORT, port)
            .apply()
    }

    fun getCameraUrl(host: String, context: Context): String {
        val port = getPort(context)
        return "http://host:port"
    }
}
