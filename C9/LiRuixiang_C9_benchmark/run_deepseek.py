"""
ReCal 本地真实模型复现脚本 / Local Real-Model Runner
================================================================================

作用：用一个真实模型（默认 DeepSeek）跑完整套流程 —— 筛题 + A/B/C 三组实验 ——
      并把结果落成 JSON，用于填写 `C9_测试结果.md` 的第二部分。

为什么需要这个脚本（而不是直接 import kbench）
--------------------------------------------------------------------------------
`task.py` 里的 `evaluate_one` / `screen_items` / `run_experiment_*` 都是串行的：
每道题、每次 trial 各发一次请求。本基准的调用量大约是
    筛题 60×2 + A组 40×10 + B组 40×2 + C组 40×10 ≈ 1080 次
串行跑（每次 2–5 秒）需要 40–90 分钟。

所以这里不改 `task.py`，而是在外面套一层"并发预取 + 样本池"的模型适配器：
  1. 先把这一阶段要用到的全部请求一次性并发发出去（8 路并发）
  2. 结果按 (提示词, 温度) 归组放进池子
  3. 再原封不动地调用 `task.py` 的原有函数 —— 它们读池子时是纯内存操作，瞬间返回

这样既拿到了并发速度，又保证 `task.py` 保持 Kaggle 提交所需的原始形态，
统计口径也完全一致。

⚠️ 一个必须小心的细节
--------------------------------------------------------------------------------
池子的键是"提示词全文 + 温度"。同一道题会被问很多次，这些次是**不同的独立样本**，
必须按次数逐个入池、逐个弹出。如果偷懒只缓存一份、重复命中，
就会让 A 组的 10 次采样全部拿到同一个值 → confidence_std 恒为 0，
整个信度实验直接作废。本脚本按"计数"预取正是为了避免这个陷阱。

用法
--------------------------------------------------------------------------------
  # 小规模验证链路（4 道题 × 3 次重复）
  python run_deepseek.py --limit 4 --repeats 3

  # 全量运行
  python run_deepseek.py --repeats 10

  # 换模型
  python run_deepseek.py --model deepseek-reasoner

凭据读取顺序：环境变量 DEEPSEEK_API_KEY → Hermes 的 .env
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# 让 task.py 可以被直接 import（脚本和 task.py 同目录）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import task as T  # noqa: E402


API_URL = "https://api.deepseek.com/chat/completions"
ENV_CANDIDATES = [
    os.path.expanduser("~/AppData/Local/hermes/.env"),
    r"C:/Users/lrx/AppData/Local/hermes/.env",
]


def load_api_key() -> str:
    """优先环境变量，其次 Hermes 的 .env。找不到就明确报错，不做任何猜测。"""
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    for path in ENV_CANDIDATES:
        if os.path.exists(path):
            txt = open(path, encoding="utf-8", errors="ignore").read()
            m = re.search(r"^DEEPSEEK_API_KEY=(\S+)", txt, re.M)
            if m:
                return m.group(1).strip()
    raise SystemExit(
        "找不到 DEEPSEEK_API_KEY。\n"
        "请设置环境变量，或在 Hermes 的 .env 里配置该项。"
    )


# ============================================================
# 模型适配器
# ============================================================

class DeepSeekLLM:
    """
    把 DeepSeek 的 HTTP 接口包装成 `task.py` 期望的 `llm.prompt()` 形态。

    对外只暴露两个方法：
      prompt(prompt, temperature=None)  —— 从池里取一条；池空则实时补一次
      prefetch(plan)                    —— 并发预热，plan = {(提示词, 温度): 次数}
    """

    def __init__(self, api_key: str, model: str = "deepseek-chat",
                 default_temperature: float = 1.0, max_tokens: int = 320,
                 concurrency: int = 8, retries: int = 4, timeout: int = 90,
                 refill_rounds: int = 3):
        self.api_key = api_key
        self.model = model
        # 模型默认温度：A 组 / 筛题 / B 组都走这个（不显式指定温度）
        # 记下来写进报告，否则读者不知道 A 组到底是什么温度跑的
        self.default_temperature = default_temperature
        self.max_tokens = max_tokens
        self.concurrency = concurrency
        self.retries = retries
        self.timeout = timeout
        self.refill_rounds = refill_rounds

        self.pool: dict[tuple[str, float | None], list[str | None]] = {}
        self.lock = threading.Lock()

        # 运行统计（要如实写进测试报告）
        self.calls = 0            # 成功调用次数
        self.errors = 0           # 最终失败次数
        self.cache_miss = 0       # 池中缺样本、被迫实时补跑的次数
        self.tok_in = 0
        self.tok_out = 0
        self.latency: list[float] = []
        self.error_samples: list[str] = []

    # ---------------- 单次调用 ----------------

    def _one_call(self, prompt: str, temperature: float | None) -> str | None:
        """发一次请求。成功返回文本，最终失败返回 None（不抛异常）。"""
        temp = self.default_temperature if temperature is None else temperature
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temp,
            "max_tokens": self.max_tokens,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_err = None

        for attempt in range(self.retries):
            req = urllib.request.Request(
                API_URL,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + self.api_key,
                },
            )
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    obj = json.loads(r.read().decode("utf-8"))
                content = obj["choices"][0]["message"]["content"]
                usage = obj.get("usage") or {}
                with self.lock:
                    self.calls += 1
                    self.latency.append(time.time() - t0)
                    self.tok_in += usage.get("prompt_tokens", 0)
                    self.tok_out += usage.get("completion_tokens", 0)
                return content

            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = e.read().decode("utf-8", "ignore")[:300]
                except Exception:
                    pass
                last_err = f"HTTP {e.code} {detail}"
                # 限流与服务端错误值得重试；4xx 里其余的（如密钥错误）重试没意义
                if e.code in (408, 429, 500, 502, 503, 504) and attempt < self.retries - 1:
                    time.sleep(min(2 ** attempt, 8) + 1)
                    continue
                break

            except Exception as e:  # 超时、连接被断、JSON 解析失败等
                last_err = f"{type(e).__name__}: {e}"
                if attempt < self.retries - 1:
                    time.sleep(min(2 ** attempt, 8) + 1)
                    continue
                break

        with self.lock:
            self.errors += 1
            if len(self.error_samples) < 10:
                self.error_samples.append(str(last_err)[:200])
        return None

    # ---------------- 并发预热 ----------------

    def prefetch(self, plan: dict[tuple[str, float | None], int],
                 desc: str = "", progress_every: int = 40) -> None:
        """
        按 plan 并发跑完一批请求，结果按 (提示词, 温度) 归组替换进池。

        plan 的 value 是**需要几个独立样本**，不是"要不要跑"。
        这是本脚本最关键的一点：同题重复采样必须拿到互不相同的样本。
        """
        todo: list[tuple[tuple[str, float | None], str, float | None]] = []
        for (prompt, temp), n in plan.items():
            for _ in range(n):
                todo.append(((prompt, temp), prompt, temp))

        buckets: dict[tuple[str, float | None], list[str]] = {k: [] for k in plan}
        total_planned = len(todo)

        for rnd in range(self.refill_rounds):
            if not todo:
                break
            failed = []
            done = 0
            total = len(todo)
            with ThreadPoolExecutor(max_workers=self.concurrency) as ex:
                futures = {}
                for item in todo:
                    _, p, t = item
                    futures[ex.submit(self._one_call, p, t)] = item
                for fut in as_completed(futures):
                    item = futures[fut]
                    key = item[0]
                    try:
                        result = fut.result()
                    except Exception as e:      # 理论上不会走到（_one_call 自己兜住了）
                        result = None
                        with self.lock:
                            self.error_samples.append(f"worker: {e}")
                    if result is None:
                        failed.append(item)
                    else:
                        buckets[key].append(result)
                    done += 1
                    if progress_every and (done % progress_every == 0 or done == total):
                        print(f"    [{desc}] {done}/{total}", flush=True)
            todo = failed
            if failed:
                print(f"    [{desc}] 第 {rnd + 1} 轮有 {len(failed)} 次失败，重试…", flush=True)

        if todo:
            print(f"    [{desc}] ⚠️ 最终仍有 {len(todo)} 次调用失败，池中会缺样本", flush=True)

        self.pool = buckets
        short = sum(len(v) for v in buckets.values())
        print(f"    [{desc}] 池已就绪：{short}/{total_planned} 个样本", flush=True)

    # ---------------- 取样本 ----------------

    def prompt(self, prompt: str, temperature: float | None = None) -> str:
        """按 (提示词, 温度) 从池中弹出一个样本。池空时实时补跑一次。"""
        key = (prompt, temperature)
        bucket = self.pool.get(key)
        if bucket:
            v = bucket.pop()
            return "" if v is None else v

        with self.lock:
            self.cache_miss += 1
        result = self._one_call(prompt, temperature)
        return "" if result is None else result

    # ---------------- 运行时统计 ----------------

    def stats(self) -> dict:
        n = len(self.latency)
        return {
            "模型": self.model,
            "默认温度(A/B组与筛题)": self.default_temperature,
            "并发数": self.concurrency,
            "成功调用次数": self.calls,
            "最终失败次数": self.errors,
            "池外实时补跑次数": self.cache_miss,
            "输入 token 合计": self.tok_in,
            "输出 token 合计": self.tok_out,
            "平均单次延迟(秒)": round(sum(self.latency) / n, 3) if n else None,
            "错误样本": self.error_samples,
        }


# ============================================================
# 主流程
# ============================================================

def parse_fail_rate(records: list[dict]) -> float | None:
    if not records:
        return None
    bad = sum(1 for r in records if not r.get("parse_ok"))
    return round(bad / len(records), 4)


# ============================================================
# 重新计分（不重新调用模型）
# ============================================================
# 场景：发现判分逻辑有 bug，要修正。
#
# 此时【不要重跑采样】。重跑会引入新的随机性，让你分不清"指标变了"
# 是因为判分修好了，还是因为模型这次抽得不一样。
# 正确做法是保留原始回复，只换判分函数重新计分 ——
# 这样修正前后的差异可以一条一条归因。
#
# 本项目真实发生过一次：模型答"国际儿童节（又称六一国际儿童节）"、
# 标准答案"儿童节"，因为括号解释把长度差撑开而被判错。
# 修正判分后用本函数重算，全批只有 1 条记录发生翻转。

def _rebuild_a(records: list[dict], n_repeats: int) -> dict:
    return {
        "experiment": "A · 重复采样",
        "n_repeats": n_repeats,
        "records": records,
        "metrics": T.compute_metrics(records),
        "reliability_overall": T.reliability_by_group(records, "全部题目"),
        "reliability_by_difficulty": {
            d: T.reliability_by_group([r for r in records if r["difficulty"] == d], f"难度={d}")
            for d in ("easy", "medium", "hard")
        },
    }


def _rebuild_b(front: list[dict], back: list[dict]) -> dict:
    m_front, m_back = T.compute_metrics(front), T.compute_metrics(back)
    cs_front, cs_back = T.calibration_score(m_front), T.calibration_score(m_back)
    delta = round(cs_front - cs_back, 4) if (cs_front is not None and cs_back is not None) else None

    cf = [r["confidence"] for r in front if r["confidence"] is not None]
    cb = [r["confidence"] for r in back if r["confidence"] is not None]
    conf_delta = round(sum(cf) / len(cf) - sum(cb) / len(cb), 4) if (cf and cb) else None

    return {
        "experiment": "B · 顺序对照",
        "records_front": front,
        "records_back": back,
        "metrics_front": m_front,
        "metrics_back": m_back,
        "calibration_score_front": cs_front,
        "calibration_score_back": cs_back,
        "delta_order": delta,
        "mean_confidence_delta": conf_delta,
        "interpretation": T._interpret_order(delta),
    }


def _rebuild_c(records: list[dict], n_repeats: int, temp_applied: bool) -> dict:
    return {
        "experiment": "C · 温度对照（temperature=0）",
        "n_repeats": n_repeats,
        "temperature_actually_applied": temp_applied,
        "records": records,
        "metrics": T.compute_metrics(records),
        "reliability_overall": T.reliability_by_group(records, "温度=0"),
    }


def rescore(in_path: str, out_path: str) -> None:
    """用当前版本的判分逻辑重算已有结果的 correct 与全部统计指标。"""
    print(f"重新计分（不重新调用模型）：{in_path}")
    payload = json.load(open(in_path, encoding="utf-8"))
    tol = {it.id: it.tolerance for it in T.QUESTION_BANK}

    diffs: list[dict] = []

    def fix(records: list[dict], tag: str) -> None:
        for r in records:
            old = bool(r.get("correct"))
            new = bool(r.get("parse_ok")) and T.is_correct(
                r.get("model_answer"), r.get("gold_answer"), tol.get(r["id"], 0.0)
            )
            if new != old:
                diffs.append({
                    "组": tag,
                    "题号": r["id"],
                    "trial": r.get("trial"),
                    "修正前": old,
                    "修正后": new,
                    "模型答案": r.get("model_answer"),
                    "标准答案": r.get("gold_answer"),
                })
            r["correct"] = new

    fix(payload["records_a"], "A")
    fix(payload["records_b_front"], "B-前置")
    fix(payload["records_b_back"], "B-后置")
    fix(payload["records_c"], "C")

    n_rep = int(payload["report"]["A_重复采样"]["repeats_per_item"] or 10)
    temp_applied = payload["report"]["C_温度对照"]["温度参数是否真的生效"]

    exp_a = _rebuild_a(payload["records_a"], n_rep)
    exp_b = _rebuild_b(payload["records_b_front"], payload["records_b_back"])
    exp_c = _rebuild_c(payload["records_c"], n_rep, temp_applied)

    payload["report"] = T.build_report(exp_a, exp_b, exp_c, payload["report"]["screening"])
    entry = {
        "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "发生翻盘的记录数": len(diffs),
        "明细": diffs,
        "说明": ("仅替换判分函数后重新计分，原始模型回复一个字没动。"
                 "这样修正前后的差异可以逐条归因，而不是被重新采样的随机性掩盖。"),
    }
    # 追加而不是覆盖 —— 判分 bug 可能修不止一次，历史要留全
    payload.setdefault("rescore_history", []).append(entry)
    payload["rescore"] = entry

    meta = payload.setdefault("run_meta", {})
    meta["A组解析失败率"] = parse_fail_rate(payload["records_a"])
    meta["B组_前置_解析失败率"] = parse_fail_rate(payload["records_b_front"])
    meta["B组_后置_解析失败率"] = parse_fail_rate(payload["records_b_back"])
    meta["C组解析失败率"] = parse_fail_rate(payload["records_c"])
    meta["重新计分"] = f"于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 用修正后的判分逻辑重算"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n翻盘记录 {len(diffs)} 条：")
    for d in diffs:
        print(f"  [{d['组']}] {d['题号']} trial={d['trial']} "
              f"{d['修正前']} → {d['修正后']}  答案={d['模型答案']!r}")
    print("\n修正后的核心指标：")
    print(json.dumps({
        "效度层": payload["report"]["A_重复采样"]["效度层"],
        "ICC": payload["report"]["A_重复采样"]["icc"],
        "C组ICC": payload["report"]["C_温度对照"]["icc"],
        "温度占比": payload["report"]["A_vs_C_温度占比"],
        "headline": payload["report"].get("headline"),
    }, ensure_ascii=False, indent=2))
    print(f"\n已保存 → {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="用真实模型跑 ReCal 基准")
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--limit", type=int, default=0,
                    help="只用题库前 N 道题（0 = 全部 60 题）")
    ap.add_argument("--repeats", type=int, default=10, help="A/C 组的重复采样次数")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--screen-rounds", type=int, default=2)
    ap.add_argument("--out", default="real_run_results.json")
    ap.add_argument("--tag", default="", help="这批结果的标签，便于区分不同 run")
    ap.add_argument("--rescore", default="", metavar="结果JSON",
                    help="不重新调用模型，只用当前判分逻辑重算已有结果")
    args = ap.parse_args()

    if args.rescore:
        rescore(args.rescore, args.out)
        return

    items = list(T.QUESTION_BANK)
    if args.limit > 0:
        items = items[:args.limit]

    llm = DeepSeekLLM(load_api_key(), model=args.model, concurrency=args.concurrency)

    run_start = time.time()
    print("=" * 72)
    print(f"ReCal 真实模型运行 · {args.model}")
    if args.tag:
        print(f"标签：{args.tag}")
    print(f"题目 {len(items)} 道 · A/C 组重复 {args.repeats} 次 · 并发 {args.concurrency}")
    print("=" * 72)

    # ---------------- 阶段 1 · 筛题 ----------------
    print(f"\n### 阶段 1/4 · 筛题（{len(items)} 题 × {args.screen_rounds} 轮裸答）")
    plan_screen: dict[tuple[str, float | None], int] = {}
    for it in items:
        q = T.PROMPT_FRONT.format(question=it.question)
        plan_screen[(q, None)] = args.screen_rounds
    llm.prefetch(plan_screen, desc="筛题")

    kept, dropped = T.screen_items(llm, items, rounds=args.screen_rounds, verbose=False)
    screening_info = {
        "原始题数": len(items),
        "筛后保留": len(kept),
        "剔除": len(dropped),
        "被剔除的题": [i.id for i in dropped],
        "说明": ("两轮裸答都答对的题才保留。筛题会刻意压低准确率——"
                 "留下的都是模型「应该会」的题，此时答错才可能来自校准失败。"),
    }
    print(f"    保留 {len(kept)} 题，剔除 {len(dropped)} 题"
          f"（{'、'.join(i.id for i in dropped) if dropped else '无'}）")

    if not kept:
        print("\n⚠️ 所有题都被筛掉了。筛题是刻意严格的：任何一题只要有一轮没答对就会被剔除。")
        print("   这可能说明该模型在本题库上表现不佳。处理办法：换模型，或用 --limit 观察小样本。")

    # ---------------- 阶段 2 · 预取 A/B/C ----------------
    print(f"\n### 阶段 2/4 · 并发预取 A/B/C 三组的全部请求")
    need = args.repeats * 2 + 2      # 每题：A 组 repeats + C 组 repeats + B 组 front/back 各 1
    print(f"    每题需要 {need} 个样本（A 组 {args.repeats} + C 组 {args.repeats} "
          f"+ B 组 2），共 {len(kept) * need} 次请求")
    plan_abc: dict[tuple[str, float | None], int] = {}
    for it in kept:
        front = T.PROMPT_FRONT.format(question=it.question)
        back = T.PROMPT_BACK.format(question=it.question)
        # A 组 repeats 次 + B 组 front 1 次 —— 提示词完全相同，所以合并计数
        plan_abc[(front, None)] = args.repeats + 1
        plan_abc[(back, None)] = 1                  # B 组 back
        plan_abc[(front, 0.0)] = args.repeats       # C 组
    llm.prefetch(plan_abc, desc="A/B/C")

    # ---------------- 阶段 3 · 跑三组实验 ----------------
    print("\n### 阶段 3/4 · 计算（读池子，纯内存）")
    exp_a = T.run_experiment_a(llm, kept, n_repeats=args.repeats, verbose=False)
    print("    A 组 · 重复采样 完成")
    exp_b = T.run_experiment_b(llm, kept, verbose=False)
    print("    B 组 · 顺序对照 完成")
    exp_c = T.run_experiment_c(llm, kept, n_repeats=args.repeats, verbose=False)
    print("    C 组 · 温度对照 完成")

    report = T.build_report(exp_a, exp_b, exp_c, screening_info)

    # ---------------- 阶段 4 · 落盘 ----------------
    print("\n### 阶段 4/4 · 汇总与落盘")

    runtime = dict(llm.stats())
    runtime["本批范围"] = "全部题库" if args.limit == 0 else f"题库前 {args.limit} 题"
    runtime["开始时间(本地)"] = datetime.fromtimestamp(run_start).strftime("%Y-%m-%d %H:%M:%S")
    runtime["墙钟耗时(秒)"] = round(time.time() - run_start, 1)
    runtime["A组解析失败率"] = parse_fail_rate(exp_a["records"])
    runtime["B组_前置_解析失败率"] = parse_fail_rate(exp_b["records_front"])
    runtime["B组_后置_解析失败率"] = parse_fail_rate(exp_b["records_back"])
    runtime["C组解析失败率"] = parse_fail_rate(exp_c["records"])
    runtime["温度参数是否真的生效(C组)"] = exp_c["temperature_actually_applied"]
    if args.tag:
        runtime["标签"] = args.tag

    payload = {
        "run_meta": runtime,
        "report": report,
        "records_a": exp_a["records"],
        "records_b_front": exp_b["records_front"],
        "records_b_back": exp_b["records_back"],
        "records_c": exp_c["records"],
    }

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.out)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # ---------------- 屏幕摘要 ----------------
    print("\n" + "=" * 72)
    print("报告摘要")
    print("=" * 72)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("\n" + "-" * 72)
    print("运行元数据")
    print("-" * 72)
    print(json.dumps(runtime, ensure_ascii=False, indent=2))
    print(f"\n已保存 → {out_path}")


if __name__ == "__main__":
    main()
