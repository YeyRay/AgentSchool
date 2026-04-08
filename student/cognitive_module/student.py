import json
import sys
import asyncio

from student.retrieve import retrieve

sys.path.append("../../")

from student.cognitive_module.memory import *
from student.cognitive_module.scratch import *
from student.cognitive_module.memory import *
from student.cognitive_module.scratch import *
from student.cognitive_module.student import *
from student.prompt.run_ds_prompt import *
from student.perceive import perceive
from student.retrieve import *
from student.reflect import *
from student.plan import *
from student.execute import execute
from student.exercise import *
from student.global_methods import load_grade_knowledge_points
from datetime import datetime, timedelta
import os
from util.BroadcastSys import BroadcastSys
from util.Recorder import *
from util.BroadcastMessage import *
from util.TimeManager import TimeManager


PERSONALITY_CONFIG = {
    'Extraversion': {
        'high': {
            'label': '外向',
            'anchor': "这让你倾向于通过大声说出来进行思考，并享受在互动和讨论中表达自己的观点，即使想法还未完全成熟。"
        },
        'low': {
            'label': '内向',
            'anchor': "这让你倾向于先在内心进行充分的思考，只有在感觉准备好之后才会发言，更喜欢倾听而不是主导对话。"
        }
    },
    'Agreeableness': {
        'high': {
            'label': '友善合作',
            'anchor': "因此你非常注重团队和谐，倾向于支持和赞同他人，会尽量用委婉的方式提出不同意见，避免直接冲突。"
        },
        'low': {
            'label': '有主见和批判性',
            'anchor': "因此你更看重事实和逻辑的正确性，敢于直接地提出质疑和挑战，即使这可能引发不同意见的交锋。"
        }
    },
    'Conscientiousness': {
        'high': {
            'label': '有条理和尽责',
            'anchor': "所以你总是试图认真理解问题并给出自己思考过的答案，即使不确定也愿意尝试，并希望保持讨论的条理性。"
        },
        'low': {
            'label': '随意和灵活',
            'anchor': "所以你表现得比较随性，如果问题让你觉得困难或无聊，你可能会很快失去耐心，或者更容易分心。"
        }
    },
    'Emotional Stability': {
        'high': {
            'label': '情绪稳定沉着',
            'anchor': "因此你总是显得很沉着冷静，即使在高压下或被指出错误时，也能保持稳定的情绪，不容易感到焦虑。"
        },
        'low': {
            'label': '情绪敏感',
            'anchor': "这使得你很容易感到紧张和不自信，尤其是在被提问或面对不确定性时，你对犯错感到格外担忧。"
        }
    },
    'Openness to Experience': {
        'high': {
            'label': '开放和好奇',
            'anchor': "这意味着你对新颖和抽象的观点很感兴趣，乐于探索问题背后的原理，而不仅仅是答案本身。"
        },
        'low': {
            'label': '传统和务实',
            'anchor': "这意味着你非常务实，更喜欢清晰、具体、有标准答案的问题，对抽象的理论讨论不太感兴趣。"
        }
    }
}

SIX_THINKING_HATS = {
	"white_hat": "客观事实与数据，关注信息收集与缺失之处。",
	"green_hat": "创造力与新点子，探索可能性与替代方案。",
	"yellow_hat": "积极乐观，看到好处、价值与潜在机会。",
	"black_hat": "批判与谨慎，指出风险、问题与不足之处。",
	"red_hat": "情感与直觉，表达感觉、态度和主观偏好。",
	"blue_hat": "思维的组织与控制，负责总结、规划与流程管理。"
}

