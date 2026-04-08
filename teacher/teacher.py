import os
import json
from datetime import datetime
from datetime import timedelta
import sys
import re

sys.path.append(os.path.dirname(os.path.abspath(__file__)))#为了导入teacher下的包
from vector_db import VectorDB 
from Textbook.textbook_pretreat import textbook_pretreat
from personality.personalize import personalize

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))#为了导入root下的包
from util.BroadcastSys import BroadcastSys
from util.BroadcastMessage import BroadcastMessage, MessageType
from util.Recorder import Recorder
from util.model import call_LLM_sync
from student.cognitive_module.student import Student
from student.cognitive_module.scratch import Scratch


script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class Teacher:
    def __init__(self, broadcast_sys:BroadcastSys = None, init_file:str = os.path.join(root_dir, "config", "teacher.json"), student_list:list = None):
        """
        教师初始化
        """
        # 读取教师信息
        data = {}
        with open(init_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 教师基本参数
        self.name = data["name"]
        self.age = data["age"]
        self.subject = data["subject"]
        self.ep_level = data["experience_level"]  # 教学经验水平，分为basic, intermediate, advanced, expert(记录下每个等级经验库训练的课时和教材范围)
        self.pck_level = data["pck_level"]#教学内容知识水平，分为basic, intermediate, advanced, expert(比如basic可以用最基础的小学到初中的教材进行训练，expert可以用大学教材和竞赛资料进行训练)
        self.overall_target = data["overall_target"]
        self.teaching_strategy_template = data["teaching_strategy_template"]  # 教学策略模板，分为“high_level”（高阶）和“low_level”（低阶），默认是高阶
        self.teaching_strategy = data["teaching_strategy"]
        self.teacher_identity = data["teacher_identity"]  # 教师身份

        #文件地址参数
        self.ep_init_file= os.path.join(script_dir, "Experience/experience_init.txt")
        self.ep_buffer_file= os.path.join(script_dir, "Experience/experience_buffer.txt")
        self.ep_vector_db_file= os.path.join(script_dir, "Experience/ep_vector_db")
        self.pck_vector_db_file= os.path.join(script_dir, "PCK/pck_vector_db")
        self.textbook_file_dirname = os.path.join(script_dir, "Textbook/")
        self.sections_file = os.path.join(script_dir, "Textbook/sections.json")
        self.subsections_file = os.path.join(script_dir, "subsections.json")
        self.status_file_dirname = os.path.join(script_dir, "Status/")

        # 教师高级参数
        #personality
        traits = {}
        personalize_or_not = data["personalize_or_not"]
        personality_theory = data.get("personality_theory", "")
        if personalize_or_not == "no":
            traits_file = os.path.join(script_dir, "personality/default_traits.json")
            with open(traits_file, "r", encoding='utf-8') as f:
                traits = json.load(f)
        else:            
            traits_file = os.path.join(script_dir, "personality/traits.json")
            if personalize_or_not == "yes":
                personalize(personality_theory)
            with open(traits_file, "r", encoding='utf-8') as f:
                traits = json.load(f)
            print(f"人格表单: {traits}")#展示给用户
            print("""请确认表单中各特质与其相应权重：\nP_N权重范围为-1到1，P_N权重影响个体的积极性和消极性，若该特质令个体心理倾向于积极，则P_N权重为正，反之为负，倾向积极或消极的程度越高，数值绝对值越高（绝对值0~0.3表示影响程度较小，0.3~0.7表示影响程度中等，0.7~1表示影响程度较大）。\nV_S权重范围为-1到1，V_S权重影响个体的生动性和死板性，若该特质令个体说话方式倾向于生动，则V_S权重为正，反之为负，倾向生动或死板的程度越高，数值绝对值越高（绝对值0~0.3表示影响程度较小，0.3~0.7表示影响程度中等，0.7~1表示影响程度较大）。：""")
            for trait, data in traits.items():
                print(f"请输入{trait}指数(0~10):")
                index = int(input())
                data["指数"] = index
        PN_index = 0
        VS_index = 0
        for trait,data in traits.items():
            PN_index += data["指数"] * data["P_N权重"]
            VS_index += data["指数"] * data["V_S权重"]
        self.PN_index = PN_index
        if VS_index > 8:
            speaking_style = "尽可能生动"
        elif VS_index > 6:
            speaking_style = "生动"
        elif VS_index > 4:
            speaking_style = "不太生动"
        elif VS_index > 2:
            speaking_style = "死板"
        else:
            speaking_style = "尽可能死板"
        self.speaking_style = speaking_style
        #experience
        leveled_ep_vector_db_file = os.path.join(self.ep_vector_db_file, f"{self.ep_level}")
        if os.path.exists(leveled_ep_vector_db_file):
            self.ep_vector_db = VectorDB()
            self.ep_vector_db.load(path=leveled_ep_vector_db_file)
            self.ep_vector_db.delete_documents()  # 经验初始化文件是用户可以编辑的教学策略，这里保证上一次输入的教学策略不会影响本次教学，同时在教学过程中形成的经验保留下来
        else:
            self.ep_vector_db = VectorDB()
        with open(self.ep_init_file, 'r', encoding='utf-8') as f:
            init_text = f.read()
        self.ep_vector_db.create_from_text(text = init_text, init = True)
        #pck
        pck_subject_file = os.path.join(self.pck_vector_db_file, f"{self.subject}")
        leveled_pck_vector_db_file = os.path.join(pck_subject_file, f"{self.pck_level}")
        if os.path.exists(leveled_pck_vector_db_file):
            self.pck_vector_db = VectorDB()
            self.pck_vector_db.load(path=leveled_pck_vector_db_file)
        else:
            self.pck_vector_db = VectorDB()
        
        #更新类属性要同步更新finish_class方法和update_status方法
        #课程参数
        self.class_number = 1 # 当前讲到第几节课
        self.target = ""  #当前课程目标
        self.student = student_list if student_list is not None else []  #学生列表
        #教材（start_class）
        self.current_section_turn = 2  #当前讲到教材的哪一节，用作索引-1（本来是1，但教材分割第一节 是空所以为2）
        self.sections_this_class = 0  #这节课要讲的小节数
        self.text_this_class = ""
        self.subsections = []  #分割的教材内容
        self.current_subsection_turn = 1 #当前讲到教材的哪一小节,用作索引-1
        self.importance = []  #所有subsection的重要性列表，范围从0到10，0表示不重要，10表示非常重要
        self.focus = []  #所有subsection的侧重点列表，“思考”或“练习”
        #讲课（next_subsection and teach and activate）
        self.detail_level = 0  # 讲解详略程度，范围从0到10，0表示不讲，10表示用10轮讲
        self.plan = []  #教学计划
        self.plan_methods = []  #对应每段教学内容的教学方式
        self.current_plan_turn = 1  #当前讲到教学内容的哪一段，用作索引-1
        self.subsection_selected = 0  #决定进行活动时当前选择的小节
        self.activity_type = ""
        self.duration = 5  #一次活动持续时间
        self.duration_turn = 1  #当前进行到活动的哪一时间,用作索引-1
        self.times = 0  #活动次数，防止连续进行活动
        self.activity_content = ""  # 当前活动接收到的信息
        #状态 
        self.saw = ""
        self.answered = "" 
        self.discussed = ""  
        self.practiced = ""  
        self.to_solve = ""
        self.feedback = "" 
        self.taught = "" #之前的讲课内容
        self.experience = ""
        self.type = ""  #当前教学活动类型
        self.period = "not_started" # 当前教学阶段，分为“not_started”（未开始）、“decide_ended”(一次决策结束)、“subsection_activity”、“subsection_lecture”、“already_ended”（课程结束）
        self.class_turns = 40  #每节课40轮
        self.current_turn = 0
        self.content = "还没开始上课" #当前教学内容

        # 广播机制
        if broadcast_sys is None:
            raise ValueError("Broadcast system is not provided")
        self.broadcast_sys = broadcast_sys; 
        self.broadcast_sys.subscribe(self, "teacher")  # 订阅广播
        self.received = []
        self.time = datetime.strptime("2025-09-01 08:00:00", "%Y-%m-%d %H:%M:%S")


    #系统调用
    @classmethod
    async def initialize_teacher_async(cls, broadcast_sys: BroadcastSys = None, init_file: str = os.path.join(root_dir, "config", "teacher.json"), student_list: list = None):
        """
        异步工厂方法，用于在异步环境中创建Teacher实例
        """
        # 读取教师信息
        with open(init_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 异步处理教材（如果需要）
        textbook_file = data["textbook_file"]
        if textbook_file != "use last":
            await textbook_pretreat(textbook_file)

        # 创建实例并初始化（跳过教材处理）
        instance = cls.__new__(cls)
        instance.__init__(broadcast_sys, init_file, student_list)
        
        return instance
    def _strip_think_blocks(self, text: str) -> str:
        """
        去除 reasoning 模型返回中的 <think>...</think> 内容，以免干扰后续解析或展示。
        """
        try:
            return re.sub(r"(?is)<think>.*?</think>", "", text)
        except Exception:
            return text



    def _generate_plan_with_constraints(self, segments: int, prefer_method: str = "", extra_instruction: str = ""):
        """
        生成受约束的教学计划，用于补全剩余计划。
        """
        high_level_teaching_strategy_template = f"""
        *不依赖教材，总结归纳教材内容并用简单易懂的话讲解。
        *提出需分析、推理、综合的高阶问题，不要问“是什么”，而要问“为什么”
        *重视学生观点，接收到学生观点时，可以追问学生答案，比如提问“能解释你为何这样想吗？”
        *鼓励多元视角，可以经常邀请不同观点，例如问“其他人有不同看法吗？”
        *用学生回答引发新问题，比如问“同学A提到的这个概念，大家如何理解这个概念？”
        *评价时给出带反馈的评价，指出答案价值并说明原因，比如“这个观点很好，因为它结合了文本细节”
        *引导学生关注同伴观点，如：“注意同学B的观察，这对理解主题很重要”
        *学生主动提出问题后给予鼓励
        """
        low_level_teaching_strategy_template = f"""
        *依赖教材，完全按照教材讲解。
        *孤立事实提问，例如问“这个词什么意思？”
        *重复答案不延伸，例如学生答后仅说“对”或“错”
        *不重视学生观点，接收到学生反馈时忽略
        *禁止自发讨论，例如指令：“独立完成，不准交谈”，很少进行小组讨论或学生展示
        """
        strategy = ""
        if self.teaching_strategy_template == "high_level":
            strategy = high_level_teaching_strategy_template
        elif self.teaching_strategy_template == "low_level":
            strategy = low_level_teaching_strategy_template
        strategy += self.teaching_strategy

        docs = self.pck_vector_db.search(self.subsections[self.current_subsection_turn-1]) if self.subsections else []
        pck_knowledge = ""
        for doc in docs:
            pck_knowledge += f"{doc.page_content.strip()}\n"

        constraint_text = ""
        if prefer_method:
            constraint_text += f"\n优先使用教学方法：{prefer_method}。"
        if extra_instruction:
            constraint_text += f"\n额外约束：{extra_instruction}"

        prompt = f"""
        你是一个教育专家，基于教师教学经验以及教学策略，并结合相关专业知识，对之后要讲的内容生成教学计划。
        教学经验：{self.experience}
        相关专业知识：{pck_knowledge}
        教学策略：{strategy}
        之后要讲的内容：{self.subsections[self.current_subsection_turn-1] if self.subsections else self.text_this_class}

        要求：
        * 仅生成剩余的教学计划，共 {segments} 段。
        * 每一段计划只能在“陈述知识点”，“向同学提问”，“对接收到的回答进行评价”中选择一种作为教学方式。
        * 提问后必须进行评价（可放在后续段）。
        * 不要在一段计划中出现多个教学方式。
        * 输出为json，键为"plan"，值为数组，每项包含"content"和"method"。
        {constraint_text}
        """
        response = call_LLM_sync(
            "teacher",
            messages=[
                {"role": "system", "content": self.teacher_identity},
                {"role": "user", "content": prompt},
            ],
            response_format={'type': 'json_object'}
        )
        result = json.loads(response)
        return result.get("plan", [])

    def regenerate_remaining_plan(self, segments: int = None, prefer_method: str = "", instruction: str = "") -> str:
        """
        仅重生成“尚未执行”的教学计划，不修改已经执行的计划前缀。
        以 current_plan_turn 为分界：保留 [0, current_plan_turn-2]，从 current_plan_turn 开始重算。
        """
        # 情况A：位于小节边界（即将开始下一个小节），此时没有待执行计划
        if self.period == "decide_ended" and (not self.plan or self.current_plan_turn > len(self.plan)):
            # 进入正常决策流程，自动生成下一小节的完整计划
            self.decide()
            return "已为当前小节生成新的教学计划"

        # 情况B：处于讲课阶段，存在已执行前缀与未执行后缀
        if segments is None:
            segments = max(1, max(1, self.detail_level) - (self.current_plan_turn - 1))

        new_plan_items = self._generate_plan_with_constraints(segments, prefer_method=prefer_method, extra_instruction=instruction)

        prefix_contents = self.plan[:max(0, self.current_plan_turn-1)]
        prefix_methods = self.plan_methods[:max(0, self.current_plan_turn-1)]

        self.plan = prefix_contents + [item.get("content", "").strip() for item in new_plan_items]
        self.plan_methods = prefix_methods + [item.get("method", "").strip() for item in new_plan_items]

        # 回到讲课阶段，继续从 current_plan_turn 执行
        self.period = "subsection_lecture"
        self.activity_type = ""
        self.times = 0
        return "已重生成剩余教学计划"

    def get_info(self):
        """
        返回教师基本信息
        """
        return f"Teacher Name: {self.name}, Age: {self.age}, Subject: {self.subject}"

    def jump(self, status_file):
        """
        跳转到指定的状态
        """
        #检查文件是否存在
        if not os.path.exists(status_file):
            raise FileNotFoundError(f"状态文件不存在: {status_file}")

        #读取JSON文件
        with open(status_file, 'r', encoding='utf-8') as f:
            status_data = json.load(f)

        #验证JSON数据格式
        if not isinstance(status_data, dict):
            raise ValueError(f"状态文件格式错误: {status_file}")  #格式错误

        #遍历JSON中的所有键值对，赋值给对应属性
        for key, value in status_data.items():
            if hasattr(self, key):
                # 特殊字段转换
                if key == "time" and isinstance(value, str):
                    try:
                        setattr(self, "time", datetime.strptime(value, "%Y-%m-%d %H:%M:%S"))
                    except Exception:
                        pass
                    continue
                setattr(self, key, value)
                
        print(f"成功从 {status_file} 恢复状态")  #成功提示
        return True

    # …………

    #功能函数
    async def receive_broadcast(self, content: dict):
        self.received.append(content)

    def receive_broadcast_sync(self, content: dict):
        self.received.append(content)

    async def handle_observer_intervention(self, intervention_data: dict):
        """
        处理观察者干预，调整教学计划（预留接口）
        
        Args:
            intervention_data: 观察者干预数据，包含调整指令和参数
            
        Returns:
            str: 处理结果描述
            
        示例 intervention_data 格式:
        {
            "type": "adjust_plan",  // 调整类型：adjust_plan, change_strategy, skip_section等
            "instruction": "学生注意力下降，建议增加互动环节",
            "parameters": {
                "add_discussion": true,
                "topic": "相反数的实际应用"
            }
        }
        
        TODO: 
        - 解析intervention_data中的指令
        - 根据指令类型调用不同的处理方法
        - 调整self.plan、self.teaching_strategy等属性
        - 使用LLM理解自然语言指令
        - 返回调整后的计划描述
        """
        print(f"\n[Teacher.handle_observer_intervention] 收到观察者干预")
        print(f"  类型: {intervention_data.get('type', '未指定')}")
        print(f"  指令: {intervention_data.get('instruction', '无')}")

        intervention_type = (intervention_data.get("type") or "").strip()
        params = intervention_data.get("parameters", {}) or {}
        instruction = (intervention_data.get("instruction") or "").strip()

        # 使用类级别的生成方法

        # 1) 调整教学计划
        if intervention_type == "adjust_plan":
            prefer_method = params.get("prefer_method", "")
            segments = params.get("segments")
            if segments is None:
                remaining = max(1, max(1, self.detail_level) - (self.current_plan_turn - 1))
                segments = remaining
            new_plan_items = self._generate_plan_with_constraints(segments, prefer_method=prefer_method, extra_instruction=instruction)
            # 拼接：保留已完成的计划段，替换剩余部分
            prefix_contents = self.plan[:max(0, self.current_plan_turn-1)]
            prefix_methods = self.plan_methods[:max(0, self.current_plan_turn-1)]
            self.plan = prefix_contents + [item.get("content", "").strip() for item in new_plan_items]
            self.plan_methods = prefix_methods + [item.get("method", "").strip() for item in new_plan_items]
            self.period = "subsection_lecture"
            self.activity_type = ""
            self.times = 0
            return "已根据干预重塑当前教学计划"

        # 2) 改变教学策略
        if intervention_type == "change_strategy":
            new_template = (params.get("template") or "").strip()  # high_level / low_level
            new_strategy = params.get("append_strategy", "")
            if new_template in ("high_level", "low_level"):
                self.teaching_strategy_template = new_template
            if new_strategy:
                self.teaching_strategy = new_strategy
            remaining = max(1, max(1, self.detail_level) - (self.current_plan_turn - 1))
            new_plan_items = self._generate_plan_with_constraints(remaining, extra_instruction=instruction)
            prefix_contents = self.plan[:max(0, self.current_plan_turn-1)]
            prefix_methods = self.plan_methods[:max(0, self.current_plan_turn-1)]
            self.plan = prefix_contents + [item.get("content", "").strip() for item in new_plan_items]
            self.plan_methods = prefix_methods + [item.get("method", "").strip() for item in new_plan_items]
            self.period = "subsection_lecture"
            return "已根据新策略更新后续教学计划"

        # 3) 跳过小节/跳转到指定小节
        if intervention_type == "skip_section":
            to_index = params.get("to_subsection_index")  # 1-based
            if to_index is None:
                # 默认跳过当前小节，进入下一小节
                self.current_subsection_turn += 1
            else:
                try:
                    to_index = int(to_index)
                    if to_index >= 1:
                        self.current_subsection_turn = to_index
                except Exception:
                    pass
            self.plan = []
            self.plan_methods = []
            self.current_plan_turn = 1
            self.period = "decide_ended"
            self.activity_type = ""
            return "已跳转至指定小节并清空当前计划，等待重新决策"

        # 4) 注入活动（例如小组讨论）
        if intervention_type == "inject_activity":
            self.activity_type = "group_discussion"
            duration = params.get("duration")
            try:
                if duration is not None:
                    self.duration = max(1, int(duration))
            except Exception:
                pass
            # 默认选择当前小节进行活动
            self.subsection_selected = max(0, self.current_subsection_turn - 1)
            self.duration_turn = 1
            self.period = "subsection_activity"
            return "已切换至小组讨论活动"

        # 5) 调整详略程度并重塑剩余计划
        if intervention_type == "set_detail_level":
            try:
                new_level = int(params.get("detail_level"))
                self.detail_level = max(1, new_level)
            except Exception:
                pass
            remaining = max(1, self.detail_level - (self.current_plan_turn - 1))
            new_plan_items = self._generate_plan_with_constraints(remaining, extra_instruction=instruction)
            prefix_contents = self.plan[:max(0, self.current_plan_turn-1)]
            prefix_methods = self.plan_methods[:max(0, self.current_plan_turn-1)]
            self.plan = prefix_contents + [item.get("content", "").strip() for item in new_plan_items]
            self.plan_methods = prefix_methods + [item.get("method", "").strip() for item in new_plan_items]
            self.period = "subsection_lecture"
            return "已调整详略程度并更新后续计划"

        # 6) 设置活动时长
        if intervention_type == "set_duration":
            try:
                new_duration = int(params.get("duration"))
                self.duration = max(1, new_duration)
            except Exception:
                pass
            return "已设置活动时长"

        return "未识别的干预类型或无需调整"

    def perceive(self):
        '''
        '''
        self.saw = ""
        self.answered = ""
        self.discussed = "" 
        self.feedback = ""
        self.to_solve = ""  
        for content in self.received:
            if content["active_event"] == "active":
                self.to_solve += f"{content['speaker']}正在提出请求,具体内容为：{content['content']}；"
            elif content["active_event"] == "answer":
                self.answered += f"{content['speaker']}回答了问题，内容为：{content['content']}；"
            elif content["active_event"] == "group_discussion":
                self.discussed += f"{content['speaker']}正在进行小组讨论总结，内容为：{content['content']}；"
            elif content["active_event"] == "practice":
                self.practiced += f"{content['speaker']}正在进行练习，内容为：{content['content']}；"
            elif content["active_event"] == "feedback":
                self.feedback += f"{content['speaker']}给出了反馈，内容为：{content['content']}；"
            else:
                self.saw += f"{content['speaker']}正在{content['active_event']},具体内容为：{content['content']}；"

            if content["active_event"] == "new_day":
                self.time = (self.time + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)

        self.received = []  # clear received after processing

    def retrive(self, content: str):
        """从教学经验中检索相关的经验"""
        self.experience = ""  # 清空之前的经验
        docs = self.ep_vector_db.search(content)
        for doc in docs:
            self.experience += f"{doc.page_content.strip()}\n"

    def update_target(self):
        """获取本节课的教学目标"""
        prompt = f"""
        基于整体教学目标和本节课的教学内容，生成本节课的教学目标。
        要求：
        * 从培养学生知识、能力、价值观念三个方面生成教学目标。
        * 整体教学目标为空时可以只依赖教学内容。
        * 要求简洁精确，只输出教学目标，只输出一段话，不要输出任何解释或额外内容。
        整体教学目标：{self.overall_target}
        教学内容：{self.text_this_class}
        """
        response = call_LLM_sync(
            "teacher",
            messages=[
                {"role": "system", "content": self.teacher_identity},
                {"role": "user", "content": prompt},
            ]
        )
        self.target = self._strip_think_blocks(response).strip()
    
    def update_experience(self):
        '''
        反思并更新教学经验
        '''
        self.perceive() #获取feedback，独立于更新状态之外的观察，因为更新经验的过程不让访问，设置初始状态时会重置
        #反思
        prompt = f"""
        你是一个教学反思专家，通过教学记录，教学内容和学生反馈进行反思，生成教学经验。
        教学记录：{self.taught}
        教材内容：{self.text_this_class}
        学生反馈：{self.feedback}
        请按照以下步骤 进行思考：
        1.回顾教材内容和教学记录，总结自己所做的行动。
        2.结合学生反馈，意识到关键问题。
        3.形成替代性的行动方案。
        4.总结出教学经验。
        最后结果只输出教学经验。
        """
        response = call_LLM_sync(
            "teacher",
            messages=[
                {"role": "system", "content": self.teacher_identity},
                {"role": "user", "content": prompt},
            ]
        )
        experience = response.strip()
        #更新经验
        self.ep_vector_db.create_from_text(text=experience)
        self.period = "not_started"  # 更新经验后，回到未开始状态
        #重置taught和text_this_class和current_turn
        self.taught = ""
        self.text_this_class = ""
        self.current_turn = 0 
        self.type = ""  #重置type
        self.content = "还没开始上课"  #重置content
        #保存向量数据库
        self.ep_vector_db.save(path=os.path.join(self.ep_vector_db_file, f"{self.ep_level}"))
        self.pck_vector_db.save(path=os.path.join(self.pck_vector_db_file, f"{self.subject}", f"{self.pck_level}"))
        print("教学经验已更新并保存。")  #提示

    def update_status(self):
        """
        更新教师状态，保存当前状态到文件
        """
        #更新状态
        self.perceive() #更新感知信息
        teacher_actions = ""
        for plan in self.plan:
            teacher_actions += plan
        t = self.saw + self.answered + self.discussed + self.practiced + self.to_solve + self.feedback + teacher_actions + '\n' + teacher_actions
        self.retrive(t) #更新经验
        status = {
            "class_number": self.class_number,
            "target": self.target,
            "current_section_turn": self.current_section_turn,
            "sections_this_class": self.sections_this_class,
            "text_this_class": self.text_this_class,
            "subsections": self.subsections,
            "current_subsection_turn": self.current_subsection_turn,
            "importance": self.importance,
            "focus": self.focus,
            "detail_level": self.detail_level,
            "plan": self.plan,
            "plan_methods": self.plan_methods,
            "current_plan_turn": self.current_plan_turn,
            "subsection_selected": self.subsection_selected,
            "activity_type": self.activity_type,
            "duration": self.duration,
            "duration_turn": self.duration_turn,
            "times": self.times,
            "activity_content": self.activity_content,
            "saw": self.saw,
            "answered": self.answered,
            "discussed": self.discussed,
            "to_solve": self.to_solve,
            "feedback": self.feedback,
            "taught": self.taught,
            "experience": self.experience,
            "type": self.type,
            "period": self.period,
            "class_turns": self.class_turns,
            "current_turn": self.current_turn,
            "content": self.content,
            "time": datetime.strftime(self.time, "%Y-%m-%d %H:%M:%S"),
            "PN_index": self.PN_index,
            "speaking_style": self.speaking_style
        }
        with open(self.status_file_dirname + f"status_{self.class_number}_{self.current_turn}.json", 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False, indent=4)


    #教学活动
    def start_class(self):
        '''开始上课时，决定教材内容，教学目标，并对教材进行分割'''
        sections = []
        with open(self.sections_file, 'r', encoding='utf-8') as f:
            sections = json.load(f)["sections"]
        # 决定当前节课的教学内容（如果要根据内容多少决定讲多少节，执行一个按token数对sections进行合并的操作）
        self.text_this_class = sections[self.current_section_turn - 1]
        # 教学目标
        self.update_target()
        # 教材分割
        text = f"""
        教材内容：{self.text_this_class}
        """
        prompt = """
        对教材进行分割，并对分割后的教材按照重要性进行评估打分，并分析每一部分教材的侧重点。
        *分割要求：
        将教材内容分割为若干部分，每一部分都相对完整，围绕着同一主题。
        不能忽略或跳过任何教材内容。
        分割数量小于八，大于五。
        *评估要求（从以下几个方面评估分割后每一部分教材的重要性，越重要分数越高，打分范围0-10，必须为整数，方差可以适当大些）：
        1. 核心概念重要性 : 
            - 该部分是否包含学科核心概念或基础理论
            -这些概念对理解整个学科体系的重要程度
        2. 知识应用价值 :
            - 内容在实际应用中的价值
            - 对解决问题能力的培养程度
        3. 认知难度 :
            - 内容理解难度
            - 是否需要先掌握其他概念作为前提
        4. 考试权重 :
            - 在考试评估中出现的频率和分值比重
            - 是否是常见的考察重点
        *分析侧重点要求：
        从“思考”，“练习”中选择一个，“思考”表示该内容侧重于学生进行思考和理解，“练习”表示该内容侧重于学生的练习和巩固。
        *请按照以下格式输出JSON：
        {
          "subsections": [
            {
              "content": "教材部分内容",
              "score": "重要性得分",
              "focus": "思考/练习"
            },
            {
              "content": "教材部分内容",
              "score": "重要性得分",
              "focus": "思考/练习"
            },
            ...
          ]
        }
        """
        response = call_LLM_sync(
            "teacher",
            messages=[
                {"role": "system", "content": self.teacher_identity},
                {"role": "system", "content": text},
                {"role": "user", "content": prompt},
            ],
            response_format={
                'type': 'json_object'
            }
        )
        t = []
        with open(self.subsections_file, 'w', encoding='utf-8') as subsections_file:
            subsections_file.write(response)
        with open(self.subsections_file, 'r', encoding='utf-8') as subsections_file:
            t = json.load(subsections_file)["subsections"]
        for item in t:
            self.subsections.append(item['content'])
            self.importance.append(item['score'])
            self.focus.append(item['focus'])
        self.type = "start_class" 
        # 广播
        msg = BroadcastMessage(
            current_time=self.time,
            message_type=MessageType.COMMAND,
            active_event=self.type,
            speaker=self.name,
            content=f"开始上课，教学目标是：{self.target}"
        )
        self.broadcast_sys.publish_sync("student", msg)
        #更新状态
        self.content = "现在开始上课。"
        self.period = "decide_ended"  # 开启第一次决策

    
    def decide(self):
        '''
        判断进行活动还是讲课，并做一些前置工作
        '''
        #先判断是否结束课程
        teaching_progress = (self.current_subsection_turn-1)/len(self.subsections)
        class_progress = self.current_turn/self.class_turns
        if teaching_progress >= 1:# 教学已完成
            if class_progress < 1:
                self.period = "waiting_for_end"
                print("decide: waiting for end")
                return 
            if class_progress >= 1:
                self.period = "already_ended"
                print("decide: already ended")
                return 
        #教学未完成
        if class_progress < 1:# 课程未结束,考虑进行活动
            #评估学生注意力
            print(f"学生反馈：{self.saw}")
            prompt = f"""
            基于学生反馈，评估所有学生的总体注意力水平。
            学生反馈：{self.saw}
            要求：
            *评估学生的总体注意力水平，范围从0到10，0表示学生都没有集中注意，10表示学生的注意力都非常集中。
            *只输出一个整数，范围从0到10，不要输出其他任何内容。
            你的评估结果：
            """
            response = call_LLM_sync(
                "teacher",
                messages=[
                    {"role": "system", "content": self.teacher_identity},
                    {"role": "user", "content": prompt},
                ]
            )
            attention = int(self._strip_think_blocks(response).strip())
            print(f"学生注意力水平：{attention}")
            #根据课程内容重要性和学生注意力水平决定是否进行活动,然后根据侧重点决定进行哪项活动
            #可以引入更多参数决定是否活动，权重表示老师的侧重可以进行一些变量实验，具体进行哪些活动还需要实现
            self.subsection_selected = self.current_subsection_turn - 2 if (self.current_subsection_turn > len(self.subsections) or self.importance[self.current_subsection_turn - 2] > self.importance[self.current_subsection_turn - 1]) else self.current_subsection_turn - 1
            #上表达式注意防止越界
            importance = int(self.importance[self.subsection_selected])
            importance_weight = 1  #重要性权重
            attention_weight = 1  #注意力权重
            times_weight = 4  #不要连续进行活动，除非重要性特别高和注意力特别低
            d = self.PN_index + importance * importance_weight - attention * attention_weight - times_weight * self.times
            print(f"当前决策因素：积极指数-{self.PN_index}, 小节重要性-{importance}, 注意力-{attention}, 活动次数-{self.times}")
            if d > 8:#大于阈值 have to test
                #暂时只有小组讨论，可以利用已经设计好的focus属性扩展更多活动类型
                self.activity_type = "group_discussion"
                self.period = "subsection_activity"
                self.times += 1  # 更新活动次数
                self.duration_turn = 1  # 重置活动轮数
                return
            else:
                self.times = 0  # 重置活动次数
        #如果不进行活动（class_progress >= 1或决定不进行活动未return） 
        #决定详略程度
        #结合重要性
        sub_num = len(self.subsections)
        average = 40/sub_num
        total_score = 0
        for ip in self.importance:
            total_score += int(ip)
        now_average = total_score/sub_num
        p = average/now_average
        self.detail_level = int(self.importance[self.current_subsection_turn-1]*p)
        #结合教学进度
        if class_progress >= 1:
            self.detail_level = 1  # 如果课程进度超过1，说明课程超时，详略程度设为1
        if teaching_progress > class_progress:
            self.detail_level += 1
        elif teaching_progress < class_progress:
            self.detail_level -= 1
            if self.detail_level <= 0:
                self.detail_level = 1
        print(f"详略程度：{self.detail_level}")
        #根据教师风格（策略）生成讲课内容
        high_level_teaching_strategy_template = f"""
        *不依赖教材，总结归纳教材内容并用简单易懂的话讲解。
        *提出需分析、推理、综合的高阶问题，不要问“是什么”，而要问“为什么”
        *重视学生观点，接收到学生观点时，可以追问学生答案，比如提问“能解释你为何这样想吗？”
        *鼓励多元视角，可以经常邀请不同观点，例如问“其他人有不同看法吗？”
        *用学生回答引发新问题，比如问“同学A提到的这个概念，大家如何理解这个概念？”
        *评价时给出带反馈的评价，指出答案价值并说明原因，比如“这个观点很好，因为它结合了文本细节”
        *引导学生关注同伴观点，如：“注意同学B的观察，这对理解主题很重要”
        *学生主动提出问题后给予鼓励
        """
        low_level_teaching_strategy_template = f"""
        *依赖教材，完全按照教材讲解。
        *孤立事实提问，例如问“这个词什么意思？”
        *重复答案不延伸，例如学生答后仅说“对”或“错”
        *不重视学生观点，接收到学生反馈时忽略
        *禁止自发讨论，例如指令：“独立完成，不准交谈”，很少进行小组讨论或学生展示
        """
        strategy = ""
        if self.teaching_strategy_template == "high_level":
            strategy = high_level_teaching_strategy_template
        elif self.teaching_strategy_template == "low_level":
            strategy = low_level_teaching_strategy_template
        strategy += self.teaching_strategy
        #pck知识
        docs = self.pck_vector_db.search(self.subsections[self.current_subsection_turn-1])
        pck_knowledge = ""
        for doc in docs:
            pck_knowledge += f"{doc.page_content.strip()}\n"
        #生成教学计划
        json_example = """
        {
            "plan": [
                {
                "content": "首先由沈阳的温度情况引入正负数概念，提问学生生活中是否有其他正负数例子",
                "method": "向同学提问"
                },
                {
                    "content": "接着对同学们的回答进行评价，鼓励同学们积极思考",
                    "method": "对接收到的回答进行评价"
                },
                {
                    "content": "接下来解释正数和负数的定义和符号表示",
                    "method": "陈述知识点"
                },
                {
                    "content": "强调0既不是正数也不是负数，提问学生对此有什么看法",
                    "method": "向同学提问"
                },
                {
                    "content": "对学生的看法进行评价，鼓励同学们积极思考",
                    "method": "对接收到的回答进行评价"
                },
                {
                    "content": "最后总结数的产生和发展的过程",
                    "method": "陈述知识点"
                }
            ]
        }
        """
        prompt = f"""
        你是一个教育专家，基于教师教学经验以及教学策略，并结合相关专业知识，对之后要讲的内容生成教学计划。
        教学经验：{self.experience}
        相关专业知识：{pck_knowledge}
        教学策略：{strategy}
        之后要讲的内容：{self.subsections[self.current_subsection_turn-1]}

        要求：
        *计划分必须分为{self.detail_level}段。
        *每一段计划只能在“陈述知识点”，“向同学提问”，“对接收到的回答进行评价”中选择一种作为教学方式。
        *提问后必须进行评价。
        *不要在一段计划中出现多个教学方式，例如“评价后追问”，可以分为“评价”和“追问”两段进行。
        *输出为json格式，包括每一段计划和其使用的教学方法。

        示例：
        之后要讲的内容："某天, 沈阳的最低温度是 -12°C, 表示零下12°C; 最高温度是3°C, 表示零上3°C。零上3°C和零下12°C是具有相反意义的量, 我们可以用正数和负数来表示。在以上出现的数中, 像-12、-2.5、-237、-0.7这样的数是负数(negative number), 像3、3.5、500、1.2这样的数是正数(positive number)。正数前面有时也可放上一个“+”(读作“正”)号, 如7可以写成+7。注意 0既不是正数, 也不是负数。我们学过各种各样的数, 那么, 数是怎样产生并发展起来的呢?我们知道, 为了表示物体的个数或者顺序, 产生了整数1, 2, 3, …; 为了表示“没有”, 引入了数0; 有时分配、测量的结果不是整数, 需要用分数(小数)表示; 为了表示具有相反意义的量, 我们又引进了负数……总之, 生产和生活的需要促进了数的产生、发展。"
        要求计划分必须分为6段
        生成内容：{json_example}
        "
        """
        if self.detail_level == 1:#只讲1段时独立出来更加准确
            json_type ="""
            {
                "plan": [
                    {
                        "content":“解释正负数的定义和符号表示，强调0既不是正数也不是负数，总结数的产生和发展的过程。”,
                        "method":"陈述知识点"
                    }
                ]
            }
            """
            prompt = f"""
            基于教师的教学经验以及教学策略，并结合相关专业知识，生成对教材内容进行讲解的计划。
            教学经验：{self.experience}
            相关专业知识：{pck_knowledge}
            教学策略：{strategy}
            教材内容：{self.subsections[self.current_subsection_turn-1]}

            要求：
            *计划应该简练，只有一段内容，但包括所有重点。
            *不能在计划中加入需要互动的教学方式，例如提问等，只能使用“陈述知识点”的方式。
            *输出为json格式，包括计划内容和计划使用的教学方法。

            示例：
            “在以上出现的数中, 像-12、-2.5、-237、-0.7这样的数是负数(negative number), 像3、3.5、500、1.2这样的数是正数(positive number)。正数前面有时也可放上一个“+”(读作“正”)号, 如7可以写成+7。注意 0既不是正数, 也不是负数。”
            生成内容：{json_type}
            """
        response = call_LLM_sync(
            "teacher",
            messages=[
                {"role": "system", "content": self.teacher_identity},
                {"role": "user", "content": prompt},
            ],
            response_format={
                'type': 'json_object'
            }   
        )
        dict = json.loads(response)
        t = dict.get("plan", [])
        self.plan = []  # 重置上次计划
        self.plan_methods = []  # 重置上次计划使用的方法
        self.current_plan_turn = 1  # 重置当前计划轮数
        print(f"本次生成{len(t)}段教学内容")  
        for item in t:
            self.plan.append(item["content"].strip())
            self.plan_methods.append(item["method"].strip())
        for i in range(len(self.plan)):
            print(f"第{i+1}段教学内容：{self.plan[i]}")  
        self.period = "subsection_lecture"  # 小节开始

    def teach(self):
        '''
        生成实际教学内容
        '''
        type = self.plan_methods[self.current_plan_turn-1] 
        if type == "陈述知识点":
            self.type = "lecture"
        elif type == "向同学提问":
            self.type = "ask_question"
        elif type == "对接收到的回答进行评价":
            self.type = "feedback"
        # 生成教学内容
        pre_text = ""  
        prompt = f"""
        基于教材,教师当前的安排,之前的教课内容以及学生反馈，使用特定的语言风格生成当前教学内容。
        教材内容：{self.subsections[self.current_subsection_turn-1]}
        当前教师安排：{self.plan[self.current_plan_turn-1]}
        应该使用的教学方法类别：{self.type} 
        之前的教课内容：{pre_text}
        学生反馈：{self.answered}
        教师语言风格：{self.speaking_style}
        要求：
        *仅根据以上内容生成教学内容，不要自己做出任何假设。
        *只生成一段话，要求完整连贯，教学方式必须符合当前教师安排。
        *不要出现混合多种教学方法,陈述知识点时不要出现提问或评价，提问时不要出现陈述知识点或评价，评价时不要出现陈述知识点或提问。
        *提问时只能提出问题，不要进行回答。
        *评价时必须根据真实学生反馈，如果学生反馈为空不要捏造学生反馈，可以对之前的讲课内容进行总结。
        *不要进行小组讨论或布置练习。
        *生成的内容与之前的讲课内容是同一节课的内容。
        *只输出教学内容，不要输出任何其他内容。
        讲课内容：
        """
        response = call_LLM_sync(
            "teacher",
            messages=[
                {"role": "system", "content": self.teacher_identity},
                {"role": "user", "content": prompt},
            ]
        )
        content = self._strip_think_blocks(response).strip()
        print(f"生成的教学内容：{content}")  
        # 广播
        msg = BroadcastMessage(
            current_time=self.time,
            message_type=MessageType.CLASS,
            active_event=self.type,
            speaker=self.name,
            content=content
        )
        self.broadcast_sys.publish_sync("student", msg)
        #更新状态
        self.content = content
        self.taught += f"{content}\n"
        self.current_plan_turn += 1  
        if self.current_plan_turn > len(self.plan):
            self.current_subsection_turn += 1  # 更新当前小节,只有lecture结束后才更新小节  
            self.period = "decide_ended"  # 小节结束

    def activate(self):
        """
        """
        # 进行活动
        if self.activity_type == "group_discussion":
            self.group_discussion()
        #可扩展
        #elif self.activity_type == "other":

    def group_discussion(self):
        """
        进行小组讨论
        """
        self.type = "group_discussion"  # 设置当前活动类型为小组讨论
        stu_num = len(self.student)  # 学生人数
        stu_group_num = stu_num // 3 if stu_num >= 3 else 1  # 组数，至少1组
        #分组
        for i in range(stu_group_num):
            group = self.student[i*3:(i+1)*3] if i < stu_group_num - 1 else self.student[i*3:]
            for student in group:
                student.scratch.group = i+1  # 设置学生所在小组编号
        if self.duration_turn == 1:
            #生成小组讨论的主题
            prompt_pre = f"""
            基于之后要讲的教材内容，引导同学们进行一个预习性的小组讨论。
            之后要讲的教材内容：{self.subsections[self.subsection_selected]}
            要求：
            *明确同学们还没有学过这部分内容，因此讨论内容在贴合主题的前提下尽可能宽泛，具有思辨性和引导性。
            *只生成一段要对同学们说的话，不要输出任何其他内容。
            *使用{self.speaking_style}的语言风格。
            你的输出：
            """
            prompt_post = f"""
            基于已经讲过的教材内容，引导同学们进行一个复习性的小组讨论。
            已经讲过的教材内容：{self.subsections[self.subsection_selected]}
            要求：
            *明确同学们已经学过这部分内容，因此讨论内容可以结合具体知识点。
            *只生成一段要对同学们说的话，不要输出任何其他内容
            *使用{self.speaking_style}的语言风格。
            你的输出：
            """
            dis_type = ""
            if self.subsection_selected + 1 == self.current_subsection_turn:
                dis_type = "预习"
            else:
                dis_type = "复习"
            prompt = f"{prompt_pre if dis_type == '预习' else prompt_post}"
            response = call_LLM_sync(
                "teacher",
                messages=[
                    {"role": "system", "content": self.teacher_identity},
                    {"role": "user", "content": prompt},
                ]
            )
            #广播
            self.content = self._strip_think_blocks(response).strip()
            msg = BroadcastMessage(
                current_time=self.time,
                message_type=MessageType.COMMAND,
                active_event="group_discussion_start",
                speaker=self.name,
                content=self.content
            )
            self.broadcast_sys.publish_sync("student", msg)
            #更新状态
            self.taught += f"{self.content}\n"
            self.duration_turn += 1  # 更新小组讨论轮数
        elif self.duration_turn == self.duration:
            #小组讨论结束
            self.content = "小组讨论结束。"
            msg = BroadcastMessage(
                current_time=self.time,
                message_type=MessageType.COMMAND,
                active_event="group_discussion_end",
                speaker=self.name,
                content=self.content
            )
            self.broadcast_sys.publish_sync("student", msg)
            self.taught += f"{self.content}\n"
            self.duration_turn += 1  # 更新小组讨论轮数
        elif self.duration_turn - 1 == self.duration:
            #进行反馈
            self.activity_content = self.discussed
            print(f"小组讨论内容：{self.activity_content}")
            prompt = f"""
            基于小组讨论的内容，进行对小组讨论的反馈。
            小组讨论内容：{self.activity_content}
            要求：
            *对小组讨论的内容进行总结和评价，指出讨论的亮点和不足。
            *只输出反馈，不要输出任何其他内容。
            *使用{self.speaking_style}的语言风格。
            你的反馈：
            """
            response = call_LLM_sync(
                "teacher",
                messages=[
                    {"role": "system", "content": self.teacher_identity},
                    {"role": "user", "content": prompt},
                ]
            )
            feedback = self._strip_think_blocks(response).strip()
            #广播反馈
            msg = BroadcastMessage(
                current_time=self.time,
                message_type=MessageType.CLASS,
                active_event="group_discussion_feedback",
                speaker=self.name,
                content=feedback
            )
            self.broadcast_sys.publish_sync("student", msg)
            #更新状态
            self.content = f"进行小组讨论反馈，反馈内容：{feedback}。"
            self.taught += f"{self.content}\n"
            self.period = "decide_ended"  # 小节结束
        else:
            #小组讨论进行中
            self.content = f"小组讨论进行中，教师正在等待。"
            #更新状态
            self.taught += f"{self.content}\n"
            self.duration_turn += 1  # 更新小组讨论轮数

    def waiting(self):
        """"""
        self.content = "教学提前完成，教师正在等待下课。"
        self.type = "waiting"

    def delay_turns(self):
        """
        如果拖堂，返回拖堂的轮数
        """
        delta = 0
        lecture_end = False
        delay_turns = 0
        if self.period == "subsection_lecture":
            # 如果是小节讲课阶段
            delta = len(self.plan) - self.current_plan_turn + 1  # 计算剩余计划段数
            if delta == 0:
                lecture_end = True
        elif self.period == "subsection_activity":
            # 如果是小节活动阶段
            delta = self.duration - self.duration_turn + 1 + 1#多一个反馈
        if lecture_end:
            delay_turns = len(self.subsections) - self.current_subsection_turn + delta + 1
        else:
            delay_turns = len(self.subsections) - self.current_subsection_turn + delta

        delay_turns = delay_turns + 1 + 1#第一个+1是为了进行finish_class，第二个+1是为了update_experience

        print(f"拖堂轮数：{delay_turns}")
        return delay_turns
    
    def finish_class(self):
        '''
        '''
        #广播教学内容和结束信息
        msg_command = BroadcastMessage(
            current_time=self.time,
            message_type=MessageType.COMMAND,
            active_event="finish_class",
            speaker=self.name,
            content=f"本节课结束。"
        )
        self.broadcast_sys.publish_sync("student", msg_command)
        msg_taught = BroadcastMessage(
            current_time=self.time,
            message_type=MessageType.CLASS,
            active_event="taught",
            speaker=self.name,
            content=f"本节课教学内容为：{self.taught}"
        )
        log_file = os.path.join(script_dir, "teacher_log.txt")
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(self.taught)
        self.broadcast_sys.publish_sync("student", msg_taught)
        #重置参数（状态）
        #与初始化不同的更新额外注释
        self.class_number += 1 # 下一节课
        self.target = "" 
        self.current_section_turn += self.sections_this_class  # 更新当前大节  
        self.sections_this_class = 0  
        #text_this_class在更新经验后重置
        self.subsections = []  
        self.current_subsection_turn = 1 
        self.importance = []  
        self.focus = []
        self.detail_level = 0  
        self.plan = []  
        self.plan_methods = []
        self.current_plan_turn = 1 
        self.subsection_selected = 0  
        self.activity_type = ""
        self.duration = 5
        self.duration_turn = 1  
        self.times = 0  
        self.activity_content = ""
        self.saw = ""
        self.answered = ""
        self.discussed = ""
        self.to_solve = ""
        self.feedback = ""
        #taught在更新经验后重置
        self.experience = ""
        self.type = "finish_class"  #在update_experience后重置
        self.class_turns = 40 
        #current_turn在update_experience中更新
        self.content = "本节课结束。"#在update_experience中重置
        #时间不重置
        self.period = "update_experience" #进入更新经验阶段


    def move(self):
        '''
        外部调用接口，执行一轮
        '''
        if self.period == "update_experience":
            self.update_experience()
            return f"{self.name} 总结经验完成。"
        if self.period == "not_started":
            self.update_status()  # 初始状态
            self.start_class()
            self.current_turn += 1
            self.time += timedelta(minutes=1)
            return  f"{self.name} 开始上课, 具体生成内容: {self.content}"
        self.update_status()  # 更新部分状态并保存本轮状态
        if self.period == "decide_ended":
            self.decide()
        if self.period == "subsection_lecture":
            self.teach()
        elif self.period == "subsection_activity":
            self.activate()
        elif self.period == "waiting_for_end":
            self.waiting()
        elif self.period == "already_ended":
            self.finish_class()

        self.current_turn += 1  
        self.time += timedelta(minutes=1)
        return_msg = f"第{self.current_turn}轮: {self.name} 进行{self.type}, 具体生成内容: {self.content}"

        return return_msg


if __name__ == "__main__":
    teacher_recorder = Recorder("teacher_log.json")
    broadcast = BroadcastSys(teacher_recorder)
    teacher = Teacher(broadcast_sys=broadcast, init_file= "C:/Users/Aover/Documents/SchoolAgent-gitee/agentschool/teacher.json")
    for i in range(10):  # 模拟10轮教学活动
        print(teacher.move())
        print("==========================")
