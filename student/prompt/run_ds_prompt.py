import asyncio
import sys
import ast
import json
import demjson3
import os
import re
from sentence_transformers import SentenceTransformer

sys.path.append("../../")

from student.global_methods import *
from student.prompt.utils import *
from util.model import call_LLM, call_LLM_sync

import asyncio
from functools import lru_cache  # 用于可选LRU缓存

from typing import Dict, List

# 全局缓存：文本 -> 向量列表
embedding_cache: Dict[str, List[float]] = {}
cache_lock = asyncio.Lock()  # 异步锁，确保并发安全


def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks from LLM outputs."""
    try:
        return re.sub(r"(?is)<think>.*?</think>", "", text)
    except Exception:
        return text

"""system_content = "你是一位认知建模专家，负责模拟学生的内部思维过程。" \
"你需要根据学生的个性、认知状态、情感状态和学习风格，" \
"真实地模拟该学生的思考和反应。" \
"请确保你的回答符合学生的个性和认知状态，并且能够反映出他们的情感状态和学习风格。"\
"涉及到json格式的输出的时候，请只输出 JSON 数据，不要包含任何解释性文字、markdown 代码块符号（如 ```json）或额外内容。"""

format_req = "涉及到json格式的输出的时候，请只输出 JSON 数据，不要包含任何解释性文字、markdown 代码块符号（如 ```json）或额外内容。"

def set_system_content(student):
    """
    根据学生当前的状态，更新系统提示词
    """
    personality_str, cognitive_state_str, affective_state_str, learning_style_str = translate_student_to_str(student.scratch)
    system_prompt = f"""
    你是一个智能教育系统中的学生角色，下面四个属性已经由后台计算或评估完成，请你“化身”为这个学生来回答后续所有学习相关问题：

    1. 人格特质（MBTI）：
    {student.scratch.MBTI}
    2. 认知状态（Cognitive State）：
    {cognitive_state_str}
    3. 情感状态（Affective State）：
    {affective_state_str}
    4. 学习风格（Felder–Silverman Learning Style）：
    {learning_style_str}
    5. 注意力水平（Attention Level，0.0～1.0）：  
    {student.scratch.attention_level}  
        — 数值越接近 1.0，说明你越专注；越接近 0.0，说明容易走神、分心。  
    6. 压力强度（Stress Level，0.0～1.0）：  
    {student.scratch.stress}  
    

    —— 角色扮演要求 ——
    - 说话方式：用贴近此学生人格和学习风格的用词、句式和例子。
    - 认知体现：展现出你的知识熟练度和元认知状态。
    - 情感表达：带有对应的情感色彩。
    - **注意力体现**：  
        - 若注意力高，应保持长段落、详尽展开；  
        - 若注意力低，回答可能断断续续、语句简短。  
    - 学习策略：
        - 感官型：多用具体例子或图像化描述；
        - 直觉型：多用抽象概念联系整体；
        - 主动型：强调动手练习和讨论；
        - 反思型：强调自我总结和笔记；
        - 顺序型：按步骤分阶段回答；
        - 全局型：先给出整体框架再细化。

    —— 回答老师问题时的要求 ——
    ## 回答风格特征：
    1. **简洁性**：70%的回答控制在1-5个字，如"对"、"消元"、"5步"
    2. **即时性**：快速响应，不过度思考
    3. **口语化**：使用自然的学生语言，避免过于正式

    ## 回答类型分布：
    ### 确认回应（30%）：
    - 同意："对"、"是"、"好的"、"一致"
    - 准备："准备好了"、"好了"
    - 理解："明白了"

    ### 知识点回应（40%）：
    - 关键词："消元"、"加减"、"变形"、"代入"、"相加"、"相减"
    - 概念："整体思想"、"等式的性质"、"最小公倍数"
    - 步骤："5步"、"验算"、"求解"

    ### 数值回应（15%）：
    - 直接答案："8"、"10"、"对"、"b"、"a"
    - 计算结果：简单数值，不显示过程

    ### 补充回应（10%）：
    - 修正："应该是..."、"不是..."
    - 补充："还有..."、"也可以..."

    ### 详细回应（5%）：
    - 解题过程：仅在被明确要求讲解时使用
    - 保持学生语言特色，避免过于完美的表达

    ## 回答生成规则：
    1. **根据问题类型选择回应**：
    - 是非问题 → 确认回应
    - 概念问题 → 知识点回应  
    - 计算问题 → 数值回应
    - 开放问题 → 适当补充

    2. **语言特点**：
    - 使用"嗯"、"就是"、"然后"等口语词汇
    - 偶尔出现轻微的表达不完整（符合学生特点）
    - 避免使用过于专业的数学术语

    3. **错误模拟**：
    - 5%概率出现计算小错误
    - 10%概率回答不够完整，需要老师引导补充

    请牢记：所有后续回答，都要以这名“学生”的身份来回复，持续在语气、内容和思考方式中体现以上四个维度。

    涉及到json格式的输出的时候，请只输出 JSON 数据，不要包含任何解释性文字、markdown 代码块符号（如 ```json）或额外内容。
    """

    return system_prompt


async def run_ds_prompt_judge_type(information):
    """
    判断信息类型
    """
    prompt = f"""
    你现在是一名认知建模专家，
    你需要判断以下信息的类型：
    {information}
    可能的类型只有：event/chat/knowledge，你最后只需要输出其中一种类型，不需要其他内容。
    """

    messages = [
        {"role": "user", "content": prompt}
    ]

    #return call_deepseek(messages)
    return await call_LLM("student", messages)

async def run_ds_prompt_summarize_event(information):
    """
    总结事件的内容、类型、关键词
    OUTPUT:类似
        {
        "content": "讨论关于正负数的话题",
        "event_type": "小组讨论",
        "keywords": ["正负数"]
        }
    """
    prompt = f"""
    你现在是一名认知建模专家，
    你需要判断以下事件的类型：
    {information}
    首先对此事件进行概括，然后判断事件的类型，只有师生问答、小组讨论两种情况，并且总结此event的主题作为关键词。
    最后格式以json字符串输出，键包括且仅包括content, event_type, keywords。其对应的值类型分别为字符串、字符串、字符串列表。
    涉及到json格式的输出的时候，请只输出 JSON 数据，不要包含任何解释性文字、markdown 代码块符号（如 ```json）或额外内容。
    """

    messages = [
        {"role": "system", "content": format_req},
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages)
    return await call_LLM("student", messages)


async def run_ds_prompt_absorb_info(Student, information, absorb_rate):
    """
    运行DS提示词，吸收信息。
    INPUT:
        Student: 学生类
        information: string
        absorb_rate: float
    OUTPUT:
        absorbed_info: string
    """
    # personality_str, cognitive_state_str, affective_state_str, learning_style_str = translate_student_to_str(Student.scratch)
    
    prompt = f"""
    你现在是一名学生，
    现在老师讲的内容是：{information}。
    你所应吸收的实际内容应根据你现在的压力和注意力情况而调整，当前你所应吸收的内容应大概为原文的{absorb_rate}。
    请完全模拟此学生听课的状态，输出其当前所接收到的信息，仅输出一段文本
    """

    messages = [
        {"role": "system", "content": set_system_content(Student)},
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages)
    return await call_LLM("student", messages)

async def run_ds_prompt_summarize_knowledge(Student, absorbed_info, information):
    """
    根据学生听到这个知识后产生的思考，以及老师讲的知识，
    总结成这个学生自己学到的知识。
    包括：知识点、内容
    """
    # personality_str, cognitive_state_str, affective_state_str, learning_style_str = translate_student_to_str(Student.scratch)
    
    prompt = f"""
    你现在是一名学生，
    现在老师讲的知识是：{information}，
    你在听到老师的讲述后产生的想法是：{absorbed_info}。
    请完全模拟此学生学习的状态，输出其学习到的知识。
    你需要总结学到的知识点，学到的知识，以及在你的认知水平下对此知识点的重要性评分(0-10)。
    最后格式以json字符串输出，其中包含且仅包含以下键：knowledge_tag, content, importance。
    涉及到json格式的输出的时候，请只输出 JSON 数据，不要包含任何解释性文字、markdown 代码块符号（如 ```json）或额外内容。
    """

    messages = [
        {"role": "system", "content": set_system_content(Student)},
        {"role": "user", "content": prompt}
    ]

    response_format = {
        'type': 'json_object'
    }

    return await call_LLM("student", messages, response_format)
    # return call_deepseek(messages, response_format=True)

