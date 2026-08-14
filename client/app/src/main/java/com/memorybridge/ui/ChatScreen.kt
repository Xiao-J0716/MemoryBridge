package com.memorybridge.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.memorybridge.ui.components.VoiceButton

/**
 * 主对话界面
 *
 * 布局结构：
 * - TopAppBar: 应用标题"记忆伙伴"
 * - 中间区域: 对话消息列表（LazyColumn，自动滚动到底部）
 * - 底部栏: 状态提示文字 + 大圆形语音按钮
 * - 顶部覆盖: 离线模式横幅、错误提示横幅
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(viewModel: ChatViewModel = viewModel()) {
    val uiState by viewModel.uiState.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = "记忆伙伴",
                        style = MaterialTheme.typography.headlineSmall,
                    )
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer,
                    titleContentColor = MaterialTheme.colorScheme.onPrimaryContainer,
                ),
            )
        },
        bottomBar = {
            BottomBar(
                state = uiState.listeningState,
                partialText = uiState.partialText,
                isAsrReady = uiState.isAsrReady,
                isAsrLoading = uiState.isAsrLoading,
                onStartListening = viewModel::startListening,
                onStopListening = viewModel::stopListening,
                onRetryAsr = viewModel::retryAsrInit,
            )
        },
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues),
        ) {
            // 离线模式提示
            if (!uiState.isOnline) {
                OfflineBanner()
            }
            // 错误提示
            uiState.errorMessage?.let { msg ->
                ErrorBanner(msg)
            }
            // 对话消息列表
            ChatMessageList(
                messages = uiState.messages,
                modifier = Modifier.weight(1f),
            )
        }
    }
}

/** 对话消息列表，自动滚动到最新消息 */
@Composable
private fun ChatMessageList(messages: List<ChatMessage>, modifier: Modifier = Modifier) {
    val listState = rememberLazyListState()
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) {
            listState.animateScrollToItem(messages.size - 1)
        }
    }
    LazyColumn(
        state = listState,
        modifier = modifier.fillMaxWidth(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        items(messages) { message ->
            ChatBubble(message = message)
        }
    }
}

/** 单条对话气泡，用户消息靠右、AI 消息靠左 */
@Composable
private fun ChatBubble(message: ChatMessage) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (message.isUser) Arrangement.End else Arrangement.Start,
    ) {
        Surface(
            shape = RoundedCornerShape(
                topStart = 16.dp,
                topEnd = 16.dp,
                bottomStart = if (message.isUser) 16.dp else 4.dp,
                bottomEnd = if (message.isUser) 4.dp else 16.dp,
            ),
            color = if (message.isUser) {
                MaterialTheme.colorScheme.primary
            } else {
                MaterialTheme.colorScheme.surfaceVariant
            },
            tonalElevation = 2.dp,
            modifier = Modifier.widthIn(max = 280.dp),
        ) {
            Text(
                text = message.text,
                style = MaterialTheme.typography.bodyLarge,
                color = if (message.isUser) {
                    MaterialTheme.colorScheme.onPrimary
                } else {
                    MaterialTheme.colorScheme.onSurfaceVariant
                },
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
            )
        }
    }
}

/** 底部栏：状态提示 + 语音按钮 */
@Composable
private fun BottomBar(
    state: ListeningState,
    partialText: String,
    isAsrReady: Boolean,
    isAsrLoading: Boolean,
    onStartListening: () -> Unit,
    onStopListening: () -> Unit,
    onRetryAsr: () -> Unit,
) {
    Surface(
        tonalElevation = 3.dp,
        shadowElevation = 8.dp,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            when {
                // ASR 正在加载模型
                isAsrLoading -> {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.padding(4.dp),
                            strokeWidth = 3.dp,
                        )
                        Text(
                            text = "正在准备语音识别，请稍候...",
                            style = MaterialTheme.typography.bodyLarge,
                            textAlign = TextAlign.Center,
                        )
                    }
                }

                // ASR 未就绪（加载失败）
                !isAsrReady -> {
                    Text(
                        text = "语音识别未就绪",
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.error,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Button(onClick = onRetryAsr) {
                        Text(text = "点击重试", style = MaterialTheme.typography.titleMedium)
                    }
                }

                // ASR 就绪，正常状态
                else -> {
                    // 状态提示文字
                    val statusText = when (state) {
                        ListeningState.IDLE -> "点击下方按钮开始说话"
                        ListeningState.LISTENING -> if (partialText.isNotBlank()) partialText else "正在听..."
                        ListeningState.PROCESSING -> "正在思考..."
                        ListeningState.SPEAKING -> "正在回复..."
                    }
                    Text(
                        text = statusText,
                        style = MaterialTheme.typography.bodyMedium,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    // 大圆形语音按钮
                    VoiceButton(
                        isListening = state == ListeningState.LISTENING,
                        isProcessing = state == ListeningState.PROCESSING || state == ListeningState.SPEAKING,
                        onClick = {
                            if (state == ListeningState.IDLE) onStartListening() else onStopListening()
                        },
                    )
                }
            }
        }
    }
}

/** 离线模式横幅 */
@Composable
private fun OfflineBanner() {
    Surface(
        color = MaterialTheme.colorScheme.secondaryContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            text = "当前离线，使用本地回复模式",
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSecondaryContainer,
            textAlign = TextAlign.Center,
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 8.dp),
        )
    }
}

/** 错误提示横幅 */
@Composable
private fun ErrorBanner(message: String) {
    Surface(
        color = MaterialTheme.colorScheme.errorContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            text = message,
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onErrorContainer,
            textAlign = TextAlign.Center,
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 8.dp),
        )
    }
}
