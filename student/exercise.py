import json
import demjson3
import asyncio
import time
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import torch
from sentence_transformers import SentenceTransformer

from student.cognitive_module.memory import *
from student.cognitive_module.scratch import *
from student.cognitive_module.student import *
from student.prompt.run_ds_prompt import *
from student.retrieve import *
from student.supervision import *
from util.file_manager import get_file_manager
from student.exercise_modifiers import PersonalizedQuestionModifier
from student.knowledge_graph import kg

# 全局模型实例
_embedding_model = None
_model_cache = {}
_embedding_model_lock = None  # 延迟锁/避免早期创建
_preprocessed_cache = {}  # 预处理缓存

async def get_embedding_model(model_name="BAAI/bge-small-zh-v1.5"):
    """GPU加载/单例锁"""
    global _embedding_model, _embedding_model_lock
    if _embedding_model is not None:
        return _embedding_model
    if _embedding_model_lock is None:
        _embedding_model_lock = asyncio.Lock()
    async with _embedding_model_lock:
        if _embedding_model is not None:
            return _embedding_model
        print(f"正在加载嵌入模型: {model_name}")
        # 环境变量优先
        load_target = os.getenv("BGE_MODEL") or model_name
        _embedding_model = await asyncio.to_thread(
            lambda: SentenceTransformer(load_target, device=("cuda" if torch.cuda.is_available() else "cpu"))
        )
        print("模型加载成功")
        return _embedding_model

async def preprocess_questions_embeddings_batch(questions_file):
    """批处理/缓存"""
    print("=== 开始批量处理题目 embedding ===")
    # mtime缓存
    try:
        mtime = os.path.getmtime(questions_file)
        cache_key = (questions_file, mtime)
        if cache_key in _preprocessed_cache:
            print("命中预处理缓存，跳过重复计算")
            cached = _preprocessed_cache[cache_key]
            return [dict(item) for item in cached]
    except Exception:
        cache_key = None
    questions_data = []
    
    # 1. 读取所有题目
    with open(questions_file, 'r', encoding='utf-8-sig') as f:
        for i, line in enumerate(f):
            question_dict = json.loads(line)
            question_content = question_dict.get("content", "")
            correct_answer = question_dict.get("answer", "")
            
            questions_data.append({
                "index": i,
                "content": question_content,
                "answer": correct_answer,
                "embedding": None
            })
    
    print(f"共取到 {len(questions_data)} 道")
    
    # 2. 提取所有问题文本批量计算 embedding
    all_questions_text = [q["content"] for q in questions_data]
    
    print("开始批量计算所有 embedding...")
    start_time = time.time()
    
    try:
        model = await get_embedding_model()
        all_embeddings = await asyncio.to_thread(
            lambda: model.encode(
                all_questions_text,
                convert_to_tensor=False,
                show_progress_bar=True,
                batch_size=64
            )
        )
        
        # 分配 embedding 结果
        for i, embedding in enumerate(all_embeddings):
            questions_data[i]["embedding"] = (embedding.tolist() if hasattr(embedding, "tolist") else list(embedding))
        
        end_time = time.time()
        print(f"批量计算完成，耗时: {end_time - start_time:.2f} 秒")
        
    except Exception as e:
        print(f"批量计算 embedding 失败: {e}")
        # 调试处理
        for i, q_data in enumerate(questions_data):
            try:
                embedding = await get_local_embedding(q_data["content"])
                q_data["embedding"] = embedding
            except:
                q_data["embedding"] = [0.0] * 384
    
    if cache_key is not None:
        _preprocessed_cache[cache_key] = [dict(item) for item in questions_data]
    print("=== embedding 参数配置完成 ===")
    return questions_data

async def process_single_question_async_optimized(student, q_data, question_id_prefix="", semaphore=None):
    """单题处理/并发"""
    # 如果有多题参数，可以逐个设置或批量处理

    if semaphore:
        async with semaphore:
            return await _process_single_question_core(student, q_data, question_id_prefix)
    else:
        return await _process_single_question_core(student, q_data, question_id_prefix)