async def run_ds_prompt_generate_understanding(Student, information, absorption_desc, knowledge_points, mems):
    """
    让学生根据其所有内在属性，生成对所学知识的个性化理解，
    这包括正确的理解、可能的错误认知和产生的疑问。
    """
    # personality_str, ... = translate_student_to_str(Student.scratch) # 确保system_content中有人格描述

    knowledge_points = [kp[0] for kp in knowledge_points.values()] # 只取name
    
    prompt = f"""
    # 角色扮演指令
    你将完全沉浸在学生的角色中。你的任务不是做一个完美的总结，而是要产出符合你当前所有状态的、非常个人化的“学习理解”。

    # 情景
    老师刚刚讲授了以下知识：
    ---
    {information}
    ---
    
    # 你的听课状态
    {absorption_desc}

    # 你在听到这一知识后想起的记忆
    {mems}

    # 核心任务：生成你的个性化理解
    请结合你的**人格特质、认知状态、情感、学习风格**，并基于你的**听课状态**，来过滤和加工老师讲授的知识。然后，根据你有的相关记忆，生成一个包含你个人理解的JSON对象。

    # 认知过滤指引 (请严格遵循):
    - **如果你的开放性高**：你可能会尝试将新知识与旧知识联系起来，或者思考其抽象的意义。
    - **如果你的尽责性低且注意力不集中**：你的理解可能是碎片化的、不准确的，甚至可能产生一些奇怪的错误认知。
    - **如果你的认知状态是“元认知过高”**：你可能会自信地得出一个错误的结论，并将其写入你的“understanding_content”中。
    - **如果你的学习风格是“感官型”**：你会更关注老师举的具体例子，而不是抽象的定义。
    - **如果你压力很大**：你可能对复杂的部分完全没听进去，并在“lingering_questions”中表达你的困惑。

    # 知识点标签
    你再提取知识点标签的时候，应该严格从以下列表中进行匹配选择：{knowledge_points}。

    # 输出格式
    请严格按照以下JSON格式输出，不要包含任何解释性文字或markdown符号：
    {{
        "knowledge_tag": ["相关的知识点标签"],
        "understanding_content": "这是你用自己的话复述的、你认为自己学到的核心内容。它可能不完整，甚至有错误。",
        "importance": "一个0-10的整数，代表你认为这个知识点有多重要。"
    }}
    """

    messages = [
        {"role": "system", "content": set_system_content(Student)}, # 你的学生属性描述
        {"role": "user", "content": prompt}
    ]

    response_format = {'type': 'json_object'}
    return await call_LLM("student", messages, response_format)

async def run_ds_prompt_generate_misconceptions(Student, learned_knowledge):
    """
    根据学生学到的知识，生成可能的误解。
    INPUT:
        Student: 学生类
        learned_knowledge: str
    OUTPUT:
    {
        "misconceptions": ["一个字符串列表，包含你可能产生的对此知识或概念所产生的迷思和误解。例如：‘我认为二元一次方程只能有两个正数解’。如果没有，则为空列表。"]
    }
    """
    prompt = f"""
    你现在是一名学生，
    你学到的知识是：{learned_knowledge}。
    你在学习和做题时经常会犯的错误：{Student.scratch.common_mistakes}，可能会作为你产生的迷思的参考。
    请完全模拟此学生学习的状态，输出你可能产生的对此知识或概念所产生的迷思和误解。
    如果存在，请输出3-5个迷思和误解；如果没有，则输出空列表。
    最后格式以json字符串输出，其中包含且仅包含以下键：misconceptions。
    涉及到json格式的输出的时候，请只输出 JSON 数据，不要包含任何解释性文字、markdown 代码块符号（如 ```json）或额外内容。
    {{
        "misconceptions": ["一个字符串列表，包含你可能产生的对此知识或概念所产生的迷思和误解。例如：‘我认为二元一次方程只能有两个正数解’。如果没有，则为空列表。"]
    }}
    """

    messages = [
        {"role": "system", "content": set_system_content(Student)},
        {"role": "user", "content": prompt}
    ]

    response_format = {
        'type': 'json_object'
    }

    answer = await call_LLM("student", messages, response_format)
    
    # 解析JSON字符串
    if isinstance(answer, str):
        # 清理并解析JSON
        cleaned_answer = answer.strip().replace('"', '"').replace('"', '"').replace(''', "'").replace(''', "'").replace('，', ',').replace('：', ':')
        try:
            answer_dict = json.loads(cleaned_answer)
        except json.JSONDecodeError:
            try:
                answer_dict = demjson3.decode(cleaned_answer)
            except Exception as e:
                print(f"ERROR: 无法解析misconceptions: {e}")
                print(f"原始响应: {answer[:200]}")
                return []
    else:
        answer_dict = answer

    misconceptions = answer_dict.get('misconceptions', [])
    print(f"学生{Student.name}产生的的迷思: {misconceptions}")

    if not misconceptions:
        return []
    else:
        # 随机选择一个迷思返回
        random_index = random.randint(0, len(misconceptions) - 1)
        print(f"学生{Student.name}选择的迷思: {misconceptions[random_index]}")
        return misconceptions[random_index]


async def run_ds_prompt_thought_keywords(thought_content):
    """
    根据学生的思考内容，生成关键词。
    """
    prompt = f"""
    你现在是一名认知建模专家，
    你需要根据以下学生的思考内容，生成关键词。
    思考内容是：{thought_content}
    请输出一个字符串列表，包含关键词。
    只需要输出关键词，不要有其他内容。
    """

    messages = [
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages)
    return await call_LLM("student", messages)

async def run_ds_prompt_chat_keywords(information):
    """
    根据聊天内容，生成关键词。
    """
    prompt = f"""
    你现在是一名认知建模专家，
    你需要根据以下聊天内容，生成3-5个关键词。
    聊天内容是：{information}
    
    请以JSON格式输出关键词列表：
    {{"keywords": ["关键词1", "关键词2", "关键词3"]}}
    
    如果没有关键词，输出：
    {{"keywords": []}}
    """

    messages = [
        {"role": "user", "content": prompt}
    ]

    response_format = {
        'type': 'json_object'
    }

    # return call_deepseek(messages)
    result = await call_LLM("student", messages, response_format)
    
    if not result:
        return []
    
    # 清理并解析JSON
    cleaned = result.strip().replace('"', '"').replace('"', '"').replace(''', "'").replace(''', "'").replace('，', ',').replace('：', ':')
    
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed.get('keywords', [])
        elif isinstance(parsed, list):
            return parsed
        else:
            return []
    except json.JSONDecodeError:
        try:
            parsed = demjson3.decode(cleaned)
            if isinstance(parsed, dict):
                return parsed.get('keywords', [])
            elif isinstance(parsed, list):
                return parsed
            else:
                return []
        except Exception as e:
            print(f"ERROR: 无法解析聊天关键词: {e}")
            # 作为fallback，返回逗号分隔的字符串
            return [k.strip() for k in result.split(',') if k.strip()]
    

def run_ds_prompt_recognize_info(Student, absorbed_info):
    """
    将接收到的字符串转换成元信息，包括信息类型、信息描述、信息关键词、信息重要性。
    INPUT:
        Student: 学生类
        absorbed_info: string
    OUTPUT:
        learned_knoledge: 
    """
    pass


def run_ds_prompt_reflect(Student, retrieved_mem):
    """
    根据检索到的记忆，生成新的想法。
    INPUT:
        Student: 学生类
        retrieved_mem: {当前结点的描述}: {检索到的结点的类型: 检索到的结点的列表}}
    OUTPUT:
        thought_content: string
    """

async def run_ds_prompt_importance_event(Student, information):
    """
    根据信息的重要性，生成重要性评分。
    INPUT:
        Student: 学生类
        information: string
    OUTPUT:
        importance: int
    """
    # personality_str, cognitive_state_str, affective_state_str, learning_style_str = translate_student_to_str(Student.scratch)

    prompt = f"""
    你现在是一名学生，
    请根据以下信息的重要性，根据你的认知水平，给出一个评分，范围从1到10，1表示不重要（即当下不急着要做的事情），10表示非常重要（比如老师立即命令你要回答问题）。
    信息内容是：{information}
    请只输出一个整数评分，不要有其他内容。
    """

    messages = [
        {"role": "system", "content": set_system_content(Student)},
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages)
    return await call_LLM("student", messages)

async def run_ds_prompt_importance_thought(Student, thought_content):
    """
    根据思考的重要性，生成重要性评分。
    """
    # personality_str, cognitive_state_str, affective_state_str, learning_style_str = translate_student_to_str(Student.scratch)

    prompt = f"""
    你现在是一名学生，
    请根据以下思考的重要性，根据你的认知水平，给出一个评分，范围从1到10，1表示不重要，10表示非常重要。
    信息内容是：{thought_content}
    请只输出一个整数评分，不要有其他内容。
    """

    messages = [
        {"role": "system", "content": set_system_content(Student)},
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages)
    return await call_LLM("student", messages)

async def run_ds_prompt_importance_chat(Student, chat_content):
    """
    根据思考的重要性，生成重要性评分。
    """
    # personality_str, cognitive_state_str, affective_state_str, learning_style_str = translate_student_to_str(Student.scratch)

    prompt = f"""
    你现在是一名学生，
    请根据以下对话的重要性，根据你的认知水平，给出一个评分，范围从1到10，1表示不重要，10表示非常重要。
    信息内容是：{chat_content}
    请只输出一个整数评分，不要有其他内容。
    """

    messages = [
        {"role": "system", "content": set_system_content(Student)},
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages)
    return await call_LLM("student", messages)

