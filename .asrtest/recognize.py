"""离线识别一个 WAV 文件，使用与 Android 客户端相同的 Vosk 模型。

用法：python recognize.py <wav> [model]
模型默认指向 client/app/src/main/assets/models/vosk-model-small-cn-0.22。
WAV 需为 16kHz 单声道 16-bit PCM（与 AudioConfig 一致）。
"""
import json
import sys
import wave
from pathlib import Path

from vosk import KaldiRecognizer, Model, SetLogLevel

SetLogLevel(0)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = ROOT / "client/app/src/main/assets/models/vosk-model-small-cn-0.22"


def recognize(wav_path: str, model_path: str) -> None:
    model = Model(model_path)
    rec = KaldiRecognizer(model, 16000)
    rec.SetWords(True)

    wf = wave.open(wav_path, "rb")
    print(f"音频: {wav_path}")
    print(f"  采样率={wf.getframerate()} 声道={wf.getnchannels()} 时长={wf.getnframes()/wf.getframerate():.1f}s")
    print(f"模型: {model_path}")
    print("-" * 60)

    finals = []
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            r = json.loads(rec.Result())
            if r.get("text"):
                finals.append(r["text"])
                print(f"[句] {r['text']}")
    tail = json.loads(rec.FinalResult())
    if tail.get("text"):
        finals.append(tail["text"])
        print(f"[尾] {tail['text']}")

    print("-" * 60)
    full = " ".join(finals).strip()
    print(f"完整识别: {full}")


if __name__ == "__main__":
    wav = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / ".asrtest/sample1.wav")
    mdl = sys.argv[2] if len(sys.argv) > 2 else str(DEFAULT_MODEL)
    recognize(wav, mdl)
