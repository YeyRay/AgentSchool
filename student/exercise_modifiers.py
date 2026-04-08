import re
import random
import copy

# ========= 中文数字工具 =========
CN_NUM = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9
}
CN_UNIT = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}

def chinese_to_arabic(cn: str) -> int:
    unit = 0
    ldig = []
    for c in reversed(cn):
        if c in CN_UNIT:
            unit = CN_UNIT[c]
            if unit in (10000, 100000000):
                ldig.append(unit)
                unit = 1
        else:
            dig = CN_NUM.get(c, None)
            if dig is not None:
                if unit:
                    dig *= unit
                    unit = 0
                ldig.append(dig)
    if unit == 10:  # 特殊处理“十”
        ldig.append(10)
    val, tmp = 0, 0
    for x in reversed(ldig):
        if x in (10000, 100000000):
            tmp *= x
            val += tmp
            tmp = 0
        else:
            tmp += x
    return val + tmp

def arabic_to_chinese(num: int) -> str:
    units = ["", "十", "百", "千"]
    nums = "零一二三四五六七八九"
    if num == 0: return "零"
    s, unit_pos = "", 0
    while num > 0:
        num, rem = divmod(num, 10)
        if rem != 0:
            s = nums[rem] + units[unit_pos] + s
        elif not s.startswith("零"):
            s = "零" + s
        unit_pos += 1
    return s.strip("零")

NUM_PATTERN = re.compile(r'(\d+(?:\.\d+)?)|([零〇一二两三四五六七八九十百千万亿]+)')

def extract_numbers(text):
    """返回 (原串, 数值, 是否中文) 列表"""
    results = []
    for m in NUM_PATTERN.finditer(text or ""):
        if m.group(1):
            results.append((m.group(1), float(m.group(1)), False))
        elif m.group(2):
            val = chinese_to_arabic(m.group(2))
            results.append((m.group(2), val, True))
    return results

def replace_first_number(text, fn):
    """替换首个数字（支持中文/阿拉伯）"""
    def repl(m):
        if m.group(1):  # 阿拉伯
            val = float(m.group(1))
            new_val = fn(val)
            # 安全地处理浮点数转换
            try:
                if isinstance(new_val, (int, float)) and float(new_val).is_integer():
                    return str(int(float(new_val)))
                else:
                    return str(new_val)
            except (ValueError, TypeError):
                return str(new_val)
        else:  # 中文
            val = chinese_to_arabic(m.group(2))
            new_val = fn(val)
            if isinstance(new_val, float) and not float(new_val).is_integer():
                return str(new_val)
            # 安全地转换为整数
            try:
                new_val_int = int(float(new_val))
                if new_val_int < 10000 and random.random() < 0.5:
                    return arabic_to_chinese(new_val_int)
                return str(new_val_int)
            except (ValueError, TypeError):
                return str(new_val)
    return NUM_PATTERN.sub(repl, text, count=1)