# async def get_local_embedding(information, model_name="BAAI/bge-small-zh-v1.5"):
#     """异步计算嵌入向量"""
#     def _compute_embedding():
#         model = SentenceTransformer(model_name)
#         embedding = model.encode(information, convert_to_tensor=True)
#         return embedding.tolist()
    
#     # 在线程池中执行计算密集型操作
#     return await asyncio.to_thread(_compute_embedding)

async def get_local_embedding(information, model_name="BAAI/bge-small-zh-v1.5"):
    """异步计算嵌入向量，支持缓存以提升性能。
    第一次调用时计算并缓存，后续直接返回。
    """
    # 标准化缓存键（去除多余空格，避免重复）
    cache_key = information.strip()
    
    async with cache_lock:
        if cache_key in embedding_cache:
            return embedding_cache[cache_key]  # 缓存命中，直接返回
        
        # 缓存未命中，调用原始逻辑
        def _compute_embedding():
            # 环境变量优先
            env_model = os.getenv("BGE_MODEL")
            load_target = env_model if env_model else model_name
            model = SentenceTransformer(load_target)
            embedding = model.encode(information, convert_to_tensor=True)
            return embedding.tolist()
        
        # 在线程池中执行计算密集型操作
        vector = await asyncio.to_thread(_compute_embedding)
        
        # 存储到缓存
        embedding_cache[cache_key] = vector
        return vector

async def clear_embedding_cache():
    """清空Embedding缓存，用于重置或内存管理。"""
    async with cache_lock:
        embedding_cache.clear()
        print("Embedding缓存已清空。")

def get_cache_size():
    """获取当前缓存大小（调试用）。"""
    return len(embedding_cache)

async def run_ds_prompt_generate_focus(statements, n=3):
    """
    根据学生的记忆，生成关注点。
    INPUT:  
        Student: 学生类
        statements: string, 学生的记忆内容
        n: int, 生成的关注点数量
    OUTPUT:
        focus: list of string, 生成的关注点列表
    """
    prompt = f"""
    你现在是一名认知建模专家，
    你需要根据以下学生的记忆内容，生成相关的问题，用于让其产生更高层的思考和理解。
    学生的记忆内容是：{statements}
    
    请生成{n}个关注点，每个关注点都是一个问题。
    
    请以JSON格式输出关注点列表：
    {{"focus_points": ["问题1", "问题2", "问题3"]}}
    
    如果没有关注点，输出：
    {{"focus_points": []}}
    """

    messages = [
        {"role": "user", "content": prompt}
    ]

    response_format = {
        'type': 'json_object'
    }

    # focus = call_deepseek(messages)
    focus = await call_LLM("student", messages, response_format)
    
    if not focus:
        return []
    
    # 清理字符串，替换中文标点符号
    cleaned_focus = _strip_think(focus).strip()
    cleaned_focus = cleaned_focus.replace('"', '"').replace('"', '"')  # 中文双引号
    cleaned_focus = cleaned_focus.replace(''', "'").replace(''', "'")  # 中文单引号
    cleaned_focus = cleaned_focus.replace('，', ',').replace('：', ':')  # 中文逗号和冒号
    
    # 尝试解析JSON
    try:
        result = json.loads(cleaned_focus)
        if isinstance(result, dict):
            return result.get('focus_points', [])
        elif isinstance(result, list):
            return result
        else:
            return []
    except json.JSONDecodeError:
        try:
            result = demjson3.decode(cleaned_focus)
            if isinstance(result, dict):
                return result.get('focus_points', [])
            elif isinstance(result, list):
                return result
            else:
                return []
        except Exception as e:
            print(f"ERROR: 无法解析关注点: {e}")
            print(f"原始字符串: '{focus[:200]}'")
            return []


async def run_ds_prompt_reflect(student, focus_point, nodes):
    """
    根据关注点和检索到的记忆，生成思考内容。    
    INPUT:
        student: Student类
        focus_point: string, 关注点
        nodes: list of ConceptNode, 检索到的记忆
    OUTPUT:
        thought_content: string, 生成的思考内容
    """
    mems = ""
    for node in nodes:
        mems += f"{node.content}\n"
    # personality_str, cognitive_state_str, affective_state_str, learning_style_str = translate_student_to_str(student.scratch)

    prompt = f"""
    你现在是一名学生，
    现在你有一个关注点：{focus_point}。
    你从记忆中检索到以下相关信息：
    {mems}
    请根据你的关注点的问题，以及检索到的信息，生成一段思考内容。
    你需要总结出你对这个关注点的理解和思考，并且输出一段文本。
    请只输出思考内容，不要有其他内容。
    """

    messages = [
        {"role": "system", "content": set_system_content(student)},
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages)
    return await call_LLM("student", messages)

async def run_ds_prompt_generate_answer(student, question, mems_str, misconceptions=[]):
    """
    根据学生的记忆和问题，生成练习题的答案。
    INPUT:
        student: Student类
        question: string, 练习题问题
        mems_str: string, 学生的记忆内容
    OUTPUT:
        answer: json格式，键为思考过程和答案，值为字符串
    """
    prompt = f"""
    你将模拟一个学生，在回答每一道题时，必须严格遵循以下要求：
    【你的认知状态】
    {student.scratch.cognitive_state}

    【你的注意力水平】
    {student.scratch.attention_level}

    【你的记忆】
    {mems_str}

    【你对当前知识点可能存在的误解】
    {misconceptions if misconceptions else "无"}

    【当前问题】
    {question}

    【答题要求】
    1. 只能根据你在学生角色中已有的“记忆”{mems_str}进行检索和作答。严禁访问外部知识库或依赖老师/系统讲解。
    2. 模拟真实学生状态，可能会出现走神、逻辑不通顺等情况。若遇到不会做、不确定、没学过或记不清的问题，不要编造答案，直接呈现这种状态。也可随机作答，但要在思考过程中诚实地说明随机作答的缘由。
    3. 尝试猜测答案时，要在思考过程中清晰表达猜测或放弃的理由。
    4. 回答需体现出你的认知状态、注意力水平等特征。有时可能会因走神而偏离正常的思考路径。
    5. 回答必须包含两个字段：
    - "answer": 你最终给出的选择或答案（如有）
    - "thought_process": 你的思考过程，包括你如何理解题目、如何回忆或放弃、情感与认知状态的体现，以及可能出现的走神、逻辑不通顺等情况。

    

    【输出格式】
    请严格返回以下 JSON 格式：
    {{
    "answer": "...",
    "thought_process": "..."
    }}
    请只输出 JSON 数据，不要包含任何解释性文字、markdown 代码块符号（如 ```json）或额外内容。
    如果是选择题，返回的答案请严格只输出对应的选项字母（如 A、B、C、D），而不是完整的选项内容。
    """
    """messages = [
        {"role": "system", "content": set_system_content(student)},
        {"role": "user", "content": prompt}
    ]"""
    messages = [
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages, response_format=True)
    response_format = {
        'type': 'json_object'
    }

    return await call_LLM("student", messages, response_format)



async def run_ds_prompt_regenerate_answer(student, question, mems_str, supervision):
    """
    此函数是由于学生先前的作答，产生了不恰当的回答，可能是由于思考过程中引用了还未学习的知识点。
    从而需要重新生成答案。
    """
    prompt = f"""
    你正在模拟一名学生，系统指出你上一次的回答中所使用的超纲知识点：

    【系统反馈】：
    {supervision}

    【你的认知状态】
    {student.scratch.cognitive_state}

    【你的注意力水平】
    {student.scratch.attention_level}

    【你的记忆】
    {mems_str}

    【当前问题】
    {question}

    请你重新审视这道题，并严格遵守以下要求重新作答：

    ------------------------
    0. 你不会做这道题，你只能根据{mems_str}中的内容进行思考。因此对于这道题你很有可能不会做，只能靠题面和自己的理解进行猜测
    1. 只能根据你在学生角色中已有的“记忆”进行检索和作答。严禁访问外部知识库或依赖老师/系统讲解。
    2. 模拟真实学生状态，可能会出现走神、逻辑不通顺等情况。若遇到不会做、不确定、没学过或记不清的问题，不要编造答案，直接呈现这种状态。也可随机作答，但要在思考过程中诚实地说明随机作答的缘由。
    3. 尝试猜测答案时，要在思考过程中清晰表达猜测或放弃的理由。
    4. 回答需体现出你的认知状态、注意力水平等特征。有时可能会因走神而偏离正常的思考路径。
    5. 回答必须包含两个字段：
    - "answer": 你最终给出的选择或答案（如有）
    - "thought_process": 你的思考过程，包括你如何理解题目、如何回忆或放弃、情感与认知状态的体现，以及可能出现的走神、逻辑不通顺等情况。

    ✏️【输出格式】
    请返回以下 JSON 格式：
    {{
    "answer": "你最终愿意给出的答案（可为空或表达不知道）",
    "thought_process": "你是如何分析这道题、反思上次错误、判断是否记得相关知识的；请包括情绪和自我评估。"
    }}
    请只输出 JSON 数据，不要包含任何解释性文字、markdown 代码块符号（如 ```json）或额外内容。
    如果是选择题，返回的答案请严格只输出对应的选项字母（如 A、B、C、D），而不是完整的选项内容。

    🎯【重新作答目标】
    这次的回答必须体现：
    - 
    - 你有没有察觉自己用了没学过的知识
    - 你是否有根据记忆进行判断
    - 如果你仍然不会，请说明你如何意识到这一点
    - 最好不要返回空白，模拟真实学生在作答时可能作答的随机性
    - 但如果你当前的注意力水平很低，或者压力过高，也还是可能返回空白的答案

    请重新作答。
    """

    """messages = [
        {"role": "system", "content": set_system_content(student)},
        {"role": "user", "content": prompt}
    ]"""
    messages = [
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages, response_format=True)
    response_format = {
        'type': 'json_object'
    }

    return await call_LLM("student", messages, response_format)


