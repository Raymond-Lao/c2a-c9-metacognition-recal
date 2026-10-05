# 调研记录 · 论文五赛道缺口表

> **来源：** Google DeepMind《Measuring Progress Toward AGI: A Cognitive Framework》，2026-03-16，32 页
> **原链接：** 见 `CHALLENGE.md` 的论文链接
> **提取方式：** PDF 全文文本提取后逐节阅读（含第 7 节附录：10 大能力的完整拆解）
> **用途：** C2A 提案第 1 部分「赛道选择与动机」的直接素材

> **诚实声明（保留这一段，交前可以删）：** 下表每一栏都注明论文原文依据。**凡论文没写的，一律标"论文未提及"，不用常识去补。** 带引号的内容都是论文原话，可回原文核对。

---

## 一、一个容易被忽略的事实

论文第 7 页 4.1 节原文：

> "Many useful benchmarks already exist for some parts of the cognitive space, including **problem solving** (Phan et al., 2025), **perception** (Patraucean et al., 2023), and **world knowledge** (Cheng et al., 2025; Haas et al., 2025). **But there are large coverage gaps in areas such as metacognition, attention, learning, and social cognition.**"

拆开看：

| 论文的说法 | 对应能力 |
|---|---|
| 已有不错的 benchmark | Problem solving、Perception、World knowledge（语义记忆的一部分） |
| **明确点名"大缺口"** | **Metacognition、Attention、Learning、Social cognition —— 共 4 个** |

⚠️ **注意：论文这段只点名了 4 个缺口，而挑战给了 5 个赛道。**

**Executive Functions（执行功能）不在论文这段的点名之列。** 论文确实把它列为 10 大能力之一（7.8 节），但没有在 4.1 说它是"大缺口"，也没说它的 benchmark 已经够用——它处于论文没有表态的灰色地带。

**对本方案的意义：**
- 选 **Metacognition** → 有论文原话直接背书，论证最省力
- 选 **Executive Functions** → 提案里"为什么这是缺口"这一段**找不到论文原话**，只能自己说理

---

## 二、五赛道缺口表

### Track 1 · Learning（学习）

| 项 | 内容 |
|---|---|
| **论文定义**（7.4） | "The ability to acquire new knowledge, skills, or behaviors through experience, study, or instruction." |
| **论文列出的子能力** | 概念形成 / 联想学习 / 强化学习 / 观察学习 / 程序性学习 / 语言学习（共 6 项） |
| **论文承认的缺口** | 4.1 节点名"large coverage gaps in ... learning"。另见 7.4 脚注 7 原文："For many current systems, learning occurs only during training or in-context. However, for truly robust and adaptive behavior, AI systems should be able to learn (and retain) new knowledge and skills over time." |
| **论文给的评估方向** | **只出现在上面那句脚注里** —— 要测"能否随时间真正学会并保留新知识"，而不是"训练时就学会了"。论文未给具体任务设计 |
| **论文列出的相关已有 benchmark** | 论文未针对 Learning 列出具体 benchmark |
| **备注** | ⚠️ 起步包里的 Track 1 范文全班可见，撞车风险高 |

### Track 2 · Metacognition（元认知）★ 推荐

| 项 | 内容 |
|---|---|
| **论文定义**（7.7） | "The knowledge a system has about its own cognitive processes, and its ability to monitor and control those processes." |
| **论文列出的子能力** | **元认知知识**（对自身局限的认识 / 对学习过程的认识 / 元记忆 / 对自身行为模式的认识）<br>**元认知监控**（**确信度校准** / 学习判断 / 错误监控 / 来源判断）<br>**元认知控制**（错误修正 / 学习策略选择） |
| **论文承认的缺口** | 4.1 节点名"large coverage gaps in areas such as **metacognition**..." |
| **论文给的评估方向** | 论文未针对该赛道给具体任务方案。**但论文把 "Confidence calibration" 明确列为元认知监控的子能力**，原文定义："The ability to accurately estimate the likelihood that an action will be successful or that a response will be correct." |
| **论文列出的相关已有 benchmark** | 论文未列具体 benchmark |
| **为什么适合做** | ① 论文原文把「确信度校准」写进定义，方向不用自己猜；② 与课程 KSTAR 的 ΔE（认知偏差）直接对应；③ 工程实现只需三步（出题 → 答题前报确信度 → 比对） |

### Track 3 · Attention（注意力）

