package com.memorybridge.net

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

/**
 * 网络客户端配置（OkHttp + Retrofit）
 *
 * 设计要点：
 * - 只传输文本到云端，不传输音频（减少带宽和保护隐私）
 * - 超时设置适配老人慢速网络环境
 * - 提供网络状态检测，用于在线/离线切换
 */
object ApiClient {
    private const val TAG = "ApiClient"

    // TODO: 替换为实际服务器地址
    var BASE_URL = "http://192.168.1.100:8000/"
        private set

    private var okHttpClient: OkHttpClient? = null
    private var retrofit: Retrofit? = null
    private var _chatApi: ChatApi? = null
    private var appContext: Context? = null

    fun init(context: Context, baseUrl: String? = null) {
        appContext = context.applicationContext
        baseUrl?.let { BASE_URL = it }

        val loggingInterceptor = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BODY
        }

        okHttpClient = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(10, TimeUnit.SECONDS)
            .addInterceptor(loggingInterceptor)
            .build()

        retrofit = Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(okHttpClient!!)
            .addConverterFactory(GsonConverterFactory.create())
            .build()

        _chatApi = retrofit!!.create(ChatApi::class.java)
        Log.i(TAG, "ApiClient 初始化完成, BASE_URL=$BASE_URL")
    }

    /** 获取 ChatApi 实例 */
    val chatApi: ChatApi
        get() = _chatApi ?: throw IllegalStateException("ApiClient 未初始化，请先调用 init()")

    /**
     * 检测网络是否可用
     * @return true 设备有网络连接
     */
    fun isNetworkAvailable(): Boolean {
        val context = appContext ?: return false
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }

    /**
     * 检测服务器是否可达
     * @return true 服务器健康检查通过
     */
    suspend fun isServerReachable(): Boolean {
        return try {
            val response = chatApi.healthCheck()
            response.isSuccessful
        } catch (e: Exception) {
            Log.w(TAG, "服务器不可达: ${e.message}")
            false
        }
    }
}
