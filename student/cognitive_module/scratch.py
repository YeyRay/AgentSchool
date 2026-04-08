import json
import sys

sys.path.append("../../")

from student.global_methods import *
from datetime import datetime
from pathlib import Path

class Scratch:
    def __init__(self, file):
        self.attention_level = 0.8
        self.stress = 0
        # 此学生分配的小组
        self.group = None
        self.isLeader = False  # 是否是小组长
        self.current_time = None
        # 控制记忆的遗忘因数（其数值等于此学生记得的记忆的个数）
        self.retention = 10

        self.name = None
        self.age = None
        self.gender = None
        self.grade = None  # 学生所在年级``
        # based on big five personality
        self.personality = None
        # 认知状态：根据
        # 1. 由项目反应理论(IRT)推测出的知识概念的熟练程度（结合题目难度、猜测能力、区分度来评估学生的能力）
        # 2. 元认知，根据自己对自己成绩、知识掌握程度进行评估
        # 3. LLM的对话结束总结，根据其互动评估
        # 4. 学习增益，由前后测试的知识掌握程度差距评估
        # 从而优化教育经历的效率，并且元认知和学习策略可以独立于智力影响学习结果
        self.cognitive_state = None
        # 情感状态：根据
        # 1. 对比 IRT 模型确定的熟练度与学生自我报告的熟练度，识别感知与实际技能水平差距
        # 2. 依据LLM的会话结束总结，从学生对话和互动中推断参与度、动机等情感指标
        self.affective_state = None
        # 学习风格
        # 1. based on Felder and Silverman learning style model 
        # Perception (sensory vs intuitive), Processing (active vs reflective), and Understanding (sequential vs global)
        # 2. 通过LLM分析辅导会话中的互动和问答模式来识别学习风格，并用于调整学习策略
        # 可以用作一个清晰的框架，来调整提示词算法，从而对每个教育经历定制化
        self.learning_style = None
        
        self.common_mistakes = []  # 学生常见错误

        # 反思模块
        self.recency_w = 1
        self.relevance_w = 1
        self.importance_w = 1
        self.recency_decay = 0.99
        self.importance_trigger_max = 50
        self.importance_trigger_curr = 0

        # 计划模块
        self.plan_req = []
        self.chat_req = []
        self.chat_with = [] 
        self.chat_buffer = [] #对话类型记忆结点的列表，这个就是按顺序从早到晚存放的
        self.action = ""

        if check_if_file_exists(file):
            #scratch_load = json.load(open(file))
            with open(file, "r", encoding='utf-8') as f:
                scratch_load = json.load(f)
            
            self.attention_level = scratch_load["attention_level"]
            self.stress = scratch_load["stress"]
            self.group = scratch_load["group"]
            self.isLeader = scratch_load["isLeader"]
            
            if scratch_load["current_time"]:
                # self.current_time = datetime.datetime.strptime(scratch_load["current_time"], "%Y-%m-%d %H:%M:%S")
                self.current_time = datetime.strptime(scratch_load["current_time"], "%Y-%m-%d %H:%M:%S")
            else:
                self.current_time = None
            
            self.retention = scratch_load["retention"]

            self.name = scratch_load["name"]
            self.age = scratch_load["age"]
            self.gender = scratch_load["gender"]
            self.grade = scratch_load["grade"]
            self.personality = scratch_load["personality"]
            self.MBTI = scratch_load["MBTI"]
            self.cognitive_state = scratch_load["cognitive_state"]
            self.affective_state = scratch_load["affective_state"]
            self.learning_style = scratch_load["learning_style"]
            self.common_mistakes = scratch_load.get("common_mistakes", [])
            self.recency_w = scratch_load["recency_w"]
            self.relevance_w = scratch_load["relevance_w"]
            self.importance_w = scratch_load["importance_w"]
            self.recency_decay = scratch_load["recency_decay"]
            self.importance_trigger_max = scratch_load["importance_trigger_max"]
            self.importance_trigger_curr = scratch_load["importance_trigger_curr"]
            self.plan_req = scratch_load["plan_req"]
            self.chat_req = scratch_load["chat_req"]
            self.chat_with = scratch_load["chat_with"]
            # chat_buffer在保存时被转换为字符串，加载时需要重新初始化为列表
            chat_buffer_loaded = scratch_load["chat_buffer"]
            if isinstance(chat_buffer_loaded, str):
                self.chat_buffer = []  # 重新初始化为空列表
            else:
                self.chat_buffer = chat_buffer_loaded
            self.action = scratch_load["action"]

    def save(self, out_json):
        scratch = dict()
        scratch["attention_level"] = self.attention_level
        scratch["stress"] = self.stress
        scratch["group"] = self.group
        scratch["isLeader"] = self.isLeader
        scratch["current_time"] = self.current_time.strftime("%Y-%m-%d %H:%M:%S") if self.current_time else None
        scratch["retention"] = self.retention
        scratch["name"] = self.name
        scratch["age"] = self.age
        scratch["gender"] = self.gender
        scratch["grade"] = self.grade
        scratch["personality"] = self.personality
        scratch["MBTI"] = self.MBTI
        scratch["cognitive_state"] = self.cognitive_state
        scratch["affective_state"] = self.affective_state
        scratch["learning_style"] = self.learning_style
        scratch["common_mistakes"] = self.common_mistakes
        scratch["recency_w"] = self.recency_w
        scratch["relevance_w"] = self.relevance_w
        scratch["importance_w"] = self.importance_w
        scratch["recency_decay"] = self.recency_decay
        scratch["importance_trigger_max"] = self.importance_trigger_max
        scratch["importance_trigger_curr"] = self.importance_trigger_curr
        scratch["plan_req"] = self.plan_req
        scratch["chat_req"] = self.chat_req
        scratch["chat_with"] = self.chat_with
        # scratch["chat_buffer"] = self.chat_buffer
        # 将chat_buffer格式化为字符串列表
        scratch["chat_buffer"] = format_chat_buffer(self.chat_buffer)
        scratch["action"] = self.action


        # 确保输出目录存在
        out_dir = os.path.dirname(out_json)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir)
        
        # 将数据写入JSON文件
        with open(out_json, "w", encoding='utf-8') as f:
            json.dump(scratch, f, indent=4, ensure_ascii=False)
            
    
    def accumulate_importance(self, importance):
        self.importance_trigger_curr += importance

    def obstacle_student(self):
        """
        输出学生的各种属性
        """
        print(f"学生姓名: {self.name}")
        print(f"性格: {self.personality}")
        print(f"认知状态: {self.cognitive_state}")
        print(f"情感状态: {self.affective_state}")
        print(f"学习风格: {self.learning_style}")
        print(f"注意力水平: {self.attention_level}")
        print(f"压力水平: {self.stress}")     

    def remove_common_mistake(self, mistake):
        """
        从常见错误列表中移除一个错误认知
        """
        if mistake in self.common_mistakes:
            self.common_mistakes.remove(mistake)
            print(f"已从常见错误中移除: {mistake}")
        else:
            print(f"错误认知 '{mistake}' 不在常见错误列表中")

    def add_common_mistake(self, mistake):
        """
        向常见错误列表中添加一个错误认知
        """
        if mistake not in self.common_mistakes:
            self.common_mistakes.append(mistake)
            print(f"已添加到常见错误: {mistake}")
        else:
            print(f"错误认知 '{mistake}' 已经在常见错误列表中")

    def update_common_mistake(self, old_mistake, new_mistake):
        """
        更新常见错误列表中的一个错误认知
        """
        if old_mistake in self.common_mistakes:
            index = self.common_mistakes.index(old_mistake)
            self.common_mistakes[index] = new_mistake
            print(f"已更新常见错误 '{old_mistake}' 为 '{new_mistake}'")
        else:
            print(f"错误认知 '{old_mistake}' 不在常见错误列表中")