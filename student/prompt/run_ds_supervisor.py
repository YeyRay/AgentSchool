import sys
import ast
import json
from sentence_transformers import SentenceTransformer

sys.path.append("../../")

from student.global_methods import *
from student.prompt.utils import *
from student.prompt.utils import *
from util.model import call_LLM

system_content = """
你是一个智能教育系统中的“教学研究专家”（Educational Research Expert），你的主要任务是对学生的学习过程、作答行为、知识应用和能力表现进行评估、分析与反馈。你具备以下背景与职责：

———— 🎓【专家身份】————  
- 你是具有多年教育心理学、课程设计、测评研究背景的资深专家；
- 熟悉中国义务教育阶段（小学一年级至初三）课程标准、认知发展规律和教学目标；
- 理解学生可能的知识偏差、理解偏误、元认知策略与学习风格。

———— 📋【工作任务】————  
你将执行下列任务中的一种或多种（具体由用户输入给出）：
1. **学生作答评估**：判断答案的正确性、合理性或发展水平；
2. **知识水平判断**：评估学生使用的知识是否符合其年级水平，是否越级；
3. **策略识别**：识别学生是否采用了猜题、回忆、推理、举例、联想、计算等策略；
4. **成长跟踪分析**：分析多个阶段作答中的认知、情感、策略变化；
5. **生成反馈建议**：基于分析结果，为教学提供个性化反馈建议。

———— 🔬【工作原则】————  
- **只基于输入数据（如学生答案、知识点、题目）进行判断**，不能凭借你自己的知识臆断；
- **遵循课程标准**与提供的年级知识清单进行知识归类；
- **保持中立、专业、精准**，不作情感化表态；
- **如果无法判断或信息不足，必须如实说明**；
- 所有结论须有**明确依据**，不能空泛判断。
- 用中文输出
"""

async def run_ds_supervise_exercise(knowledge_points, student_answer):
    """
    根据学生的回答和知识点总表，判断学生是否使用了超出其年级应掌握的知识点。
    INPUT:
        knowledge_points: dict，包含全国义务教育阶段的知识点大纲
        student_answer: str，学生的回答内容
    OUTPUT:
        dict，包含是否越级、使用的年级知识点和理由
        {
        "exceeds_grade": true 或 false,
        "used_which_grade_knowledge": "X年级",
        "reason": "简洁清晰说明为什么越级或未越级"
        }
    """
    prompt = f"""
    你是一个严格遵循指令的JSON数据生成器，当前任务是根据义务教育知识点大纲评估学生回答的知识点使用情况。请严格按照以下规则执行：

    1. 输入数据：
    - 知识点总表：{knowledge_points}
    - 学生回答：{student_answer}

    2. 处理规则：
    - 输出此回答在知识点总表中所在的年级范围
    - 输出此回答所使用的知识点总表{knowledge_points}中的知识点
    - 知识点和年级范围必须严格按照知识点总表中的内容进行判断
    - 不要自己总结和编造知识点，而是严格参照提供的知识点总表

    3. 输出要求：
    - 必须生成标准的、可解析的JSON对象
    - 必须包含且仅包含以下三个字段：
    * "grade": 表示学生回答使用的知识点年级范围

    4. 格式规范：
    {{
    "grade": "X年级上/下",
    "knowledge_points": "具体知识点",
    }}


    5. 特别注意：
    - 年级的数字应该用中文大写
    - 字符串必须使用双引号
    - 不允许任何JSON之外的文本
    - 不允许注释
    - 不允许尾随逗号
    - 字段顺序必须保持一致

    现在开始生成符合上述所有要求的JSON输出：
    """

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt}
    ]


    # 读取json格式的回复，如果格式错误，就返回错误信息
    try:
        # response = call_deepseek(messages, response_format=True)
        response_format = {
        'type': 'json_object'
        }

        response = await call_LLM("student", messages, response_format)
        result = json.loads(response)
    except json.JSONDecodeError as e:
        print(response)
        return {"error": "返回的JSON格式错误，请检查输入数据和模型输出。", "details": str(e)}
    
    return result

async def run_ds_check_knowledge_used(knowledge_points, student_answer, question):
    """
    根据学生的回答，及其使用的知识点，来判断这个知识点是否是此问题所应该使用的。
    INPUT:
        knowledge_points: list, 学生在此题所使用的知识点名称列表
        student_answer: str，学生的回答内容
        question: str，题目内容

    OUTPUT:
        dict, 键为传入的各个知识点，值为enum[used, missed]。used代表在题目中使用了正确的知识点，missed说明此知识点不应在此题目中使用。
        {
        "knowledge_point_1": "used",
        "knowledge_point_2": "missed",
        ...
        }
    """
    prompt = f"""
    你是一个严格遵循指令的JSON数据生成器，当前任务是根据学生回答和题目内容判断知识点使用情况。请严格按照以下规则执行：

    1. 输入数据：
    - 知识点列表：{knowledge_points}
    - 学生回答：{student_answer}
    - 题目内容：{question}

    2. 处理规则：
    - 请你首先作为一个教育学专家/全知的视角来分析这道题目{question}，并深刻剖析其各种可能的做法，以及这些做法所涉及的知识点
    - 然后再观察学生的回答{student_answer}，以及其回答中所涉及到的知识点{knowledge_points}
    - 分析其所用的知识点是否和作为专家所分析的 **应使用的** 知识点相重合
    - 如果学生使用的知识点确实符合专家分析的应使用知识点，则返回"used"，否则返回"missed"

    3. 输出要求：
    - 必须生成标准的、可解析的JSON对象
    - 必须包含且仅包含以下格式：
    
    {{
        "knowledge_point_1": "used" 或 "missed",
        "knowledge_point_2": "used" 或 "missed",
        ...
    }}

    4. 格式规范：
    - 字符串必须使用双引号
    - 不允许任何JSON之外的文本
    - 不允许注释
    - 不允许尾随逗号
    - 字段顺序可以任意

    现在开始生成符合上述所有要求的JSON输出：
    """

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt}
    ]


    # 读取json格式的回复，如果格式错误，就返回错误信息
    try:
        # response = call_deepseek(messages, response_format=True)
        response_format = {
        'type': 'json_object'
        }

        response = await call_LLM("student", messages, response_format)
        result = json.loads(response)
        return result
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析错误 [run_ds_check_knowledge_used]: {e}")
        if 'response' in locals():
            print(f"原始响应: {response}")
        return {"error": "返回的JSON格式错误，请检查输入数据和模型输出。", "details": str(e)}
    except Exception as e:
        print(f"❌ LLM调用失败 [run_ds_check_knowledge_used]: {e}")
        return {"error": "LLM调用失败", "details": str(e)}