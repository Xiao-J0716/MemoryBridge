"""讯飞·实时语音转写大模型（RTASR LLM）客户端。

接口：wss://office-api-ast-dx.iflyaisol.com/ast/communicate/v1
鉴权：参数按名升序+URL编码→HmacSHA1(APISecret)→base64，放 URL query。
音频：PCM 16k 16bit 单声道，WS 二进制帧，每 40ms 发 1280 字节，末尾发 {"end":true,"sessionId":...}
结果：data.cn.st.rt.ws.cw[].w 拼词，type=0 为确定结果，ls=true 为最终帧。

用法：python ifly_rtasr.py <wav> [--env <envfile>]
凭证读 .asrtest/.env：IFLY_APPID / IFLY_API_KEY / IFLY_API_SECRET / IFLY_WS_HOST
"""
import base64
import hashlib
import hmac
import json
import sys
import time
import urllib.parse
import uuid
import wave
from pathlib import Path

import websocket  # websocket-client

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".asrtest" / ".env"


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


def sign(params: dict, api_secret: str) -> str:
    """参数按名升序，key/value 各自 URL 编码，拼 baseString，HmacSHA1→base64。"""
    items = sorted(params.items())
    enc = []
    for k, v in items:
        kk = urllib.parse.quote(k, safe="")
        vv = urllib.parse.quote(str(v), safe="")
        enc.append(f"{kk}={vv}")
    base_str = "&".join(enc)
    digest = hmac.new(api_secret.encode("utf-8"), base_str.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def build_url(env: dict, lang: str = "autodialect") -> str:
    host = env.get("IFLY_WS_HOST", "office-api-ast-dx.iflyaisol.com").strip("/")
    params = {
        "accessKeyId": env["IFLY_API_KEY"],
        "appId": env["IFLY_APPID"],
        "uuid": str(uuid.uuid4()),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%S+0800"),
        "audio_encode": "pcm_s16le",
        "lang": lang,
        "samplerate": "16000",
    }
    sig = sign(params, env["IFLY_API_SECRET"])
    params["signature"] = sig
    query = "&".join(f"{urllib.parse.quote(k,safe='')}={urllib.parse.quote(str(v),safe='')}" for k, v in params.items())
    return f"wss://{host}/ast/communicate/v1?{query}"


def parse_text(msg: dict) -> str:
    """从结果消息抽词拼文本。"""
    data = msg.get("data")
    if not data or not isinstance(data, dict):
        return ""
    cn = data.get("cn") or {}
    st = cn.get("st") or {}
    words = []
    for rt in st.get("rt", []) or []:
        for w in rt.get("ws", []) or []:
            for cw in w.get("cw", []) or []:
                wp = cw.get("wp", "n")
                # 标点(p)和分段(g)也拼上，顺滑词(s)可忽略或保留
                if wp == "s":
                    continue
                words.append(cw.get("w", ""))
    return "".join(words)


def transcribe(wav_path: str, env_path: Path = ENV, lang: str = "autodialect") -> str:
    env = load_env(env_path)
    url = build_url(env, lang)
    print(f"握手: wss://.../ast/communicate/v1?appId={env['IFLY_APPID']}&lang={lang}...", file=sys.stderr)

    wf = wave.open(wav_path, "rb")
    assert wf.getframerate() == 16000 and wf.getnchannels() == 1, "需 16k 单声道 PCM"
    print(f"音频: {wav_path} 时长={wf.getnframes()/16000:.1f}s", file=sys.stderr)

    results = []  # (type, text, ls)
    session_id = None

    def on_message(ws, raw):
        nonlocal session_id
        try:
            msg = json.loads(raw)
        except Exception:
            print(f"[非JSON帧] {raw[:80]}", file=sys.stderr)
            return
        mt = msg.get("msg_type") or msg.get("action")
        if mt == "started":
            session_id = msg.get("sessionId") or msg.get("data", {}).get("sessionId")
            print(f"[started] sessionId={session_id}", file=sys.stderr)
        elif mt == "result":
            res = msg.get("res_type")
            data = msg.get("data") or {}
            st = (data.get("cn") or {}).get("st") or {}
            ttype = st.get("type")
            ls = data.get("ls")
            txt = parse_text(msg)
            if txt:
                results.append((ttype, txt, ls))
                tag = "最终" if ls else ("确定" if ttype == "0" else "中间")
                print(f"[{tag}] {txt}", file=sys.stderr)
        elif mt == "error" or msg.get("code") not in (None, 0, "0"):
            print(f"[错误] {json.dumps(msg, ensure_ascii=False)[:200]}", file=sys.stderr)
            ws.close()
        else:
            print(f"[其它 {mt}] {json.dumps(msg, ensure_ascii=False)[:120]}", file=sys.stderr)

    def on_open(ws):
        frames_per = 1280
        while True:
            data = wf.readframes(frames_per // 2)
            if not data:
                break
            ws.send(data, opcode=websocket.ABNF.OPCODE_BINARY)
            time.sleep(0.04)
        end = json.dumps({"end": True, "sessionId": session_id or ""})
        ws.send(end)
        print("[发送结束帧]", file=sys.stderr)

    def on_error(ws, err):
        print(f"[WS错误] {err}", file=sys.stderr)

    def on_close(ws, code, reason):
        print(f"[关闭] code={code} reason={reason}", file=sys.stderr)

    ws = websocket.WebSocketApp(
        url, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close,
    )
    ws.run_forever()

    # 合并：取所有 ls=True 的最终帧；若无最终帧则取 type=0 的确定帧去重
    finals = [t for (tp, t, ls) in results if ls for (tp2, t2, ls2) in [(tp, t, ls)] if t]
    # 简化：直接按出现顺序拼，用确定结果(type=0)为准
    seen, merged = set(), []
    for tp, t, ls in results:
        if tp == "0" and t not in seen:
            merged.append(t)
            seen.add(t)
    text = "".join(merged) if merged else "".join(t for _, t, _ in results)
    return text


if __name__ == "__main__":
    wav = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / ".asrtest/audio_示例一.wav")
    lang = "autodialect"
    out = transcribe(wav, lang=lang)
    print("===== 完整识别 =====")
    print(out)