async def _process_single_question_core(student, q_data, question_id_prefix=""):
    """核心处理逻辑"""
    try:
        # 安全地获取索引，保证它是整数
        raw_index = q_data["index"]

        if isinstance(raw_index, str):
            try:
                if raw_index.isdigit():
                    i = int(raw_index)
                else:
                    float_val = float(raw_index)
                    i = int(float_val)
            except (ValueError, TypeError) as e:
                print(f"⚠️ 索引转换失败: '{raw_index}' -> {e}")
                i = 0
        elif isinstance(raw_index, (int, float)):
            # 直接转换为整数（这是最常见的情况）
            i = int(raw_index)
        else:
            print(f"⚠️ 未知索引类型: {type(raw_index)} = {raw_index}")
            i = 0
            
        question = q_data["content"]
        correct_answer = q_data["answer"]
        question_embedding = q_data["embedding"]
        
        # 添加任务ID用于跟踪
        task_id = f"{question_id_prefix}Q{i+1}"
        print(f"[{task_id}] {student.name} 开始...")
        start_time = time.time()
        
        # 记录练习前的知识点掌握度快照
        mastery_before = {}
        
        # 初始化变量，防止异常时未定义
        retrieved_memories = []
        mems_str = ""
        mems_misconceptions = []
        supervision = {}
        
        # 1. 索引
        print(f"[{task_id}] 开始索引相关..")
        # 复用预计算向量
        retrieved_mem = await further_retrieve_with_precomputed_embedding(
            student,
            question,
            question_embedding,
            n_count=10
        )

        # 提取记忆信息用于保存
        retrieved_memories = []
        for node in retrieved_mem:
            memory_info = {
                "node_id": node.node_id,
                "content": node.embedding_key,  # 记忆的具体内容
                "importance": getattr(node, 'importance', 0),  # 重要性
                "keywords": getattr(node, 'keywords', []),     # 关键词
                "last_accessed": str(getattr(node, 'last_accessed', '')),  
                "node_type": getattr(node, 'type', ""),  # 节点类型
            }
            # 如果是知识节点，添加知识标签
            if hasattr(node, 'knowledge_tag'):
                knowledge_tag = node.knowledge_tag
                if knowledge_tag is None:
                    memory_info["knowledge_tag"] = []
                else:
                    memory_info["knowledge_tag"] = knowledge_tag
            
            retrieved_memories.append(memory_info)
        
        mems = [node.embedding_key for node in retrieved_mem]
        mems_str = "\n".join(mems)
        mems_misconceptions = [node.misconceptions for node in retrieved_mem if hasattr(node, 'misconceptions')]
        
        # 2. 答案生成
        print(f"[{task_id}] 开始生成答案...")
        try:
            answer_response = await run_ds_prompt_generate_answer(student, question, mems_str, mems_misconceptions)
            answer = demjson3.decode(answer_response)
            print(f"[{task_id}] 初始答案: {answer.get('answer', 'N/A')}")
            answer["correct"] = (str(answer.get('answer', '')).strip() == str(correct_answer).strip())
            
            # 3. 监督
            print(f"[{task_id}] 开始监督...")
            supervision = await supervise_exercise(student, "student/knowledge_points.json", answer)

            # 4. 监督知识点的使用
            print(f"[{task_id}] 监督知识点的使用情况。")
            # 我需要两个字典，一个用于存放每个知识点出现的次数，
            # 另一个用于存放每个知识点是正确使用还是错误使用
            knowledge_tags_times = dict()
            knowledge_tags_to_check = dict()
            if retrieved_memories:
                for memory in retrieved_memories:
                    if 'knowledge_tag' in memory:
                        tags = memory['knowledge_tag']
                        # 防御性检查：确保 tags 是可迭代的列表
                        if tags is not None and isinstance(tags, (list, tuple)):
                            for tag in tags:
                                if tag not in knowledge_tags_times:
                                    knowledge_tags_times[tag] = 0
                                knowledge_tags_times[tag] += 1
                        else:
                            print(f"⚠️ 警告：记忆节点的 knowledge_tag 不是列表: {tags}")
            
            if knowledge_tags_times:
                try:
                    knowledge_tags_to_check = await supervise_knowledge_used(
                        list(knowledge_tags_times.keys()), 
                        answer.get("answer", ""), 
                        question
                    )
                    # 检查返回值是否有效
                    if knowledge_tags_to_check is None:
                        print(f"⚠️ 警告：supervise_knowledge_used 返回了 None")
                        knowledge_tags_to_check = {}
                    elif "error" in knowledge_tags_to_check:
                        print(f"⚠️ 知识点监督返回错误: {knowledge_tags_to_check.get('error')}")
                        knowledge_tags_to_check = {}
                except Exception as e:
                    print(f"⚠️ 知识点监督失败: {e}")
                    knowledge_tags_to_check = {}
            
            # 将知识点的熟练度存入知识图谱
            # 策略：
            # 1. 正确使用的知识点(used) -> 增强掌握度(正向学习)
            # 2. 错误使用的知识点(missed) -> 轻微惩罚(暴露误解)
            # 3. 答对题目 -> 额外加成
            # 4. 使用次数多 -> 说明该知识点在此题中很重要，权重更高
            
            # 记录更新前的掌握度
            if knowledge_tags_to_check and knowledge_tags_times:
                for tag_name in knowledge_tags_to_check.keys():
                    tag_id = kg.get_id_by_name(tag_name, student.knowledge_points_of_the_grade)
                    if tag_id:
                        mastery_before[tag_name] = {
                            "id": tag_id,
                            "mastery": kg.get_mastery(student.name, tag_id)
                        }
            
            # 执行知识点更新
            mastery_changes = []
            
            # 修改逻辑：即使LLM监督失败,只要检测到知识点使用就应该更新
            if knowledge_tags_times:
                # 如果有LLM监督结果,优先使用;否则使用默认策略
                if knowledge_tags_to_check:
                    # 场景1: LLM成功返回监督结果,按照used/missed处理
                    for tag_name, usage_status in knowledge_tags_to_check.items():
                        # 先将知识点名称转换为ID
                        tag_id = kg.get_id_by_name(tag_name, student.knowledge_points_of_the_grade)
                        if tag_id is None:
                            print(f"⚠️ 警告：未找到知识点'{tag_name}'的ID，跳过")
                            continue
                        
                        # 获取该知识点在记忆中出现的次数（重要性权重）
                        times = knowledge_tags_times.get(tag_name, 1)
                        
                        # 基础学习强度（根据使用次数调整）
                        base_strength = 0.03 * min(times / 3.0, 2.0)  # 次数越多权重越高，但有上限
                        
                        if usage_status == "used":
                            # 正确使用知识点
                            strength = base_strength * (1.5 if answer["correct"] else 1.0)
                            # 答对题目时给予额外加成
                            print(f"[{task_id}] 知识点'{tag_name}'(ID:{tag_id})使用正确，强度={strength:.3f}")
                            kg.passive_learn(
                                student.name, 
                                tag_id,  # 使用ID而不是名称
                                strength=strength,
                                config_kg=student.knowledge_points_of_the_grade
                            )
                        elif usage_status == "missed":
                            # 错误使用知识点（暴露了误解）
                            # 给予极小的负向调整（通过降低增强效果实现）
                            strength = base_strength * 0.2  # 仅保留20%的正向效果
                            print(f"[{task_id}] 知识点'{tag_name}'(ID:{tag_id})使用错误，轻微惩罚，强度={strength:.3f}")
                            kg.passive_learn(
                                student.name, 
                                tag_id,  # 使用ID而不是名称
                                strength=strength,
                                config_kg=student.knowledge_points_of_the_grade
                            )
                        
                        # 记录更新后的掌握度和变化
                        mastery_after = kg.get_mastery(student.name, tag_id)
                        mastery_before_value = mastery_before.get(tag_name, {}).get("mastery", None)
                        
                        change_info = {
                            "knowledge_point": tag_name,
                            "knowledge_point_id": tag_id,
                            "usage_status": usage_status,
                            "usage_times": times,
                            "learning_strength": strength,
                            "mastery_before": round(mastery_before_value, 4) if mastery_before_value else None,
                            "mastery_after": round(mastery_after, 4) if mastery_after else None,
                            "mastery_change": round(mastery_after - mastery_before_value, 4) if (mastery_after and mastery_before_value) else None
                        }
                        mastery_changes.append(change_info)
                else:
                    # 场景2: LLM监督失败,使用保守的默认策略
                    # 假设所有检测到的知识点都是"可能正确使用"(给予中等强度)
                    print(f"[{task_id}] ⚠️ LLM监督失败,使用默认策略更新{len(knowledge_tags_times)}个知识点")
                    for tag_name, times in knowledge_tags_times.items():
                        tag_id = kg.get_id_by_name(tag_name, student.knowledge_points_of_the_grade)
                        if tag_id is None:
                            print(f"⚠️ 警告：未找到知识点'{tag_name}'的ID，跳过")
                            continue
                        
                        # 使用保守的默认强度(比"used"弱,比"missed"强)
                        base_strength = 0.03 * min(times / 3.0, 2.0)
                        strength = base_strength * 0.6  # 60%的基础强度(介于used和missed之间)
                        
                        print(f"[{task_id}] 知识点'{tag_name}'(ID:{tag_id})默认更新(无监督)，强度={strength:.3f}")
                        kg.passive_learn(
                            student.name, 
                            tag_id,
                            strength=strength,
                            config_kg=student.knowledge_points_of_the_grade
                        )
                        
                        # 记录更新后的掌握度和变化
                        mastery_after = kg.get_mastery(student.name, tag_id)
                        mastery_before_value = mastery_before.get(tag_name, {}).get("mastery", None)
                        
                        change_info = {
                            "knowledge_point": tag_name,
                            "knowledge_point_id": tag_id,
                            "usage_status": "default_update",  # 标记为默认更新
                            "usage_times": times,
                            "learning_strength": strength,
                            "mastery_before": round(mastery_before_value, 4) if mastery_before_value else None,
                            "mastery_after": round(mastery_after, 4) if mastery_after else None,
                            "mastery_change": round(mastery_after - mastery_before_value, 4) if (mastery_after and mastery_before_value) else None
                        }
                        mastery_changes.append(change_info)

            # 将知识点使用情况添加到监督结果中
            if knowledge_tags_times:
                supervision["knowledge_points_cnt"] = knowledge_tags_times
            
            if knowledge_tags_to_check:
                supervision["knowledge_points_used"] = knowledge_tags_to_check
            
            # 添加知识点掌握度变化记录
            if mastery_changes:
                supervision["knowledge_mastery_changes"] = mastery_changes
                

            # 记录监督信息
            supervision_info = {
                "grade": supervision.get("grade", ""),
                "knowledge_points": supervision.get("knowledge_points", ""),
                "exceeds_grade": supervision.get("exceeds_grade", False),
                "supervision_triggered": supervision.get("exceeds_grade", False)
            }

            if supervision.get("exceeds_grade", False):
                print(f"[{task_id}] 要重新生成回答...")
                try:
                    regenerated_response = await run_ds_prompt_regenerate_answer(
                        student, question, mems_str, supervision
                    )
                    original_answer = answer.copy()  # 保存原答案
                    answer = demjson3.decode(regenerated_response)

                    # 重新生成
                    supervision_info["original_answer"] = original_answer.get("answer", "")
                    supervision_info["regenerated_answer"] = answer.get("answer", "")
                    supervision_info["regeneration_successful"] = True

                    print(f"[{task_id}] 监督后回答: {answer.get('answer', 'N/A')}")
                except Exception as e:
                    print(f"[{task_id}] 监督重新生成失败: {e}")
                    supervision_info["regeneration_successful"] = False
                    supervision_info["regeneration_error"] = str(e)
            
        except Exception as e:
            print(f"[{task_id}] 回答生成失败处理: {e}")
            answer = {
                "answer": "A",
                "thought_process": f"处理错误: {e}",
                "correct": False  # 确保 correct 字段存在
            }
        
        # 4. 结果处理
        # 如果 answer 还没有 correct 字段（正常流程已设置，异常流程刚设置），确保其存在
        if "correct" not in answer:
            answer["correct"] = (str(answer.get('answer', '')).strip() == str(correct_answer).strip())
        
        answer["question_id"] = i
        answer["question"] = question
        answer["correct_answer"] = correct_answer

        # 添加记忆
        answer["retrieved_memories"] = retrieved_memories
        answer["retrieved_memories_count"] = len(retrieved_memories)
        answer["memory_summary"] = mems_str if retrieved_memories else "无相关记忆"

        # 记录监督
        answer["supervision"] = supervision

        duration = time.time() - start_time
        answer["processing_time"] = round(duration, 2)
        answer["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        answer["misconceptions"] = mems_misconceptions
        result_msg = "✓" if answer["correct"] else f"✗错(正确: {correct_answer})"
        print(f"[{task_id}] 完成 - {result_msg} (耗时: {duration:.2f}s)")
        
        return i, answer
        
    except Exception as e:
        print(f"[{task_id}] 异常: {e}")
        return q_data["index"], {
            "answer": "",
            "thought_process": f"异常错误: {str(e)}",
            "correct": False,
            "question_id": q_data["index"],
            "question": q_data.get("content", ""),
            "correct_answer": q_data.get("answer", ""),
            "error": str(e),
            "retrieved_memories": [],
            "retrieved_memories_count": 0,
            "memory_summary": "处理异常，无法索引",
            "supervision": {"error": str(e)},
            "processing_time": 0,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "midsconceptions": []
        }

async def process_single_question_with_personalization(student, question_data, question_index, semaphore=None):
    """处理单个题目（包含个性化）"""
    
    # 1. 初始化修改器
    modifier = PersonalizedQuestionModifier(student)
    
    # 2. 根据学生特点修改题目
    modified_question = modifier.modify_question(question_data, question_index)
    
    # 3. 记录信息
    modification_log = {
        "student_name": student.name,
        "question_index": question_data.get("index", question_index),
        "original_content": question_data["content"],
        "modified_content": modified_question["content"],
        "modifications": modified_question.get("modification_info", {}),
        "timestamp": datetime.now().isoformat()
    }
    
    # 4. 处理修改后的题目（使用并发控制）
    question_id, answer_result = await process_single_question_async_optimized(
        student, modified_question, question_index, semaphore
    )
    
    # 5. 在结果中记录修改信息
    if "modification_info" in modified_question:
        answer_result["question_modification"] = {
            "was_modified": True,
            "original_question": question_data["content"],
            "modified_question": modified_question["content"],
            "modification_details": modified_question["modification_info"]
        }
        # answer_result["personalization_log"] = modification_log
    else:
        answer_result["question_modification"] = {
            "was_modified": False,
            "original_question": question_data["content"],
            "modified_question": question_data["content"]
        }
    
    return question_id, answer_result

async def process_questions_batch_async_optimized(student, questions_batch, max_concurrent=5):
    """批调度/并发"""
    # 减少并发数，避免过度竞争
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # 安全地打印批次信息避免index出错
    safe_indices = []
    for q in questions_batch:
        try:
            idx = q['index']
            if isinstance(idx, str):
                if idx.isdigit():
                    safe_indices.append(int(idx) + 1)
                else:
                    safe_indices.append(int(float(idx)) + 1)
            else:
                safe_indices.append(int(idx) + 1)
        except (ValueError, TypeError) as e:
            print(f"🔍 调试信息 - 批索索引出错: {q['index']}, 错误: {e}")
            safe_indices.append(f"ERROR({q['index']})")
    
    print(f"=== 开始处理批次，题目索引: {safe_indices} ===")
    
    # 创建任务但不立即执行
    tasks = []
    for q_data in questions_batch:
        # 同样要安全地获取首个题目的index用于批命名
        try:
            first_idx = questions_batch[0]['index']
            if isinstance(first_idx, str):
                if first_idx.isdigit():
                    batch_num = int(first_idx) // 20 + 1
                else:
                    batch_num = int(float(first_idx)) // 20 + 1
            else:
                batch_num = int(first_idx) // 20 + 1
        except (ValueError, TypeError) as e:
            print(f"🔍 调试信息 - 批编号计算错误: {questions_batch[0]['index']}, 错误: {e}")
            batch_num = 1
            
        task = asyncio.create_task(
            process_single_question_async_optimized(
                student, q_data, f"Batch{batch_num}-", semaphore
            )
        )
        tasks.append(task)
        # 节流更小
        await asyncio.sleep(0.01)
    
    print(f"已创建 {len(tasks)} 个任务，开始并发执行...")
    
    # 等待所有任务完
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 整理结果
    batch_answers = {}
    successful_count = 0
    
    for result in results:
        if isinstance(result, Exception):
            print(f"任务执行异常: {result}")
            continue
            
        question_id, answer = result
        batch_answers[question_id] = answer
        if answer.get('correct', False):
            successful_count += 1
    
    success_rate = (successful_count / len(batch_answers)) * 100 if batch_answers else 0
    print(f"=== 批量处理完成，成功率: {success_rate:.1f}% ({successful_count}/{len(batch_answers)}) ===")
    
    return batch_answers

async def exercise_with_true_concurrency(student, questions_data, batch_size=20, max_concurrent=5):
    """并发做题"""
    print(f"=== {student.name}开始真正异步并发做题 ===")
    print(f"配置: 批大小={batch_size}, 每批并发数={max_concurrent}")
    
    all_answers = {}
    total_questions = len(questions_data)
    total_correct = 0
    processed_count = 0
    
    start_time = time.time()
    
    # 批处理，但减小批大小以提高并发效果
    for batch_start in range(0, total_questions, batch_size):
        batch_end = min(batch_start + batch_size, total_questions)
        questions_batch = questions_data[batch_start:batch_end]
        
        batch_num = batch_start // batch_size + 1
        print(f"\n*** 第{batch_num}: 题目 {batch_start+1}-{batch_end} ***")
        batch_start_time = time.time()
        
        # 异并发处理当前批次
        batch_answers = await process_questions_batch_async_optimized(
            student, questions_batch, max_concurrent
        )
        
        # 统计结果
        batch_correct = sum(1 for ans in batch_answers.values() if ans.get('correct', False))
        total_correct += batch_correct
        processed_count += len(batch_answers)
        
        # 合并到结果
        all_answers.update(batch_answers)
        
        batch_duration = time.time() - batch_start_time
        overall_accuracy = (total_correct / processed_count) * 100 if processed_count > 0 else 0
        
        print(f"*** 第{batch_num}批完成 ***")
        print(f"耗时: {batch_duration:.2f}s, 平均每: {batch_duration/len(batch_answers):.2f}s")
        print(f"进度: {processed_count}/{total_questions} ({processed_count/total_questions*100:.1f}%)")
        print(f"总体正确率: {total_correct}/{processed_count} ({overall_accuracy:.1f}%)")
        
        # 减少持久化频率
        if batch_num % 3 == 0:
            save_exercise_results(student, all_answers, f"progress_batch_{batch_num}")
    
    total_duration = time.time() - start_time
    final_accuracy = (total_correct / processed_count) * 100 if processed_count > 0 else 0
    
    print(f"\n🎉 === 并发做题完成 === 🎉")
    print(f"总时间: {total_duration:.2f}s ({total_duration/60:.2f}分钟)")
    print(f"平均每题: {total_duration/processed_count:.2f}s")
    print(f"最终正确率: {final_accuracy:.2f}%")
    
    return all_answers

async def exercise(student, questions_file, batch_size=20, max_concurrent=5):
    """主流程/并发"""
    overall_start_time = time.time()
    
    # 1: 批量预处理 embedding
    print("=== 步骤1: 批量预处理 embedding ===")
    questions_data = await preprocess_questions_embeddings_batch(questions_file)
    
    preprocess_time = time.time()
    preprocess_duration = preprocess_time - overall_start_time
    print(f"预处理完成，耗时: {preprocess_duration:.2f} ")
    
    # 2: 真的异步并发做题
    print("=== 步骤2: 真的异步并发做题 ===")
    answers = await exercise_with_true_concurrency(
        student, questions_data, batch_size, max_concurrent
    )
    
    answer_time = time.time()
    answer_duration = answer_time - preprocess_time
    total_duration = answer_time - overall_start_time
    
    print(f"做题完成，耗时: {answer_duration:.2f} ")
    print(f"总体耗时: {total_duration:.2f}  ({total_duration/60:.2f} 分钟)")
    
    # 保存最终结果
    save_exercise_results(student, answers, "final_true_concurrent")
    save_memory_analysis(student, answers, "final_with_memory")

    return answers


def save_exercise_results(student, answers, postfix):
    """
    保存练习题的结果到json文件
    """
    file_mgr = get_file_manager()
    
    # 计算统计数据
    total_questions = len(answers)
    correct_count = sum(1 for ans in answers.values() if ans.get('correct', False))
    accuracy = (correct_count / total_questions * 100) if total_questions > 0 else 0
    
    # 统计记忆使用情况
    total_memories_used = sum(ans.get('retrieved_memories_count', 0) for ans in answers.values())
    avg_memories_per_question = total_memories_used / total_questions if total_questions > 0 else 0
    
    # 统计监督触发情况
    supervision_triggered = sum(1 for ans in answers.values() 
                              if ans.get('supervision', {}).get('supervision_triggered', False))
    
    # 统计个性化修改情况
    modification_stats = _analyze_question_modifications(answers)
    
    # 组织结果数据
    result_data = {
        "test_info": {
            "test_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "postfix": postfix,
            "total_duration_seconds": getattr(student, '_test_duration', 0),
            "environment": "concurrent_processing_with_personalization"
        },
        "statistics": {
            "performance": {
                "total_questions": total_questions,
                "correct_answers": correct_count,
                "incorrect_answers": total_questions - correct_count,
                "accuracy_percentage": round(accuracy, 2),
                "difficulty_distribution": _analyze_difficulty_distribution(answers)
            },
            "memory_usage": {
                "total_memories_retrieved": total_memories_used,
                "avg_memories_per_question": round(avg_memories_per_question, 2),
                "memory_efficiency_score": _calculate_memory_efficiency(answers)
            },
            "supervision": {
                "supervision_triggered_count": supervision_triggered,
                "supervision_rate": round(supervision_triggered / total_questions * 100, 2) if total_questions > 0 else 0,
                "supervision_effectiveness": _analyze_supervision_effectiveness(answers)
            },
            "personalization": modification_stats
        },
        "detailed_answers": answers
    }
    
    # 使用 file manager 保存结果
    filepath = file_mgr.save_exercise_results(student.name, result_data, postfix)
    
    # 保存进度检查点（用于恢复）
    if total_questions > 50:  # 大型测试才保存检查点
        checkpoint_data = {
            "completed_questions": total_questions,
            "current_accuracy": accuracy,
            "timestamp": datetime.now().isoformat()
        }
        file_mgr.save_progress_checkpoint(student.name, checkpoint_data, f"checkpoint_{postfix}")
    
    print(f"练习题结果已保存: {filepath}")
    print(f"📊 统计信息: 正确率 {accuracy:.1f}%, 平均每 {avg_memories_per_question:.1f} 条")
    print(f"🎯 个性化修改：题目 {modification_stats['modified_questions']}/{modification_stats['total_questions']} ({modification_stats['modification_rate']:.1f}%)")
    if modification_stats['modified_questions'] > 0:
        print(f"   个性化修改题目正确率: {modification_stats['effectiveness']['modified_accuracy']:.1f}% vs 未个性化修改题目正确率: {modification_stats['effectiveness']['unmodified_accuracy']:.1f}%")
    print(f"📂 文件结构: results/{student.name}/{datetime.now().strftime('%Y-%m-%d')}/exercises/")
    
    return str(filepath)

def save_memory_analysis(student, answers, postfix):
    """
    单独保存记忆使用分析报告
    """
    file_mgr = get_file_manager()
    
    memory_analysis = {
        "summary": {
            "total_questions_analyzed": len(answers),
            "memory_retrieval_stats": _calculate_memory_stats(answers),
            "knowledge_coverage": _analyze_knowledge_coverage(answers),
            "personalization_stats": _analyze_question_modifications(answers)
        },
        "detailed_analysis": {
            "memory_usage_by_question": [],
            "frequently_used_memories": {},
            "knowledge_gaps": [],
            "memory_effectiveness": _analyze_memory_effectiveness(answers),
            "personalization_effectiveness": []
        }
    }
    
    all_used_memories = []
    
    for q_id, answer in answers.items():
        question_analysis = {
            "question_id": q_id,
            "question": answer.get("question", ""),
            "correct": answer.get("correct", False),
            "memories_count": answer.get("retrieved_memories_count", 0),
            "memory_types": {},
            "key_memories": [],
            "memory_relevance_score": _calculate_memory_relevance(answer)
        }
        
        # 分析使用的记忆类型和重要记忆
        for memory in answer.get("retrieved_memories", []):
            memory_type = memory.get("node_type", "Unknown")
            question_analysis["memory_types"][memory_type] = question_analysis["memory_types"].get(memory_type, 0) + 1
            
            # 重要记忆（重要性>=7）
            if memory.get("importance", 0) >= 7:
                question_analysis["key_memories"].append({
                    "content": memory.get("content", ""),
                    "importance": memory.get("importance", 0),
                    "keywords": memory.get("keywords", []),
                    "relevance_score": memory.get("relevance_score", 0)
                })
            
            # 用于统计频繁使用的记忆
            content = memory.get("content", "")
            if content:
                all_used_memories.append(content)
        
        # 添加个性化信息
        question_mod = answer.get("question_modification", {})
        if question_mod.get("was_modified", False):
            question_analysis["personalization"] = {
                "was_modified": True,
                "original_question": question_mod.get("original_question", ""),
                "modification_types": list(question_mod.get("modification_details", {}).keys())
            }
        else:
            question_analysis["personalization"] = {"was_modified": False}
        
        # 检查知识差距（没有所引导相关记忆但答错的题目）
        if not answer.get("correct", False) and answer.get("retrieved_memories_count", 0) == 0:
            memory_analysis["detailed_analysis"]["knowledge_gaps"].append({
                "question_id": q_id,
                "question": answer.get("question", ""),
                "correct_answer": answer.get("correct_answer", ""),
                "student_answer": answer.get("answer", ""),
                "potential_knowledge_area": _identify_knowledge_area(answer.get("question", "")),
                "was_modified": question_mod.get("was_modified", False)
            })
        
        memory_analysis["detailed_analysis"]["memory_usage_by_question"].append(question_analysis)
    
    # 分析个性化的效果
    for answer in answers.values():
        question_mod = answer.get("question_modification", {})
        if question_mod.get("was_modified", False):
            memory_analysis["detailed_analysis"]["personalization_effectiveness"].append({
                "question_id": answer.get("question_id", "unknown"),
                "correct": answer.get("correct", False),
                "memory_count": answer.get("retrieved_memories_count", 0),
                "modification_types": list(question_mod.get("modification_details", {}).keys()),
                "effectiveness_score": 1.0 if answer.get("correct", False) else 0.0
            })
    
    # 统计频繁使用的记忆
    from collections import Counter
    memory_counter = Counter(all_used_memories)
    memory_analysis["detailed_analysis"]["frequently_used_memories"] = dict(memory_counter.most_common(10))
    
    # 使用文件管理器保存分析报告
    analysis_filepath = file_mgr.save_memory_analysis(student.name, memory_analysis, postfix)
    
    # 生成可视化数据
    viz_data = {
        "memory_type_distribution": {},
        "performance_vs_memory_usage": [],
        "knowledge_gap_areas": [],
        "frequently_used_memories": memory_analysis["detailed_analysis"]["frequently_used_memories"],
        "personalization_analysis": {
            "modification_distribution": {},
            "effectiveness_comparison": [],
            "modification_memory_correlation": []
        }
    }
    
    # 填充可视化数据
    for question_data in memory_analysis["detailed_analysis"]["memory_usage_by_question"]:
        # 记忆类型分布
        for mem_type, count in question_data["memory_types"].items():
            viz_data["memory_type_distribution"][mem_type] = viz_data["memory_type_distribution"].get(mem_type, 0) + count
        
        # 性能与记忆使用关系
        viz_data["performance_vs_memory_usage"].append({
            "memories_used": question_data["memories_count"],
            "correct": question_data["correct"],
            "relevance_score": question_data["memory_relevance_score"],
            "was_modified": question_data["personalization"]["was_modified"]
        })
        
        # 个性化分析
        if question_data["personalization"]["was_modified"]:
            for mod_type in question_data["personalization"]["modification_types"]:
                viz_data["personalization_analysis"]["modification_distribution"][mod_type] = \
                    viz_data["personalization_analysis"]["modification_distribution"].get(mod_type, 0) + 1
            
            viz_data["personalization_analysis"]["modification_memory_correlation"].append({
                "memories_used": question_data["memories_count"],
                "correct": question_data["correct"],
                "modification_types": question_data["personalization"]["modification_types"]
            })
    
    # 效果对比数据
    personalization_stats = memory_analysis["summary"]["personalization_stats"]
    viz_data["personalization_analysis"]["effectiveness_comparison"] = {
        "modified_accuracy": personalization_stats["effectiveness"]["modified_accuracy"],
        "unmodified_accuracy": personalization_stats["effectiveness"]["unmodified_accuracy"],
        "modification_rate": personalization_stats["modification_rate"]
    }
    
    # 知识缺口区域
    viz_data["knowledge_gap_areas"] = [gap["potential_knowledge_area"] 
                                     for gap in memory_analysis["detailed_analysis"]["knowledge_gaps"]]
    viz_dir = file_mgr.get_category_dir(student.name, "visualizations")
    viz_filename = file_mgr.generate_unique_filename(student.name, "viz_data", postfix)
    viz_filepath = viz_dir / viz_filename
    
    with open(viz_filepath, 'w', encoding='utf-8') as f:
        json.dump(viz_data, f, ensure_ascii=False, indent=2)
    
    print(f"记忆使用分析已保存到: {analysis_filepath}")
    print(f"📈 可视化数据保存: {viz_filepath}")
    
    return str(analysis_filepath)

# 辅助函数定义
def _analyze_question_modifications(answers):
    """分析题目修改的统计数据"""
    modification_stats = {
        "total_questions": len(answers),
        "modified_questions": 0,
        "modification_rate": 0.0,
        "modification_types": {},
        "effectiveness": {
            "modified_correct": 0,
            "modified_incorrect": 0,
            "unmodified_correct": 0,
            "unmodified_incorrect": 0
        },
        "common_modifications": []
    }
    
    modification_details = []
    
    for answer in answers.values():
        question_mod = answer.get("question_modification", {})
        was_modified = question_mod.get("was_modified", False)
        is_correct = answer.get("correct", False)
        
        if was_modified:
            modification_stats["modified_questions"] += 1
            
            # 统计修改类型
            mod_details = question_mod.get("modification_details", {})
            mod_types = mod_details.get("applied", [])
            for mod_type in mod_types:
                if mod_type not in modification_stats["modification_types"]:
                    modification_stats["modification_types"][mod_type] = 0
                modification_stats["modification_types"][mod_type] += 1
            
            # 统计效果
            if is_correct:
                modification_stats["effectiveness"]["modified_correct"] += 1
            else:
                modification_stats["effectiveness"]["modified_incorrect"] += 1
                
            # 收集详细修改记录
            modification_details.append({
                "question_id": answer.get("question_id", "unknown"),
                "original": question_mod.get("original_question", ""),
                "modified": question_mod.get("modified_question", ""),
                "correct": is_correct,
                "modification_types": list(mod_types)
            })
        else:
            if is_correct:
                modification_stats["effectiveness"]["unmodified_correct"] += 1
            else:
                modification_stats["effectiveness"]["unmodified_incorrect"] += 1
    
    # 计算修改率
    if modification_stats["total_questions"] > 0:
        modification_stats["modification_rate"] = round(
            modification_stats["modified_questions"] / modification_stats["total_questions"] * 100, 2
        )
    
    # 计算效果对比
    modified_total = modification_stats["effectiveness"]["modified_correct"] + modification_stats["effectiveness"]["modified_incorrect"]
    unmodified_total = modification_stats["effectiveness"]["unmodified_correct"] + modification_stats["effectiveness"]["unmodified_incorrect"]
    
    if modified_total > 0:
        modification_stats["effectiveness"]["modified_accuracy"] = round(
            modification_stats["effectiveness"]["modified_correct"] / modified_total * 100, 2
        )
    else:
        modification_stats["effectiveness"]["modified_accuracy"] = 0
        
    if unmodified_total > 0:
        modification_stats["effectiveness"]["unmodified_accuracy"] = round(
            modification_stats["effectiveness"]["unmodified_correct"] / unmodified_total * 100, 2
        )
    else:
        modification_stats["effectiveness"]["unmodified_accuracy"] = 0
    
    # 找出最常见的修改类型
    if modification_stats["modification_types"]:
        sorted_mods = sorted(modification_stats["modification_types"].items(), 
                           key=lambda x: x[1], reverse=True)
        modification_stats["common_modifications"] = [
            {"type": mod_type, "count": count, "percentage": round(count/modification_stats["modified_questions"]*100, 1)}
            for mod_type, count in sorted_mods[:5] 
        ]
    
    # 添加详细修改记录（最多10条）
    modification_stats["detailed_modifications"] = modification_details[:10]  
    
    return modification_stats

def _analyze_difficulty_distribution(answers):
    """分析题目难度分布"""
    difficulty_levels = {"easy": 0, "medium": 0, "hard": 0}
    
    for answer in answers.values():
        memories_used = answer.get("retrieved_memories_count", 0)
        is_correct = answer.get("correct", False)
        
        # 简单规则：使用记忆少且答对的题目视为简单
        if memories_used <= 2 and is_correct:
            difficulty_levels["easy"] += 1
        elif memories_used <= 5:
            difficulty_levels["medium"] += 1
        else:
            difficulty_levels["hard"] += 1
    
    return difficulty_levels

def _calculate_memory_efficiency(answers):
    """计算记忆使用效率分数"""
    total_questions = len(answers)
    if total_questions == 0:
        return 0
    
    efficiency_scores = []
    for answer in answers.values():
        memories_used = answer.get("retrieved_memories_count", 0)
        is_correct = answer.get("correct", False)
        
        # 效率分数：硭案且使用较少记忆 = 高效
        if is_correct:
            if memories_used <= 3:
                efficiency_scores.append(10)  # 高效
            elif memories_used <= 6:
                efficiency_scores.append(7)   # 中效率
            else:
                efficiency_scores.append(5)   # 低效
        else:
            efficiency_scores.append(0)  # 错答
    
    return round(sum(efficiency_scores) / len(efficiency_scores), 2)

def _analyze_supervision_effectiveness(answers):
    """分析监督的效果"""
    supervision_cases = [ans for ans in answers.values() 
                        if ans.get('supervision', {}).get('supervision_triggered', False)]
    
    if not supervision_cases:
        return {"effectiveness_rate": 0, "improvement_count": 0}
    
    improvement_count = sum(1 for case in supervision_cases 
                          if case.get('supervision', {}).get('improved_after_supervision', False))
    
    return {
        "effectiveness_rate": round(improvement_count / len(supervision_cases) * 100, 2),
        "improvement_count": improvement_count,
        "total_supervised": len(supervision_cases)
    }

def _calculate_memory_stats(answers):
    """计算记忆使用的统计数据"""
    total_retrievals = sum(ans.get("retrieved_memories_count", 0) for ans in answers.values())
    questions_with_memories = sum(1 for ans in answers.values() if ans.get("retrieved_memories_count", 0) > 0)
    
    return {
        "total_memory_retrievals": total_retrievals,
        "questions_with_memories": questions_with_memories,
        "avg_memories_per_question": round(total_retrievals / len(answers), 2) if answers else 0,
        "memory_usage_rate": round(questions_with_memories / len(answers) * 100, 2) if answers else 0
    }

def _analyze_knowledge_coverage(answers):
    """分析知识覆盖范围"""
    knowledge_areas = set()
    for answer in answers.values():
        for memory in answer.get("retrieved_memories", []):
            keywords = memory.get("keywords", [])
            knowledge_areas.update(keywords)
    
    return {
        "unique_knowledge_areas": len(knowledge_areas),
        "knowledge_diversity_score": min(len(knowledge_areas) / 20, 1.0)  
    }

def _analyze_memory_effectiveness(answers):
    """分析记忆使用的有效性"""
    effective_cases = 0
    total_cases = 0
    
    for answer in answers.values():
        if answer.get("retrieved_memories_count", 0) > 0:
            total_cases += 1
            if answer.get("correct", False):
                effective_cases += 1
    
    return {
        "effectiveness_rate": round(effective_cases / total_cases * 100, 2) if total_cases > 0 else 0,
        "effective_cases": effective_cases,
        "total_memory_usage_cases": total_cases
    }

def _calculate_memory_relevance(answer):
    """计算记忆相关性分数"""
    memories = answer.get("retrieved_memories", [])
    if not memories:
        return 0
    
    relevance_scores = [mem.get("relevance_score", 0.5) for mem in memories]
    return round(sum(relevance_scores) / len(relevance_scores), 3)

def _identify_knowledge_area(question):
    """识别题目所属的知识领域"""
    # 简单的关键词匹配识别
    knowledge_keywords = {
        "数学": ["计算", "方程", "函数", "多项式", "小数", "数字", "运算"],
        "物理": ["力学", "电学", "光学", "热学", "速度", "加速度"],
        "化学": ["元素", "化合物", "反应", "分子", "原子"],
        "语文": ["阅读", "写作", "语法", "文学", "词语"]
    }
    
    question_lower = question.lower()
    for area, keywords in knowledge_keywords.items():
        if any(keyword in question_lower for keyword in keywords):
            return area
    
    return "未分类"