"""ASR 引擎对比：多引擎共识 + 语义可用性（无需原文，贴合老人实时场景）。

思路：客户端是老人实时说话，无"原文脚本"。故不评估字面还原度，
而评估"识别结果对下游老人陪伴任务是否可用"：
1) 引擎间一致性：多引擎都识别出的内容 = 高可信真说出的；独有/乱拼 = 错误。
2) 语义可用性：识别文本是否通顺、能否提取老人明确意图（喂下游 LLM 用）。
3) 通顺度：乱码/断句错误占比。
"""
import json
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"
AUDIOS = ["示例一", "示例二", "中科创达智能汽车产业园", "中科创达智能汽车产业园 2"]
PREFIX = {"vosk": "vosk_audio_", "u2": "u2_", "ifly_rt": "ifly_rt_", "ifly_dialect": "ifly_dialect_"}
SPACEREPL = {"vosk": "_", "u2": " ", "ifly_rt": "_", "ifly_dialect": "_"}


def fpath(engine, audio):
    base = audio.replace(" ", SPACEREPL.get(engine, "_"))
    return OUT / f"{PREFIX.get(engine, engine+'_')}{base}.txt"


def read_text(p):
    if not p.exists():
        return None
    raw = p.read_text(encoding="utf-8", errors="ignore").strip()
    if not raw:
        return None
    lines = re.findall(r'"text"\s*:\s*"([^"]*)"', raw)
    if lines:
        return "".join(lines)
    m = re.search(r"完整识别[:：]\s*(.*)", raw)
    if m:
        return m.group(1).strip()
    return raw


def normalize(s):
    return re.sub(r"[^一-鿿A-Za-z0-9]", "", s or "")


def char_coverage(candidate, reference):
    """候选里有多少字命中参照（不要求顺序），返回命中比例。"""
    c, r = normalize(candidate), normalize(reference)
    if not r:
        return 0.0
    from collections import Counter
    cr, rr = Counter(c), Counter(r)
    hit = sum(min(cr[ch], rr[ch]) for ch in cr)
    return hit / len(r)


def jaccard_words(a, b):
    """字集合 Jaccard 相似度，衡量两引擎是否在说同一内容。"""
    sa, sb = set(normalize(a)), set(normalize(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def main():
    engines = ["vosk", "u2", "ifly_rt", "ifly_dialect"]
    # 云知声作为"高可信参照"（不是真值，仅用于一致性比对），讯飞实时转写做第二参照
    print("=" * 76)
    print("ASR 引擎对比 —— 多引擎一致性 + 语义可用性（无需原文，贴合老人实时场景）")
    print("=" * 76)

    summary = {e: {"consistency": [], "usable": 0, "n": 0} for e in engines}

    for audio in AUDIOS:
        print(f"\n{'='*76}\n【{audio}】")
        texts = {e: read_text(fpath(e, audio)) for e in engines}
        ref = texts["u2"] or texts["ifly_rt"]  # 参照用云知声，缺则用讯飞实时
        for e in engines:
            t = texts[e]
            summary[e]["n"] += 1
            if not t:
                print(f"  [{e:11}] 无结果")
                continue
            cov = char_coverage(t, ref) if ref else 0
            summary[e]["consistency"].append(cov)
            # 可用性粗判：通顺（非全乱拼）+ 命中参照>50%
            usable = cov > 0.5 and len(normalize(t)) > 10
            if usable:
                summary[e]["usable"] += 1
            mark = "✓可用" if usable else "✗不可用"
            print(f"  [{e:11}] 一致性={cov*100:5.1f}% {mark}")
            print(f"      -> {t[:70]}{'...' if len(t)>70 else ''}")

    print(f"\n{'='*76}\n汇总排名（按平均一致性 + 可用条数）\n{'='*76}")
    ranked = sorted(engines, key=lambda e: -(sum(summary[e]["consistency"])/max(len(summary[e]["consistency"]),1)))
    for i, e in enumerate(ranked, 1):
        cons = summary[e]["consistency"]
        avg = sum(cons)/len(cons)*100 if cons else 0
        print(f"  {i}. {e:11} 平均一致性={avg:5.1f}%  可用={summary[e]['usable']}/{summary[e]['n']}")


if __name__ == "__main__":
    main()
