package com.memorybridge.ui.components

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.memorybridge.ui.theme.ListeningIndicator
import com.memorybridge.ui.theme.RecordingActive

/**
 * 大圆形语音按钮组件
 *
 * 设计要点：
 * - 96dp 大圆形，老人容易点击
 * - 录音时红色 + 脉冲缩放动画，视觉反馈明显
 * - 处理中橙色，禁止重复点击
 * - 空闲蓝色，显示麦克风图标
 * - 无障碍：带 contentDescription
 */
@Composable
fun VoiceButton(
    isListening: Boolean,
    isProcessing: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    // 录音时脉冲动画
    val infiniteTransition = rememberInfiniteTransition(label = "pulse")
    val scale by infiniteTransition.animateFloat(
        initialValue = 1f,
        targetValue = 1.15f,
        animationSpec = infiniteRepeatable(
            animation = tween(800, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "scale",
    )
    val buttonScale = if (isListening) scale else 1f
    val buttonColor = when {
        isListening -> RecordingActive
        isProcessing -> ListeningIndicator
        else -> MaterialTheme.colorScheme.primary
    }

    Box(
        modifier = modifier
            .size(96.dp)
            .scale(buttonScale)
            .clip(CircleShape)
            .background(buttonColor),
        contentAlignment = Alignment.Center,
    ) {
        IconButton(
            onClick = onClick,
            modifier = Modifier
                .size(96.dp)
                .semantics {
                    contentDescription = if (isListening) "停止说话" else "开始说话"
                },
            enabled = !isProcessing,
        ) {
            Icon(
                imageVector = if (isListening) Icons.Filled.Stop else Icons.Filled.Mic,
                contentDescription = null,
                tint = Color.White,
                modifier = Modifier.size(48.dp),
            )
        }
    }
}