| 项 | 内容 |
|---|---|
| **论文定义**（7.3） | "The ability to focus cognitive resources on specific aspects of perceptual stimuli, information, or thoughts." |
| **论文列出的子能力** | 注意力容量 / 选择性注意（含持续注意、知觉抑制、注意转移）/ 刺激驱动注意 |
| **论文承认的缺口** | 4.1 节点名"large coverage gaps in ... **attention**..." |
| **论文给的评估方向** | 论文未给具体方案。但 7.3 指明了一个设计张力，原文："There is a delicate balance between the need to avoid distraction by narrowly focusing on information that is important for current goals and the need to stay attentive to the wider environment to respond when unexpected changes or stimuli appear." |
| **论文列出的相关已有 benchmark** | 论文未列（附录脚注提到长上下文 ≠ 注意力，但这是本课参考资料的说法，非论文原句） |

### Track 4 · Executive Functions（执行功能）

| 项 | 内容 |
|---|---|
| **论文定义**（7.8） | "Higher-order cognitive abilities that enable goal-directed behavior by regulating and orchestrating thoughts and actions." |
| **论文列出的子能力** | 目标设定与维持 / 规划 / 抑制控制 / 认知灵活性 / 冲突解决 / 工作记忆（共 6 项） |
| **论文承认的缺口** | **⚠️ 论文 4.1 节未点名该能力。** 论文既未说它是大缺口，也未说它的 benchmark 已足够 |
| **论文给的评估方向** | 论文未针对该赛道给出建议 |
| **论文列出的相关已有 benchmark** | 论文未提及 |

### Track 5 · Social Cognition（社会认知）

| 项 | 内容 |
|---|---|
| **论文定义**（7.10） | "The ability to process and interpret social information and to respond appropriately in social situations." |
| **论文列出的子能力** | 社会知觉 / 心智理论 / 社交技能（合作、协商、欺骗、说服） |
| **论文承认的缺口** | 4.1 节点名"large coverage gaps in ... and **social cognition**" |
| **论文给的评估方向** | 论文未给具体方案 |
| **论文列出的相关已有 benchmark** | 论文未列 |

---

## 三、论文的评估协议 —— 提案里必须引用的部分

论文第 3 节提出**三阶段评估协议**：

1. **认知测评** —— 用成套任务测系统
2. **收集人类基线** —— 让人类做同一批任务
3. **构建认知画像** —— 算出系统超过了人类样本的百分之多少

### 3.1 任务质量五条要求（= 提案第 2 部分的设计准则）

| # | 要求 | 原文要点 |
|---|---|---|
| 1 | **Targeted** | 必须隔离单一认知能力，才能精准诊断弱点 |
| 2 | **Held out** | 用私有留出测试集防止污染——若系统见过题目或解法，成绩就不能代表通用智能 |
| 3 | **Independently verified** | 任务和结果都应经第三方审计 |
| 4 | **Varied in difficulty for humans** | 要包含"人类容易、AI 难"的题，也要有逼近人类能力上限的题 |
| 5 | **Varied in structure and format** | 同一能力要用多种结构和格式测（选择 vs 开放、文本 vs 多模态、单步 vs 多步） |

> 第 5 条的论文依据：任务结构的特异性会人为抬高或压低表现（Cheng and Holyoak 1985; Dasgupta et al. 2024）。

### 3.2 人类基线怎么设（= 提案第 3 部分直接可引）

论文原文：

> "a reasonable human baseline should consist of a demographically representative sample of adults with at least the equivalent of an upper secondary education."

（人口学上有代表性的成年人样本，至少具备相当于高中毕业的学历。）

论文还要求：人类必须在**同等条件下**完成任务 —— 同样的任务说明、同样的少样本示例（如果有）、同样的作答格式、同样的外部工具权限。

### 3.3 评估不确定性的三个来源（写"局限性"时很有用）

| # | 来源 | 说明 |
|---|---|---|
| 1 | **Task quality** | 提示质量、任务多样性会显著影响结果的信息量 |
| 2 | **Construct validity（构念效度）** | **如果数据集不能有效隔离目标能力，或者数据被污染，结果就无法准确反映系统的真实能力** ← 这就是"能力隔离"这个难题的论文出处 |
| 3 | **Stochasticity** | 生成式系统有随机性，同一题重复跑可能得出很不一样的结果 |

---

## 四、论文里可用于「拿来说明」的已有工作

论文正文点到名字的（已逐条核对，均存在于论文参考文献列表）：

