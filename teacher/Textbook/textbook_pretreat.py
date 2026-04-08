import os
import tiktoken
import json
import sys
import time
import re
import asyncio
import aiofiles

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
script_dir = os.path.dirname(os.path.abspath(__file__))
from util.model import call_LLM_sync, call_LLM

def count_tokens(text, model="deepseek-reasoner"):
    """计算文本的token数量"""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        #如果无法获取特定模型的编码，使用cl100k_base作为后备
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))

async def textbook_pretreat(textbook_file: str = None):
    # 输入和输出文件
    text_book_file = ""
    if textbook_file:
        text_book_file = textbook_file
    else:
        raise ValueError("请提供教材文件路径")
    textbook_refined_file = f"{script_dir}/textbook_refined.txt"
    sections_output_file = f"{script_dir}/sections.json"
    
    MAX_TOKENS = 20000  # 降低token限制，避免响应被截断
    
    if not os.path.exists(text_book_file):
        raise FileNotFoundError(f"教材文件 '{text_book_file}' 不存在")
    
    with open(text_book_file, 'r', encoding='utf-8') as input_file:
        content = input_file.read()
    
    token_count = count_tokens(content)
    print(f"输入文档token数量: {token_count}")  # 显示token数量
    
    if token_count > MAX_TOKENS:
        print(f"输入文本过长，将进行异步分块处理...")
        # 使用异步分块处理
        return await textbook_pretreat_chunked_async(text_book_file, MAX_TOKENS)

    # 改进的提示词，要求更严格的JSON格式
    prompt = """
    作为Markdown教材内容预处理助手，你需要完成以下三个步骤：

    步骤1：优化输入文本
    1. 将数学公式转换为纯文本表示
    2. 删除所有图片链接
    3. 移除页眉和页脚的非内容部分
    4. 确保删除所有习题，保留例题
    5. 修正排版问题和符号错误
    6. 尽量不要改动教材原文
    7. 在小节分隔处添加标记符"xiaojiefenge"，强调一定要是小节，章节分隔处不添加，段落分隔处也不添加

    步骤2：总结专业内容知识
    1. 识别优化后教材中所有有关专业知识的内容即知识点。
    2. 每个知识点总结为一句话，重点在核心概念与定义，定理与定律，重要公式，知识点之间的逻辑关系和层次结构，知识点的实际应用场景和意义等。
    3. 每个知识点作为数组的一个元素。

    重要要求：
    - 必须返回严格的JSON格式
    - 所有字符串中的引号必须转义
    - 不要在JSON外添加任何解释文字
    - 确保JSON完整且格式正确

    JSON格式：
    {
      "refined_content": "完整的精炼后内容",
      "pck":[
      "知识点的总结内容"
      ]
    }
    """
    
    print("开始处理教材内容（精炼+总结+分节）...")
    start_time = time.perf_counter()  # 记录开始时间
    
    try:
        response = call_LLM_sync(
            "textbook",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
            response_format={'type': 'json_object'}
        )

        end_time = time.perf_counter()  # 记录结束时间
        print(f"LLM处理时间: {end_time - start_time:.2f} 秒")
        print(f"响应长度: {len(response)} 字符")  # 显示响应长度

        response_file = f"{script_dir}/raw_response.json"
        refined_file = f"{script_dir}/textbook_refined.txt"
        pck_file = f"{script_dir}/pck.json"
        sections_file = f"{script_dir}/sections.json"

        response_json = {}
        with open(response_file, 'w', encoding='utf-8') as f:
            f.write(response)
        with open(response_file, 'r', encoding='utf-8') as f:
            response_json = json.load(f)

        refined_content = response_json.get("refined_content", "")
        with open(refined_file, 'w', encoding='utf-8') as f:
            f.write(refined_content)
        print(f"精炼内容已保存到: {refined_file}")
        
        pck = response_json.get("pck", [])
        with open(pck_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps({"pck": pck}, ensure_ascii=False, indent=2))
        print(f"pck内容已保存到: {pck_file}")
        
        #通过分隔标记对精炼内容进行分节
        sections = refined_content.split("xiaojiefenge")
        with open(sections_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps({"sections": sections}, ensure_ascii=False, indent=2))
        print(f"分节结果已保存到: {sections_file}")
        
        return True
    except Exception as e:
        print(f"处理出错: {e}")
        return False

