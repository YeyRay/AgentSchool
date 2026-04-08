import json
import os
from pathlib import Path
from openai import AsyncOpenAI, OpenAI

# 获取API密钥
api_key = os.getenv("SCHOOLAGENT_API_KEY")
if not api_key:
    raise ValueError("SCHOOLAGENT_API_KEY 环境变量未设置")

# 解析配置文件路径
current_dir = Path(__file__).parent
config_path = current_dir.parent / "config" / "model.json"

# 读取配置文件
if not config_path.exists():
    raise FileNotFoundError(f"配置文件未找到: {config_path}")

with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

# 初始化异步客户端
teacher_client_async = AsyncOpenAI(
    api_key=api_key,
    base_url=config["teacher_api_url"]
)

student_client_async = AsyncOpenAI(
    api_key=api_key,
    base_url=config["student_api_url"]
)

textbook_client_async = AsyncOpenAI(
    api_key=api_key,
    base_url=config["textbook_api_url"]
)

evaluation_client_async = AsyncOpenAI(
    api_key=api_key,
    base_url=config["evaluation_api_url"]
)

# 初始化同步客户端
teacher_client_sync = OpenAI(
    api_key=api_key,
    base_url=config["teacher_api_url"]
)

student_client_sync = OpenAI(
    api_key=api_key,
    base_url=config["student_api_url"]
)

textbook_client_sync = OpenAI(
    api_key=api_key,
    base_url=config["textbook_api_url"]
)

evaluation_client_sync = OpenAI(
    api_key=api_key,
    base_url=config["evaluation_api_url"]
)


async def call_LLM(role: str, messages: list, response_format: dict = None, temperature: float = 0.7):
    """
    异步调用大模型接口的函数，返回模型生成的文本内容

    参数:
    role: 角色 ('teacher', 'student', 'textbook' 或 'evaluation')
    messages: 对话消息列表
    response_format: 响应格式 (默认为None)
    temperature: 生成温度 (0-2之间)

    返回:
    模型生成的文本内容

    异常:
    ValueError: 角色无效
    """
    # 根据角色选择客户端和模型
    if role == "teacher":
        client = teacher_client_async
        model = config["teacher_model"]
    elif role == "student":
        client = student_client_async
        model = config["student_model"]
    elif role == "textbook":
        client = textbook_client_async
        model = config["textbook_model"]
    elif role == "evaluation":
        client = evaluation_client_async
        model = config["evaluation_model"]
    else:
        raise ValueError(f"无效角色: {role}，必须是 'teacher', 'student', 'textbook' 或 'evaluation'")

    # 构造请求参数
    params = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False
    }

    # 添加响应格式（如果提供）
    if response_format:
        params["response_format"] = response_format

    try:
        completion = await client.chat.completions.create(**params)
        return completion.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] 调用异步 LLM 失败: {e}")
        # 返回错误信息以便后续处理
        return f"LLM error: {e}"


def call_LLM_sync(role: str, messages: list, response_format: dict = None, temperature: float = 0.7):
    """
    同步调用大模型接口的函数，返回模型生成的文本内容

    参数:
    role: 角色 ('teacher', 'student', 'textbook' 或 'evaluation')
    messages: 对话消息列表
    response_format: 响应格式 (默认为None)
    temperature: 生成温度 (0-2之间)

    返回:
    模型生成的文本内容

    异常:
    ValueError: 角色无效
    """
    # 根据角色选择客户端和模型
    if role == "teacher":
        client = teacher_client_sync
        model = config["teacher_model"]
    elif role == "student":
        client = student_client_sync
        model = config["student_model"]
    elif role == "textbook":
        client = textbook_client_sync
        model = config["textbook_model"]
    elif role == "evaluation":
        client = evaluation_client_sync
        model = config["evaluation_model"]
    else:
        raise ValueError(f"无效角色: {role}，必须是 'teacher', 'student', 'textbook' 或 'evaluation'")

    # 构造请求参数
    params = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False
    }

    # 添加响应格式（如果提供）
    if response_format:
        params["response_format"] = response_format

    try:
        completion = client.chat.completions.create(**params)
        return completion.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] 调用同步 LLM 失败: {e}")
        # 返回错误信息以便后续处理
        return f"LLM error: {e}"