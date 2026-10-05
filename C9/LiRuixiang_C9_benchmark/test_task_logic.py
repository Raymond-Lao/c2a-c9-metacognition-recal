"""
逻辑自检 / Unit checks —— 不依赖 Kaggle 环境，可直接用本地 Python 运行。

用途：
  1. 验证题库完整性（题量、分层比例、id 唯一性、容差标注规则）
  2. 验证纯逻辑函数：parse_response / is_correct / compute_metrics / ICC
  3. 用假模型端到端跑一遍 A/B/C 三组实验，确认统计链路算得对
  4. 作为"可复现性"的证据 —— C9 的"技术实现"维度会看这个

运行：
  python test_task_logic.py

前置：本文件用 stub 顶替了 kaggle_benchmarks，所以本地没装该库也能跑。
预期输出以「自检结果：全部通过」结尾。
"""

import hashlib
import os
import sys
import types

# ------------------------------------------------------------
# 用 stub 顶替 kaggle_benchmarks，让本文件能脱离 Kaggle 环境运行
# ------------------------------------------------------------
kbench = types.ModuleType("kaggle_benchmarks")


class _Assertions:
    def assert_true(self, cond, expectation=""):
        if not cond:
            raise AssertionError(expectation)

    def assert_contains_regex(self, pat, text, expectation=""):
        import re
        if not re.search(pat, text or ""):
            raise AssertionError(expectation)


kbench.assertions = _Assertions()
kbench.llm = None


def _task(name):
    def deco(fn):
        return fn
    return deco


kbench.task = _task
sys.modules["kaggle_benchmarks"] = kbench

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import task as T  # noqa: E402


# ------------------------------------------------------------
# 假模型
# ------------------------------------------------------------
class CalibrationFakeLLM:
    """
    一个"看起来校准得不错、其实在抖"的模型。

    设计意图：它正好复现本基准要抓的那种情况 ——
    校准分看着还行，但同一道题重复问，它报的确信度每次都不一样。
    如果自检能算出低 ICC，说明统计链路真的在工作。

    抖动是确定性的（用题面 + 调用序号做哈希），保证每次运行结果一致。
    """

    def __init__(self):
        self.by_question = {it.question: it for it in T.QUESTION_BANK}
        self.calls = {}

    def _jitter(self, key: str, span: int = 12) -> float:
        h = hashlib.md5(key.encode("utf-8")).hexdigest()
        return (int(h[:8], 16) % (2 * span + 1)) - span

    def prompt(self, p, temperature=None):
        # 前置/后置模板的差别就在 '{' 后面先出现哪个字段
        is_front = '{"confidence"' in p
        q = p.split("问题：")[-1].strip()
        item = self.by_question.get(q)

        # 计数：同一道题的调用序号，用来制造"每次不一样"
        self.calls[q] = self.calls.get(q, 0) + 1
        nth = self.calls[q]

        if item is None:
            return '{"confidence": 50, "answer": "不知道"}'

        # 基础确信度按难度给：简单题更自信
        base = {"easy": 95.0, "medium": 78.0, "hard": 62.0}.get(item.difficulty, 70.0)
        jit = self._jitter(f"{item.id}|{nth}")

        # 模拟"温度越低越稳"：温度 0 时抖动减半。
        # 这样 C 组（温度对照）才会产出与 A 组不同的数字，
        # 否则 temperature_share 恒等于 1.0，等于这条链路没被真正测到。
        if temperature == 0.0:
            jit = jit / 2.0

        # 后置组系统性低一点 —— 用来验证 B 组能不能测出顺序效应
        if not is_front:
            base -= 8.0

        conf = max(1, min(100, round(base + jit)))

        # hard 题有约 1/3 会答错（模拟"过度自信"）
        wrong = item.difficulty == "hard" and self._jitter(f"{item.id}|wrong") > 6
        answer = "错答" if wrong else item.answer

        if is_front:
            return f'{{"confidence": {conf}, "answer": "{answer}"}}'
        return f'{{"answer": "{answer}", "confidence": {conf}}}'


