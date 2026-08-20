#!/usr/bin/env python3
"""P1 Step 4: 连续 20 轮对话稳定性测试 — 响应时间 + 记忆召回准确率"""

import json
import statistics
import sys
import time
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8000"
USER_ID = 1
SESSION_ID = "stability-test-001"

# (输入, 期望回复包含的关键词, 类型)
ROUNDS = [
    ("我叫张奶奶", None, "info"),
    ("我今年78岁了", None, "info"),
    ("我喜欢喝小米粥", None, "info"),
    ("我儿子叫小明", None, "info"),
    ("我住在阳光养老院", None, "info"),
    ("你还记得我叫什么吗？", "张奶奶", "recall"),
    ("我多大了？", "78", "recall"),
    ("我喜欢吃什么？", "小米粥", "recall"),
    ("我儿子叫什么？", "小明", "recall"),
    ("我住在哪里？", "阳光", "recall"),
    ("今天天气不错", None, "chat"),
    ("我有点想家了", None, "chat"),
    ("谢谢你陪我聊天", None, "chat"),
    ("你还记得我叫什么吗？", "张奶奶", "recall"),
    ("我喜欢喝什么？", "小米粥", "recall"),
    ("你好呀", None, "chat"),
    ("我孙子今年上高中了", None, "info"),
    ("我儿子的名字是什么？", "小明", "recall"),
    ("我住哪个养老院？", "阳光", "recall"),
    ("你还记得关于我的哪些事情？", "张奶奶", "recall"),
]


def chat(text: str, session_id: str) -> tuple[dict, float]:
    payload = json.dumps(
        {"user_id": USER_ID, "text": text, "session_id": session_id},
        ensure_ascii=False,
    ).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode())
    elapsed = time.perf_counter() - start
    return body, elapsed


def main() -> int:
    print("==> P1 Step 4 稳定性测试：20 轮对话")
    print(f"    BASE_URL={BASE_URL}  session={SESSION_ID}\n")

    results = []
    latencies = []
    recall_total = 0
    recall_hit = 0

    for i, (text, expect, kind) in enumerate(ROUNDS, 1):
        try:
            body, elapsed = chat(text, SESSION_ID)
            reply = body.get("reply", "")
            memories_used = body.get("memories_used", 0)
            latencies.append(elapsed)

            hit = None
            if expect:
                recall_total += 1
                hit = expect in reply
                if hit:
                    recall_hit += 1

            status = "OK"
            if expect and not hit:
                status = "MISS"

            results.append(
                {
                    "round": i,
                    "type": kind,
                    "input": text,
                    "reply": reply,
                    "expect": expect,
                    "hit": hit,
                    "memories_used": memories_used,
                    "latency_s": round(elapsed, 2),
                    "status": status,
                }
            )

            mark = "✓" if status == "OK" else "✗"
            print(f"[{i:02d}/{len(ROUNDS)}] {mark} {elapsed:.2f}s | mem={memories_used} | {text[:20]}")
            if status == "MISS":
                print(f"         期望含「{expect}」，实际: {reply[:60]}...")

        except urllib.error.HTTPError as e:
            err = e.read().decode()
            print(f"[{i:02d}/{len(ROUNDS)}] ✗ HTTP {e.code}: {err[:120]}")
            return 1
        except Exception as e:
            print(f"[{i:02d}/{len(ROUNDS)}] ✗ 异常: {e}")
            return 1

    # 跨 session 追加 1 轮 recall
    print("\n==> 跨 session 召回测试 (session-B)...")
    try:
        body, elapsed = chat("你还记得我叫什么吗？", "stability-test-002")
        reply = body.get("reply", "")
        cross_hit = "张奶奶" in reply
        latencies.append(elapsed)
        print(f"    {'✓' if cross_hit else '✗'} {elapsed:.2f}s | mem={body.get('memories_used')} | {reply[:50]}...")
        results.append(
            {
                "round": "cross-session",
                "type": "recall",
                "input": "你还记得我叫什么吗？",
                "reply": reply,
                "expect": "张奶奶",
                "hit": cross_hit,
                "memories_used": body.get("memories_used", 0),
                "latency_s": round(elapsed, 2),
                "status": "OK" if cross_hit else "MISS",
            }
        )
        recall_total += 1
        if cross_hit:
            recall_hit += 1
    except Exception as e:
        print(f"    ✗ 跨 session 测试失败: {e}")
        return 1

    # 汇总
    print("\n" + "=" * 50)
    print("汇总报告")
    print("=" * 50)
    print(f"总轮数:        {len(ROUNDS) + 1} (含 1 轮跨 session)")
    print(f"成功率:        {sum(1 for r in results if r['status']=='OK')}/{len(results)}")
    print(f"记忆召回准确率: {recall_hit}/{recall_total} ({100*recall_hit/recall_total:.0f}%)")
    print(f"响应时间 avg:  {statistics.mean(latencies):.2f}s")
    print(f"响应时间 p50:  {statistics.median(latencies):.2f}s")
    print(f"响应时间 max:  {max(latencies):.2f}s")
    print(f"响应时间 min:  {min(latencies):.2f}s")

    report_path = "/tmp/p1_step4_stability_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "summary": {
                    "total_rounds": len(results),
                    "success_rate": f"{sum(1 for r in results if r['status']=='OK')}/{len(results)}",
                    "recall_accuracy": f"{recall_hit}/{recall_total}",
                    "latency_avg_s": round(statistics.mean(latencies), 2),
                    "latency_p50_s": round(statistics.median(latencies), 2),
                    "latency_max_s": round(max(latencies), 2),
                    "latency_min_s": round(min(latencies), 2),
                },
                "results": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n详细报告: {report_path}")

    if recall_hit < recall_total:
        print("\n⚠️  部分记忆召回未命中，请检查 RAG 检索或 Prompt")
        return 1

    print("\n✅ Step 4 稳定性测试通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
