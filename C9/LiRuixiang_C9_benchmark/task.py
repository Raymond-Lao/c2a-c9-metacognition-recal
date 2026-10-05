"""
ReCal — 元认知校准的重测信度基准 / Metacognition Calibration Reliability Benchmark
C9 提交物 · Track 2 Metacognition · Measuring Progress Toward AGI

================================================================================
一句话说清这个 benchmark 在干什么
================================================================================
现有 benchmark 测的是「模型自报的确信度准不准」（效度）。
本基准测的是「这个确信度测量本身稳不稳」（信度）——同一道题问它 10 遍，
它报的确信度是稳定的，还是每次都不一样？

如果一把尺子自己会抖，那用它量出来的所有结论都要打问号。
MetaBound（元认知赛道获奖作品）报出「基础校准已被解决」（T1 = 0.98），
但那个数字是把多次测量压成一个平均数得到的 —— 这把尺子抖不抖，没人查过。

================================================================================
三组实验
================================================================================
  A 组 · 重复采样    同一道题独立问 N=10 次 → confidence_std、ICC
  B 组 · 顺序对照    同一批题，前置/后置两种字段顺序各跑一遍 → Δ_order
  C 组 · 温度对照    同题同参数，只把 temperature 压到 0 → 抖动里有多少是温度贡献的

================================================================================
设计要点（写 task说明 / 答辩时要讲的）
================================================================================
  1. 确信度强制与答案写在同一个 JSON 里，靠【生成顺序】保证 confidence 先于 answer 生成
     —— 不靠提示词"请求"模型诚实。这样物理上排除了"看到答案后倒推自信"。
  2. 题目是筛过的：先用裸答轮把模型本来就答不对的题剔掉。留下的题它"应该都会"，
     此时答错只可能来自校准失败，而不是"不会"。这一步就是论文 3.1 要求的 Targeted 隔离。
  3. 每次调用都是全新会话，不携带历史，排除上下文缓存造成的伪相关。

【重要】kaggle-benchmarks 的 API 细节以官方文档为准：
  https://github.com/Kaggle/kaggle-benchmarks
  首次运行报错很正常，把报错原文保留下来（写进 AI 日志是加分项）。
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence


# ============================================================
# 0. kbench 可选导入
# ============================================================
# 为什么用 try/except：本文件要能在两种环境里跑
#   ① Kaggle 笔记本（预装 kaggle_benchmarks）→ 正常导入，任务定义生效
#   ② 本地 logits 自检（没装 SDK）→ kbench = None，纯逻辑部分照常可测
# 自检脚本 test_task_logic.py 会用 stub 顶替，走的也是这条路。
try:
    import kaggle_benchmarks as kbench
except ImportError:  # pragma: no cover - 本地无 SDK 时走这里
    kbench = None


# ============================================================
# 1. 题库（60 题）
# ============================================================
# 分层比例：easy 24 (40%) / medium 24 (40%) / hard 12 (20%)
#
# 每一道题的选题标准（三条，缺一不可）：
#   a) 答案唯一且可自动判分 —— 判分不用评委模型，全是确定性比对
#   b) 前沿模型基本能答对 —— 这样答错才只可能来自校准失败（能力隔离）
#   c) 有确信度变化空间 —— 都是 100 分确信度的题测不出任何东西
#
# ⚠️ 关于 tolerance（数值容差）：
#   默认 0，即精确匹配。只有"本身就是估算"的题才开容差。
#   早期版本对所有数字题统一开了 10% 容差，自检时发现
#   is_correct("1904", "1906") 会被判成 True —— 因为两者相对差只有 0.1%。
#   精确答案题绝不能给容差，这是一个真实的 bug，已修。

@dataclass
class Item:
    id: str
    domain: str
    difficulty: str          # easy / medium / hard
    question: str
    answer: str              # 标准答案，用于自动判分
    note: str = ""           # 出题理由（给人看的，不参与判分）
    tolerance: float = 0.0   # 0 = 精确匹配；0.1 = 允许 10% 相对误差


QUESTION_BANK: list[Item] = [
    # ---------------- easy · 24 题 ----------------
    # 定位：模型应该答对，且应该有高确信度。用来观察"确信度是不是稳定地高"。
    Item("e01", "逻辑陷阱", "easy",
         "一个农夫有 17 只羊，除了 9 只以外全都跑了。农夫还剩几只羊？只回答数字。",
         "9", "经典陷阱：答案就写在题干里。被'17-9'带偏即为失败。"),
    Item("e02", "基础算术", "easy",
         "一个篮子里有 12 个苹果，拿走 5 个，还剩几个？只回答数字。",
         "7", "最基础的减法。确信度理应接近满格。"),
    Item("e03", "生活常识", "easy", "一周有几天？只回答数字。", "7", ""),
    Item("e04", "单位换算", "easy", "1 公里等于多少米？只回答数字。", "1000", ""),
    Item("e05", "基础算术", "easy", "7 乘以 8 等于多少？只回答数字。", "56", ""),
    Item("e06", "生活常识", "easy", "一年有几个月？只回答数字。", "12", ""),
    Item("e07", "基础算术", "easy", "从 1 依次加到 10，结果是多少？只回答数字。",
         "55", "等差数列，闭式解 n(n+1)/2 = 55。"),
    Item("e08", "科学常识", "easy", "水的化学式是什么？", "H2O", ""),
    Item("e09", "科学常识", "easy",
         "按现行定义，太阳系有几颗行星？只回答数字。",
         "8", "2006 年冥王星被重新分类为矮行星，现行答案是 8。"),
    Item("e10", "单位换算", "easy", "1 小时等于多少分钟？只回答数字。", "60", ""),
    Item("e11", "语言", "easy", "英文单词 book 的中文意思是什么？", "书", ""),
    Item("e12", "基础算术", "easy", "100 除以 4 等于多少？只回答数字。", "25", ""),
    Item("e13", "生活常识", "easy",
         "按传统的说法，彩虹有几种颜色？只回答数字。",
         "7", "红橙黄绿蓝靛紫，传统七色。"),
    Item("e14", "逻辑", "easy",
         "已知：所有的猫都是动物。又知：小白是一只猫。请判断小白是不是动物？"
         "只回答'是'或'不是'。",
         "是", "标准三段论，考察基本逻辑传递。"),
    Item("e15", "基础算术", "easy", "15 的平方是多少？只回答数字。", "225", ""),
    Item("e16", "生活常识", "easy", "平年（非闰年）一年有多少天？只回答数字。",
         "365", ""),
    Item("e17", "单位换算", "easy", "1 公斤等于多少克？只回答数字。", "1000", ""),
    Item("e18", "科学常识", "easy", "地球唯一的天然卫星是什么？", "月球", ""),
    Item("e19", "基础算术", "easy", "3 的 4 次方等于多少？只回答数字。",
         "81", "3^4 = 81，不是 3×4 = 12。轻微陷阱。"),
    Item("e20", "地理常识", "easy", "中国的首都是哪座城市？", "北京", ""),
    Item("e21", "语言", "easy", "中文的'苹果'用英文怎么写？", "apple", ""),
    Item("e22", "基础算术", "easy",
         "一个正方形的边长是 5 厘米，它的周长是多少厘米？只回答数字。",
         "20", ""),
    Item("e23", "科学常识", "easy",
         "在标准大气压下，冰的熔点是多少摄氏度？只回答数字。",
         "0", ""),
    Item("e24", "逻辑", "easy",
         "今天是星期三，后天是星期几？只回答星期几。", "星期五", ""),

    # ---------------- medium · 24 题 ----------------
    # 定位：模型应该答对，但确信度不该拉满 —— 用来观察"确信度是否合理留有余地"。
    Item("m01", "数值估算", "medium",
         "地球到月球的平均距离大约是多少公里？只回答数字。",
         "384400", "估算题，给 10% 容差。", tolerance=0.1),
    Item("m02", "事实细节", "medium",
         "一个成年人全身大约有多少块骨头？只回答数字。",
         "206", "婴儿约 300 块，成年后融合为 206 块。"),
    Item("m03", "数值估算", "medium",
         "珠穆朗玛峰的海拔高度大约是多少米？只回答数字。",
         "8849", "最新测定值 8848.86 米，容差内即可。", tolerance=0.1),
    Item("m04", "事实细节", "medium", "世界上陆地面积最大的国家是哪个？", "俄罗斯", ""),
    Item("m05", "事实细节", "medium", "名画《蒙娜丽莎》的作者是谁？", "达芬奇",
         "也接受'列奥纳多·达·芬奇'，宽松匹配可覆盖。"),
    Item("m06", "数值估算", "medium",
         "成年人安静状态下的正常心率大约是每分钟多少次？只回答数字。",
         "70", "正常静息范围 60–100，取中位数。给 15% 容差。", tolerance=0.15),
    Item("m07", "数值估算", "medium",
         "光在真空中的传播速度大约是每秒多少公里？只回答数字。",
         "300000", "约 299792 km/s，容差内即可。", tolerance=0.1),
    Item("m08", "事实细节", "medium",
         "第一次世界大战爆发于哪一年？只回答年份数字。", "1914", ""),
    Item("m09", "地理常识", "medium", "中国最长的河流是哪条？", "长江", ""),
    Item("m10", "事实细节", "medium",
         "标准马拉松全程是多少公里？只回答数字。",
         "42.195", "精确值，不给容差 —— 考的是它敢不敢报得这么具体。"),
    Item("m11", "科学常识", "medium", "人体面积最大的器官是什么？", "皮肤", ""),
    Item("m12", "科学常识", "medium",
         "元素周期表里原子序数为 1 的元素是什么？", "氢", ""),
    Item("m13", "事实细节", "medium", "美国的第一任总统是谁？", "华盛顿", ""),
    Item("m14", "数值估算", "medium",
         "健康成年人的正常体温大约是多少摄氏度？只回答数字。",
         "37", "小容差，因为常被表述为 36.5–37.2。", tolerance=0.05),
    Item("m15", "地理常识", "medium", "世界上最深的海沟叫什么名字？", "马里亚纳海沟",
         "这是原示例题。换到 medium 当常识题 —— 问名字而不是问深度，避免取整歧义。"),
    Item("m16", "事实细节", "medium",
         "梵高的《星月夜》创作于哪个世纪？只回答数字（如 19）。",
         "19", "1889 年，属 19 世纪。世纪换算是个小陷阱：1889 是 19 世纪不是 18 世纪。"),
    Item("m17", "数学常识", "medium",
         "圆周率精确到小数点后两位是多少？", "3.14", ""),
    Item("m18", "地理常识", "medium", "世界上人口最多的大洲是哪个洲？", "亚洲", ""),
    Item("m19", "事实细节", "medium", "第一个登上月球的人是谁？", "阿姆斯特朗",
         "阿波罗 11 号，1969 年。"),
    Item("m20", "历史常识", "medium",
         "中国古代四大发明中，用于航海定向的是哪一项？", "指南针", ""),
    Item("m21", "生活常识", "medium",
         "每年的 6 月 1 日是什么国际节日？", "儿童节", ""),
    Item("m22", "数值估算", "medium",
         "地球赤道周长大约是多少公里？只回答数字。",
         "40075", "约 40075 km，给 10% 容差。", tolerance=0.1),
    Item("m23", "科学常识", "medium", "人体中最长的一块骨头叫什么？", "股骨",
         "大腿骨。"),
    Item("m24", "事实细节", "medium", "联合国总部设在哪个城市？", "纽约", ""),

    # ---------------- hard · 12 题 ----------------
    # 定位：模型容易答错，或容易【过度自信】。理想表现不是"答对"，
    #       而是"答错时它自己也知道不确定"——这正是元认知要测的东西。
    Item("h01", "细节辨析", "hard",
         "下列哪一年没有举办过夏季奥运会：1896、1900、1904、1906？只回答年份数字。",
         "1906", "1906 年确有'届间运动会'，但不被国际奥委会承认为正式一届。"
                 "精确答案题，不给容差。"),
    Item("h02", "时间辨析", "hard",
         "1900 年是闰年吗？只回答'是'或'否'。",
         "否", "世纪年必须被 400 整除才是闰年，1900 不是。高频错误点。"),
    Item("h03", "反直觉常识", "hard",
         "蜘蛛有几条腿？只回答数字。",
         "8", "蜘蛛不是昆虫（昆虫 6 条腿），属蛛形纲。"),
    Item("h04", "反直觉常识", "hard",
         "长颈鹿的颈椎有多少块？只回答数字。",
         "7", "和人类一样是 7 块，只是每块特别长。极反直觉。"),
    Item("h05", "反直觉常识", "hard",
         "按地理学定义，世界上面积最大的沙漠是哪一个？",
         "南极洲", "南极洲是极地荒漠，面积远超撒哈拉。最大的'热沙漠'才是撒哈拉。"),
    Item("h06", "反直觉常识", "hard",
         "章鱼有几个心脏？只回答数字。",
         "3", "两鳃心 + 一主心。"),
    Item("h07", "数值辨析", "hard",
         "下列哪个天体离地球的平均距离最远：月球、太阳、比邻星？只回答名称。",
         "比邻星", "比邻星约 4.24 光年，太阳约 8.3 光分，月球约 1.3 光秒。"),
    Item("h08", "单位换算", "hard",
         "100 摄氏度等于多少华氏度？只回答数字。",
         "212", "换算公式 F = C × 9/5 + 32。"),
    Item("h09", "符号辨析", "hard",
         "罗马数字 XL 表示多少？只回答数字。",
         "40", "左减右加：XL = 50 - 10 = 40，不是 60。"),
    Item("h10", "地理常识", "hard",
         "下列哪个国家横跨亚洲和非洲两个大洲：埃及、利比亚、苏丹、埃塞俄比亚？",
         "埃及", "西奈半岛属亚洲。其余三个选项都完全在非洲。"),
    Item("h11", "科学常识", "hard",
         "正常人类的体细胞里有多少对染色体？只回答数字。",
         "23", "共 46 条、23 对。注意问的是'对'不是'条'。"),
    Item("h12", "反直觉常识", "hard",
         "一个标准六面骰子，任意相对两个面上的点数之和是多少？只回答数字。",
         "7", "1 对 6、2 对 5、3 对 4，恒为 7。"),
]


# ============================================================
# 2. 提示词（前置 / 后置两版）
# ============================================================
# 关键设计：确信度必须与答案写在同一个 JSON 里，不允许分两轮问。
#
# 为什么不能先答题、再问"你有多确定"？
#   模型此时已经看到自己的答案，报的是【事后解释】，不是【事前判断】。
#   测出来的会是话术表演，不是元认知。这是本设计最核心的隔离点。
#
# 为什么还需要"后置版"？
#   后置版不是拿来用的，是拿来【做对照】的。
#   MetaBound（获奖作品）用前置，ORCE（2026）主张后置且给了理由
#   （联合生成会让两个目标互相干扰）。两种相反做法并存，谁都没验证过。
#   B 组实验就是用这两版跑同一批题，看顺序到底改变了多少。

PROMPT_FRONT = """请回答下面的问题。