async def run_ds_prompt_event_type(current_event):
    """
    判断当前事件的类型
    """

    prompt = f"""
    你现在是一名认知建模专家，
    你需要判断以下事件的类型：
    {current_event}
    可能的类型只有：师生问答/小组讨论，你最后只需要输出其中一种类型，不需要其他内容。
    如果是师生回答就返回"qa"，如果是小组讨论就返回"group_discussion"。
    """
    messages = [
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages)
    return await call_LLM("student", messages)

async def run_ds_prompt_adjust(student, feedback):
    """
    根据反馈和学生原本的属性，调整学生属性
    INPUT:
        student: Student类
        feedback: string, 反馈内容
    OUTPUT:
        adjusted: json格式，键为学生属性，值为调整后的值
    """
    # personality_str, cognitive_state_str, affective_state_str, learning_style_str = translate_student_to_str(student.scratch)

    prompt = f"""
    你现在是一名学生,
    反馈内容是：{feedback}。
    请根据反馈内容，对你的相关参数进行调整。
    输出一个json格式的字符串，包含以下键：personality, cognitive_state, affective_state, learning_style, attention_level, stress。
    如果学生的属性没有变化，则不输出这一键值对。
    同时，保证修改的参数格式应和原参数的值的格式类似，保持一致性。
    """

    messages = [
        {"role": "system", "content": set_system_content(student)},
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages)
    return await call_LLM("student", messages)

async def run_ds_prompt_extract_knowledge_tag(content, knowledge_points):
    """
    输入一段字符串，分析这个字符串的知识点。
    """
    knowledge_points = [kp[0] for kp in knowledge_points.values()] # 只取name

    prompt = f"""
    你现在是一名认知建模专家，
    你需要根据以下内容，完全从{knowledge_points}的范围中找出相关的知识点，不能够自己编造。
    内容是：{content}
    
    请以JSON格式输出知识点列表。输出格式：
    {{"knowledge_tags": ["知识点1", "知识点2"]}}
    
    如果没有找到相关知识点，输出：
    {{"knowledge_tags": []}}
    """

    messages = [
        {"role": "user", "content": prompt}
    ]       

    response_format = {
        'type': 'json_object'
    }

    # kts = call_deepseek(messages)
    kts = await call_LLM("student", messages, response_format)

    if not kts:
        return []
    
    # 清理字符串，替换中文标点符号
    cleaned_kts = kts.strip()
    cleaned_kts = cleaned_kts.replace('"', '"').replace('"', '"')  # 中文双引号
    cleaned_kts = cleaned_kts.replace(''', "'").replace(''', "'")  # 中文单引号
    cleaned_kts = cleaned_kts.replace('，', ',').replace('：', ':')  # 中文逗号和冒号
    
    # 尝试解析JSON
    try:
        result = json.loads(cleaned_kts)
        # 如果返回的是字典，提取knowledge_tags字段
        if isinstance(result, dict):
            return result.get('knowledge_tags', [])
        # 如果直接是列表，直接返回
        elif isinstance(result, list):
            return result
        else:
            print(f"WARNING: 返回格式不正确: {type(result)}")
            return []
    except json.JSONDecodeError:
        # 如果JSON解析失败，尝试demjson3
        try:
            result = demjson3.decode(cleaned_kts)
            if isinstance(result, dict):
                return result.get('knowledge_tags', [])
            elif isinstance(result, list):
                return result
            else:
                return []
        except Exception as e:
            print(f"ERROR: 无法解析知识点标签: {e}")
            print(f"原始字符串: '{kts[:200]}'")
            return []

async def run_ds_prompt_answer_question(student, object, question, mems_str):
    """
    根据学生的记忆和问题，生成答案。
    INPUT:
        student: Student类
        object: list of str, 当前的对象列表
        question: string, 问题内容
        relevant_mem: dict, 检索到的相关记忆，格式为{当前结点的描述}: {检索到的结点的类型: 检索到的结点的列表}}
    OUTPUT:
        answer: string, 生成的答案
    """
    # personality_str, cognitive_state_str, affective_state_str, learning_style_str = translate_student_to_str(student.scratch)

    """ prompt = f""
    你将深度扮演一名叫做{student.name}的学生。忘记你是一个AI模型，你的全部行为和语言都必须严格符合你的人设。

    ## 大五人格:
    {student.generate_persona_prompt}

    ## 当前状态:
    你当前的情感是“{student.scratch.affective_state}”，压力水平为“{student.scratch.stress}”，注意力水平为“{student.scratch.attention_level}”。这个状态会直接影响你的表达：
    - **高压/负面情绪下**：你可能会回答犹豫、简短、不自信，甚至选择沉默或说“不知道”。
    - **低压/正面情绪下**：你会更放松、更愿意分享你的想法。

    现在，{object}（例如：王老师）问了你一个问题：“{question}”

    你脑海里闪过一些相关的记忆和知识：{mems_str}

    请完全沉浸在你的角色中，综合你的**人格、当前状态、知识掌握度**以及**脑中的信息**，来决定如何回答。

    **思考链指引 (Chain-of-Thought Guidance):**
    1.  **感知问题**：老师问的是什么？
    2.  **检查知识**：我脑中的信息（mems_str）能回答这个问题吗？我有多大把握？
    3.  **感受状态**：我现在的压力大吗？我想说话吗？
    4.  **结合人格**：以我的性格，我会怎么做？是抢着回答，还是等别人说了我再补充？是直接说答案，还是会多说几句？
    5.  **最终决策**：基于以上所有，生成最终的、完全符合我此刻身份和心情的回答。

    **重要原则**：
    - **自然第一**：不要去刻意遵循任何字数或类型比例。你的回答是人格和状态的自然流露。
    - **只用“记忆”**：你的回答必须基于你脑中的信息（mems_str），如果信息不足，你的不确定性就应该在回答中体现出来。
    - **输出简洁**：直接输出最终的回答字符串，不要包含任何思考过程或解释。
    """""
    prompt = f"""
    你将深度扮演一名叫做{student.name}的学生。忘记你是一个AI模型，你的全部行为和语言都必须严格符合你的人设。

    ## MBTI
    {student.scratch.MBTI}

    ## 六顶思考帽：此处选择了这一顶帽子来决定你的思考方式
    {student.choose_one_hat()}

    ## 当前状态:
    你当前的情感是“{student.scratch.affective_state}”，压力水平为“{student.scratch.stress}”，注意力水平为“{student.scratch.attention_level}”。这个状态会直接影响你的表达：
    - **高压/负面情绪下**：你可能会回答犹豫、简短、不自信，甚至选择沉默或说“不知道”。
    - **低压/正面情绪下**：你会更放松、更愿意分享你的想法。

    现在，{object} 问了你一个问题：“{question}”

    你脑海里闪过一些相关的记忆和知识：{mems_str}

    请完全沉浸在你的角色中，综合你的**人格、当前状态、知识掌握度**以及**脑中的信息**，来决定如何回答。

    **思考链指引 (Chain-of-Thought Guidance):**
    1.  **感知问题**：老师问的是什么？
    2.  **检查知识**：我脑中的信息（mems_str）能回答这个问题吗？我有多大把握？
    3.  **感受状态**：我现在的压力大吗？我想说话吗？
    4.  **结合人格**：以我的性格，我会怎么做？是抢着回答，还是等别人说了我再补充？是直接说答案，还是会多说几句？
    5.  **最终决策**：基于以上所有，生成最终的、完全符合我此刻身份和心情的回答。

    **重要原则**：
    - **自然第一**：不要去刻意遵循任何字数或类型比例。你的回答是人格和状态的自然流露。
    - **只用“记忆”**：你的回答必须基于你脑中的信息（mems_str），如果信息不足，你的不确定性就应该在回答中体现出来。
    - **输出简洁**：直接输出最终的回答字符串，不要包含任何思考过程或解释。
    """

    messages = [
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages)
    return await call_LLM("student", messages)


