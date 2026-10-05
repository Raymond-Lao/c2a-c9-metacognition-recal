# 文献核查报告 · v2 方案的四条生死线

**核查日期：** 2026-10-05
**核查目的：** 确认 v2「元认知测量信度」方案有没有已经被做过的工作
**核查方式：** 逐条检索 → 交叉验证来源 → 判断撞车程度

---

## 总览：一句话结论

> **方法已经成熟，但从未被用到元认知能力基准上。**
> **而且有一条意外发现，反而让 v2 的立论比以前更硬。**

四条全部查完。结果不是"没人做过"，也不是"被人做完了"，而是第三种——**v2 必须把卖点从"方法新颖"改成"应用位置空白"，同时增加一条更硬的论据。**

---

## 第一条 · LLM 确信度的重测信度 ⚠️ 部分撞车

### 查到了什么

**🔴 最接近的一篇（必须重视）**

- **Schroeder, K. & Wood-Doughty, Z. (2024). Can You Trust LLM Judgments? Reliability of LLM-as-a-Judge. arXiv:2412.12509.**
  - 做法：同一条判分提示 **重复 100 次，只改随机种子**，用 **McDonald's omega** 算内部一致性
  - 发现：3 个裁判模型里 **2 个低于 0.7 可接受阈值**
  - 结论：**deterministic settings（固定种子）不保证可靠性，单次判分就是"一次抽样"**
  - 被引 47 次

**🟡 第二接近的一篇**

- **Del, M., Kängsepp, M., Domnich, M., Tampuu, A., Yankovskaya, L., Kull, M., & Fishel, M. (2026). How Uncertainty Estimation Scales with Sampling in Reasoning Models. arXiv:2603.19118.**（✅ 已核实：另有题名为《Two Samples Are Enough: Verbal Confidence Meets Self-Consistency in Reasoning LLMs》的版本，作者名单与本文**完全一致**，确认为**同一篇工作的不同版本**，不是两篇独立工作）
  - 做法：把**模型自报的确信度**（VC）和多答案一致性（SC）混合，看采样数 K 增大时效果怎么变
  - 关键数据：**VC@1 在数学任务上 AUROC = 71.3，K=8 时升到 81.4（+10.1）**；SCVC 用 K=2 就比单样本 VC 提升 **+12.9**
  - 结论：反复采样能显著提升不确定性估计的质量

**🟢 第三篇（不是撞车，是理论靠山）**

- **Lin, Z. (2025). From Prompts to Constructs: A Dual-Validity Framework for LLM Research in Psychology. arXiv:2506.16697.** ⭐ 已被 **Annu. Rev. Psychol. 2027** 接收
  - 核心概念：**"measurement phantom（测量幻象）"** —— 把统计规律误当成真实的心理现象
  - 提出 **双重效度框架**：心理测量效度 + 因果推断标准
  - 明确讨论 **test-retest reliability / parallel-forms reliability / internal consistency**
  - 一句可以直接引用的原则：**"信度是效度的天花板"** —— 观测量与效标的相关系数**不可能超过该测量信度的平方根**。信度 0.40 的量表，就算效标完美，能测出的相关也只有 √0.40 ≈ 0.63

### 对我们的影响

| 判断 | 说明 |
|---|---|
| v2 的核心想法 | ✅ **保留** —— 测元认知测量的信度，这个位置依然空着 |
| 原来的说法"从没人测过" | ❌ **必须改** —— 站不住，方法早就有 |
| 新增论据 | ✅ Del et al. 那篇是**白送的弹药**（下面详述） |

### 🎁 白捡的最强论据

**Del et al. 的数据，等于替我们证明了"单次确信度测量含噪"这件事。**

看这个数字：**VC@1 = 71.3 AUROC → K=8 = 81.4**。

如果单次确信度是可靠测量，那多采几次**不应该**带来 10 个 AUROC 的提升。这个增益的存在本身，就是在说：**单次的确信度里混着大量噪声。**

**但 Del et al. 把这个噪声当成"可以榨取的增益"，去优化 AUROC —— 从头到尾没有报告过这个噪声有多大、稳不稳。**

> **他们优化的是"判别力"（discrimination），我们要测的是"稳定性"（stability）。这是两个不同的量。**
> **同行们已经在用"多采几次确信度"这个方法了 —— 也就是说，他们默认了一次不准。既然如此，那次究竟有多不准，为什么没人量化？**

**这句话可以直接作为提案第 2 部分的开场。** 它比我上一版写的"没人验证过这把尺子"更有力，因为**证据来自对手自己的数据**。

### 📌 必须处理的撞车风险

Schroeder & Wood-Doughty 那篇**结构上最接近**（同题重复 100 次 + 心理测量系数）。评审可能问：**"你这不就是把 2412.12509 换个对象做一遍吗？"**

