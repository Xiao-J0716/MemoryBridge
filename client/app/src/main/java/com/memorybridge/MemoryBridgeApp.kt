package com.memorybridge

import android.app.Application
import com.memorybridge.net.ApiClient
import com.memorybridge.tts.TtsManager

class MemoryBridgeApp : Application() {
    override fun onCreate() {
        super.onCreate()
        instance = this
        // 初始化网络客户端
        ApiClient.init(this)
        // 预加载 TTS 引擎（离线 TTS 初始化较慢，提前初始化避免首次播放延迟）
        TtsManager.init(this)
    }

    companion object {
        lateinit var instance: MemoryBridgeApp
            private set
    }
}