class Student:
    # TODO：添加recorder类
    def __init__(self, name, broadcast_sys=False, recorder=False, folder_mem_saved=False):
        self.name = name

        self.broadcast_sys = broadcast_sys

        self.recorder = recorder  # Recorder类的实例，用于记录学生的行为

        f_mem_saved = f"{folder_mem_saved}"
        self.mem = Memory(f_mem_saved)

        scratch_saved = f"{folder_mem_saved}/scratch.json"
        self.scratch = Scratch(scratch_saved)

        # TODO: 需要在创建所有agent的实例后，对每个agent分别进行订阅
        if self.broadcast_sys and isinstance(self.broadcast_sys, BroadcastSys):
            # self.broadcast_sys.subscribe(self, "Teacher") 
            self.broadcast_sys.subscribe(self, "student")
            self.broadcast_sys.subscribe(self, self.name)  # 订阅自己的名字
            group = "group" + str(self.scratch.group)
            self.broadcast_sys.subscribe(self, group) # 订阅自己的小组, 小组名为"group0", "group1", ...
                                                #TODO: 以后如果要设定过程中分小组的功能，记得更新此订阅


        self.infos = [] # list of strings, 用于存储当前环境下的所有信息

        self.current_turn = 0  # 当前轮次
        
        self.current_course_number = 0  # 当前课程编号(从0开始)

        self.config_path = "config"

        self.config_schedule = f"{self.config_path}/schedule.json"

        self.config_teacher = f"{self.config_path}/teacher.json"

        with open(self.config_schedule, "r", encoding="utf-8") as f:
            schedule_data = json.load(f)
        
        with open(self.config_teacher, "r", encoding="utf-8") as f:
            teacher_data = json.load(f)
        
        self.round_time = schedule_data.get("round_time", 30)  # 每轮时间，默认为30秒

        self.teacher_name = teacher_data.get("name", "Teacher")  # 教师的名字，默认为"Teacher"

        self.time_manager = TimeManager(
            daily_schedule_path="config/schedule.json",
            broadcast_system=self.broadcast_sys,
            day_start_time="08:00"
        )

        self.scratch.current_time = self.time_manager.current_time  # 初始化当前时间

        self.students_list = []

        self.knowledge_points_of_the_grade = [] # 该学生所在年级的知识点列表，不代表学生掌握的知识点
        self.knowledge_points_of_the_grade = load_grade_knowledge_points(self) # 加载该学生所在年级的知识点

    def receive_broadcast(self, info):
        """
        存储信息到学生的infos列表中。
        INPUT:
            info: dict
            info = {"message_type": "class",
                "active_event": "lecture",
                "speaker": self.name, 
                "content": self.sections[self.current_section_turn],
                "time": self.current_time} # 应该添加时间
            TODO: 这个类需要变量：发送者sender（学生或老师的实例），
        OUTPUT: 
            None
        """
        self.infos.append(info)
        print(f"[{self.name}] 接收到消息: {info.get('active_event', 'unknown')}")  # 调试信息

    def receive_broadcast_sync(self, info):
        """
        同步接收广播消息，与异步版本功能相同
        INPUT:
            info: dict
        OUTPUT: 
            None
        """
        self.infos.append(info)
        print(f"[{self.name}] 同步接收到消息: {info.get('active_event', 'unknown')}")  # 调试信息

    """    
    def move(self):
        
        INPUT:
            student
            file: 存入的文件
            i: 轮次
            info: 字符串，当前信息

        OUTPUT:
            字符串，用于显示当前这个学生
        
        print(f"--- 现在是 {self.scratch.current_time} ---")
        infos = self.infos
        print(f"当前收到的信息列表: {infos}")
        folder_name = f"student/test_{self.name}"

        # 如果是knowledge，info如
        # {"message_type": "class",
        #  "active_event": "lecture",
        #  "speaker": self.name,
        #  "content": self.sections[self.current_section_turn]}
        # 如果是event，info如
        # 问答：
        #   "message_type": "class",
        #    "active_event": "response",
        #    "speaker": self.name,
        #    "content": response.choices[0].message.content.strip()
        # 小组讨论：
        #（开始）
        #    "message_type": "class",
        #    "active_event": "group_discussion_start",
        #    "speaker": self.name,
        #    "content": f"请进行小组讨论，讨论内容为：{point}"
        #（结束）
        #    "message_type": "class",
        #    "active_event": "group_discussion_end",
        #    "speaker": self.name,
        #    "content": "小组讨论结束。"
        

        # 每次就处理一个信息，然后加30s；每次处理都会保存当前状态
        # 一般来说，上课的时候，只会有一个信息在处理（因为老师一次只发一段话）。即infos这个列表只有一个元素
        # 在小组讨论的时候，infos这个列表可能会有多个元素（吗？）

        overall_thougts = {}  # 用于存储所有的思考内容

        for i, info in enumerate(infos):
            node = perceive(self, info.get("content", None), info.get("speaker", None), info.get("time", self.scratch.current_time), info.get("active_event", None))
            retrieved = retrieve(self, node)
            if retrieved and retrieved[node.content]:
                print(f"检索到相关记忆: {retrieved[node.content]}")
            else:
                print("没有检索到相关记忆。")
            
            reflected = reflect(self, retrieved)

            if(reflected):
                overall_thougts.update(reflected)  # 将当前轮次的思考内容添加到整体思考内容中

            objects = plan(self, self.broadcast_sys.subscriptions.get("Students", []), node, self.broadcast_sys.subscriptions.get("Teacher", None))

            execute(self, objects)

            # 时间+30s
            self.scratch.current_time = self.scratch.current_time + timedelta(seconds=30) # 假设每次感知后时间增加30秒

            # 保存当前状态
            self.scratch.save(f"{folder_name}/{self.name}_scratch_{self.current_turn}_{i}.json")  # 保存当前scratch状态到文件

            memory_file = f"{folder_name}/{self.name}_memory_{self.current_turn}_{i}"
            if not os.path.exists(memory_file):
                os.makedirs(memory_file, exist_ok=True) #确保 memory_file 作为目录存在
            self.mem.save(memory_file)
    

            details = {
                "thoughts": reflected if reflected else {},
            }
            self.recorder.log(self.scratch.current_time, info.get("active_event", "unknown_event"), details)

            


        # 清空当前信息列表
        self.infos = []

        if overall_thougts is None:
            return None
    
        return run_ds_prompt_generalize(overall_thougts)"""

    async def move(self):
        """
        INPUT:
            student
            file: 存入的文件
            i: 轮次
            info: 字符串，当前信息

        OUTPUT:
            字符串，用于显示当前这个学生
        """
        try:
            print(f"--- 现在是 {self.scratch.current_time} ---")
            infos = self.infos
            print(f"{self.name}当前收到的信息列表: {infos}")
            saving_folder_name = "student/saving"
            folder_name = f"{saving_folder_name}/{self.name}"

            # 初始化变量
            # 初始化变量在循环外部
            reflected = {}
            absorbed_info = ""
            learned = ""

            if infos is None or len(infos) == 0:
                action = self.scratch.action
            else: 
                action = infos[0].get("active_event")
                
            if "group_discussion" in action:
                self.action = "group_discussion"
            elif action == "ask_question" or action == "answer":
                self.action = "answer"
            else:
                self.action = "listen"

            overall_thougts = {}  # 用于存储所有的思考内容

            for i, info in enumerate(infos):
                # 如果在上课，先跳过
                #if info.get("active_event") == "lecture":
                    #self.infos = []
                    #return None
                
                # 仅测试小组讨论
                # if info.get("active_event") != "group_discussion_start" and info.get("active_event") != "group_discussion" and info.get("active_event") != "group_discussion_end":
                    # continue  # 跳过非小组讨论的事件

                try:
                    # 感知阶段 - 异步调用
                    print(f"{self.name}处理第 {i+1} 个信息...")
                    node, absorbed_info, learned = await perceive(self, info.get("content", None), info.get("speaker", None), info.get("receiver", None),
                                info.get("time", info.get("current_time", None)), info.get("active_event", None))
                    
                except Exception as e:
                    print(f"{self.name}感知阶段出错: {e}")
                    continue  # 跳过当前信息，继续处理下一个
                
                try:
                    # 检索阶段 - 异步调用
                    retrieved = await retrieve(self, node)
                    
                    if retrieved and retrieved.get(node.content):
                        print(f"{self.name}检索到相关记忆: {retrieved[node.content]}")
                    else:
                        print(f"{self.name}没有检索到相关记忆。")
                        
                except Exception as e:
                    print(f"{self.name}检索阶段出错: {e}")
                    retrieved = {}  # 使用空字典作为默认值
                
                try:
                    # 反思阶段 - 异步调用
                    reflected = await reflect(self, retrieved)
                    
                    
                    if reflected:
                        overall_thougts.update(reflected)  # 将当前轮次的思考内容添加到整体思考内容中
                        
                except Exception as e:
                    print(f"{self.name}反思阶段出错: {e}")
                    reflected = {}  # 使用空字典作为默认值
                
                try:
                    # 规划阶段 - 异步调用
                    #students_list = self.broadcast_sys.subscriptions.get("Students", []) if self.broadcast_sys else []
                    #teacher = self.broadcast_sys.subscriptions.get("Teacher", None) if self.broadcast_sys else None
                    # 遍历config/student文件夹，获取同组学生的名字
                    """students_list = []
                    student_config_path = "config/student"
                    for filename in os.listdir(student_config_path):
                        with open(os.path.join(student_config_path, filename), "r", encoding="utf-8") as f:
                            student_config = json.load(f)
                            print(f"学生{student_config.get('name', 'Unknown')}的组别: {student_config.get('group', 'Unknown')}")
                        if student_config.get("group") == self.scratch.group:
                            students_list.append(student_config.get("name", "Unknown"))"""

                    students_list = [student.name for student in self.students_list if hasattr(student, 'name') and student.scratch.group == self.scratch.group]
                    
                    
                    objects = plan(self, students_list, node, info.get("active_event", None), info.get("receiver", None))
                    
                        
                    
                except Exception as e:
                    print(f"{self.name}规划阶段出错: {e}")
                    objects = []  # 使用空列表作为默认值
                
                try:
                    # 执行阶段 - 异步调用
                    await execute(self, objects, retrieved=retrieved, info=info)
                                        
                except Exception as e:
                    print(f"{self.name}执行阶段出错: {e}")
                    # 执行失败也继续进行\
                
                try:
                    # 动态调整注意力和压力
                    event_type = info.get("active_event", "")
                    self.adjust_attention_and_stress(event_type)
                    
                    # 根据反思结果进一步调整
                    if reflected:
                        # 有深度思考时提升注意力
                        reflection_bonus = min(0.1, len(reflected) * 0.02)
                        self.scratch.attention_level += reflection_bonus
                        self.scratch.attention_level = min(1.0, self.scratch.attention_level)
                    
                except Exception as e:
                    print(f"{self.name}状态调整出错: {e}")
                
                """try:
                    # 时间更新
                    
                    
                    self.scratch.current_time = self.scratch.current_time + timedelta(seconds=self.round_time)
                    
                except Exception as e:
                    print(f"时间更新出错: {e}")
                    # 如果时间更新失败，使用当前时间
                    from datetime import datetime
                    self.scratch.current_time = datetime.now()"""
                
                try:
                    # 保存内存 - 异步文件操作
                    # 新结构: student/saving/{StudentName}/{Date}_{CourseNumber}/{StudentName}_{turn}_{i}
                    course_date = self.scratch.current_time.strftime("%Y%m%d")
                    course_number = self.current_course_number
                    
                    # 构建完整路径
                    course_dir = f"{folder_name}/{course_date}_{course_number}"
                    memory_file = f"{course_dir}/{self.name}_{self.current_turn}_{i}"
                    
                    if not os.path.exists(memory_file):
                        await asyncio.to_thread(os.makedirs, memory_file, exist_ok=True)
                    
                    # 使用异步线程执行保存操作
                    await asyncio.to_thread(self.mem.save, memory_file)
                    
                except Exception as e:
                    print(f"保存内存状态出错: {e}")
                    # 继续执行，不中断流程

                try:
                    # 保存状态 - 异步文件操作
                    scratch_file = f"{memory_file}/scratch.json"
                    await asyncio.to_thread(self.scratch.save, scratch_file)
                        
                except Exception as e:
                    print(f"保存scratch状态出错: {e}")
                    # 继续执行，不中断流程
                
                try:
                    # 记录日志 - 异步调用
                    if self.recorder:
                        details = {
                            "name": self.name,
                            "stress": self.scratch.stress,
                            "attention": self.scratch.attention_level,
                            "absorbed": absorbed_info if absorbed_info else "",
                            "learned": learned if learned else "",
                            "reflection": reflected if reflected else {},
                        }
                        
                        await self.recorder.log(self.scratch.current_time, 
                                        info.get("active_event", "unknown_event"), details)
                        
                        
                except Exception as e:
                    print(f"记录日志出错: {e}")
                    # 日志记录失败不影响主流程

                # 生成当前学生的一个表现发送到广播 - 异步调用
                try:
                    
                    content = await run_ds_prompt_summarize_status(self)
                                        
                    msg = BroadcastMessage(
                        current_time=self.scratch.current_time,
                        message_type=MessageType.CLASS,
                        active_event="expression",
                        speaker=self.name,
                        content=content
                    )
                    
                    self.broadcast_sys.publish_sync("teacher", msg)
                                           
                except Exception as e:
                    print(f"发送广播消息出错: {e}")

            # 清空当前信息列表
            self.infos = []

            # 更新轮次
            self.current_turn += 1

            # 更新时间
            self.update_time()

            try:
                # 生成总结
                """if overall_thougts:
                    return run_ds_prompt_generalize(overall_thougts)
                else:
                    return None"""
                if self.action == "listen" and reflected is not None:
                    return "reflection"
                else:
                    return self.action
                    
            except Exception as e:
                print(f"生成总结出错: {e}")
                return None
                
        except Exception as e:
            print(f"move函数整体执行出错: {e}")
            # 确保即使出错也清空信息列表
            self.infos = []
            return None
    
    def update_time(self):
        """
        更新当前时间，增加一轮的时间
        """
        self.scratch.current_time = self.scratch.current_time + timedelta(seconds=self.round_time)
        
    def update_students_list(self, students_list):
        """
        传入Student实例列表，更新学生列表
        INPUT:
            students_list: List[Student]
        """
        self.students_list = students_list

    """def adjust_attention_and_stress(self, event_type, duration=0, success_rate=None):
        ""
        根据事件类型动态调整注意力和压力
        INPUT:
            event_type: str, 事件类型
            duration: int, 活动持续轮数
            success_rate: float, 成功率(0-1)，可选
        ""
        # 基础调整规则
        adjustments = {
            "lecture": {"attention": -0.05, "stress": 0.02},  # 听课：注意力下降，压力微增
            "group_discussion_start": {"attention": 0.1, "stress": -0.05},  # 开始讨论：注意力提升，压力降低
            "group_discussion": {"attention": 0.05, "stress": -0.02},  # 讨论中：保持积极状态
            "ask_question": {"attention": 0.15, "stress": 0.1},  # 被提问：注意力大幅提升，压力增加
            "answer": {"attention": 0.1, "stress": 0.05},  # 回答问题：注意力提升，轻微压力
            "practice": {"attention": -0.02, "stress": 0.03},  # 练习：注意力微降，压力微增
        }
        
        if event_type in adjustments:
            adj = adjustments[event_type]
            
            # 基础调整
            self.scratch.attention_level += adj["attention"]
            self.scratch.stress += adj["stress"]
            
            # 根据持续时间调整（长时间活动会增加疲劳）
            if duration > 3:
                fatigue_factor = (duration - 3) * 0.02
                self.scratch.attention_level -= fatigue_factor
                self.scratch.stress += fatigue_factor * 0.5
            
            # 根据成功率调整（如果提供）
            if success_rate is not None:
                if success_rate > 0.8:  # 高成功率
                    self.scratch.attention_level += 0.05
                    self.scratch.stress -= 0.03
                elif success_rate < 0.4:  # 低成功率
                    self.scratch.attention_level -= 0.03
                    self.scratch.stress += 0.05
        
        # 限制数值范围
        self.scratch.attention_level = max(0.0, min(1.0, self.scratch.attention_level))
        self.scratch.stress = max(0.0, min(1.0, self.scratch.stress))
        
        print(f"{self.name} 状态调整: 注意力={self.scratch.attention_level:.2f}, 压力={self.scratch.stress:.2f}")"""

    def adjust_attention_and_stress(self, event_type, success_rate=None):
        """
        根据“平滑的动态均衡系统”调整注意力和压力。
        这个版本降低了脉冲强度，并引入了状态惯性。
        """
        # --- 1. 计算个性化的“基准值” (Baseline) ---
        attention_baseline = 0.5 + (self.scratch.personality.get('Extraversion', 15) - 15) * 0.01 + (self.scratch.personality.get('Conscientiousness', 15) - 15) * 0.015
        stress_baseline = 0.3 + (self.scratch.personality.get('Emotional Stability', 15) - 15) * -0.02

        # --- 2. 调整“均值回归”与引入“状态惯性” ---
        # 【调整点】我们将回归速度和事件冲击看作是共同作用于状态变化的“力”
        # 'inertia_factor' 代表状态保持不变的趋势，'change_factor' 代表状态改变的趋势
        inertia_factor = 0.85  # 状态有85%的可能保持上一轮的样子 (此值越高，变化越平滑)
        change_factor = 1.0 - inertia_factor # 只有15%的空间留给“变化”

        # a. 计算均值回归的“拉力”
        regression_pull = change_factor * (attention_baseline - self.scratch.attention_level)

        # b. 计算事件脉冲的“推力”
        pulse_push = {"attention": 0.0, "stress": 0.0}

        # 【调整点】大幅降低基础脉冲值，它们现在代表的是“变化趋势”，而不是绝对增量
        pulse_definitions = {
            # 注意力是“资源”，听课消耗它，讨论/提问增加对它的“需求”
            "lecture":          {"attention": -0.1, "stress": 0.02}, # 持续消耗
            "group_discussion": {"attention": 0.15, "stress": 0.05}, # 积极参与
            "ask_question":     {"attention": 0.4, "stress": 0.25}, # 强刺激
            "answer_success":   {"attention": 0.1, "stress": -0.15}, # 成功带来放松
            "answer_fail":      {"attention": -0.05, "stress": 0.2}, # 失败带来压力
            "idle":             {"attention": 0.0, "stress": -0.03},# 休息时压力会自然下降
        }
        
        # 根据事件类型和成功率选择合适的脉冲
        effective_event = event_type
        if event_type == "answer":
            effective_event = "answer_success" if success_rate is not None and success_rate > 0.6 else "answer_fail"
            
        if effective_event in pulse_definitions:
            pulse = pulse_definitions[effective_event]
            
            # 个性化调节因子（这部分保持，但作用于更小的值）
            attention_factor = 1.0
            stress_factor = 1.0
            if effective_event == "group_discussion" and self.scratch.personality.get('Extraversion', 15) > 18:
                attention_factor = 1.3
            if effective_event == "ask_question" and self.scratch.personality.get('Emotional Stability', 15) < 12:
                stress_factor = 1.8
            
            pulse_push["attention"] = change_factor * pulse["attention"] * attention_factor
            pulse_push["stress"] = change_factor * pulse["stress"] * stress_factor

        # --- 3. 计算最终的状态变化 ---
        # 新状态 = 绝大部分的旧状态 + 受均值回归和事件脉冲共同影响的一小部分变化
        self.scratch.attention_level = (self.scratch.attention_level * inertia_factor) + regression_pull + pulse_push["attention"]
        regression_pull_stress = change_factor * (stress_baseline - self.scratch.stress)
        self.scratch.stress = (self.scratch.stress * inertia_factor) + regression_pull_stress + pulse_push["stress"] # 注意：压力的回归也需要计算

        # --- 4. 状态间的相互影响 (保持不变，但作用于更平滑的值) ---
        max_attention_under_stress = 1.0 - (self.scratch.stress ** 2) * 0.5
        self.scratch.attention_level = min(self.scratch.attention_level, max_attention_under_stress)

        # --- 5. 限制最终数值范围 (保持不变) ---
        self.scratch.attention_level = max(0.0, min(1.0, self.scratch.attention_level))
        self.scratch.stress = max(0.0, min(1.0, self.scratch.stress))
        
        print(f"{self.name} 状态调整后: 注意力={self.scratch.attention_level:.2f} (基准: {attention_baseline:.2f}), 压力={self.scratch.stress:.2f} (基准: {stress_baseline:.2f})")
        
    def update_group(self, group):
        "更新broadcast的小组订阅"
        group = "group" + str(self.scratch.group)
        self.broadcast_sys.subscribe(self, group)
    
    def get_group(self):
        """
        获取学生所在的组号
        """
        return self.scratch.group
    
    def update_student_scratch(self, students_list, group):
        """
        更新学生的scratch状态，包括学生列表和组号
        """
        self.update_students_list(students_list)
        self.update_group(group)

    def get_full_personality_description(self, trait_name):
        """
        根据人格特质的数值，生成一个包含强度、基础描述和行为影响锚点的完整描述性句子。
        """
        value = self.scratch.personality.get(trait_name, 0)
        
        # 1. 确定强度词(level)和描述方向(desc_key: 'high' or 'low')
        if value >= 23:
            level, desc_key = '极其', 'high'
        elif value >= 19:
            level, desc_key = '相当', 'high'
        elif value >= 15:
            level, desc_key = '比较', 'high'
        elif value >= 12:
            level, desc_key = '略微偏', 'high'
        elif value >= 9:
            level, desc_key = '比较', 'low'
        else:  # 5-8
            level, desc_key = '非常', 'low'

        # 2. 从配置中心获取基础标签和行为锚点
        try:
            config = PERSONALITY_CONFIG[trait_name][desc_key]
            base_label = config['label']
            anchor_text = config['anchor']
        except KeyError:
            # 如果配置中没有找到，返回一个安全的默认值
            return f"无法为'{trait_name}'生成描述。"

        # 3. 组合最终的句子
        # 处理中性区间的特殊措辞
        if 12 <= value < 15:
            first_part = f"在'{trait_name}'方面，你表现得{level}{base_label}"
        else:
            first_part = f"在'{trait_name}'方面，你是一个{level}{base_label}的人"
            
        # 将第一部分和行为锚点组合起来
        full_description = f"{first_part}，{anchor_text}"
        
        return full_description

    def generate_persona_prompt(self):
        traits = ['Extraversion', 'Agreeableness', 'Conscientiousness', 'Emotional Stability', 'Openness to Experience']
        descriptions = [self.get_full_personality_description(trait) for trait in traits]
        return "\n".join(descriptions)
    
    def get_personalized_retrieval_params(self):
        """
        根据学生的真实 scratch 数据计算个性化的检索参数
        INPUT:
            student: Student类
        OUTPUT:
            retrieval_params: dict, 包含个性化参数
        """
        params = {
            "n_count": 10,  # 默认检索数量
            "recency_weight": 1.0,
            "importance_weight": 1.0, 
            "relevance_weight": 1.0,
            "similarity_threshold": 0.1,  # 相似度阈值
            "diversity_factor": 0.0,  # 多样性因子
        }
        
        scratch = self.scratch
        
        # 1. 基于注意力水平调整
        attention_level = getattr(scratch, 'attention_level', 0.8)
        if attention_level < 0.4:  # StudentA: 0.34 (低注意力)
            params["n_count"] = max(5, int(params["n_count"] * 0.6))  # 减少到6个
            params["recency_weight"] = 1.3  # 更依赖近期记忆
            print(f"[个性化] {self.name} 注意力低({attention_level:.2f})，减少检索数量到{params['n_count']}")
        elif attention_level > 0.7:
            params["n_count"] += 3
            params["diversity_factor"] = 0.2
        
        # 2. 基于压力水平调整
        stress = getattr(scratch, 'stress', 0.0)
        if stress > 0.3:  # StudentA: 0.35 (中等压力)
            params["importance_weight"] = 1.4  # 更重视重要信息
            params["recency_weight"] = 1.2     # 优先近期熟悉内容
            params["similarity_threshold"] += 0.05  # 提高相似度要求
            print(f"[个性化] {self.name} 压力较高({stress:.2f})，优化为保守检索策略")
        
        # 3. 基于五大人格特征调整
        personality = getattr(scratch, 'personality', {})
        if personality:
            extraversion = personality.get('Extraversion', 15)
            if extraversion <= 12:
                params["n_count"] = max(4, params["n_count"] - 2)  # 内向者检索更少
                params["importance_weight"] *= 1.2
            elif extraversion >= 20:  # 高外向性
                params["n_count"] += 2
                params["diversity_factor"] = 0.1

            conscientiousness = personality.get('Conscientiousness', 15)
            if conscientiousness <= 10:
                params["recency_weight"] *= 1.3  # 低尽责性更依赖近期记忆
                params["similarity_threshold"] -= 0.02  # 降低标准
                print(f"[个性化] {self.name} 尽责性低({conscientiousness:.2f})，倾向近期记忆")
            elif conscientiousness >= 20:  # 高尽责性
                params["importance_weight"] *= 1.4
                params["n_count"] += 2
            
            openness = personality.get('Openness to Experience', 15)
            if openness <= 10:
                params["diversity_factor"] = 0.0  # 低开放性不需要多样性
                params["relevance_weight"] *= 1.2  # 更重视直接相关
                print(f"[个性化] {self.name} 开放性低({openness:.2f})，专注直接相关记忆")
            elif openness >= 20:
                params["diversity_factor"] = 0.3
                params["n_count"] += 3
                params["relevance_weight"] *= 0.9  # 适当降低相关性要求，允许更广泛的检索
            
            # 情绪稳定性 (Emotional Stability): StudentA = 19 (较低)
            emotional_stability = personality.get('Emotional Stability', 15)
            if emotional_stability <= 10:
                params["n_count"] = max(4, params["n_count"] - 2)  # 减少信息过载
                params["importance_weight"] *= 1.3
                print(f"[个性化] {self.name} 情绪稳定性低({emotional_stability:.2f})，减少认知负荷")
            elif emotional_stability >= 20:  # 高情绪稳定性
                params["n_count"] += 1
                params["diversity_factor"] += 0.1

            agreeableness = personality.get('Agreeableness', 15)
            if agreeableness <= 10:  # 低宜人性
                params["relevance_weight"] *= 1.1  # 更重视直接相关的信息
            elif agreeableness >= 20:  # 高宜人性
                # 宜人性主要影响社交学习，在个人检索中影响相对较小
                pass
        
        """# 4. 基于认知状态调整
        cognitive_state = getattr(scratch, 'cognitive_state', [])
        if cognitive_state:
            cognitive_text = " ".join(cognitive_state) if isinstance(cognitive_state, list) else str(cognitive_state)
            
            # 检测元认知过高估计 - StudentA的特征
            if "元认知过高估计" in cognitive_text or "自我评估" in cognitive_text:
                params["importance_weight"] *= 1.5  # 更依赖客观重要信息
                params["similarity_threshold"] += 0.03  # 提高标准，避免过度自信
                print(f"[个性化] {student.name} 元认知过高估计，强化客观信息依赖")
            
            # 检测能力评估差距
            if "熟练度低于" in cognitive_text or "实际65%" in cognitive_text:
                params["n_count"] = max(6, params["n_count"] - 2)  # 适当减少
                params["recency_weight"] *= 1.2  # 更依赖近期学习
                print(f"[个性化] {student.name} 存在能力评估差距，采用保守检索")"""
        
        """# 5. 基于情感状态调整
        affective_state = getattr(scratch, 'affective_state', [])
        if affective_state:
            affective_text = " ".join(affective_state) if isinstance(affective_state, list) else str(affective_state)
            
            # 检测挫败感和焦虑 - StudentA的特征
            if "挫败感" in affective_text or "焦虑" in affective_text:
                params["importance_weight"] *= 1.4  # 依赖重要基础知识
                params["n_count"] = max(5, params["n_count"] - 3)  # 减少认知负荷
                params["recency_weight"] *= 1.3  # 优先近期成功经验
                print(f"[个性化] {student.name} 存在挫败感/焦虑，采用支持性检索策略")
            
            # 检测动机水平
            if "中等动机" in affective_text:
                params["relevance_weight"] *= 1.1  # 稍微提高相关性要求"""
        
        # 6. 基于学习风格调整
        learning_style = getattr(scratch, 'learning_style', {})
        if learning_style:
            # 感知类型：StudentA是"感官型"
            perception = learning_style.get('感知', [])
            if isinstance(perception, list) and "感官型" in " ".join(perception):
                params["importance_weight"] *= 1.3  # 感官型重视具体重要信息
                params["similarity_threshold"] += 0.02  # 需要更直接相关的信息
                print(f"[个性化] {self.name} 感官型学习者，优先具体重要信息")
            
            # 处理类型：StudentA是"反思型"
            processing = learning_style.get('处理', [])
            if isinstance(processing, list) and "反思型" in " ".join(processing):
                params["n_count"] += 2  # 反思型需要更多信息进行思考
                params["importance_weight"] *= 1.2
                print(f"[个性化] {self.name} 反思型学习者，增加检索深度")
            
            # 理解类型：StudentA是"顺序型"
            understanding = learning_style.get('理解', [])
            if isinstance(understanding, list) and "顺序型" in " ".join(understanding):
                params["recency_weight"] *= 1.1  # 顺序型重视建构性学习
                # 可以考虑按重要性顺序排列检索结果
        
        # 7. 应用最终限制和调整
        params["n_count"] = max(3, min(20, params["n_count"]))  # 限制在3-20之间
        params["similarity_threshold"] = max(0.01, min(0.5, params["similarity_threshold"]))
        
        return params
    
    def get_hat_weights(self):
        """
        根据学生的人格特质计算六顶思考帽的权重。
        权重基于五大人格特质与帽子的心理学关联：
        - 白帽（客观事实）：与尽责性和情绪稳定性相关
        - 绿帽（创造力）：与开放性和外向性相关
        - 黄帽（积极乐观）：与宜人性和情绪稳定性相关
        - 黑帽（批判谨慎）：与尽责性和低宜人性相关
        - 红帽（情感直觉）：与外向性和低情绪稳定性相关
        - 蓝帽（组织控制）：与尽责性和低开放性相关
        OUTPUT:
            weights: dict, 每个帽子的权重值
        """
        personality = self.scratch.personality
        
        # 获取人格数值（默认值为15，中性）
        extraversion = personality.get('Extraversion', 15)
        agreeableness = personality.get('Agreeableness', 15)
        conscientiousness = personality.get('Conscientiousness', 15)
        emotional_stability = personality.get('Emotional Stability', 15)
        openness = personality.get('Openness to Experience', 15)
        
        # 基础权重（所有帽子都有最小权重1.0）
        weights = {
            "white_hat": 1.0,  # 白帽：客观事实
            "green_hat": 1.0,  # 绿帽：创造力
            "yellow_hat": 1.0, # 黄帽：积极乐观
            "black_hat": 1.0,  # 黑帽：批判谨慎
            "red_hat": 1.0,    # 红帽：情感直觉
            "blue_hat": 1.0    # 蓝帽：组织控制
        }
        
        # 根据人格特质调整权重
        # 外向性：高外向偏好绿帽（创造性互动）和红帽（情感表达）
        if extraversion > 18:
            weights["green_hat"] += 1.5
            weights["red_hat"] += 1.2
        elif extraversion < 12:
            weights["blue_hat"] += 0.8  # 内向者偏好组织性思考
        
        # 尽责性：高尽责偏好白帽（事实）和蓝帽（组织）
        if conscientiousness > 18:
            weights["white_hat"] += 1.5
            weights["blue_hat"] += 1.3
            weights["black_hat"] += 0.8  # 谨慎批判
        elif conscientiousness < 12:
            weights["red_hat"] += 0.7  # 随意者偏好直觉
        
        # 情绪稳定性：高稳定偏好黄帽（乐观）和白帽（理性）
        if emotional_stability > 18:
            weights["yellow_hat"] += 1.4
            weights["white_hat"] += 0.9
        elif emotional_stability < 12:
            weights["red_hat"] += 1.3  # 不稳定者偏好情感表达
            weights["black_hat"] += 0.6  # 谨慎避免风险
        
        # 开放性：高开放偏好绿帽（新想法）和黄帽（探索）
        if openness > 18:
            weights["green_hat"] += 1.4
            weights["yellow_hat"] += 1.1
        elif openness < 12:
            weights["blue_hat"] += 1.0  # 传统者偏好结构化
        
        # 宜人性：高宜人偏好黄帽（和谐）和红帽（共情）
        if agreeableness > 18:
            weights["yellow_hat"] += 1.3
            weights["red_hat"] += 1.0
        elif agreeableness < 12:
            weights["black_hat"] += 1.2  # 低宜人偏好批判
        
        return weights
    
    def choose_one_hat(self):
        """
        从六项思考帽中根据人格权重进行加权随机选择。
        OUTPUT:
            hat: str, 选择的帽子描述
        """
        weights = self.get_hat_weights()
        
        # 获取帽子列表和对应权重
        hats = list(SIX_THINKING_HATS.keys())
        hat_weights = [weights[hat] for hat in hats]
        
        # 使用权重进行随机选择
        total_weight = sum(hat_weights)
        if total_weight == 0:
            # 如果权重全为0，使用均匀分布
            chosen_hat = random.choice(hats)
        else:
            # 加权随机选择
            r = random.uniform(0, total_weight)
            cumulative = 0
            chosen_hat = hats[0]  # 默认选择第一个
            for i, weight in enumerate(hat_weights):
                cumulative += weight
                if r <= cumulative:
                    chosen_hat = hats[i]
                    break
        
        chosen_desc = SIX_THINKING_HATS[chosen_hat]
        print(f"{self.name} 选择的思考帽 ({chosen_hat}): {chosen_desc}")
        return chosen_desc
    
    def get_all_misconceptions(self):
        """
        获取学生所有的错误认知
        OUTPUT:
            dict: {knowledge_tag: [misconceptions]}
        """
        misconceptions_dict = {}
        
        for node in self.mem.seq_knowledge:
            if node.misconceptions:
                tag = node.knowledge_tag[0] if node.knowledge_tag else "未分类"
                if tag not in misconceptions_dict:
                    misconceptions_dict[tag] = []
                misconceptions_dict[tag].extend(node.misconceptions)
        
        return misconceptions_dict
    
    def get_certain_misconceptions(self, knowledge_tag):
        """
        获取学生在某个知识点上的错误认知
        INPUT:
            knowledge_tag: str, 知识点标签
        OUTPUT:
            list: [misconceptions]
        """
        misconceptions = []
        
        for node in self.mem.seq_knowledge:
            if node.misconceptions and knowledge_tag in node.knowledge_tag:
                misconceptions.extend(node.misconceptions)
        
        return misconceptions
    
    async def read_latest_saving_dir(self, course_date=None, course_number=None):
        """
        异步读取最新的保存文件夹的路径（避免阻塞事件循环）

        新文件结构: student/saving/{StudentName}/{Date}_{CourseNumber}/{StudentName}_{X}_{Y}
        例如: student/saving/StudentA/20251101_1/StudentA_0_0
        
        INPUT:
            course_date: str, 课程日期，格式为 YYYYMMDD，如果为None则查找最新
            course_number: int, 课程编号，如果为None则查找最新
        """

        saving_base_dir = f"student/saving/{self.name}"
        # 在线程中检查是否存在目录
        exists = await asyncio.to_thread(os.path.exists, saving_base_dir)
        if not exists:
            print(f"未找到 {self.name} 的保存目录: {saving_base_dir}")
            return None

        base = Path(saving_base_dir)

        # 在后台线程中列出并筛选目录
        def _find_latest():
            # 首先找到日期_课程编号目录
            course_dirs = [d for d in base.iterdir() if d.is_dir()]
            if not course_dirs:
                print(f"目录 {saving_base_dir} 中没有子目录")
                return None
            
            # 如果指定了日期和课程编号，直接查找对应目录
            if course_date is not None and course_number is not None:
                target_course_dir = base / f"{course_date}_{course_number}"
                if not target_course_dir.exists():
                    print(f"指定的课程目录不存在: {target_course_dir}")
                    return None
                course_dir = target_course_dir
            else:
                # 否则找最新的课程目录
                def course_key(dir_path):
                    parts = dir_path.name.split('_')
                    if len(parts) >= 2:
                        try:
                            date = int(parts[0])
                            course_num = int(parts[1])
                            return (date, course_num)
                        except ValueError:
                            return (-1, -1)
                    return (-1, -1)
                
                course_dirs.sort(key=course_key, reverse=True)
                course_dir = course_dirs[0]
            
            # 在课程目录中找到最新的版本目录
            version_dirs = [d for d in course_dir.iterdir() if d.is_dir()]
            if not version_dirs:
                print(f"课程目录 {course_dir} 中没有版本子目录")
                return None
            
            def version_key(dir_path):
                parts = dir_path.name.split('_')
                if len(parts) >= 3:
                    try:
                        x = int(parts[1])
                        y = int(parts[2])
                        return (x, y)
                    except ValueError:
                        return (-1, -1)
                return (-1, -1)

            version_dirs.sort(key=version_key, reverse=True)
            return version_dirs[0] if version_dirs else None

        latest_dir = await asyncio.to_thread(_find_latest)

        if latest_dir is None:
            print(f"未找到 {self.name} 的任何保存版本目录")
            return None

        # 解析并显示版本号
        parts = latest_dir.name.split('_')
        if len(parts) >= 3:
            try:
                x, y = int(parts[1]), int(parts[2])
                print(f"最新保存目录: {latest_dir.name} (版本: X={x}, Y={y})")
            except ValueError:
                print(f"最新保存目录: {latest_dir.name}")
        else:
            print(f"最新保存目录: {latest_dir.name}")
        
        return latest_dir
        
    
    async def improve_from_exercise(self, analyze_correct, analyze_wrong):
        """
        从做题分析中生成错误改进分析。
        INPUT:
            self: Student类
            analyze_correct: 分析正确答案的结果
            analyze_wrong: 分析错误答案的结果
        OUTPUT:
            None
        """
        result = await run_ds_prompt_improve_from_exercise(self, analyze_correct, analyze_wrong)
        # 读取json格式回答
        data = json.loads(result)

        # 读取各部分内容
        elimination = data.get("Elimination", [])
        evolution = data.get("Evolution", {})
        emergence = data.get("Emergence", [])

        # 示例输出
        print("消除的错误认知:", elimination)
        print("演化的错误认知:", evolution)
        print("新增的错误认知:", emergence)

        # 更新学生的常见错误认知
        for common_mistake in elimination:
            self.scratch.remove_common_mistake(common_mistake)

        for original_mistake, new_mistake in evolution.items():
            self.scratch.update_common_mistake(original_mistake, new_mistake)

        for common_mistake in emergence:
            self.scratch.add_common_mistake(common_mistake)

    async def save_student_state(self, course_date=None, course_number=None):
        """
        保存当前学生的全部状态到新的saving下的对应文件中
        
        新文件结构: student/saving/{StudentName}/{Date}_{CourseNumber}/{StudentName}_{X}_{Y}
        例如: student/saving/StudentA/20251101_1/StudentA_0_0
        
        INPUT:
            course_date: str, 课程日期，格式为 YYYYMMDD，默认为当前日期
            course_number: int, 课程编号，默认为 self.current_course_number
        """
        # 如果没有提供日期，使用当前时间的日期
        if course_date is None:
            course_date = self.scratch.current_time.strftime("%Y%m%d")
        
        # 如果没有提供课程编号，使用实例变量
        if course_number is None:
            course_number = self.current_course_number
        
        # 构建课程目录路径
        course_dir_name = f"{course_date}_{course_number}"
        saving_base_dir = f"student/saving/{self.name}"
        course_dir_path = Path(saving_base_dir) / course_dir_name
        
        # 确保课程目录存在
        await asyncio.to_thread(os.makedirs, course_dir_path, exist_ok=True)
        
        # 读取当前课程的最新保存目录
        latest_dir = await self.read_latest_saving_dir(course_date, course_number)
        
        # 确定新的版本号
        if latest_dir is None:
            # 如果这是该课程的第一次保存，从 0_0 开始
            new_x, new_y = 0, 0
            print(f"首次保存课程 {course_dir_name} 的状态")
        else:
            # 否则增加版本号
            latest_name = latest_dir.name  # 格式: {StudentName}_{X}_{Y}
            parts = latest_name.split("_")  
            if len(parts) < 3:
                print(f"保存目录名称格式错误: {latest_name}，从 0_0 开始")
                new_x, new_y = 0, 0
            else:
                try:
                    x = int(parts[1])
                    new_x = x + 1
                    new_y = 0
                except ValueError:
                    print(f"无法解析保存目录中的版本号: {parts[1]}，从 0_0 开始")
                    new_x, new_y = 0, 0
        
        # 构建新目录名和路径
        new_dir_name = f"{self.name}_{new_x}_{new_y}"
        new_dir_path = course_dir_path / new_dir_name
        
        # 创建新目录
        await asyncio.to_thread(os.makedirs, new_dir_path, exist_ok=True)
        print(f"保存新的状态到目录: {new_dir_path}")
        
        # 保存记忆和scratch状态
        await asyncio.to_thread(self.mem.save, str(new_dir_path))
        scratch_file = f"{new_dir_path}/scratch.json"
        await asyncio.to_thread(self.scratch.save, scratch_file)

    def set_for_new_class(self):
        """
        进入新的课程，重置相关状态
        """
        self.current_course_number += 1
        self.current_turn = 0