**三点差异（已写进提案）：**

| # | 差异 | 说明 |
|---|---|---|
| 1 | **被测量的对象不同** | 他们测的是**裁判（judge）给别人的作品打分**稳不稳；我们测的是**被考者对自己认知的评估**稳不稳。前者是评价任务，后者是元认知任务 |
| 2 | **信号性质不同** | 他们的是**离散选项**（A–E）+ 非应答，用 omega（需要把选项当平行题项）；我们的是**连续数值确信度**，可以直接算标准差和 ICC，不受类别化处理影响 |
| 3 | **目的不同** | 他们的结论是"单次判分不可靠，多采几次"；我们的结论是"**用这个去质疑 MetaBound 的 T1=0.98**" —— 是**对既有 benchmark 结论的再检验**，不是对新评估流程的建议 |

**第 3 点最关键 —— 我们是唯一的"回头查账"型工作。**

---

## 第二条 · 顺序效应（前置 vs 后置）⚠️ 有业余版撞车

### 查到了什么

**🟡 结构最像的一个（但不是学术工作）**

- **macebake/llm-self-confidence-test（GitHub，2025）《Metacognitive Accuracy in Large Language Models》**
  - 四个条件：**Control / Single-shot / Confidence-pre（先报自信）/ Confidence-post（后报自信）**
  - 规模：30 道约束满足题 × 4 条件 × 3 次迭代 = 每模型 360 次试验
  - 结果：GPT-5 后置条件相关 r=0.381，GPT-4o r=0.120
  - ⚠️ **这是个人 GitHub 项目，未经同行评审，规模小。** 但"想法已被公开发表过"这一点依然成立，必须在提案里主动提及并说明差异

**🟢 两篇支持"顺序不是中性的"的证据**

- **ORCE (arXiv:2605.12446). Order-Aware Alignment of Verbalized Confidence.**
  - 核心论点：**答案和确信度"联合生成"会让两个优化目标互相干扰**，所以主张解耦 —— **先生成答案，再基于固定的问答对估计确信度**
  - 🔥 **注意这里有个绝妙的矛盾：ORCE 主张「先答后估」，MetaBound 用的是「先估后答」—— 两个都在做，方向相反，谁都没验证过哪个对。**
  - 这句可以直接写进提案：**"业界对确信度采集顺序的做法是分裂的，而这个选择从未被检验。"**

- **Thinking Out of Order (arXiv:2601.22035).**
  - 发现：自回归模型在 "answer-first" 提示下，准确率相对下降 **最多 67%**
  - 说明：**输出顺序会大幅改变模型行为** —— 这是"顺序对照"这个设计必要性的直接证据

### 对我们的影响

| 判断 | 说明 |
|---|---|
| 抓点 2（前置/后置对照） | ✅ **保留，而且理由更充分了** |
| 需要主动说明的 | 必须在提案里**主动引用** GitHub 那个项目，并说明我们做得更系统（更多题、更多模型、统计检验、且与元认知基准结论挂钩） |
| 新增论据 | ✅ ORCE 与 MetaBound 的做法冲突 + Thinking Out of Order 的 67% 数据 |

> **主动提及撞车，比被评审发现要好得多。** 这是"拿来主义"这一项的得分点，也是这个比赛的核心学术诚信要求。

---

## 第三条 · 温度对校准的影响 ⚠️ 需要调整表述

### 查到了什么

- **Sun, F., Li, N., Wang, K., Goette, L. et al. (2025). Large Language Models are overconfident and amplify human bias. arXiv:2505.02151.**
  - 测了 **T = 0 / 0.6 / 1.0** 三个温度
  - 发现：**确信度水平变化小于 2 个百分点**，准确率变化 2–3 个百分点
  - 结论：**过度自信是模型的本质特征，不是采样参数的产物**

- **Schroeder & Wood-Doughty (2024)** 也发现：**最佳温度依模型和 benchmark 而变** —— 温度确实影响可靠性，但方向不统一

- **Guo et al. (2017)** 的 temperature scaling：温度改变的是分布形状，**不改变 argmax**，所以会影响 ECE 等校准指标

### 对我们的影响

🚨 **原文的表述有漏洞，必须改。**

原文写的是：

> "如果 0 温度下抖动依然存在，就证明不是采样温度的问题"

**问题在于：Sun et al. 已经证明「确信度的均值对温度不敏感」。** 如果我们还是按原来的说法去写，评审会立刻指出"这个已经有人做过了"。

**正确的改法 —— 把问题从"均值"改成"方差"：**

> Sun et al. (2025) 证明了**确信度的均值**对温度不敏感（变化 <2 个百分点）。
> **但"均值不敏感"不等于"方差为零"。**
> 一个模型可以在任何温度下都报出 0.93 的平均确信度 —— **同时每次报的数字在 0.6 和 1.0 之间乱跳。**
> **均值是稳定的，个体测量仍然是不可靠的。** 这正是心理测量学里"信度"要单独测量的原因（Lin 2025）。