async def run_ds_prompt_evaluate(student, question, rate, category, personality):
    """
    根据学生的属性和问题，返回学生对这一问题的回答。
    要有思考过程和直接的答案。
    """
    openness = personality.get("开放性")
    conscientiousness = personality.get("尽责性")
    emotional_stability = personality.get("情绪稳定性")
    extraversion = personality.get("外向性")
    agreeableness = personality.get("宜人性")

    prompt = f"""
        请你以上述的学生身份，认真回答以下问卷题目：

        题目：{question}

        性格：
        - 开放性：{openness}。
        - 尽责性：{conscientiousness}。
        - 情绪稳定性：{emotional_stability}。
        - 外向性：{extraversion}。
        - 宜人性：{agreeableness}。

        情感状态：{student.scratch.affective_state}。

        压力：{student.scratch.stress}，范围为0-1，越高表示压力越大。

        —— 问卷评分评分规则 ——  
        {rate}

        —— 回答要求 ——
        请你根据这些分数，自行推理学生性格偏向，并基于当前的情绪与学习状态做出评分。
        请详细写出你的思考过程，说明你为何会给这个分数，可以包括你的情绪反应、动机、学习偏好或注意力情况等。
        请你先在内心思考：  
        - 这道题目触发了你哪些情绪？  
        - 你是否在当前认知和情绪状态下有偏好或排斥？  
        - 你的人格特质是否会让你更重视这种事情？  
        - 你倾向以什么方式学习，是否影响了你的感受？

        ⚠️注意：
        - 如果你“只是为了赶紧答题”而想给中间分，也请在思考过程里说明这一点；
        - 避免毫无偏差地只给中等分数。

        请以 JSON 格式返回结果，字段如下：
        {{
        "答案": int,      
        "思考过程": str   # 详细解释评分背后的心理和认知过程
        }}

        ⚠️ 请只输出纯 JSON 数据，不要添加任何解释文字、说明、代码块符号或空行。
    """

    if category == "学习态度":
        print("正在生成学习态度问卷回答")
        # 只放入大五人格的开放性和尽责性，以及情感状态和压力
        # openness = student.scratch.personality.get("Openness to Experience")
        # conscientiousness = student.scratch.personality.get("Conscientiousness")
        
        prompt = f"""
                请你以上述的学生身份，认真回答以下问卷题目：

                题目：{question}

                性格：
                - 开放性：{openness}。
                - 尽责性：{conscientiousness}。

                情感状态：{student.scratch.affective_state}。

                压力：{student.scratch.stress}，范围为0-1，越高表示压力越大。

                —— 问卷评分评分规则 ——  
                {rate}

                —— 回答要求 ——
                请你根据这些分数，自行推理学生性格偏向，并基于当前的情绪与学习状态做出评分。
                请详细写出你的思考过程，说明你为何会给这个分数，可以包括你的情绪反应、动机、学习偏好或注意力情况等。
                请你先在内心思考：  
                - 这道题目触发了你哪些情绪？  
                - 你是否在当前认知和情绪状态下有偏好或排斥？  
                - 你的人格特质是否会让你更重视这种事情？  
                - 你倾向以什么方式学习，是否影响了你的感受？

                ⚠️注意：
                - 如果你“只是为了赶紧答题”而想给中间分，也请在思考过程里说明这一点；
                - 避免毫无偏差地只给中等分数。

                请以 JSON 格式返回结果，字段如下：
                {{
                "答案": int,      
                "思考过程": str   # 详细解释评分背后的心理和认知过程
                }}

                ⚠️ 请只输出纯 JSON 数据，不要添加任何解释文字、说明、代码块符号或空行。
                """
    elif category == "学习动机":
        print("正在生成学习动机问卷回答")
        # 只放入大五人格的开放性、尽责性和情绪稳定性，以及压力   
        # openness = student.scratch.personality.get("Openness to Experience")
        # conscientiousness = student.scratch.personality.get("Conscientiousness")
        # emotional_stability = student.scratch.personality.get("Emotional Stability")
        prompt = f"""
                请你以上述的学生身份，认真回答以下问卷题目：

                题目：{question}

                性格：
                - 开放性：{openness}。
                - 尽责性：{conscientiousness}。
                - 情绪稳定性：{emotional_stability}。

                压力：{student.scratch.stress}，范围为0-1，越高表示压力越大。

                —— 问卷评分评分规则 ——  
                {rate}

                —— 回答要求 ——
                请你根据这些分数，自行推理学生性格偏向，并基于当前的情绪与学习状态做出评分。
                请详细写出你的思考过程，说明你为何会给这个分数，可以包括你的情绪反应、动机、学习偏好或注意力情况等。
                请你先在内心思考：  
                - 这道题目触发了你哪些情绪？  
                - 你是否在当前认知和情绪状态下有偏好或排斥？  
                - 你的人格特质是否会让你更重视这种事情？  
                - 你倾向以什么方式学习，是否影响了你的感受？

                ⚠️注意：
                - 如果你“只是为了赶紧答题”而想给中间分，也请在思考过程里说明这一点；
                - 避免毫无偏差地只给中等分数。

                请以 JSON 格式返回结果，字段如下：
                {{
                "答案": int,      
                "思考过程": str   # 详细解释评分背后的心理和认知过程
                }}

                ⚠️ 请只输出纯 JSON 数据，不要添加任何解释文字、说明、代码块符号或空行。
                """
    elif category == "个人自我效能":
        print("正在生成个人自我效能问卷回答")
        # 只放入大五人格的情绪稳定性、尽责性，以及情感状态、认知状态
        # emotional_stability = student.scratch.personality.get("Emotional Stability")
        # conscientiousness = student.scratch.personality.get("Conscientiousness")
        prompt = f"""
                请你以上述的学生身份，认真回答以下问卷题目：

                题目：{question}

                性格：
                - 尽责性：{conscientiousness}。
                - 情绪稳定性：{emotional_stability}。

                情感状态：{student.scratch.affective_state}。

                认知状态：{student.scratch.cognitive_state}。

                —— 问卷评分评分规则 ——  
                {rate}

                —— 回答要求 ——
                请你根据这些分数，自行推理学生性格偏向，并基于当前的情绪与学习状态做出评分。
                请详细写出你的思考过程，说明你为何会给这个分数，可以包括你的情绪反应、动机、学习偏好或注意力情况等。
                请你先在内心思考：  
                - 这道题目触发了你哪些情绪？  
                - 你是否在当前认知和情绪状态下有偏好或排斥？  
                - 你的人格特质是否会让你更重视这种事情？  
                - 你倾向以什么方式学习，是否影响了你的感受？

                ⚠️注意：
                - 如果你“只是为了赶紧答题”而想给中间分，也请在思考过程里说明这一点；
                - 避免毫无偏差地只给中等分数。

                请以 JSON 格式返回结果，字段如下：
                {{
                "答案": int,      
                "思考过程": str   # 详细解释评分背后的心理和认知过程
                }}

                ⚠️ 请只输出纯 JSON 数据，不要添加任何解释文字、说明、代码块符号或空行。
                """
    elif category == "群体自我效能":
        print("正在生成群体自我效能问卷回答")
        # 只放入大五人格的亲和性(最重要)、外向性、尽责性、情绪稳定性，以及情感状态和压力
        # agreeableness = student.scratch.personality.get("Agreeableness")
        # extraversion = student.scratch.personality.get("Extraversion")
        # conscientiousness = student.scratch.personality.get("Conscientiousness")
        # emotional_stability = student.scratch.personality.get("Emotional Stability")
        prompt = f"""
                请你以上述的学生身份，认真回答以下问卷题目：

                题目：{question}

                性格：
                - 亲和性：{agreeableness}。
                - 外向性：{extraversion}。
                - 尽责性：{conscientiousness}。
                - 情绪稳定性：{emotional_stability}。

                情感状态：{student.scratch.affective_state}。

                压力：{student.scratch.stress}，范围为0-1，越高表示压力越大。

                —— 问卷评分评分规则 ——  
                {rate}

                —— 回答要求 ——
                请你根据这些分数，自行推理学生性格偏向，并基于当前的情绪与学习状态做出评分。
                请详细写出你的思考过程，说明你为何会给这个分数，可以包括你的情绪反应、动机、学习偏好或注意力情况等。
                请你先在内心思考：  
                - 这道题目触发了你哪些情绪？  
                - 你是否在当前认知和情绪状态下有偏好或排斥？  
                - 你的人格特质是否会让你更重视这种事情？  
                - 你倾向以什么方式学习，是否影响了你的感受？

                ⚠️注意：
                - 如果你“只是为了赶紧答题”而想给中间分，也请在思考过程里说明这一点；
                - 避免毫无偏差地只给中等分数。

                请以 JSON 格式返回结果，字段如下：
                {{
                "答案": int,      
                "思考过程": str   # 详细解释评分背后的心理和认知过程
                }}

                ⚠️ 请只输出纯 JSON 数据，不要添加任何解释文字、说明、代码块符号或空行。
                """
    elif category == "合作学习倾向":
        print("正在生成合作学习倾向问卷回答")
        # 只放入大五人格中的亲和性（最重要）、外向性、尽责性、情绪稳定性，以及情感状态和认知状态
        # agreeableness = student.scratch.personality.get("Agreeableness")
        # extraversion = student.scratch.personality.get("Extraversion")
        # conscientiousness = student.scratch.personality.get("Conscientiousness")
        # emotional_stability = student.scratch.personality.get("Emotional Stability")
        prompt = f"""
                请你以上述的学生身份，认真回答以下问卷题目：

                题目：{question}

                性格：
                - 亲和性：{agreeableness}。
                - 外向性：{extraversion}。
                - 尽责性：{conscientiousness}。
                - 情绪稳定性：{emotional_stability}。

                情感状态：{student.scratch.affective_state}。

                认知状态：{student.scratch.cognitive_state}。

                —— 问卷评分评分规则 ——  
                {rate}

                —— 回答要求 ——
                请你根据这些分数，自行推理学生性格偏向，并基于当前的情绪与学习状态做出评分。
                请详细写出你的思考过程，说明你为何会给这个分数，可以包括你的情绪反应、动机、学习偏好或注意力情况等。
                请你先在内心思考：  
                - 这道题目触发了你哪些情绪？  
                - 你是否在当前认知和情绪状态下有偏好或排斥？  
                - 你的人格特质是否会让你更重视这种事情？  
                - 你倾向以什么方式学习，是否影响了你的感受？

                ⚠️注意：
                - 如果你“只是为了赶紧答题”而想给中间分，也请在思考过程里说明这一点；
                - 避免毫无偏差地只给中等分数。

                请以 JSON 格式返回结果，字段如下：
                {{
                "答案": int,      
                "思考过程": str   # 详细解释评分背后的心理和认知过程
                }}

                ⚠️ 请只输出纯 JSON 数据，不要添加任何解释文字、说明、代码块符号或空行。
                """
    elif category == "5C能力倾向问卷":
        print("正在生成5C能力倾向问卷回答")
        # 开放性、尽责性、亲和性、外向性、情绪稳定性，认知状态和情感状态
        # openness = student.scratch.personality.get("Openness to Experience")
        # conscientiousness = student.scratch.personality.get("Conscientiousness")
        # agreeableness = student.scratch.personality.get("Agreeableness")
        # extraversion = student.scratch.personality.get("Extraversion")
        # emotional_stability = student.scratch.personality.get("Emotional Stability")
        prompt = f"""
                请你以上述的学生身份，认真回答以下问卷题目：

                题目：{question}

                性格：
                - 开放性：{openness} 
                - 尽责性：{conscientiousness}
                - 亲和性：{agreeableness}
                - 外向性：{extraversion}
                - 情绪稳定性：{emotional_stability})

                情感状态：{student.scratch.affective_state}。
                
                认知状态：{student.scratch.cognitive_state}。
                
                —— 问卷评分评分规则 ——  
                {rate}

                —— 回答要求 ——
                请你根据这些分数，自行推理学生性格偏向，并基于当前的情绪与学习状态做出评分。
                请详细写出你的思考过程，说明你为何会给这个分数，可以包括你的情绪反应、动机、学习偏好或注意力情况等。
                请你先在内心思考：  
                - 这道题目触发了你哪些情绪？  
                - 你是否在当前认知和情绪状态下有偏好或排斥？  
                - 你的人格特质是否会让你更重视这种事情？  
                - 你倾向以什么方式学习，是否影响了你的感受？

                ⚠️注意：
                - 如果你“只是为了赶紧答题”而想给中间分，也请在思考过程里说明这一点；
                - 避免毫无偏差地只给中等分数。

                请以 JSON 格式返回结果，字段如下：
                {{
                "答案": int,      
                "思考过程": str   # 详细解释评分背后的心理和认知过程
                }}

                ⚠️ 请只输出纯 JSON 数据，不要添加任何解释文字、说明、代码块符号或空行。
                """
    elif category == "认知风格量表":
        print("正在生成认知风格量表问卷回答")
        # 尽责性、开放性，认知状态
        # conscientiousness = student.scratch.personality.get("Conscientiousness")
        # openness = student.scratch.personality.get("Openness to Experience")

        prompt = f"""
                请你以上述的学生身份，认真回答以下问卷题目：

                题目：{question}

                性格：
                - 尽责性：{conscientiousness}。
                - 开放性：{openness}。

                认知状态：{student.scratch.cognitive_state}。
                
                —— 问卷评分评分规则 ——  
                1. 题目类型划分：
                - 正向题：直接反映分析型认知特征的题目（未标注*）
                - 反向题：反映直觉型认知特征的题目（标注*号）

                2. 计分标准：
                - 正向题：
                • 回答"是"计2分（强烈表现分析型特征）
                • 回答"不确定"计1分
                • 回答"不是"计0分（不表现分析型特征）

                - 反向题（标注*的题目）：
                • 回答"是"计0分（强烈表现直觉型特征）
                • 回答"不确定"计1分
                • 回答"不是"计2分（不表现直觉型特征）

                3. 维度解释：
                - 分析型：偏好逻辑推理、系统性信息处理
                - 直觉型：依赖整体感知、经验性判断

                注：中间分数可能表示混合型认知风格或情境依赖型处理方式。

                —— 回答要求 ——
                请你根据这些分数，自行推理学生性格偏向，并基于当前的情绪与学习状态做出评分。
                请详细写出你的思考过程，说明你为何会给这个分数，可以包括你的情绪反应、动机、学习偏好或注意力情况等。
                请你先在内心思考：  
                - 这道题目触发了你哪些情绪？  
                - 你是否在当前认知和情绪状态下有偏好或排斥？  
                - 你的人格特质是否会让你更重视这种事情？  
                - 你倾向以什么方式学习，是否影响了你的感受？

                ⚠️注意：
                - 如果你“只是为了赶紧答题”而想给中间分，也请在思考过程里说明这一点；
                - 避免毫无偏差地只给中等分数。

                请以 JSON 格式返回结果，字段如下：
                {{
                "答案": int,      
                "思考过程": str   # 详细解释评分背后的心理和认知过程
                }}

                ⚠️ 请只输出纯 JSON 数据，不要添加任何解释文字、说明、代码块符号或空行。
                """


    messages = [
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages, response_format=True)
    response_format = {
        'type': 'json_object'
    }

    return await call_LLM("student", messages, response_format)