async def process_chunk_async(chunk, chunk_index):
    """异步版本的分块处理函数"""
    simplified_prompt = """
    作为Markdown教材内容预处理助手，你需要完成以下三个步骤：

    步骤1：优化输入文本
    1. 将数学公式转换为纯文本表示
    2. 删除所有图片链接
    3. 删除目录部分
    4. 移除页眉和页脚的非内容部分
    5. 删除所有标题
    6. 确保删除所有习题，保留例题
    7. 修正排版问题和符号错误
    8. 尽量不要改动教材原文
    9. 在小节分隔处添加标记符"xiaojiefenge"
    强调一定是小节，不要把章节和小节内的分节或段落识别为小节
    例如：
    文本结构：
    “第一章 章节标题
    1.1 小节标题
    1.知识点1
    2.知识点2
    ……”
    只有“1.1 小节标题”标志着小节的开始，在这里添加标记符"xiaojiefenge"


    步骤2：总结专业内容知识
    1. 识别优化后教材中所有有关专业知识的内容即知识点。
    2. 每个知识点总结为一句话，重点在核心概念与定义，定理与定律，重要公式，知识点之间的逻辑关系和层次结构，知识点的实际应用场景和意义等。
    3. 每个知识点作为数组的一个元素。

    重要要求：
    - 必须返回严格的JSON格式
    - 所有字符串中的引号必须转义
    - 不要在JSON外添加任何解释文字
    - 确保JSON完整且格式正确

    JSON格式：
    {
      "refined_content": "完整的精炼后内容",
      "pck":[
      "知识点的总结内容"
      ]
    }
    """
    
    try:
        print(f"开始异步处理第 {chunk_index + 1} 块...")
        start_time = time.perf_counter()
        
        # 使用异步LLM调用
        response = await call_LLM(
            "textbook",
            messages=[
                {"role": "system", "content": simplified_prompt},
                {"role": "user", "content": chunk},
            ],
            response_format={'type': 'json_object'}
        )
        
        end_time = time.perf_counter()
        print(f"第 {chunk_index + 1} 块处理完成，耗时: {end_time - start_time:.2f} 秒")
        
        response_json = json.loads(response)
        return {
            "chunk_index": chunk_index,
            "refined_content": response_json.get("refined_content", ""),
            "pck": response_json.get("pck", [])
        }
        
    except Exception as e:
        print(f"异步处理第 {chunk_index + 1} 块出错: {e}")
        return {
            "chunk_index": chunk_index,
            "refined_content": "",
            "pck": []
        }

async def textbook_pretreat_chunked_async(text_book_file, max_tokens, max_concurrent=3):
    """异步分块处理大文件"""
    # 异步读取文件
    async with aiofiles.open(text_book_file, 'r', encoding='utf-8') as f:
        content = await f.read()

    # 分块逻辑（保持原有逻辑）
    tokens_per_chunk = max_tokens // 2
    chunks = []
    remaining_content = content
    
    while remaining_content:
        current_chunk = remaining_content
        current_tokens = count_tokens(current_chunk)
        
        if current_tokens <= tokens_per_chunk:
            chunks.append(current_chunk)
            break
        
        split_point = tokens_per_chunk
        sentence_end = max(
            remaining_content[:split_point].rfind(". "),
            remaining_content[:split_point].rfind("。"),
            remaining_content[:split_point].rfind("! "),
            remaining_content[:split_point].rfind("?"),
            remaining_content[:split_point].rfind("\n")
        )
        if sentence_end > 0 and sentence_end > len(remaining_content) // 4:
            split_point = sentence_end + 1
        
        chunks.append(remaining_content[:split_point])
        remaining_content = remaining_content[split_point:].lstrip()
    
    print(f"文件被分为 {len(chunks)} 个块进行异步处理，最大并发数: {max_concurrent}")
    
    # 使用信号量控制并发数
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_with_semaphore(chunk, index):
        async with semaphore:
            return await process_chunk_async(chunk, index)
    
    # 创建所有异步任务
    tasks = [
        process_with_semaphore(chunk, i) 
        for i, chunk in enumerate(chunks)
    ]
    
    # 并发执行所有任务
    start_time = time.perf_counter()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    end_time = time.perf_counter()
    
    print(f"所有块异步处理完成，总耗时: {end_time - start_time:.2f} 秒")
    
    # 处理结果
    successful_results = []
    failed_count = 0
    
    for result in results:
        if isinstance(result, Exception):
            print(f"任务失败: {result}")
            failed_count += 1
        else:
            successful_results.append(result)
    
    if failed_count > 0:
        print(f"警告: {failed_count} 个块处理失败")
    
    # 按chunk_index排序结果
    successful_results.sort(key=lambda x: x["chunk_index"])
    
    # 合并结果
    refined_content_parts = [result["refined_content"] for result in successful_results]
    all_pck = []
    for result in successful_results:
        all_pck.extend(result["pck"])
    
    # 生成最终内容
    refined_content = "".join(refined_content_parts)
    all_sections = refined_content.split("xiaojiefenge")
    
    # 异步保存文件
    refined_file = f"{script_dir}/textbook_refined.txt"
    pck_file = f"{script_dir}/pck.json"
    sections_file = f"{script_dir}/sections.json"
    
    # 并发保存所有文件
    save_tasks = [
        save_text_file_async(refined_file, refined_content),
        save_json_file_async(pck_file, {"pck": all_pck}),
        save_json_file_async(sections_file, {"sections": all_sections})
    ]
    
    await asyncio.gather(*save_tasks)
    
    print(f"精炼内容已保存到: {refined_file}")
    print(f"知识点总结已保存到: {pck_file}，共 {len(all_pck)} 个知识点")
    print(f"分节结果已保存到: {sections_file}，共 {len(all_sections)} 个分节")
    
    print(f"异步分块处理完成！共 {len(all_sections)} 个分节。")
    return True

async def save_text_file_async(filepath: str, content: str):
    """异步保存文本文件"""
    async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
        await f.write(content)

async def save_json_file_async(filepath: str, data: dict):
    """异步保存JSON文件"""
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
        await f.write(json_str)

if __name__ == "__main__":
    # 测试异步处理
    textbook_file = "C:\\Users\\Aover\\Documents\\SchoolAgent_gitee\\agentschool\\teacher\\Textbook\\textbooks\\textbook.md"
    asyncio.run(textbook_pretreat(textbook_file))