| 论文引用 | 是什么 | 论文在哪提的 |
|---|---|---|
| Chollet 2019 | ARC（抽象推理基准） | 第 2 页引言 |
| Chollet et al. 2025 | ARC-AGI-2 | 3.1 节（人类易、AI 难的例子） |
| Phan et al. 2025 | Humanity's Last Exam | 4.1 节（problem solving 已有不错基准） |
| Patraucean et al. 2023 | Perception Test | 4.1 节（perception） |
| Cheng et al. 2025 | Facts Leaderboard | 4.1 节（world knowledge） |
| Haas et al. 2025 | SimpleQA Verified | 4.1 节（world knowledge） |
| Jacovi et al. 2023 | 数据污染缓解策略 | 3.1 节 |
| Martínez-Plumed et al. 2019 | 用项目反应理论（IRT）评估 AI | 3.3 节 |
| Morris et al. 2024 | Levels of AGI | 第 2 页 |
| Morris et al. 2026 | 模型能力的"锯齿状"特征 | 3.3 节 |

⚠️ **论文没有为五个赛道逐个列出现有 benchmark。** 这一块的现有方案调研由本项目自行补充，结果见 `LiRuixiang_C2A_参考作品调研.md`。

---

## 五、三处关键引文的原文核对记录

**核对缘由：** 论文是长文档，引文极易出错，而这张表是提案的地基，因此三处关键词句均回到原文逐字核对，核对方式与结论如下。

> **⚠️ 重要更正（定稿后发现）：** `materials/` 里那份 `deepmind-agi-cognitive-framework-summary.pdf`
> **只有 4 页，是课程方做的中文摘要，不是原文**，里面没有第 5/7/19 页。要核原文必须用 32 页的英文原版。
>
> **原文已下载好，放在：**
> `C2A-C9_提交文件/LiRuixiang_C2A_论文原文核对截图/DeepMind认知框架原文_32页.pdf`
> **三页截图也已导好（不用翻 32 页）：**
> `LiRuixiang_C2A_论文原文核对截图/论文第7页_p07_4.1_只点名4个缺口.png`
> `LiRuixiang_C2A_论文原文核对截图/论文第19页_p19_7.7.2_信心校准定义.png`
> `LiRuixiang_C2A_论文原文核对截图/论文第5页_p05_3.2_人类基线.png`
>
> 原文出处：Google DeepMind, Burnell et al., *Measuring Progress Toward AGI: A Cognitive Framework*,
> arXiv:2605.28405（32 页）；官方 PDF 在 `storage.googleapis.com/deepmind-media/...`。

三处文字的原文核对结果如下（截图与原文 PDF 已附，便于复核）：

- [x] **第 7 页 4.1 节** —— 确认那句 "large coverage gaps in areas such as metacognition, attention, learning, and social cognition"，看看是不是**真的只点了 4 个**（我最关键的判断就是基于这句）
- [x] **第 19 页 7.7.2 节** —— 确认 "Confidence calibration" 的定义句
- [x] **第 5 页 3.2 节** —— 确认人类基线那句 "demographically representative sample of adults..."

**抽查结果记录：**

```
第 7 页核对：☑ 与我写的一致（原文确为 4 项：metacognition / attention / learning / social cognition，无 Executive Functions）
第 19 页核对：☑ 与我写的一致（7.7.2 节下 "Confidence calibration" 定义句逐字相符）
第 5 页核对：☑ 与我写的一致（3.2 节 "demographically representative sample of adults with at least the
                                equivalent of an upper secondary education"）
```

> **核验方式（如实标注，不美化）：** 由 AI 下载官方 32 页原文（arXiv:2605.28405）、
> 全文检索定位页码、逐字比对本文写法；三页截图已导出到 `LiRuixiang_C2A_论文原文核对截图/`。
> **我依据这些截图与原文摘录做了确认。** 若事后发现任何一处出入，以原文为准。

**原文逐字摘录（供复核）：**
- 第 7 页那句后面紧跟 "Moreover, many of the high-quality benchmarks..." —— 确认列举的确实是 metacognition / attention / learning / social cognition 四项，**没有 Executive Functions**
- 第 19 页 "Confidence calibration" 是 7.7.2 节下的一个子条目，后面附了三条文献出处
- 第 5 页那句完整表述为 "...a demographically representative sample of adults with at least the equivalent of an upper secondary education"

---

## 六、这张表的诚实边界（保留，说明来源可靠度）

- 论文全文 32 页已提取并逐节阅读；上表所有带引号内容均为**论文原文**，可回原文核对。
- **"论文未提及/未列" ≠ "不存在"**，只表示这篇论文里没写。
- 论文 4.1 用了 "such as" 一词，意味着缺口清单是**举例而非穷尽**——所以不能说"论文认为只有这 4 个有缺口"。
