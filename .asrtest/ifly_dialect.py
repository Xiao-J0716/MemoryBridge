"""讯飞·方言识别大模型客户端（已验证可用版）。

接口：wss://iat.cn-huabei-1.xf-yun.com/v1，HmacSHA256 鉴权。
关键：首帧带音频、连续发完所有帧+末帧(status=2)再收结果、按 sn 去重(rpl替换/apd追加)。
音频：PCM 16k 16bit 单声道，每帧 1280 字节，间隔 40ms，上限 60s。

用法：python ifly_dialect.py <wav> [--env <envfile>]
"""
import base64
import hashlib
import hmac
import json
import sys
import time
import urllib.parse
import wave
from email.utils import formatdate
from pathlib import Path

import websocket

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".asrtest" / ".env"
HOST = "iat.cn-huabei-1.xf-yun.com"
PATH = "/v1"


def load_env(path: Path) -> dict:
    d = {}
    if not path.exists():
        return d
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        d[k.strip()] = v.strip()
    return d


def auth_url(api_key: str, api_secret: str) -> str:
    date = formatdate(timeval=None, localtime=False, usegmt=True)
    sig_origin = f"host: {HOST}\ndate: {date}\nGET {PATH} HTTP/1.1"
    signature = base64.b64encode(hmac.new(api_secret.encode(), sig_origin.encode(), hashlib.sha256).digest()).decode()
    auth_origin = (
        f'api_key="{api_key}",algorithm="hmac-sha256",'
        f'headers="host date request-line",signature="{signature}"'
    )
    authorization = urllib.parse.quote(base64.b64encode(auth_origin.encode()).decode(), safe="")
    return f"wss://{HOST}{PATH}?authorization={authorization}&date={urllib.parse.quote(date, safe='')}&host={HOST}"


def first_frame(app_id: str, audio_b64: str) -> dict:
    return {
        "header": {"app_id": app_id, "status": 0},
        "parameter": {
            "iat": {
                "language": "zh_cn", "accent": "mulacc", "domain": "slm",
                "eos": 1800, "dwa": "wpgs", "ptt": 1, "nunum": 1, "ltc": 1,
                "result": {"encoding": "utf8", "compress": "raw", "format": "json"},
            }
        },
        "payload": {
            "audio": {"encoding": "raw", "sample_rate": 16000, "channels": 1,
                      "bit_depth": 16, "status": 0, "seq": 0, "audio": audio_b64}
        },
    }


def mid_frame(audio_b64: str, seq: int, app_id: str = "") -> dict:
    # 讯飞要求每帧 header 都带 app_id，否则服务端在收到缺 app_id 的帧时立即断连(10053)
    return {"header": {"app_id": app_id, "status": 1},
            "payload": {"audio": {"encoding": "raw", "sample_rate": 16000, "channels": 1,
                                  "bit_depth": 16, "status": 1, "seq": seq, "audio": audio_b64}}}


def end_frame(seq: int, app_id: str = "") -> dict:
    return {"header": {"app_id": app_id, "status": 2},
            "payload": {"audio": {"encoding": "raw", "sample_rate": 16000, "channels": 1,
                                  "bit_depth": 16, "status": 2, "seq": seq, "audio": ""}}}


def words_of(inner: dict) -> str:
    out = []
    for w in inner.get("ws", []) or []:
        for cw in w.get("cw", []) or []:
            out.append(cw.get("w", ""))
    return "".join(out)


def transcribe(wav_path: str, env_path: Path = ENV) -> str:
    env = load_env(env_path)
    app_id, api_key, api_secret = env["IFLY_APPID"], env["IFLY_API_KEY"], env["IFLY_API_SECRET"]
    url = auth_url(api_key, api_secret)
    print(f"握手: wss://{HOST}{PATH}", file=sys.stderr)

    wf = wave.open(wav_path, "rb")
    assert wf.getframerate() == 16000 and wf.getnchannels() == 1, "需 16k 单声道 PCM"
    dur = wf.getnframes() / 16000
    print(f"音频: {wav_path} 时长={dur:.1f}s", file=sys.stderr)
    if dur > 60:
        print("警告: 上限60s, 截断", file=sys.stderr)

    ws = websocket.create_connection(url, timeout=30)
    ws.settimeout(8)

    # 发首帧(带音频)
    data = wf.readframes(640)
    ws.send(json.dumps(first_frame(app_id, base64.b64encode(data).decode()), ensure_ascii=False))

    # 连续发中间帧
    seq = 1
    while True:
        data = wf.readframes(640)
        if not data or wf.tell() / 16000 > 60:
            break
        ws.send(json.dumps(mid_frame(base64.b64encode(data).decode(), seq, app_id), ensure_ascii=False))
        seq += 1
        time.sleep(0.04)

    # 末帧
    ws.send(json.dumps(end_frame(seq, app_id), ensure_ascii=False))
    print(f"发完, 收结果...", file=sys.stderr)

    # 收结果。方言识别每帧返回"本句累加文本"，pgs=rpl 替换上一帧、apd 开新句。
    # 正确累积：rpl → 覆盖当前句; apd → 开新句并覆盖。
    segments = []  # 各句最终文本
    cur = ""      # 当前正在累积的句
    t0 = time.time()
    while time.time() - t0 < 20:
        try:
            raw = ws.recv()
        except Exception as e:
            print(f"收结束: {e}", file=sys.stderr)
            break
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        code = msg.get("header", {}).get("code")
        if code != 0:
            print(f"错误: {json.dumps(msg, ensure_ascii=False)[:200]}", file=sys.stderr)
            break
        res = (msg.get("payload") or {}).get("result") or {}
        tb64 = res.get("text") or ""
        if tb64:
            try:
                inner = json.loads(base64.b64decode(tb64).decode("utf-8"))
            except Exception:
                inner = {}
            pgs = inner.get("pgs", "")
            ls = inner.get("ls", False)
            t = words_of(inner)
            if not t:
                continue
            if pgs == "rpl":
                # 替换当前句（本句累进）
                cur = t
            else:
                # apd：上一句定稿，开新句
                if cur:
                    segments.append(cur)
                cur = t
            if ls:
                segments.append(cur)
                cur = ""
                print(f"[句终] {t}", file=sys.stderr)
        if msg.get("header", {}).get("status") == 2:
            print("服务端结束", file=sys.stderr)
            break
    if cur:
        segments.append(cur)

    ws.close()
    return "".join(segments)


if __name__ == "__main__":
    wav = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / ".asrtest/audio_示例一_short.wav")
    out = transcribe(wav)
    print("===== 完整识别 =====")
    print(out)