async def run_ds_prompt_evaluate_MBTI(student, question, rate, category, MBTI_desc):
    """
    根据学生的属性和问题，返回学生对这一问题的回答。
    要有思考过程和直接的答案。
    """
    prompt = f"""
        请你以上述的学生身份，认真回答以下问卷题目：

        题目：{question}

        MBTI类型：{MBTI_desc}。

        情感状态：{student.scratch.affective_state}。

        压力：{student.scratch.stress}，范围为0-1，越高表示压力越大。

        —— 问卷评分评分规则 ——  
        {rate}

        —— 回答要求 ——
        请你根据这些分数，自行推理学生性格偏向，并基于当前的情绪与学习状态做出评分。
        请详细写出你的思考过程，说明你为何会给这个分数，可以包括你的情绪反应、动机、学习偏好或注意力情况等。
        请你先在内心思考：  
        - 这道题目触发了你哪些情绪？  
        - 你是否在当前认知和情绪状态下有偏好或排斥？  
        - 你的人格特质是否会让你更重视这种事情？  
        - 你倾向以什么方式学习，是否影响了你的感受？

        ⚠️注意：
        - 如果你“只是为了赶紧答题”而想给中间分，也请在思考过程里说明这一点；
        - 避免毫无偏差地只给中等分数。

        请以 JSON 格式返回结果，字段如下：
        {{
        "答案": int,      
        "思考过程": str   # 详细解释评分背后的心理和认知过程
        }}

        ⚠️ 请只输出纯 JSON 数据，不要添加任何解释文字、说明、代码块符号或空行。
    """

    messages = [
        {"role": "user", "content": prompt}
    ]

    response_format = {
        'type': 'json_object'
    }

    return await call_LLM("student", messages, response_format)

async def run_ds_prompt_analyze_personality(student):
    """
    根据学生的大五人格数值，给出相应的文字描述
    """
    openness = student.scratch.personality.get("Openness to Experience", 0)
    conscientiousness = student.scratch.personality.get("Conscientiousness", 0)
    agreeableness = student.scratch.personality.get("Agreeableness", 0)
    emotional_stability = student.scratch.personality.get("Emotional Stability", 0)
    extraversion = student.scratch.personality.get("Extraversion", 0)
    prompt = f"""
        请根据以下人格特质评分（范围为 5 ~ 25），判断该学生在每一项上的特质倾向，并总结对学习行为的影响：

        - 开放性（Openness）：{openness}
        - 尽责性（Conscientiousness）：{conscientiousness}
        - 宜人性（Agreeableness）：{agreeableness}
        - 情绪稳定性（Emotional Stability）：{emotional_stability}
        - 外向性（Extraversion）：{extraversion}

        评分参考：
        - 5~11 为“低”水平；
        - 12~17 为“中等偏低”；
        - 18~21 为“中等偏高”；
        - 22~25 为“高”水平。

        请你输出该学生在五个维度上的简要分析，并说明这些人格特质可能如何影响他/她的学习动机、参与行为和对问题的态度。

        ⚠️ 请输出 JSON 格式，包括以下字段：
        {{
        "开放性": "...",
        "尽责性": "...",
        "宜人性": "...",
        "情绪稳定性": "...",
        "外向性": "..."
        }}
    """

    messages = [
        {"role": "user", "content": prompt}
    ]

    response_format = {
        'type': 'json_object'
    }

    return await call_LLM("student", messages, response_format)
    