def main():
    ok = True

    def check(flag_ok, label):
        nonlocal ok
        if not flag_ok:
            ok = False
        print(f"  [{'OK  ' if flag_ok else 'FAIL'}] {label}")

    # ========================================================
    print("=== 1) 题库体检 ===")
    bank = T.QUESTION_BANK
    check(len(bank) == 60, f"总题数 = {len(bank)}（目标 60）")

    dist = {}
    for it in bank:
        dist[it.difficulty] = dist.get(it.difficulty, 0) + 1
    check(dist.get("easy") == 24, f"easy = {dist.get('easy')}（目标 24，占 40%）")
    check(dist.get("medium") == 24, f"medium = {dist.get('medium')}（目标 24，占 40%）")
    check(dist.get("hard") == 12, f"hard = {dist.get('hard')}（目标 12，占 20%）")

    ids = [it.id for it in bank]
    check(len(ids) == len(set(ids)), f"id 唯一性（{len(ids)} 个 id，{len(set(ids))} 个不同）")
    check(all(it.answer.strip() for it in bank), "每题都有非空标准答案")
    check(all(it.difficulty in ("easy", "medium", "hard") for it in bank),
          "difficulty 取值合法")

    # 容差只应出现在"本身就是估算"的题上
    tol_items = [it.id for it in bank if it.tolerance > 0]
    check(len(tol_items) <= 8, f"开了容差的题只有 {len(tol_items)} 道（{', '.join(tol_items)}）")

    # ========================================================
    print("\n=== 2) parse_response：格式容错 ===")
    cases = [
        ('{"confidence": 80, "answer": "x"}', True, "标准 JSON"),
        ('```json\n{"confidence": 50, "answer": "y"}\n```', True, "代码块包裹"),
        ('前言 {"confidence": 30, "answer": "z"} 后记', True, "夹在文本里"),
        ('{"confidence": 150, "answer": "bad"}', False, "超出 0-100 范围"),
        ('完全不是 JSON', False, "非 JSON"),
        ('', False, "空回复"),
        ('{"answer": "只有答案"}', False, "缺 confidence 字段"),
        ('{"confidence": 70}', False, "缺 answer 字段"),
    ]
    for raw, expect, desc in cases:
        got = T.parse_response(raw)["parse_ok"]
        check(got == expect, f"{desc}: expect={expect} got={got}")

    # ========================================================
    print("\n=== 3) 确信度归一化（模型不听话时的兜底）===")
    conf_cases = [
        (88, 88.0, "整数"),
        ("88", 88.0, "字符串数字"),
        ("88%", 88.0, "带百分号"),
        (0.88, 88.0, "0-1 之间的小数自动换算成百分数"),
        (150, None, "超出上界"),
        (-5, None, "低于下界"),
        ("abc", None, "非数字"),
        (None, None, "空值"),
    ]
    for raw, expect, desc in conf_cases:
        got = T._normalize_confidence(raw)
        check(got == expect, f"{desc}: _normalize_confidence({raw!r}) = {got}")

    # ========================================================
    print("\n=== 4) is_correct：判分逻辑 ===")
    jc = [
        ("9", "9", 0.0, True, "完全一致"),
        ("380000", "384400", 0.1, True, "估算题，容差内"),
        ("300000", "384400", 0.1, False, "估算题，超容差"),
        ("1904", "1906", 0.0, False, "回归用例：精确题曾被 10% 容差误判为正确"),
        ("1906", "1906", 0.0, True, "精确匹配"),
        ("大约 9 只", "9", 0.0, True, "文本里含数字"),
        ("比邻星", "比邻星", 0.0, True, "纯文本题，完全一致"),
        ("不是", "是", 0.0, False, "回归用例：'是'是'不是'的子串，必须挡住否定反转"),
        ("是", "不是", 0.0, False, "反向否定反转同样要挡住"),
        ("是的", "是", 0.0, True, "语气词扩展应判对"),
        ("达芬奇", "列奥纳多·达·芬奇", 0.0, True, "简称对应全称"),
        ("纽约市", "纽约", 0.0, True, "答案比标准答案略长"),
        # ---- 下面 4 条是【跑真实模型之后】补的回归用例 ----
        # 本地自检 59 项全绿时并没有暴露这个 bug：模型答"国际儿童节（又称六一国际儿童节）"、
        # 标准答案"儿童节"，语义完全正确，却因为括号里的解释把长度差撑到 11 而被判错。
        # 说明"自检通过"≠"测量正确"，必须拿真实数据再验一遍。
        ("国际儿童节（又称六一国际儿童节）", "儿童节", 0.0, True,
         "回归用例：括号补充撑开长度差，曾被误判为错"),
        ("H2O（水）", "H2O", 0.0, True, "回归用例：括号补充不该影响判分"),
        ("南极洲（极地荒漠）", "南极洲", 0.0, True, "回归用例：中文括号补充"),
        ("月球[地球的卫星]", "月球", 0.0, True, "回归用例：方括号补充"),
        # ---- 数值题的中文量级单位（同样是跑真实模型后才补的）----
        # 问光速，标准答案 "300000"，模型答 "30万" —— 同一个数，
        # 最初只抽阿拉伯数字、读成 30，于是被判错。
        ("30万", "300000", 0.0, True, "回归用例：中文量级后缀 万"),
        ("30万", "300000", 0.1, True, "同上，走容差分支"),
        ("1.5万", "15000", 0.0, True, "小数 + 万"),
        ("3亿", "300000000", 0.0, True, "中文量级后缀 亿"),
        ("2千", "2000", 0.0, True, "中文量级后缀 千"),
        ("30万", "300001", 0.1, True, "归一化后落在容差内"),
        ("20万", "300000", 0.1, False, "归一化后仍超出容差"),
        ("H2O", "H2O", 0.0, True, "含数字但非数值的答案不该被当成数值题"),
        ("错答", "9", 0.0, False, "完全无关"),
        (None, "9", 0.0, False, "空答案"),
        ("", "9", 0.0, False, "空字符串"),
    ]
    for a, g, tol, expect, desc in jc:
        got = T.is_correct(a, g, tol)
        check(got == expect, f"{desc}: is_correct({a!r}, {g!r}, tol={tol}) = {got}")

    # ========================================================
    print("\n=== 5) compute_metrics：手算校验 ===")
    recs = [{"confidence": 90, "correct": False, "difficulty": "hard"}] * 10
    got = T.compute_metrics(recs)
    for k, v in {"accuracy": 0.0, "mean_confidence": 0.9, "gap": 0.9, "ECE": 0.9}.items():
        check(abs(got[k] - v) < 1e-9, f"全报 90% 却全错 → {k}: expect={v} got={got[k]}")

    recs = ([{"confidence": 70, "correct": True, "difficulty": "easy"}] * 7 +
            [{"confidence": 70, "correct": False, "difficulty": "easy"}] * 3)
    got = T.compute_metrics(recs)
    check(abs(got["ECE"]) < 1e-9 and abs(got["gap"]) < 1e-9,
          f"完美校准（报 70% 恰好 70% 对）→ ECE={got['ECE']} gap={got['gap']}")

    check(T.calibration_score(got) == 1.0, f"校准分 = 1 − ECE = {T.calibration_score(got)}")

    # ========================================================
    print("\n=== 6) ICC(1,1)：三个可精确手算的用例 ===")
    # 用例 A：组内完全没有变异 → 信度应为理论上限 1.0
    icc_a = T.icc_1_1([[80, 80, 80], [60, 60, 60], [40, 40, 40]])
    check(icc_a["icc"] == 1.0,
          f"组内零变异（完美信度）→ ICC = {icc_a['icc']}（期望 1.0）")

    # 用例 B：组间均值完全相同、组内全在跳 → 信度应为理论下界 −1/(n−1) = −0.5
    icc_b = T.icc_1_1([[80, 60, 40], [60, 40, 80], [40, 80, 60]])
    check(icc_b["icc"] == -0.5,
          f"组间无差异、组内全抖动 → ICC = {icc_b['icc']}（期望 −0.5，即理论下界）")

    # 用例 C：中间情形。手算：MSB=1200, MSW=4, n̄=3 → 1196/1208 ≈ 0.9901
    icc_c = T.icc_1_1([[90, 88, 92], [70, 72, 68], [50, 52, 48]])
    check(icc_c["icc"] == 0.9901,
          f"高信度情形 → ICC = {icc_c['icc']}（期望 0.9901；MSB={icc_c['MSB']}, MSW={icc_c['MSW']}）")
    check("excellent" in icc_c["interpretation"],
          f"判读等级 → {icc_c['interpretation']}")

    # 数据不足时必须返回 None，而不是编一个数字
    icc_d = T.icc_1_1([[80, 82]])
    check(icc_d["icc"] is None, f"只有 1 道题 → ICC = {icc_d['icc']}（应为 None，宁缺勿假）")

    # 判读阈值（Koo & Li 2016）
    check("poor" in T.interpret_icc(0.30), "ICC=0.30 → poor")
    check("moderate" in T.interpret_icc(0.60), "ICC=0.60 → moderate")
    check("good" in T.interpret_icc(0.80), "ICC=0.80 → good")
    check("excellent" in T.interpret_icc(0.95), "ICC=0.95 → excellent")

    # ========================================================
    print("\n=== 7) 端到端：A 组（重复采样）===")
    llm = CalibrationFakeLLM()
    # 为控制自检耗时，只取题库的一个子集（分层抽样），逻辑完全一致
    subset = [it for it in T.QUESTION_BANK if it.id in
              ("e02", "e05", "e12", "m04", "m08", "m17", "h03", "h09")]
    exp_a = T.run_experiment_a(llm, subset, n_repeats=5, verbose=False)
    rel = exp_a["reliability_overall"]
    print(f"  题目数 {rel['n_items']}，每题重复 {rel['repeats_per_item']} 次")
    print(f"  平均确信度标准差 = {rel['mean_confidence_std']}")
    print(f"  ICC = {rel['icc']['icc']}（{rel['icc'].get('interpretation')}）")
    print(f"  效度层指标 = {exp_a['metrics']}")
    check(rel["icc"]["icc"] is not None, "A 组能算出 ICC")
    check(rel["mean_confidence_std"] is not None, "A 组能算出确信度标准差")

    # ========================================================
    print("\n=== 8) 端到端：B 组（顺序对照）===")
    llm2 = CalibrationFakeLLM()
    exp_b = T.run_experiment_b(llm2, subset, verbose=False)
    print(f"  校准分（前置）= {exp_b['calibration_score_front']}")
    print(f"  校准分（后置）= {exp_b['calibration_score_back']}")
    print(f"  Δ_order = {exp_b['delta_order']}")
    print(f"  解读：{exp_b['interpretation']}")
    check(exp_b["delta_order"] is not None, "B 组能算出 Δ_order")

    # ========================================================
    print("\n=== 9) 端到端：C 组（温度对照）+ 汇总报告 ===")
    llm3 = CalibrationFakeLLM()
    exp_c = T.run_experiment_c(llm3, subset, n_repeats=5, verbose=False)
    cmp_ac = T.compare_a_vs_c(exp_a, exp_c)
    print(f"  默认温度 std = {cmp_ac['std_default_temp']}，0 温度 std = {cmp_ac['std_zero_temp']}")
    print(f"  temperature_share = {cmp_ac['temperature_share']}")
    check(cmp_ac["temperature_share"] is not None, "能算出温度对抖动的贡献占比")

    report = T.build_report(
        exp_a, exp_b, exp_c,
        screening={"原始题数": 60, "筛后保留": 54, "剔除": 6, "被剔除的题": []},
    )
    print("\n  报告结构：")
    for k in report:
        print(f"    · {k}")
    check("headline" in report, f"报告含一句话结论：{report.get('headline')}")

    # ========================================================
    print("\n" + "=" * 52)
    print("自检结果：" + ("全部通过" if ok else "存在失败项"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
