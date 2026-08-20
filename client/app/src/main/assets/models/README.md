# Vosk 中文模型（运行时资产，不入 Git）

本目录存放 Vosk 离线中文模型 `vosk-model-small-cn-0.22`（约 42MB）。
模型二进制**不入库**，由 `app/scripts/setup-asr-assets.sh` 下载。

## 准备

在 `app/` 目录下运行：

```bash
bash scripts/setup-asr-assets.sh
```

脚本会下载并解压模型到本目录，确保存在 `vosk-model-small-cn-0.22/am/`（含 `am/ conf/ graph/ ivector/`）。

## 手动（备选）

1. 下载 https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip （约 42MB）
2. 解压到本目录，使 `vosk-model-small-cn-0.22/am/` 存在

## 验证

构建安装后，Logcat tag `SpeechRecognizer` 应见：
`模型解压完成: .../models/vosk-model-small-cn-0.22` 与 `Vosk 模型初始化成功`。