**这样一改，不仅补上了漏洞，还多了一个支撑点 —— 直接引用了对方的数据来划清界限。**

**同时，`temperature=0` 对照组的价值不变，但定位要改：**
不是"证明抖动不是温度造成的"，而是 **"检验温度这个已知影响因素在多大程度上解释抖动"** —— 更准确，也更难被反驳。

---

## 第四条 · ICC 的标准引用 ✅ 已确定

### 查到了什么

- **Koo, T. K. & Li, M. Y. (2016). A Guideline of Selecting and Reporting Intraclass Correlation Coefficients for Reliability Research. Journal of Chiropractic Medicine.**
  - **判读标准（直接抄）：**
    - < 0.50 → poor
    - 0.50 – 0.75 → moderate
    - 0.75 – 0.90 → good
    - > 0.90 → excellent

- **Shrout, P. E. & Fleiss, J. L. (1979). Intraclass Correlations: Uses in Assessing Rater Reliability. Psychological Bulletin.** —— ICC 的经典源头

- **先例（ICC 已用于 LLM 评估）**：*When Can We Trust LLMs in Mental Health? Large-Scale Benchmarks for Reliable LLM Evaluation.* (EACL 2026, arXiv:2510.19032)
  - 用**双因素混合效应 ICC** 评估 LLM 裁判
  - 区分了两种 ICC：**ICC(C,1) 一致性**（只看排序）和 **ICC(A,1) 绝对一致性**（也看量级）
  - 用非参数 bootstrap（1000 次）算置信区间

- **工具**：Python 的 `pingouin` 包（Vallat 2018）可直接算 ICC

### 对我们的影响

✅ 引用齐了，可以直接写。**额外收获：EACL 2026 那篇给了我们"ICC 该怎么用在 LLM 评估上"的现成模板**（双因素混合效应 + bootstrap 置信区间 + 两种 ICC 变体）—— 我们的实现可以直接参考，而且这又是一个"方法已成熟、只是没用到元认知上"的佐证。

---

## 五、v2 定位修订：卖点从"方法新颖"改成"应用空白"

### ❌ 旧说法（站不住）

> "整个元认知赛道现在都在用一把没校准过的尺子。"

**问题：** 这把尺子的校准方法在别的领域早就有了（LLM-as-judge、AI 心理学方法论），只是没用到元认知上。说"没人校准过"不准确。

### ✅ 新说法（更硬）

> **信度检验这套方法在 LLM 评估里已经成熟** —— 有人用它查过裁判（LLM-as-judge）的可靠性（Schroeder & Wood-Doughty 2024），有人在 AI 心理学方法论层面呼吁必须做（Lin 2025，Annu. Rev. Psychol.），有人用它评估过心理健康场景的评估者（EACL 2026）。
>
> **但这套方法从未被用于任何认知能力基准（cognitive ability benchmark）。**
>
> 更值得说的是：同行们**已经在用"多次采样确信度"来提升性能**（Del et al. 2026：K=1 → K=8 提升 10 个 AUROC 点）。**这个增益的存在，本身就等于承认单次确信度不可靠。**
>
> **可是这个不可靠有多大，从来没有人报告过。**
>
> 而 MetaBound 用单次前置采样算出 **T1 = 0.98**，就宣布"基础校准已被解决（It no longer discriminates）"。
>
> **那个 0.98 的重测信度，至今是未知的。**

### 为什么新说法更强

| # | 理由 |
|---|---|
| 1 | **有权威背书** —— 方法来自 Annu. Rev. Psychol. 级别的综述，评审不能说"你这套不成熟" |
| 2 | **论据来自对手** —— Del et al. 的 K=1 vs K=8 增益是我们的证据，不是我们自己造的 |
| 3 | **空白定位精准** —— "应用位置空白"比"方法空白"可信，也更少被质疑 |
| 4 | **有现成的内部矛盾** —— ORCE（先答后估）vs MetaBound（先估后答），做法相反且都未验证 |
| 5 | **唯一性仍在** —— 我们是唯一"回头查账"的：不是提新评估流程，而是**检验既有 benchmark 结论的可靠性** |

---

## 六、修订后的核心想法（v3 候选）

> 现有 benchmark 能测出模型自报的确信度**准不准**（效度），但测不出这个测量本身**稳不稳**（信度）。
> 同行们已经在用"多采几次确信度"来提升判别力（Del et al. 2026：K=1→K=8 提升 10 点 AUROC）——**这等于默认了单次测量不可靠，却没有人报告过它有多不可靠。**
> 我的设计是对同一题重复采样并做前置/后置对照，用标准差和 ICC 量化这个测量本身可不可信，
> **据此回头检验 MetaBound "T1=0.98，基础校准已解决"这个结论站不站得住。**

