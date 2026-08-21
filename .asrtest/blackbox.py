"""黑盒测试：对测试集每个用例跑各引擎识别，按真值算字错率(CER)/字准确率。

输入：.asrtest/testset/cases.json（含真值）
引擎：vosk / u2 / ifly_rt / ifly_dialect
输出：.asrtest/out/blackbox.json（每用例每引擎的 CER + 识别文本）
"""
import difflib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST = ROOT / ".asrtest"
VENV = str(TEST / ".venv/Scripts/python.exe")

# 云知声 key：config.py 用 pydantic-settings 读 server/.env，但黑盒从项目根跑时 cwd 不在 server。
# 在 import config 前直接设环境变量，确保 UNISOUND_API_KEY 生效（env 优先级高于 .env 文件）。
_U2ENV = TEST / ".env"
if _U2ENV.exists():
    for line in _U2ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if k.strip().startswith("U2_") or k.strip() == "UNISOUND_API_KEY":
                os.environ.setdefault(k.strip(), v.strip())
# 也读 server/.env 里的 UNISOUND_API_KEY
_SRVENV = ROOT / "server/.env"
if _SRVENV.exists():
    for line in _SRVENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("UNISOUND_API_KEY="):
            os.environ["UNISOUND_API_KEY"] = line.split("=", 1)[1].strip()


def normalize(s):
    return re.sub(r"[^一-鿿A-Za-z0-9]", "", s or "")


def cer(candidate, truth):
    c, t = normalize(candidate), normalize(truth)
    if not t:
        return 1.0
    return 1.0 - difflib.SequenceMatcher(None, c, t).ratio()


def run_vosk(wav, model="C:/voskrun/model"):
    import wave
    from vosk import KaldiRecognizer, Model
    m = Model(model)
    rec = KaldiRecognizer(m, 16000)
    wf = wave.open(wav, "rb")
    finals = []
    while True:
        d = wf.readframes(4000)
        if not d:
            break
        if rec.AcceptWaveform(d):
            r = json.loads(rec.Result())
            if r.get("text"):
                finals.append(r["text"])
    tail = json.loads(rec.FinalResult())
    if tail.get("text"):
        finals.append(tail["text"])
    return "".join(finals).strip()


def run_unisound(wav):
    import importlib.util, asyncio, sys, os
    # config.py 用 pydantic-settings 读相对 cwd 的 .env，需切到 server/ 才能读到 server/.env
    prev = os.getcwd()
    os.chdir(str(ROOT / "server"))
    try:
        sys.path.insert(0, str(ROOT / "server"))
        from config import settings
        spec = importlib.util.spec_from_file_location("a", str(ROOT / "server/services/asr_service.py"))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        svc = mod.UnisoundService()
        return asyncio.run(svc.recognize(open(wav, "rb").read(), "zh")).strip()
    finally:
        os.chdir(prev)


def run_ifly_rt(wav):
    import importlib.util
    spec = importlib.util.spec_from_file_location("a", str(TEST / "ifly_rtasr.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.transcribe(wav).strip()


def run_ifly_dialect(wav):
    import importlib.util
    spec = importlib.util.spec_from_file_location("a", str(TEST / "ifly_dialect.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.transcribe(wav).strip()


ENGINES = {
    "vosk": run_vosk,
    "u2": run_unisound,
    "ifly_rt": run_ifly_rt,
    "ifly_dialect": run_ifly_dialect,
}


def main(only=None):
    cases = json.loads((TEST / "testset/cases.json").read_text(encoding="utf-8"))
    engs = [only] if only else list(ENGINES)
    rows = []
    for c in cases:
        cid, truth, wav = c["id"], c["truth"], c["wav"]
        print(f"\n[{cid}] 真值: {truth}")
        for e in engs:
            try:
                text = ENGINES[e](wav)
                err = cer(text, truth)
                acc = 1 - err
                print(f"  {e:11} CER={err*100:5.1f}% 准确率={acc*100:5.1f}% -> {text[:50]}")
                rows.append({"id": cid, "dim": c["dim"], "engine": e, "cer": round(err, 4),
                             "acc": round(acc, 4), "text": text, "truth": truth})
            except Exception as ex:
                print(f"  {e:11} 异常: {str(ex)[:80]}")
                rows.append({"id": cid, "dim": c["dim"], "engine": e, "cer": 1.0,
                             "acc": 0.0, "text": "", "truth": truth, "error": str(ex)[:200]})
    (TEST / "out/blackbox.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    # 汇总
    print(f"\n{'='*60}\n各引擎平均字准确率（按真值）\n{'='*60}")
    by = {}
    for r in rows:
        by.setdefault(r["engine"], []).append(r["acc"])
    for e, accs in sorted(by.items(), key=lambda kv: -sum(kv[1])/len(kv[1])):
        print(f"  {e:11} {sum(accs)/len(accs)*100:5.1f}%  (n={len(accs)})")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