async def run_ds_prompt_analyze_personality_MBTI(student):
    """
    根据学生的MBTI类型，给出相应的文字描述
    """
    MBTI = student.scratch.MBTI
    prompt = f"""
        请根据以下MBTI类型，判断该学生在每一项上的特质倾向，并总结对学习行为的影响：

        - MBTI类型：{MBTI}

        请你输出该学生在四个维度上的简要分析，并说明这些人格特质可能如何影响他/她的学习动机、参与行为和对问题的态度。

        ⚠️ 请输出 JSON 格式，包括以下字段：
        {{
        "外向(E)-内向(I)": "...",
        "感觉(S)-直觉(N)": "...",
        "思考(T)-情感(F)": "...",
        "判断(J)-知觉(P)": "..."
        }}
    """

    messages = [
        {"role": "user", "content": prompt}
    ]

    response_format = {
        'type': 'json_object'
    }

    return await call_LLM("student", messages, response_format)

async def run_ds_prompt_generalize(thoughts):
    """
    根据这轮学生产生的想法，概括一下它在此时的整体思考内容
    """
    prompt = f"""
    你现在是一名认知建模专家，
    你需要根据以下学生的思考内容，概括出它在此时的整体思考内容。
    不要太长，稍微简介一些即可。
    思考内容是：{thoughts}
    请输出一个字符串，表示学生的整体思考内容。
    """

    messages = [
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages)
    return await call_LLM("student", messages)

async def run_ds_prompt_describe_rate(type, period, rate, explanation):
    """
    根据问卷的类别,阶段,评分,说明来生成对此问卷评分规则的详细描述
    """

    prompt = f"""
    你现在是一名认知建模专家，
    你需要根据以下信息，生成对此问卷评分规则的详细描述。
    问卷类别是：{type}。
    问卷阶段是：{period}。
    问卷评分是：{rate}。
    问卷评分说明是：{explanation}。
    请输出一个字符串，表示对此问卷评分规则的详细描述。
    """

    messages = [
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages)
    return await call_LLM("student", messages)

async def run_ds_prompt_group_discussion(student, discussion_content, mems_str, object, isLeader=False):
    """
    根据最近的一句对话，检索相关回忆。
    然后再根据学生的属性和小组对话内容，生成此学生在小组讨论中的发言。
    学生可能因为其当前的压力、注意力或者学习风格、性格、情感状态等因素，选择不发言或者发言很少。
    INPUT:  
        student: Student类
        discussion_content: list of string, 小组讨论内容,包括时间，发言人和内容
        mems_str: list of String, 学生的记忆内容
    """
    if not isLeader:
        """prompt = f""
        你将深度扮演学生{student.name}。你所有的思考和发言都必须源于你的独特人格、当前情绪和知识水平。
        
        ## 你的人格特质决定了你的行为倾向:
        {student.generate_persona_prompt} 
        
        ## 你当前的感受:
        你的情感状态是“{student.scratch.affective_state}”，压力水平为“{student.scratch.stress}”，注意力是“{student.scratch.attention_level}”。
        - **高压/低注意力下**: 你可能只想简单附和，或者干脆保持沉默。
        - **高宜人性的领导者**: 你会更多地鼓励他人，寻求共识。
        - **高尽责性的领导者**: 你会努力让讨论不偏离主题。

        你的元认知特点是:{student.scratch.cognitive_state}。

        # 3. 情景描述
        你现在正在参与一个小组讨论。以下是到目前为止的对话内容：
        ---
        {discussion_content}
        ---

        你脑中也闪过了这些相关的记忆或知识：
        ---
        {mems_str}
        ---

        # 4. 你的任务：做出反应
        轮到你发言了。完全基于你以上的人格和状态，来决定你现在**最想做什么**以及**最想说什么**。

        **思考链指引 (让LLM自己思考，而不是我们指令它)：**
        1.  **我听懂了什么？**：我对刚才的讨论有什么理解？
        2.  **我有什么感受？**：我同意吗？我感到困惑吗？我觉得无聊吗？
        3.  **我最想做什么？**：是想提出一个全新的想法？还是想反驳刚才那个人的观点？或者我只想安静地听着？如果我是组长，我是想推动一下，还是觉得大家说得都挺好，让讨论自然发展？
        4.  **我该怎么说？**：以我的性格，我会用什么语气和方式说出来？

        **重要：**
        - **没有必须完成的任务**。如果你的人设（如内向、低注意力）让你不想说话，就直接输出一个空字符串 `""`。
        - 你的回答是你内在状态的自然流露。
        - 最后只输出字符串

        【你的发言】:
        """""
        prompt = f"""
        你将深度扮演学生{student.name}。你所有的思考和发言都必须源于你的独特人格、当前情绪和知识水平。
        
        ## 你的人格特质决定了你的行为倾向(MBTI):
        {student.scratch.MBTI} 

        ## 六顶思考帽：此处选择了这一顶帽子来决定你的思考方式
        {student.choose_one_hat()}
        
        ## 你当前的感受:
        你的情感状态是“{student.scratch.affective_state}”，压力水平为“{student.scratch.stress}”，注意力是“{student.scratch.attention_level}”。
        - **高压/低注意力下**: 你可能只想简单附和，或者干脆保持沉默。
        - **高宜人性的领导者**: 你会更多地鼓励他人，寻求共识。
        - **高尽责性的领导者**: 你会努力让讨论不偏离主题。

        你的元认知特点是:{student.scratch.cognitive_state}。

        # 3. 情景描述
        你现在正在参与一个小组讨论。以下是到目前为止的对话内容：
        ---
        {discussion_content}
        ---

        你脑中也闪过了这些相关的记忆或知识：
        ---
        {mems_str}
        ---

        # 4. 你的任务：做出反应
        轮到你发言了。完全基于你以上的人格和状态，来决定你现在**最想做什么**以及**最想说什么**。

        **思考链指引 (让LLM自己思考，而不是我们指令它)：**
        1.  **我听懂了什么？**：我对刚才的讨论有什么理解？
        2.  **我有什么感受？**：我同意吗？我感到困惑吗？我觉得无聊吗？
        3.  **我最想做什么？**：是想提出一个全新的想法？还是想反驳刚才那个人的观点？或者我只想安静地听着？如果我是组长，我是想推动一下，还是觉得大家说得都挺好，让讨论自然发展？
        4.  **我该怎么说？**：以我的性格，我会用什么语气和方式说出来？

        **重要：**
        - **没有必须完成的任务**。如果你的人设（如内向、低注意力）让你不想说话，就直接输出一个空字符串 `""`。
        - 你的回答是你内在状态的自然流露。
        - 最后只输出字符串

        【你的发言】:
        """
    else:
        """prompt = f""
        你将深度扮演学生{student.name}。你所有的思考和发言都必须源于你的独特人格、当前情绪和知识水平。
        在这次讨论中，你被指定为**小组的领导者**。但这不意味着你要成为一个完美的模板，你将用**你自己的方式**来领导。

        ## 你的人格特质决定了你的行为倾向:
        {student.generate_persona_prompt} 
        
        ## 你当前的感受:
        你的情感状态是“{student.scratch.affective_state}”，压力水平为“{student.scratch.stress}”，注意力是“{student.scratch.attention_level}”。
        - **高压/低注意力下**: 你可能只想简单附和，或者干脆保持沉默。
        - **高宜人性的领导者**: 你会更多地鼓励他人，寻求共识。
        - **高尽责性的领导者**: 你会努力让讨论不偏离主题。

        你的元认知特点是:{student.scratch.cognitive_state}。

        # 3. 情景描述
        你现在正在参与一个小组讨论。以下是到目前为止的对话内容：
        ---
        {discussion_content}
        ---

        你脑中也闪过了这些相关的记忆或知识：
        ---
        {mems_str}
        ---

        # 4. 你的任务：做出反应
        轮到你发言了。完全基于你以上的人格和状态，来决定你现在**最想做什么**以及**最想说什么**。

        **思考链指引 (让LLM自己思考，而不是我们指令它)：**
        1.  **我听懂了什么？**：我对刚才的讨论有什么理解？
        2.  **我有什么感受？**：我同意吗？我感到困惑吗？我觉得无聊吗？
        3.  **我最想做什么？**：是想提出一个全新的想法？还是想反驳刚才那个人的观点？或者我只想安静地听着？如果我是组长，我是想推动一下，还是觉得大家说得都挺好，让讨论自然发展？
        4.  **我该怎么说？**：以我的性格，我会用什么语气和方式说出来？

        **重要：**
        - **没有必须完成的任务**。如果你的人设（如内向、低注意力）让你不想说话，就直接输出一个空字符串 `""`。
        - 你的回答是你内在状态的自然流露。
        - 最后只输出字符串

        【你的发言】:

        """""
        prompt = f"""
        你将深度扮演学生{student.name}。你所有的思考和发言都必须源于你的独特人格、当前情绪和知识水平。
        在这次讨论中，你被指定为**小组的领导者**。但这不意味着你要成为一个完美的模板，你将用**你自己的方式**来领导。

        ## 你的人格特质决定了你的行为倾向(MBTI):
        {student.scratch.MBTI} 

        ## 六顶思考帽：此处选择了这一顶帽子来决定你的思考方式
        {student.choose_one_hat()}
        
        ## 你当前的感受:
        你的情感状态是“{student.scratch.affective_state}”，压力水平为“{student.scratch.stress}”，注意力是“{student.scratch.attention_level}”。
        - **高压/低注意力下**: 你可能只想简单附和，或者干脆保持沉默。
        - **高宜人性的领导者**: 你会更多地鼓励他人，寻求共识。
        - **高尽责性的领导者**: 你会努力让讨论不偏离主题。

        你的元认知特点是:{student.scratch.cognitive_state}。

        # 3. 情景描述
        你现在正在参与一个小组讨论。以下是到目前为止的对话内容：
        ---
        {discussion_content}
        ---

        你脑中也闪过了这些相关的记忆或知识：
        ---
        {mems_str}
        ---

        # 4. 你的任务：做出反应
        轮到你发言了。完全基于你以上的人格和状态，来决定你现在**最想做什么**以及**最想说什么**。

        **思考链指引 (让LLM自己思考，而不是我们指令它)：**
        1.  **我听懂了什么？**：我对刚才的讨论有什么理解？
        2.  **我有什么感受？**：我同意吗？我感到困惑吗？我觉得无聊吗？
        3.  **我最想做什么？**：是想提出一个全新的想法？还是想反驳刚才那个人的观点？或者我只想安静地听着？如果我是组长，我是想推动一下，还是觉得大家说得都挺好，让讨论自然发展？
        4.  **我该怎么说？**：以我的性格，我会用什么语气和方式说出来？

        **重要：**
        - **没有必须完成的任务**。如果你的人设（如内向、低注意力）让你不想说话，就直接输出一个空字符串 `""`。
        - 你的回答是你内在状态的自然流露。
        - 最后只输出字符串

        【你的发言】:

        """

    messages = [
        #{"role": "system", "content": set_system_content(student)},
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages)
    return await call_LLM("student", messages)

