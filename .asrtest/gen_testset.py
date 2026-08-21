"""生成 ASR 黑盒测试集：用系统 TTS 合成已知真值的中文句子，
再用 ffmpeg 构造变体（干净/含噪/慢速长停顿/短句/长句），供各引擎识别后按真值算 CER。

真值 = 合成时用的原文，故黑盒测试有确定答案（与真实音频不同）。
输出：.asrtest/testset/cases.json（用例清单）+ 各 wav 文件（16k mono）。
"""
import json
import subprocess
import wave
from pathlib import Path

TS = Path(__file__).resolve().parent / "testset"
TS.mkdir(parents=True, exist_ok=True)

# 测试用例：真值 + 变体维度。覆盖老人陪伴场景易错点。
CASES = [
    # id, 真值, 维度, TTS语速, 后处理
    ("s1_clean",   "你好，我叫张奶奶，我喜欢喝小米粥",            "干净基线",  -2, []),
    ("s2_clean",   "今天天气怎么样，我想听一首邓丽君的歌",          "干净基线",  -2, []),
    ("s3_clean",   "我有点头晕，能不能帮我叫一下护士",              "干净基线",  -2, []),
    ("s4_noise",   "你好，我叫张奶奶，我喜欢喝小米粥",            "含噪",     -2, ["noise"]),
    ("s5_noise",   "我想回家，我想我儿子了",                  "含噪",     -2, ["noise"]),
    ("s6_slow",   "我以前是当老师的，教了一辈子书",            "慢速长停顿", -4, ["silence"]),
    ("s7_slow",   "谢谢你陪我聊天，我心里不那么孤单了",          "慢速长停顿", -4, ["silence"]),
    ("s8_short",  "几点了",                                "短句",      0, []),
    ("s9_short",  "我冷",                                 "短句",      0, []),
    ("s10_long",  "我还想看看年轻时候在上海外滩拍的那张黑白照片，那时候我才二十出头，日子过得真快啊",
                 "长句",      -2, []),
]

PS = r"""Add-Type -AssemblyName System.Speech;
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;
$s.SelectVoice('Microsoft Huihui Desktop');
$s.Rate = {rate};
$s.SetOutputToWaveFile('{out}');
$s.Speak('{text}');
$s.Dispose();"""


def synth(text, rate, out_wav):
    """用 Huihui TTS 合成，输出 22050 wav。"""
    ps = PS.format(rate=rate, out=str(out_wav).replace("\\", "\\\\"), text=text.replace("'", "''"))
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True)


def to16k(src, dst):
    """转 16k mono s16le。"""
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
                    "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(dst)], check=True)


def add_noise(src, dst):
    """叠加白噪声（模拟环境噪声），用临时中间文件避免输入输出同名。"""
    tmp = str(dst) + ".tmp.wav"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
                    "-f", "lavfi", "-t", "20", "-i", "anoisesrc=color=white:amplitude=0.05",
                    "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:weights=1 0.3",
                    "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", tmp], check=True)
    import os; os.replace(tmp, str(dst))


def add_silence(src, dst):
    """句中插 2.5s 静音（模拟老人停顿，测 VAD），用临时中间文件。"""
    tmp = str(dst) + ".tmp.wav"
    # 在音频中段插入静音：取前半 + 2.5s 静音 + 后半
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
                    "-af", "apad=pad_dur=2.5:whole_dur=0",
                    "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", tmp], check=True, capture_output=True)
    import os
    if Path(tmp).exists():
        os.replace(tmp, str(dst))
    else:
        # apad 方案失败则用 anullsrc 拼接
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-i", str(src), "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
                        "-filter_complex", "[1:a]atrim=0:2.5[a];[0:a][a]concat=n=2:v=0:a=1",
                        "-c:a", "pcm_s16le", tmp], check=True)
        os.replace(tmp, str(dst))


def main():
    cases = []
    for cid, truth, dim, rate, mods in CASES:
        raw = TS / f"{cid}_raw.wav"
        out = TS / f"{cid}.wav"
        try:
            synth(truth, rate, raw)
            to16k(raw, out)
            if "noise" in mods:
                add_noise(out, out)
            if "silence" in mods:
                add_silence(out, out)
            dur = wave.open(str(out), "rb").getnframes() / 16000
            cases.append({"id": cid, "truth": truth, "dim": dim, "wav": str(out), "dur": round(dur, 1)})
            print(f"OK {cid} [{dim}] dur={dur:.1f}s")
        except Exception as e:
            print(f"FAIL {cid}: {e}")
    (TS / "cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n生成 {len(cases)} 个用例 -> {TS/'cases.json'}")


if __name__ == "__main__":
    main()
