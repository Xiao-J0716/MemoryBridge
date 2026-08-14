package com.memorybridge.offline

/**
 * 离线模板引擎
 *
 * 断网时使用关键词匹配生成预设回复，保证基本陪伴功能不中断
 * ASR 始终离线运行，因此即令断网老人仍可语音输入
 *
 * 匹配策略：
 * 1. 遍历模板列表，检查用户输入是否包含任一关键词
 * 2. 命中则从该模板的回复列表中随机选取一条
 * 3. 无命中则返回通用兜底回复
 */
object OfflineTemplateEngine {

    private data class Template(
        val keywords: List<String>,
        val replies: List<String>,
    )

    private val templates = listOf(
        Template(
            keywords = listOf("你好", "您好", "嗨", "早上好", "下午好", "晚上好"),
            replies = listOf(
                "您好呀，很高兴和您聊天。今天感觉怎么样？",
                "您好，我在呢，您想聊点什么？",
                "您好呀，能和您说话真好。",
            ),
        ),
        Template(
            keywords = listOf("吃饭", "吃了", "没吃", "饿了"),
            replies = listOf(
                "您按时吃饭了吗？要好好吃饭，对身体好。",
                "吃饭是最重要的事，您要多吃点有营养的。",
                "今天吃了什么呀？要记得好好吃饭哦。",
            ),
        ),
        Template(
            keywords = listOf("想家", "回家", "儿子", "女儿", "家人", "孩子"),
            replies = listOf(
                "您的家人一定很想念您。要不要给他们打个电话？",
                "家人是最亲的人，他们都很爱您。",
                "我理解您想家人的心情，要不要和我聊聊他们？",
            ),
        ),
        Template(
            keywords = listOf("不舒服", "疼", "头痛", "难受", "头晕"),
            replies = listOf(
                "您哪里不舒服？要不要叫护士看看？",
                "身体不舒服要及时说，别忍着。",
                "我帮您联系一下护理人员好吗？",
            ),
        ),
        Template(
            keywords = listOf("今天", "日期", "星期", "几号"),
            replies = listOf(
                "今天是美好的一天，您今天有什么打算吗？",
                "每一天都是新的开始，让我们好好度过今天。",
            ),
        ),
        Template(
            keywords = listOf("谢谢", "感谢"),
            replies = listOf(
                "不用谢，能陪您聊天我很开心。",
                "您太客气了，这是我应该做的。",
            ),
        ),
        Template(
            keywords = listOf("无聊", "没意思", "寂寞", "孤单"),
            replies = listOf(
                "我陪您聊天就不无聊了，您想听故事吗？",
                "有我在呢，我们一起说说话就不孤单了。",
                "要不要听首歌？或者我给您讲个笑话？",
            ),
        ),
        Template(
            keywords = listOf("以前", "记得", "回忆", "过去"),
            replies = listOf(
                "您想起了什么有趣的事？跟我说说吧。",
                "以前的时光一定很美好，我很想听您讲讲。",
                "每个人心里都有珍贵的回忆，您愿意分享吗？",
            ),
        ),
    )

    /** 通用兜底回复 */
    private val fallbackReplies = listOf(
        "嗯，我在听，您继续说。",
        "我理解您的意思，能再多说一点吗？",
        "您说得真好，我在认真听呢。",
        "不要着急，慢慢说，我陪着您。",
        "嗯嗯，我在呢，您想聊什么都可以。",
        "您说的我都记着呢，继续说吧。",
    )

    /**
     * 根据用户输入匹配回复
     * @param input 用户输入文本
     * @return 匹配的回复，无匹配则返回随机兜底回复
     */
    fun generateReply(input: String): String {
        if (input.isBlank()) return fallbackReplies.random()
        for (template in templates) {
            if (template.keywords.any { input.contains(it) }) {
                return template.replies.random()
            }
        }
        return fallbackReplies.random()
    }

    /** 是否为离线模式可处理的输入 */
    fun canHandle(input: String): Boolean {
        if (input.isBlank()) return false
        return templates.any { template ->
            template.keywords.any { input.contains(it) }
        }
    }
}