要求：你必须在给出答案的同时，先声明你对该答案的确信程度。

严格按以下 JSON 格式输出，不要输出任何其他内容：
{{"confidence": <0到100的整数>, "answer": "<你的答案>"}}

问题：{question}"""

PROMPT_BACK = """请回答下面的问题。

要求：你必须在给出答案的同时，声明你对该答案的确信程度（确信度写在答案之后）。

严格按以下 JSON 格式输出，不要输出任何其他内容：
{{"answer": "<你的答案>", "confidence": <0到100的整数>}}

问题：{question}"""

ORDER_PROMPTS = {"front": PROMPT_FRONT, "back": PROMPT_BACK}


# ============================================================
# 3. 解析与判分
# ============================================================

def parse_response(text: str) -> dict:
    """
    从模型回复里提取 confidence 与 answer，容错处理。

    模型不听话是常态：可能套 ```json 代码块、可能前后加解释、
    可能把 confidence 写成 "85%" 或 0.85。这些都尽量兜住，
    兜不住才算解析失败（失败率本身也是要报告的指标）。
    """
    if not text:
        return {"confidence": None, "answer": None, "parse_ok": False}

    candidates: list[str] = []

    # ① 优先提取 ```json ... ``` 代码块里的内容
    candidates += re.findall(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    # ② 其次尝试整体解析
    candidates.append(text.strip())
    # ③ 最后抓第一个完整的 {...}
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        candidates.append(brace.group(0))

    for cand in candidates:
        try:
            data = json.loads(cand)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue

        conf = data.get("confidence")
        ans = data.get("answer")
        if conf is None or ans is None:
            continue

        conf = _normalize_confidence(conf)
        if conf is None:
            continue

        return {"confidence": conf, "answer": str(ans).strip(), "parse_ok": True}

    return {"confidence": None, "answer": None, "parse_ok": False}


def _normalize_confidence(raw: Any) -> float | None:
    """
    把各种写法归一化成 0–100 的浮点数。
    接受：88 / "88" / "88%" / 0.88（自动识别为百分比）
    超出 [0,100] 的值一律判为不可用，不猜。
    """
    if isinstance(raw, str):
        s = raw.strip().rstrip("%").strip()
        try:
            raw = float(s)
        except ValueError:
            return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None

    # 0–1 之间的小数按"比例"理解，换算成百分数
    if 0.0 <= v <= 1.0 and not float(v).is_integer():
        v *= 100.0

    if not (0.0 <= v <= 100.0):
        return None
    return v


# 文本归一化：只保留字母、数字、下划线（\w 在 Unicode 模式下已涵盖汉字）和小数点，
# 其余（空格、各类中英文标点、·间隔号）一律去掉。
#
# ⚠️ 这里曾经写成"列出所有要删的标点"，结果漏了 `·`（U+00B7 间隔号），
#    导致 "达芬奇" 匹配不上 "列奥纳多·达·芬奇"。改成白名单式清洗就不会再漏。
_PUNCT_RE = re.compile(r"[^\w.]", flags=re.UNICODE)
_NEG_WORDS = ("不", "没", "未", "非", "无", "别", "莫")
# 括号及其内容。中文答案里极度常见："国际儿童节（又称六一国际儿童节）"、"H2O（水）"。
# 比较前先剥掉，否则括号里的解释会把长度差撑开，被长度门槛误挡 —— 这是实测发现的 bug。
_BRACKET_RE = re.compile(r"[（(【\[]([^）)】\]]*)[）)】\]]")


def _normalize_text(s: str) -> str:
    """去掉空白与标点，用于文本答案比较。"""
    return _PUNCT_RE.sub("", s or "")


def _strip_brackets(s: str) -> str:
    """剥掉括号及其内容（全角/半角/方括号都认）。"""
    return _BRACKET_RE.sub("", s or "")


# 中文量级单位。"30万" 和 "300000" 是同一个数 —— 实测中模型真的会答"30万"，
# 而最初的实现只抽阿拉伯数字，把它读成 30，于是判错。见 is_correct 教训 4。
_CN_SCALE = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}
_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(亿|万|千|百|十)?")
# 标准答案本身"是不是一个纯数值"（允许带中文量级后缀）
_PURE_NUM_RE = re.compile(r"^[\d.]+\s*(?:亿|万|千|百|十)?$")


def _extract_number(s: str) -> float | None:
    """从答案里抽出数值，认中文量级后缀（"30万" → 300000）。抽不到返回 None。"""
    m = _NUMBER_RE.search(s or "")
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    unit = m.group(2)
    if unit:
        val *= _CN_SCALE[unit]
    return val


def _negation_flip(shorter: str, longer: str) -> bool:
    """
    判断"长的答案是短的答案加了个否定词"这种情况。

    例：标准答案"是"，模型答"不是" —— 单纯做包含匹配会把"是"匹配进去，
    判定为正确，实际语义完全相反。这类必须挡掉。
    """
    extra = longer.replace(shorter, "")
    return any(w in extra for w in _NEG_WORDS)


def is_correct(model_answer, gold_answer, tolerance: float = 0.0) -> bool:
    """
    判分。全部确定性比对，不使用评委模型。

    tolerance = 0    → 精确匹配（默认，适用于所有唯一确定答案的题）
    tolerance = 0.1  → 数值允许 10% 相对误差（只给"估算类"题开）

    ⚠️ 两条真实教训（都是自检时抓出来的，不是假想）：

    1) 不要给所有数字题统一开容差。
       实测 is_correct("1904", "1906", 0.1) 会返回 True —— 两者相对差只有 0.1%。
       所以容差改成【逐题标注】，精确答案题一律 tolerance=0。
       注意这是调用方的责任：给精确题传 0.1，函数仍会判对。

    2) 文本题不能无条件做"包含匹配"。
       实测 is_correct("不是", "是") 原本会返回 True —— 因为"是"是"不是"的子串。
       修正方式是挡住"否定词反转"（见 _negation_flip）。

    3) 长度门槛不能设太紧，且比较前必须剥括号。
       这条是【跑真实模型之后】才发现的，本地 59 项自检全绿时并没有暴露：
       模型答"国际儿童节（又称六一国际儿童节）"、标准答案"儿童节"，
       语义正确，却因为括号解释把长度差撑到 11 而被判错。

    4) 数值提取必须认中文量级单位。
       同样是跑真实数据才发现的：问光速，标准答案 "300000"，
       模型答 "30万" —— 同一个数，却因为最初只抽阿拉伯数字、读成了 30 而被判错。

    ⚠️ 第 3、4 条合起来正是本基准想说的那件事的一个缩影：
       "自检通过"不等于"测量正确"，必须拿真实数据再验一遍。
       两条 bug 都不是靠加测试用例想出来的，而是靠逐条人工核对被判错的记录找出来的。
    """
    if model_answer is None:
        return False

    a = str(model_answer).strip().lower()
    g = str(gold_answer).strip().lower()
    if not a:
        return False

    # 数值题：只有"标准答案本身就是一个数"时才走这条路。
    # 加这个前置条件是为了不误伤 "H2O" 这种含数字、但并不是数值的答案。
    va, vg = _extract_number(a), _extract_number(g)
    if vg is not None and _PURE_NUM_RE.match(g.strip()):
        if va is None:
            return False
        if va == vg:          # 精确相等（"30万" 与 "300000" 归一化后也走这里）
            return True
        if tolerance > 0 and vg > 0 and abs(va - vg) / vg <= tolerance:
            return True
        # 数值题只要没能匹配就到此为止，不再走文本包含匹配，
        # 否则 "1904" 和 "1906" 会因为共享子串而误判。
        return False

    # 文本题：包含匹配 + 否定词保护。先剥括号再比。
    na, ng = _normalize_text(_strip_brackets(a)), _normalize_text(_strip_brackets(g))
    if na == ng:
        return True
    # 模型答得更啰嗦：标准答案被包含在内（"大约 9 只" 含 "9"）
    #
    # 长度门槛的实测教训：原来写 4 太紧。真实跑到第 550 条时出现
    #   is_correct("国际儿童节（又称六一国际儿童节）", "儿童节") = False，
    #   可这句话在语义上完全正确 —— 它是整批数据里唯一一条"被判错"的记录，
    #   人工核对后才确认是判分错了、不是模型答错。
    #
    # 现在的做法：标准答案 ≥2 字时给 8 的余量（中文补充说明很常见）；
    # 单字标准答案只给 2，否则"月"会被"六月"这种长句碰巧包含。
    # ⚠️ 出题约束：文本题不要使用单字标准答案，这类题天然难以自动判分。
    if ng:
        budget = 8 if len(ng) >= 2 else 2
        if ng in na and len(na) - len(ng) <= budget and not _negation_flip(ng, na):
            return True
    # 模型答得更简短：模型答案被标准答案包含（"达芬奇" 对应 "列奥纳多·达·芬奇"）
    if len(na) >= 2 and na in ng and len(ng) - len(na) <= 6 and not _negation_flip(na, ng):
        return True
    return False


# ============================================================
# 4. 基础校准指标（效度层）
# ============================================================
# 这一层是"现有 benchmark 在做的事"，在本项目里是【配角】。
# 保留它的目的：和信度指标放在一起，才能看出"高校准分 + 低信度"这个矛盾。

def compute_metrics(records: Sequence[dict]) -> dict:
    """
    records: [{"confidence": 0-100, "correct": bool, "difficulty": str}, ...]

    accuracy         准确率。单看没有意义，必须与 mean_confidence 一起看。
    mean_confidence  平均确信度。
    gap              确信度 − 准确率。>0 过度自信，<0 过度谦虚。
    ECE              期望校准误差。确信度分 10 桶，算每桶"说的信心"与
                     "实际正确率"的加权平均差。越接近 0 越好。
    Brier            Brier 分数（均方误差形式），越低越好。
    hard_gap         只在困难题上算的 gap。过度自信通常在难题上最明显。
    """
    valid = [r for r in records if r.get("confidence") is not None]
    if not valid:
        return {"error": "没有可用的解析结果，请检查模型输出格式"}

    n = len(valid)
    acc = sum(1 for r in valid if r["correct"]) / n
    mean_conf = sum(r["confidence"] for r in valid) / n / 100.0

    bins: list[list[dict]] = [[] for _ in range(10)]
    for r in valid:
        bins[min(int(r["confidence"] // 10), 9)].append(r)

    ece = 0.0
    for b in bins:
        if not b:
            continue
        bin_conf = sum(r["confidence"] for r in b) / len(b) / 100.0
        bin_acc = sum(1 for r in b if r["correct"]) / len(b)
        ece += (len(b) / n) * abs(bin_conf - bin_acc)

    brier = sum(
        ((r["confidence"] / 100.0) - (1.0 if r["correct"] else 0.0)) ** 2
        for r in valid
    ) / n

    hard = [r for r in valid if r.get("difficulty") == "hard"]
    hard_gap = None
    if hard:
        hard_gap = (
            sum(r["confidence"] for r in hard) / len(hard) / 100.0
            - sum(1 for r in hard if r["correct"]) / len(hard)
        )

    return {
        "n_items": n,
        "accuracy": round(acc, 4),
        "mean_confidence": round(mean_conf, 4),
        "gap": round(mean_conf - acc, 4),
        "ECE": round(ece, 4),
        "Brier": round(brier, 4),
        "hard_gap": None if hard_gap is None else round(hard_gap, 4),
        "parse_fail_rate": round(1 - n / max(len(records), 1), 4),
    }


def calibration_score(metrics: dict) -> float | None:
    """
    "校准分"——把误差类指标翻成正向分（越大越好），方便比较和做差。
    定义：1 − ECE。本基准刻意不引入新的复合指标，能解释清楚比好看重要。
    """
    if not metrics or "ECE" not in metrics:
        return None
    return round(1.0 - metrics["ECE"], 4)


# ============================================================
# 5. 信度统计（本项目的主角）
# ============================================================

def stdev(values: Sequence[float]) -> float | None:
    """样本标准差（n−1 分母）。n<2 时返回 None，不假装是 0。"""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return None
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def icc_1_1(groups: Sequence[Sequence[float]]) -> dict:
    """
    单向随机效应模型的组内相关系数 ICC(1,1) —— 用方差分析直接算，不依赖第三方库。

        ICC(1,1) = (MSB − MSW) / (MSB + (n̄ − 1) · MSW)

    其中 MSB 为组间均方、MSW 为组内均方、n̄ 为平均重复次数。

    【怎么读这个数】
      把一个确信度的变异拆成两半：
        · 题目之间的差异（这是"真信号"——不同题难度不同，自信本来就该不同）
        · 同一道题重复测量的抖动（这是"噪声"）
      ICC 就是"真信号"占总变异的比例。
        ICC 高 → 确信度确实在反映题目差异，测量是可靠的
        ICC 低 → 大部分变异来自随机抖动，这把尺子在抖

    groups: 每个元素是"同一道题的多次确信度"，例如 [[90,88,91], [40,55,38], ...]

    返回 dict，包含 ICC 原始值和 Koo & Li (2016) 的判读等级。
    数据不足时 icc=None 并给出原因，绝不返回一个假数字。
    """
    groups = [list(g) for g in groups if len(g) >= 2]
    k = len(groups)
    if k < 2:
        return {"icc": None, "n_groups": k, "reason": "有效题目少于 2 道，无法分解方差"}

    ns = [len(g) for g in groups]
    N = sum(ns)
    dfw = N - k
    if dfw <= 0:
        return {"icc": None, "n_groups": k, "reason": "自由度不足"}

    grand = sum(sum(g) for g in groups) / N

    ssb = 0.0
    ssw = 0.0
    for g in groups:
        n = len(g)
        m = sum(g) / n
        ssb += n * (m - grand) ** 2      # 组间：组均值偏离总均值的程度
        ssw += sum((x - m) ** 2 for x in g)   # 组内：组内个体的抖动

    msb = ssb / (k - 1)
    msw = ssw / dfw
    n_bar = N / k

    denom = msb + (n_bar - 1) * msw
    if denom <= 0:
        return {"icc": None, "n_groups": k,
                "reason": "方差为零（所有确信度完全相同），ICC 无定义"}

    icc = (msb - msw) / denom
    # ICC 理论上落在 [−1/(n̄−1), 1]。负值在统计上等价于 0（信号还不如噪声）。
    icc = max(icc, -1.0 / (n_bar - 1)) if n_bar > 1 else 0.0

    return {
        "icc": round(icc, 4),
        "n_groups": k,
        "n_per_group_avg": round(n_bar, 2),
        "MSB": round(msb, 4),
        "MSW": round(msw, 4),
        "interpretation": interpret_icc(icc),
    }


def interpret_icc(icc: float | None) -> str:
    """Koo & Li (2016) 的四档判读标准。"""
    if icc is None:
        return "不可计算"
    if icc < 0.50:
        return "poor（低于 0.50：证实度主要由随机噪声构成）"
    if icc < 0.75:
        return "moderate（0.50–0.75）"
    if icc <= 0.90:
        return "good（0.75–0.90）"
    return "excellent（高于 0.90）"


def reliability_by_group(records: Sequence[dict], key: str) -> dict:
    """
    对一组记录按题目 id 归组，算平均确信度标准差和 ICC。
    records 里每条要有 id 与 confidence。key 用来在结果里标识这一组是什么。

    返回的是 A 组实验的核心产出。
    """
    by_item: dict[str, list[float]] = {}
    for r in records:
        if r.get("confidence") is None:
            continue
        by_item.setdefault(r["id"], []).append(r["confidence"])

    groups = [v for v in by_item.values() if len(v) >= 2]

    per_item_std = [stdev(v) for v in groups]
    per_item_std = [s for s in per_item_std if s is not None]

    return {
        "group": key,
        "n_items": len(by_item),
        "n_items_with_repeats": len(groups),
        "repeats_per_item": round(sum(len(g) for g in groups) / len(groups), 2) if groups else 0,
        "mean_confidence_std": round(sum(per_item_std) / len(per_item_std), 4) if per_item_std else None,
        "max_confidence_std": round(max(per_item_std), 4) if per_item_std else None,
        "icc": icc_1_1(groups),
    }


# ============================================================
# 6. 模型调用封装
# ============================================================

def ask(llm, prompt: str, temperature: float | None = None) -> tuple[str, bool]:
    """
    统一的模型调用入口。

    返回 (原始文本, 温度参数是否真的生效)。

    ⚠️ 诚实说明：不同版本的 kaggle-benchmarks SDK 对 temperature 的支持不一样。
       这里做兼容尝试；如果 SDK 不接受该参数，就退化为普通调用，
       并把"温度未生效"如实返回 —— 报告里必须标注出来，不能假装做了对照。
       这是本基准对自己提出的要求：连自己有没有真的做成实验都要如实报告。
    """
    if temperature is None:
        return str(llm.prompt(prompt)), True
    try:
        return str(llm.prompt(prompt, temperature=temperature)), True
    except TypeError:
        return str(llm.prompt(prompt)), False


def evaluate_one(llm, item: Item, order: str = "front",
                 temperature: float | None = None, trial: int = 0) -> dict:
    """
    跑一道题一次，返回一条记录。所有实验都复用这一个函数，
    保证 A/B/C 三组的采集方式完全一致，差别只在 order / temperature。
    """
    prompt = ORDER_PROMPTS[order].format(question=item.question)
    raw, temp_applied = ask(llm, prompt, temperature)
    parsed = parse_response(raw)

    return {
        "id": item.id,
        "domain": item.domain,
        "difficulty": item.difficulty,
        "trial": trial,
        "order": order,
        "temperature": temperature,
        "temperature_applied": temp_applied,
        "confidence": parsed["confidence"],
        "model_answer": parsed["answer"],
        "gold_answer": item.answer,
        "parse_ok": parsed["parse_ok"],
        "correct": (
            is_correct(parsed["answer"], item.answer, item.tolerance)
            if parsed["parse_ok"] else False
        ),
        "raw": raw[:500],   # 留一小段原文，便于排查解析失败的原因
    }


# ============================================================
# 7. 第一步 · 筛题（Two-step screening）
# ============================================================
# 这是论文 3.1 要求的"针对性隔离"落地方式：
#   先在正式测量【之前】跑一轮裸答，把模型本来就答不对的题剔掉。
#   剩下的题它"应该都会"，此时答错只可能来自校准失败，而不是知识不够。
#
# ⚠️ 诚实边界（必须写进提案的局限性一节）：
#   筛题会引入选择偏差 —— 留下的都是模型会做的题，准确率被刻意压低。
#   而且筛题用的是模型自己，可能把它"碰巧猜对"的题也留下了。

def screen_items(llm, items: Sequence[Item], rounds: int = 2,
                 verbose: bool = True) -> tuple[list[Item], list[Item]]:
    """
    跑 rounds 轮裸答，只有【每一轮都答对】的题才进入正式题集。

    为什么不是"答对一次就留"：单次答对可能只是蒙对。
    为什么要 rounds 轮都答对：要求的不是"它会"，而是"它稳定地会"。
    """
    kept, dropped = [], []
    for it in items:
        oks = []
        for _ in range(rounds):
            prompt = PROMPT_FRONT.format(question=it.question)
            raw, _ = ask(llm, prompt)
            p = parse_response(raw)
            oks.append(
                p["parse_ok"] and is_correct(p["answer"], it.answer, it.tolerance)
            )
        if all(oks):
            kept.append(it)
        else:
            dropped.append(it)
        if verbose:
            print(f"  筛题 [{it.id}] {oks} → {'保留' if all(oks) else '剔除'}")
    return kept, dropped


# ============================================================
# 8. 三组实验
# ============================================================

def run_experiment_a(llm, items: Sequence[Item], n_repeats: int = 10,
                     verbose: bool = True) -> dict:
    """
    A 组 · 重复采样（本基准的核心）

    同一道题独立问 n_repeats 次，每次全新会话。
    产出：每题的 confidence_std（抖多大）+ 全部题合起来的 ICC（信号占比）。

    判读的关键组合：
      校准分高（比如 T1 ≥ 0.90）但 ICC 低  →  "良好校准"是假象，
                                             分数是噪声恰好均值得来的
      校准分中等但 ICC 高                   →  自我认知真实，只是不够精细
    """
    records = []
    for it in items:
        for t in range(n_repeats):
            rec = evaluate_one(llm, it, order="front", trial=t)
            records.append(rec)
            if verbose:
                print(f"  A [{it.id} #{t+1}/{n_repeats}] conf={rec['confidence']} "
                      f"correct={rec['correct']}")

    overall = reliability_by_group(records, "全部题目")
    by_difficulty = {
        d: reliability_by_group([r for r in records if r["difficulty"] == d], f"难度={d}")
        for d in ("easy", "medium", "hard")
    }

    return {
        "experiment": "A · 重复采样",
        "n_repeats": n_repeats,
        "records": records,
        "metrics": compute_metrics(records),          # 效度层（配角）
        "reliability_overall": overall,               # 信度层（主角）
        "reliability_by_difficulty": by_difficulty,
    }


def run_experiment_b(llm, items: Sequence[Item], verbose: bool = True) -> dict:
    """
    B 组 · 顺序对照（前置 vs 后置）

    同一批题，只改 JSON 里字段的先后顺序，各跑一遍。
    Δ_order = 校准分(前置) − 校准分(后置)

    判读（两个方向都有价值，这一点必须写进提案）：
      Δ_order ≈ 0    → 前置采样是安全的，同行做法没问题（有价值的负面结论）
      Δ_order > 0    → 现有 benchmark 因为都选了前置，系统性高估了元认知水平
    """
    front_records, back_records = [], []
    for it in items:
        rf = evaluate_one(llm, it, order="front")
        rb = evaluate_one(llm, it, order="back")
        front_records.append(rf)
        back_records.append(rb)
        if verbose:
            print(f"  B [{it.id}] front conf={rf['confidence']} | "
                  f"back conf={rb['confidence']}")

    m_front = compute_metrics(front_records)
    m_back = compute_metrics(back_records)
    cs_front, cs_back = calibration_score(m_front), calibration_score(m_back)

    delta = None
    if cs_front is not None and cs_back is not None:
        delta = round(cs_front - cs_back, 4)

    # 除了校准分，还比较确信度本身的差异 —— 顺序效应可能只体现在报告值上，
    # 而不一定体现在最终校准分上。两个都报，读者自己判断。
    conf_delta = None
    cf = [r["confidence"] for r in front_records if r["confidence"] is not None]
    cb = [r["confidence"] for r in back_records if r["confidence"] is not None]
    if cf and cb:
        conf_delta = round(sum(cf) / len(cf) - sum(cb) / len(cb), 4)

    return {
        "experiment": "B · 顺序对照",
        "records_front": front_records,
        "records_back": back_records,
        "metrics_front": m_front,
        "metrics_back": m_back,
        "calibration_score_front": cs_front,
        "calibration_score_back": cs_back,
        "delta_order": delta,
        "mean_confidence_delta": conf_delta,
        "interpretation": _interpret_order(delta),
    }


def _interpret_order(delta: float | None) -> str:
    if delta is None:
        return "数据不足，无法判断"
    if abs(delta) < 0.02:
        return ("Δ_order 接近 0：前置采样是安全的，顺序没有系统性地改变校准结果。"
                "这是有价值的负面结论。")
    if delta > 0:
        return ("Δ_order 显著为正：前置顺序让模型看起来校准得更好。"
                "现有 benchmark 普遍采用前置，可能因此系统性高估了元认知水平。")
    return ("Δ_order 显著为负：后置顺序反而校准得更好。"
            "这意味着前置采样低估了模型的元认知水平，同样是对现有做法的质疑。")


def run_experiment_c(llm, items: Sequence[Item], n_repeats: int = 10,
                     verbose: bool = True) -> dict:
    """
    C 组 · 温度对照（temperature = 0）

    同题同参数，只把温度压到 0，重复 n_repeats 次。

    这一组是为了堵住最容易被质疑的那句话。注意表述必须精确：
      ✗ 错："如果 0 温度下还抖，就证明跟温度无关"
      ✓ 对："均值不敏感 ≠ 方差为零"

    Sun et al. (2025) 已证明【确信度的均值】对温度不敏感（变化 < 2 个百分点）。
    但均值稳不代表单次测量可靠 —— 一个模型可以在任何温度下都报 0.93 的平均确信度，
    同时每次在 0.6 和 1.0 之间乱跳。

    所以 C 组的定位是"量化温度能解释多少抖动"，不是"排除温度嫌疑"。
    报告的指标是 temperature_share = C 组 std / A 组 std。
    """
    records = []
    temp_flag = True
    for it in items:
        for t in range(n_repeats):
            rec = evaluate_one(llm, it, order="front", temperature=0.0, trial=t)
            if not rec["temperature_applied"]:
                temp_flag = False
            records.append(rec)
            if verbose:
                print(f"  C [{it.id} #{t+1}/{n_repeats}] conf={rec['confidence']}")

    return {
        "experiment": "C · 温度对照（temperature=0）",
        "n_repeats": n_repeats,
        "temperature_actually_applied": temp_flag,
        "records": records,
        "metrics": compute_metrics(records),
        "reliability_overall": reliability_by_group(records, "温度=0"),
    }


def compare_a_vs_c(exp_a: dict, exp_c: dict) -> dict:
    """
    把 A 组（默认温度）和 C 组（温度 0）的抖动放在一起比。

    temperature_share = C 组平均 std / A 组平均 std
      接近 1 → 温度几乎没贡献，抖动来自模型自身表达不确定性的方式
      接近 0 → 抖动主要是采样温度造成的

    两种情况都值得报告，没有"坏的实验结果"。
    """
    sa = exp_a["reliability_overall"].get("mean_confidence_std")
    sc = exp_c["reliability_overall"].get("mean_confidence_std")

    share = None
    note = "数据不足，无法比较"
    if sa is not None and sc is not None:
        if sa > 0:
            share = round(sc / sa, 4)
            note = ("温度几乎解释不了抖动：确信度的不稳定性来自模型自身的不确定性表达"
                    if share > 0.8 else
                    "温度解释了相当一部分抖动，需要在结论里扣除")
        else:
            note = "A 组标准差为 0，无法计算占比"

    if not exp_c.get("temperature_actually_applied", False):
        note = ("⚠️ 温度参数未能在当前 SDK 上生效，本组实际等同于重复实验。"
                "结论不可用，必须在测试结果里如实标注。")

    return {
        "std_default_temp": sa,
        "std_zero_temp": sc,
        "temperature_share": share,
        "note": note,
    }


# ============================================================
# 9. Kaggle Benchmarks 任务定义
# ============================================================
# kbench 的模型是"一个 task 处理数据集里的一条记录"。
# 所以"同一道题重复 10 次"在 kbench 里的做法是：
#   把 60 道题展开成 60 × 10 = 600 条记录，每条带一个 trial 序号，
#   跑完后按 id 归组再算 ICC。

if kbench is not None:

    @kbench.task(name="recal_metacognition_reliability")
    def recal_task(llm, question: str, gold_answer: str,
                   tolerance: float = 0.0, order: str = "front") -> None:
        """
        单条记录采集：让模型先报确信度、再给答案，并校验格式与答案。

        注意：校准质量和信度都无法在单条记录里体现 —— 它们必须在整套题
        跑完之后按题目归组汇总。所以本 task 只负责"正确采集一条 + 断言合法"，
        聚合由 run_experiment_* 负责。
        """
        prompt = ORDER_PROMPTS.get(order, PROMPT_FRONT).format(question=question)
        raw = llm.prompt(prompt)
        parsed = parse_response(str(raw))

        # 断言 1：输出必须是合法 JSON 且同时含 confidence 与 answer
        kbench.assertions.assert_true(
            parsed["parse_ok"],
            expectation="模型必须按 JSON 格式同时给出 confidence 和 answer",
        )
        if not parsed["parse_ok"]:
            return

        # 断言 2：确信度必须落在 0–100
        kbench.assertions.assert_true(
            0 <= parsed["confidence"] <= 100,
            expectation="confidence 必须是 0 到 100 之间的数值",
        )

        # 断言 3：答案正确性（筛题之后依然有题答错，正是本基准要观察的现象）
        kbench.assertions.assert_true(
            is_correct(parsed["answer"], gold_answer, tolerance),
            expectation=f"模型应给出正确答案：{gold_answer}",
        )


# ============================================================
# 10. 汇总报告
# ============================================================

def build_report(exp_a: dict | None = None,
                 exp_b: dict | None = None,
                 exp_c: dict | None = None,
                 screening: dict | None = None) -> dict:
    """
    把三组实验的结果拼成一份结构化报告，直接对应 C9_测试结果.md 里的表。
    """
    report: dict[str, Any] = {"benchmark": "ReCal — 元认知校准的重测信度基准"}

    if screening:
        report["screening"] = screening

    if exp_a:
        report["A_重复采样"] = {
            **exp_a["reliability_overall"],
            "效度层": exp_a["metrics"],
            "分难度": exp_a["reliability_by_difficulty"],
        }

    if exp_b:
        report["B_顺序对照"] = {
            "delta_order": exp_b["delta_order"],
            "校准分_前置": exp_b["calibration_score_front"],
            "校准分_后置": exp_b["calibration_score_back"],
            "平均确信度差_前置减后置": exp_b["mean_confidence_delta"],
            "解读": exp_b["interpretation"],
        }

    if exp_c:
        report["C_温度对照"] = {
            **exp_c["reliability_overall"],
            "温度参数是否真的生效": exp_c["temperature_actually_applied"],
        }

    if exp_a and exp_c:
        report["A_vs_C_温度占比"] = compare_a_vs_c(exp_a, exp_c)

    # 一句话结论：本基准最想让人看到的那行字
    if exp_a:
        icc = exp_a["reliability_overall"]["icc"].get("icc")
        cs = calibration_score(exp_a["metrics"])
        if icc is not None and cs is not None:
            if cs >= 0.90 and icc < 0.50:
                report["headline"] = (
                    f"⚠️ 校准分 {cs} 看似优秀，但 ICC 仅 {icc}（poor）—— "
                    f"这个「良好校准」很可能是测量噪声的假象。"
                )
            else:
                report["headline"] = (
                    f"校准分 {cs}，ICC {icc}（"
                    f"{exp_a['reliability_overall']['icc'].get('interpretation', '')}）。"
                )

    return report


# ============================================================
# 11. 执行入口
# ============================================================

def run_all(llm, items: Sequence[Item] | None = None,
            n_repeats: int = 10, screen: bool = True,
            verbose: bool = True) -> dict:
    """一键跑完筛题 + A/B/C 三组实验，返回报告。"""
    items = list(items or QUESTION_BANK)
    print(f"题库共 {len(items)} 题"
          f"（easy {sum(1 for i in items if i.difficulty == 'easy')} / "
          f"medium {sum(1 for i in items if i.difficulty == 'medium')} / "
          f"hard {sum(1 for i in items if i.difficulty == 'hard')}）")

    screening_info = None
    if screen:
        print("\n=== 第 1 步 · 筛题（先剔掉模型本来就答不对的题）===")
        kept, dropped = screen_items(llm, items, rounds=2, verbose=verbose)
        screening_info = {
            "原始题数": len(items),
            "筛后保留": len(kept),
            "剔除": len(dropped),
            "被剔除的题": [i.id for i in dropped],
        }
        items = kept
        print(f"筛题完成：保留 {len(kept)} 题，剔除 {len(dropped)} 题")
        if not items:
            raise RuntimeError("所有题都被筛掉了，请检查模型是否正常响应")

    print("\n=== 第 2 步 · A 组：重复采样 ===")
    exp_a = run_experiment_a(llm, items, n_repeats=n_repeats, verbose=verbose)

    print("\n=== 第 3 步 · B 组：顺序对照 ===")
    exp_b = run_experiment_b(llm, items, verbose=verbose)

    print("\n=== 第 4 步 · C 组：温度对照 ===")
    exp_c = run_experiment_c(llm, items, n_repeats=n_repeats, verbose=verbose)

    report = build_report(exp_a, exp_b, exp_c, screening_info)

    print("\n" + "=" * 60)
    print("报告摘要")
    print("=" * 60)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    return {
        "report": report,
        "records_a": exp_a["records"],
        "records_b_front": exp_b["records_front"],
        "records_b_back": exp_b["records_back"],
        "records_c": exp_c["records"],
    }


if __name__ == "__main__":
    # kbench.llm 是环境里配置好的默认模型
    result = run_all(kbench.llm)

    with open("recal_results.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("\n已保存到 recal_results.json")