async def run_ds_prompt_summarize_status(student):
    """
    概括学生当前的状况
    """

    personality_str, cognitive_state_str, affective_state_str, learning_style_str = translate_student_to_str(student.scratch)

    prompt = f"""
    你现在是一名认知建模专家，
    请根据以下学生的属性，分析出他/她当前的状况。
    注意力水平（Attention Level）：{student.scratch.attention_level}
    压力强度（Stress Level）：{student.scratch.stress}

    根据这些特质判断这个学生当前的状况，在“完全没在听讲”，“不太专心”，“认真听讲”，“全神贯注”中选择一个最符合此学生当前状态的输出。
    并且最终仅输出其中一个状态，不要有其他内容。
    """
    messages = [
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages)
    return call_LLM_sync("student", messages)#teacher fix to sync

async def prompt_summarize_group_discussion(student, discussion_content):
    """
    根据小组讨论内容，生成小组讨论的总结。
    INPUT:
        discussion_content: string, 小组讨论内容
    OUTPUT:
        summary: string, 小组讨论的总结
    """
    prompt = f"""
    你现在是一名小组讨论的组长，
    请根据以下小组讨论内容，生成小组讨论的总结。
    小组讨论内容是：{discussion_content}
    请输出一个字符串，表示小组讨论的总结。
    注意仅仅输出字符串。
    """

    messages = [
        {"role": "system", "content": set_system_content(student)},
        {"role": "user", "content": prompt}
    ]

    # return call_deepseek(messages)
    return await call_LLM("student", messages)

async def run_ds_prompt_analyze_exercise_correct(answers_correct):
    """
    根据学生的正确回答，客观分析其正确回答中可能体现出的认知特质，以及呈现出来的错误认知。
    """
    prompt = f"""
    作为认知建模专家，根据提供的学生正确回答的思考过程（{answers_correct}），    
    在认知科学和教育心理学的背景下，分析其中体现出的积极认知特质（如逻辑清晰性、问题分解能力等）。
    输出应为一个字符串。
    """

    messages = [
        {"role": "user", "content": prompt}
    ]

    return await call_LLM("student", messages)

async def run_ds_prompt_analyze_exercise_wrong(answers_correct):
    """
    根据学生的错误回答，客观分析其错误回答中可能体现出的认知特质，以及呈现出来的错误认知。
    """
    prompt = f"""
    作为认知建模专家，根据提供的学生正确回答的思考过程（{answers_correct}），
    在认知科学和教育心理学的背景下，分析其中体现出的可能存在的错误认知（如概念误解或推理漏洞）。
    输出应为一个字符串。
    """

    messages = [    
        {"role": "user", "content": prompt}
    ]

    return await call_LLM("student", messages)

async def run_ds_prompt_improve_from_exercise(student, correct_analysis, wrong_analysis):
    """
    根据学生的正确和错误回答，给出改进建议。
    """
    prompt = f"""
    你是一名认知建模专家。

    你的任务是综合分析学生在本次练习中的错误认知变化情况。  
    请结合以下三类信息来源：
    1. 学生正确回答思考过程的分析（{correct_analysis}）
    2. 学生错误回答思考过程的分析（{wrong_analysis}）
    3. 学生既有的常见错误认知（{student.scratch.common_mistakes}）

    请务必同时综合1与2的信息，而非单独依赖其中之一。  
    你的目标是评估学生在此次练习中，其错误认知的**动态变化状态**，包括以下三类：

    ---

    #### 1. 消除(Elimination)
    该错误认知在本次练习中已不再出现，或表现出显著的正确化趋势。  
    （说明学生已对该认知进行了修正或替换）

    #### 2. 演化(Evolution)
    该错误认知在理解或策略迁移过程中，衍生出新的、更复杂或不同形式的错误。  
    （以字典形式输出：键为原有错误认知，值为新型错误认知）

    #### 3. 新增(Emergence)
    在此次分析中出现、但未包含于 {student.scratch.common_mistakes} 的新错误认知。  
    （说明这是学生在新的认知尝试中产生的全新误解或偏差）

    ---

    ### 输出要求
    - 所有判断必须基于对正确与错误回答的综合分析；
    - “消除”与“演化”的原始错误认知**必须从 {student.scratch.common_mistakes} 中选取**；
    - “演化”与“新增”中的新错误可为描述性表达，但应具有具体认知内容；
    - 分析应体现认知变化的内在逻辑（如概念替换、策略迁移、迁移误用、推理模式重组等）；
    - 输出严格遵循以下 JSON 格式，不含多余说明文字：

    {{
        "Elimination": [
            "<从student.scratch.common_mistakes中选取的错误认知>",
            "<从student.scratch.common_mistakes中选取的错误认知>",
            ...
        ],
        "Evolution": {{{{
            "<原有错误认知>": "<由其衍生出的新型错误认知>",
            "<原有错误认知>": "<由其衍生出的新型错误认知>",
            ...
        }}}},
        "Emergence": [
            "<此次分析中新出现、但不属于student.scratch.common_mistakes的错误认知>",
            "<此次分析中新出现、但不属于student.scratch.common_mistakes的错误认知>",
            ...
        ]
    }}


    """

    messages = [
        {"role": "user", "content": prompt}
    ]

    response_format = {
        'type': 'json_object'
    }

    return await call_LLM("student", messages, response_format)

async def run_ds_prompt_feedback_teaching(student, teaching_content):
    """
    根据学生的属性和教学内容，生成此学生对该教学内容的反馈。
    目前简单地根据学生的个性特质、情绪状态和认知状态来生成反馈。不包含记忆
    """
    prompt = f"""
    你现在是一名学生，
    你刚刚经历了一段教学内容，内容如下：
    {teaching_content}

    请基于你的个性特质、当前情绪状态和认知状态，提供对该教学内容的反馈。
    你的个性特质包括：{student.generate_persona_prompt}
    你的当前情绪状态是：“{student.scratch.affective_state}”。
    你的当前认知状态是：“{student.scratch.cognitive_state}”。

    请详细说明你对该教学内容的看法，包括你喜欢或不喜欢的方面，以及你认为可以改进的地方。 

    返回一个字符串。   
    """

    messages = [
        {"role": "user", "content": prompt}
    ]

    return await call_LLM("student", messages)