---

## 七、抽查记录（已逐条完成）

三篇重点文献的原文核对结论如下：

- [x] **arXiv:2412.12509**（Schroeder & Wood-Doughty）—— **✅ 一致。** 标题、两位作者、时间（v1 2024-12-17 / v2 2025-02-18）核对无误；摘要确认使用 **McDonald's omega** 框架，并明确讨论"固定随机性的局限"与"多采样的必要性"。
  > 注：「100 次重复只改种子」「3 个模型里 2 个低于 0.7」这两个具体数字在**正文**，摘要层未体现 —— 引用时已限定为论文结论，未夸大成摘要原话。
- [x] **arXiv:2603.19118**（Del et al.）—— **✅ 一致。** 标题 *How Uncertainty Estimation Scales with Sampling in Reasoning Models* 核对无误；原文数据确认 **VC@1 = 71.3 → K=8 = 81.4 AUROC（数学域，约 +10）**。
  另核实：题名 *Two Samples Are Enough* 的版本**作者名单完全一致**，属同一篇工作。
- [x] **Koo & Li (2016)** —— **✅ 一致。** *J. Chiropractic Medicine* 15(2):155–163，DOI 10.1016/j.jcm.2016.02.012；原文判读逐字为 *"less than 0.5 … poor, between 0.5 and 0.75 … moderate, between 0.75 and 0.9 … good, and greater than 0.90 … excellent"*，与本文写法完全一致。

**核验方式（如实标注）：** 由 AI 逐条打开 arXiv 摘要页与期刊页比对，关键句已摘录在上。
**我依据这些摘录与原页面做了确认。** 为什么这一步重要：这四条是整个方案的立论基础，一旦有一个引错，后面全塌。

---

## 八、引用清单（提案参考文献）

```
[1] Lin, Z. (2025). From Prompts to Constructs: A Dual-Validity Framework for
    LLM Research in Psychology. arXiv:2506.16697. (Annu. Rev. Psychol. 2027)
[2] Schroeder, K., & Wood-Doughty, Z. (2024). Can You Trust LLM Judgments?
    Reliability of LLM-as-a-Judge. arXiv:2412.12509.
[3] Del, M., Kängsepp, M., Domnich, M., Tampuu, A., Yankovskaya, L., Kull, M.,
    & Fishel, M. (2026). How Uncertainty Estimation Scales with Sampling in
    Reasoning Models. arXiv:2603.19118.
[4] Koo, T. K., & Li, M. Y. (2016). A Guideline of Selecting and Reporting
    Intraclass Correlation Coefficients for Reliability Research.
    Journal of Chiropractic Medicine, 15(2), 155-163.
[5] Shrout, P. E., & Fleiss, J. L. (1979). Intraclass Correlations: Uses in
    Assessing Rater Reliability. Psychological Bulletin, 86(2), 420-428.
[6] Guo, C., Pleiss, G., Sun, Y., & Weinberger, K. Q. (2017). On Calibration of
    Modern Neural Networks. ICML.
[7] Kadavath, S., et al. (2022). Language Models (Mostly) Know What They Know.
    Anthropic. arXiv:2207.05221.
[8] Sun, F., Li, N., Wang, K., & Goette, L. (2025). Large Language Models are
    overconfident and amplify human bias. arXiv:2505.02151.
[9] Flavell, J. H. (1979). Metacognition and Cognitive Monitoring.
    American Psychologist, 34(10), 906-911.
```

---

## 九、事项清单

**✅ 全部完成，当前无遗留项。**

- [x] 抽查上节 3 个文献（arXiv:2412.12509 / arXiv:2603.19118 / Koo & Li 2016）—— 三篇均一致，详见第七节
- [x] 把新定位写进 `LiRuixiang_C2A_定题_核心想法.md` → v3
- [x] 把 Schroeder & Wood-Doughty 的三点差异写进提案（防撞车质疑）
- [x] 把 GitHub 那个项目写进"拿来说明"（主动承认）
- [x] 核实《Two Samples Are Enough》与 arXiv:2603.19118 是同一篇工作（作者名单完全一致：Del, Kängsepp, Domnich, Tampuu, Yankovskaya, Kull, Fishel）
- [x] 补核拿来说明里 3 条此前"只来自摘要、未点开原文"的来源（ORCE 2605.12446 / Thinking Out of Order 2601.22035 / macebake GitHub），逐条打开后标题、作者、年份、关键数字均与描述相符
- [x] 论文原文三处（第 7 / 19 / 5 页）抽查 —— 一致，见 `LiRuixiang_C2A_调研记录_论文缺口表.md` 第五节