# ========= 主类 =========
class PersonalizedQuestionModifier:
    def __init__(self, student, base_prob=0.35, seed=None):
        self.student = student
        self.mistake_levels = self._analyze_student_mistakes()
        self.base_prob = base_prob
        if seed is not None:
            random.seed(seed)

    # --------- 画像解析 ---------
    def _analyze_student_mistakes(self):
        texts = [t.lower() for t in getattr(self.student.scratch, "common_mistakes", [])]
        levels = {
            "careless_calculation": 0,
            "concept_confusion": 0,
            "shallow_understanding": 0,
            "overconfidence": 0,
            "impatience": 0,
            "surface_reading": 0
        }
        def bump(key, val): levels[key] = max(levels[key], val)

        for s in texts:
            if any(k in s for k in ["跳过","粗心","不检查","计算错误","单位","代入"]): bump("careless_calculation", 3)
            if any(k in s for k in ["小错误","细节"]): bump("careless_calculation", 1)
            if any(k in s for k in ["混淆","公式","概念","只记公式"]): bump("concept_confusion", 3)
            if any(k in s for k in ["浮于表面","忽视原理","不理解推导","只记事实","缺乏因果"]): bump("shallow_understanding", 2)
            if any(k in s for k in ["自信过高","不检查","直觉"]): bump("overconfidence", 2)
            if any(k in s for k in ["放弃","缺乏坚持","犹豫","卡在中间"]): bump("impatience", 2)
            if any(k in s for k in ["关键词","忽略上下文","片面","不包括","正确/不正确"]): bump("surface_reading", 3)
        return levels

    # --------- 是否改题 ---------
    def should_modify_question(self, question_index):
        active = sum(1 for v in self.mistake_levels.values() if v > 0)
        prob = min(0.15 + 0.1*active + 0.05*max(self.mistake_levels.values()), 0.85)
        return random.random() < max(self.base_prob, prob)

    # --------- 主入口 ---------
    def modify_question(self, question_data, question_index):
        if not self.should_modify_question(question_index):
            return question_data
        q = copy.deepcopy(question_data)
        
        # 保护关键字段，避免被意外修改
        protected_fields = {
            "index": q.get("index"),
            "embedding": q.get("embedding"),
            "answer": q.get("answer"),  # 保护答案字段
            "question_id": q.get("question_id"),  # 保护问题ID
            "id": q.get("id"),  # 保护ID字段
        }
        
        applied = []
        L = self.mistake_levels
        if L["careless_calculation"] > 0: self._calc_traps(q,L["careless_calculation"]); applied.append("calc_traps")
        if L["concept_confusion"] > 0: self._concept_traps(q,L["concept_confusion"]); applied.append("concept_traps")
        if L["overconfidence"] > 0: self._overconfidence_traps(q,L["overconfidence"]); applied.append("overconfidence_traps")
        if L["impatience"] > 0: self._impatience_traps(q,L["impatience"]); applied.append("impatience_traps")
        if L["surface_reading"] > 0: self._reading_traps(q,L["surface_reading"]); applied.append("reading_traps")
        if L["shallow_understanding"] > 0: self._shallow_traps(q,L["shallow_understanding"]); applied.append("shallow_traps")
        
        # 恢复被保护的字段
        for field, value in protected_fields.items():
            if value is not None:
                q[field] = value
                
        q.setdefault("modification_info", {})
        q["modification_info"].update({
            "applied": applied,
            "levels": {k:v for k,v in self.mistake_levels.items() if v},
        })
        return q

    # --------- 工具函数 ---------
    def _numbers(self, text):
        return extract_numbers(text)

    def _replace_first_number(self, text, fn):
        return replace_first_number(text, fn)

    def _ensure_options(self, q):
        if "options" not in q or not isinstance(q["options"], list): q["options"] = []
        return q["options"]

    def _inject_rounding_rule(self, q, rule):
        q["content"] = (q.get("content","").rstrip() +
            f"\n（作答要求：最终结果按{rule['sf']}位有效数字，以{rule['unit']}为单位给出；若为小数请保留{rule['dp']}位小数）")

    def _add_numeric_distractors(self, q, base=None, count=2):
        opts = self._ensure_options(q)
        target = None
        if isinstance(q.get("answer"), (int,float,str)):
            try: target = float(q["answer"])
            except: pass
        if target is None:
            nums = self._numbers(q.get("content",""))
            if nums:
                try: target = float(nums[0][1])
                except: pass
        if target is None and base is not None: target = base
        if target is None: return
        near = [target*(1+x) for x in [0.1,-0.1,0.01,-0.01,0.5,-0.5]]
        random.shuffle(near)
        for v in near[:count]:
            s = self._fmt_number(v)
            if s not in opts: opts.append(s)

    def _fmt_number(self, x):
        try: 
            # 避免科学计数法，对于很大或很小的数字使用固定格式
            val = float(x)
            if abs(val) >= 1e6 or (abs(val) < 1e-3 and val != 0):
                # 对于极大或极小的数字，四舍五入到合理范围
                if abs(val) >= 1e6:
                    val = round(val / 1e6) * 1e6  # 精确到百万
                else:
                    val = round(val, 3)  # 小数保留3位
            
            # 使用固定格式避免科学计数法
            if abs(val - round(val)) < 1e-10:  # 更严格的整数判断
                return str(int(round(val)))
            else:
                # 确保小数格式不会被误解为整数
                formatted = f"{val:.6f}".rstrip('0').rstrip('.')
                # 如果格式化后看起来像整数，添加.0后缀以明确表示
                if '.' not in formatted and abs(val - round(val)) > 1e-10:
                    formatted += '.0'
                return formatted
        except (ValueError, TypeError): 
            return str(x)

    # --------- 各维度陷阱（示例保留） ---------
    def _calc_traps(self, q, level):
        c = q.get("content","")
        nums = self._numbers(c)
        if not nums: return
        if level >= 1:
            def near_miss(v): return self._fmt_number(v + random.choice([1,-1,0.1,-0.1]))
            q["content"] = self._replace_first_number(c, near_miss)
        if level >= 2:
            self._inject_rounding_rule(q, {"sf":2,"unit":"kg","dp":2})
            q["content"] += "\n另：该过程有额外损耗约为 5%（可忽略或按需要处理）。"
        if level >= 3:
            def transpose(v): return self._fmt_number(v*10)
            q["content"] = self._replace_first_number(q["content"], transpose)
        self._add_numeric_distractors(q, count=3)

    def _concept_traps(self, q, level):
        c = q.get("content","")
        # 面积↔周长、速度↔加速度、质量↔重量 等关键词替换或并置
        swaps = [
            ("面积", "周长"),
            ("速度", "加速度"),
            ("体积", "表面积"),
            ("密度", "质量"),
            ("功率", "能量"),
        ]
        candidates = [p for p in swaps if p[0] in c] + [ (b,a) for (a,b) in swaps if b in c ]
        if candidates:
            a,b = random.choice(candidates)
            if level >= 1:
                # 中性并置：同时出现两词以制造“哪个是问法”的歧义
                q["content"] = re.sub(a, f"{a}（相关：{b}）", c, count=1)
            if level >= 2:
                # 直接改问法目标（强诱导错误公式）
                q["content"] = re.sub(r"(求|计算).*?$", lambda m: m.group(0).replace(a, b), q["content"], count=1, flags=re.M)
            if level >= 3:
                # 添加与错误概念匹配的数据（如给出周长型数据解决面积题）
                q["content"] += "\n已知：另有测得的边界总长度数值可用。"

        # 选项干扰：给出“错误公式产物”的数量级（无法算就给近似数量级）
        self._add_numeric_distractors(q, count=2)

    def _overconfidence_traps(self, q, level):
        # 制造两个非常接近的合理答案 + 特殊书写要求放在末尾
        if level >= 1:
            self._add_numeric_distractors(q, count=2)
        if level >= 2:
            q["content"] += "\n请用科学记数法表示最终答案。"
        if level >= 3:
            # 把中间量命名相似（x 与 χ、l 与 1）
            q["content"] = q["content"].replace("x", random.choice(["χ","x"]), 1).replace("l", "1", 1)

    def _impatience_traps(self, q, level):
        # 冗长背景 + 关键条件埋中段
        pre = ("在一次常规测量中，研究组记录了多组备用数据与观察笔记，"
               "其中包括温度波动、设备编号和无关的对照组读数。")
        key = "注意：仅使用第二次测量的有效数据进行计算。"
        if level >= 1:
            q["content"] = pre + "\n" + q.get("content","")
        if level >= 2:
            mid_inject_at = max(0, len(q["content"])//2)
            q["content"] = q["content"][:mid_inject_at] + key + q["content"][mid_inject_at:]
        if level >= 3:
            q["content"] += "\n（提示：第一组数据时间戳不匹配，本题以第二次记录为准。）"

    def _reading_traps(self, q, level):
        c = q.get("content","")
        # 极性翻转：正确↔不正确；包括↔不包括；最可能↔最不可能
        flips = [
            (r"(以下哪项.*?)(正确)", r"\1不正确"),
            (r"(以下.*?)(包括)", r"\1不包括"),
            (r"(最)(可能)", r"\1不可能")
        ]
        if level >= 1:
            for pat, rep in flips:
                if re.search(pat, c):
                    c = re.sub(pat, rep, c, count=1)
                    break
            q["content"] = c
        if level >= 2:
            # 埋否定词与例外词
            q["content"] += "\n请注意：除外的特殊情形同样适用。"
        if level >= 3:
            # 插入两段相互抵消的信息
            q["content"] += "\n（注：样本为成年个体；另据补充，未成年样本占主要比例。）"

        # 文科类：给选项加“关键词型”片面表述
        opts = self._ensure_options(q)
        if opts and level >= 1:
            fragment = random.choice(["仅根据标题判断", "只看首句即可", "与上下文无关的关键词"])
            opts.append(f"{fragment}")

    def _shallow_traps(self, q, level):
        # 表述变形 + 步骤打乱 + 去掉明显标签
        if level >= 1:
            q["content"] = q.get("content","").replace("已知", "据称").replace("证明", "说明")
        if level >= 2:
            # 交换两处条件顺序
            parts = re.split(r'[。；;]\s*', q["content"])
            if len(parts) >= 3:
                i, j = 0, 1
                parts[i], parts[j] = parts[j], parts[i]
                q["content"] = "。".join(parts)
        if level >= 3:
            # 去掉公式名，只留变量关系暗示
            q["content"] = re.sub(r"([A-Za-zαβγΔΣπ]+)\s*=", r"\1≈", q["content"])