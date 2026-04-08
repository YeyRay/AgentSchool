"""
异步批量做题处理模块
"""
import json
import asyncio
import time
from student.exercise import exercise, save_exercise_results

async def process_questions_in_batches(student, questions_file, batch_size=10):
    """
    分批处理题目，提高性能和内存使用效率
    
    Args:
        student: 学生对象
        questions_file: 题目文件路径
        batch_size: 每批处理的题目数量
    
    Returns:
        dict: 所有答案结果
    """
    print(f"开始分批处理题目，每批 {batch_size} 题")
    
    all_answers = {}
    correct_count = 0
    total_count = 0
    
    # 读取所有题目
    questions = []
    with open(questions_file, 'r', encoding='utf-8-sig') as f:
        for line_num, line in enumerate(f):
            try:
                question_dict = json.loads(line)
                questions.append((line_num, question_dict))
            except json.JSONDecodeError as e:
                print(f"跳过第 {line_num+1} 行，JSON解析错误: {e}")
    
    total_questions = len(questions)
    print(f"共读取到 {total_questions} 道题目")
    
    # 分批处理
    for batch_start in range(0, total_questions, batch_size):
        batch_end = min(batch_start + batch_size, total_questions)
        batch = questions[batch_start:batch_end]
        
        print(f"\n处理第 {batch_start+1}-{batch_end} 题 (共 {len(batch)} 题)")
        batch_start_time = time.time()
        
        # 异步处理当前批次
        batch_results = await process_question_batch(student, batch)
        
        # 合并结果
        for question_id, result in batch_results.items():
            all_answers[question_id] = result
            total_count += 1
            if result.get('correct', False):
                correct_count += 1
        
        batch_duration = time.time() - batch_start_time
        current_accuracy = (correct_count / total_count) * 100 if total_count > 0 else 0
        
        print(f"批次完成耗时: {batch_duration:.2f} 秒")
        print(f"当前进度: {total_count}/{total_questions} ({total_count/total_questions*100:.1f}%)")
        print(f"当前正确率: {correct_count}/{total_count} ({current_accuracy:.2f}%)")
        
        # 保存中间结果（防止程序意外中断）
        if total_count % (batch_size * 2) == 0:  # 每2批保存一次
            save_exercise_results(student, all_answers, f"progress_{total_count}")
            print(f"已保存进度: {total_count} 题")
    
    return all_answers

async def process_question_batch(student, question_batch):
    """
    异步处理一批题目
    
    Args:
        student: 学生对象
        question_batch: 题目批次 [(question_id, question_dict), ...]
    
    Returns:
        dict: 批次答案结果
    """
    # 为了避免并发过高，限制并发数量
    semaphore = asyncio.Semaphore(3)  # 最多同时处理3题
    
    async def process_single_question(question_id, question_dict):
        async with semaphore:
            return await process_one_question_async(student, question_id, question_dict)
    
    # 创建异步任务
    tasks = [
        process_single_question(question_id, question_dict)
        for question_id, question_dict in question_batch
    ]
    
    # 等待所有任务完成
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 整理结果
    batch_answers = {}
    for i, result in enumerate(results):
        question_id = question_batch[i][0]
        if isinstance(result, Exception):
            print(f"题目 {question_id+1} 处理失败: {result}")
            batch_answers[question_id] = {
                "answer": "",
                "thought_process": "处理失败",
                "correct": False,
                "error": str(result)
            }
        else:
            batch_answers[question_id] = result
    
    return batch_answers

async def process_one_question_async(student, question_id, question_dict):
    """
    异步处理单个题目
    """
    try:
        from student.retrieve import further_retrieve
        from student.prompt.run_ds_prompt import run_ds_prompt_generate_answer, run_ds_prompt_regenerate_answer
        from student.supervision import supervise_exercise
        import demjson3
        
        question = question_dict.get("content", "")
        correct_answer = question_dict.get("answer", "")
        
        # 检索相关记忆
        retrieved_mem = await further_retrieve(student, [question], n_count=10)
        mems = [i.embedding_key for i in retrieved_mem[question]]
        mems_str = "\n".join(mems)
        
        # 生成答案
        answer_response = await run_ds_prompt_generate_answer(student, question, mems_str)
        answer = demjson3.decode(answer_response)
        
        # 监督检查
        supervision = await supervise_exercise(student, "student/knowledge_points.json", answer)
        if supervision.get("exceeds_grade", False):
            regenerated_response = await run_ds_prompt_regenerate_answer(student, question, mems_str, supervision)
            answer = demjson3.decode(regenerated_response)
        
        # 判断正确性
        answer["correct"] = (str(answer.get('answer', '')).strip() == str(correct_answer).strip())
        answer["question_id"] = question_id
        answer["question"] = question
        
        return answer
        
    except Exception as e:
        print(f"处理题目 {question_id+1} 时发生错误: {e}")
        return {
            "answer": "",
            "thought_process": f"处理错误: {str(e)}",
            "correct": False,
            "question_id": question_id,
            "error": str(e)
        }

async def enhanced_exercise_with_progress(student, questions_file, batch_size=5):
    """
    增强版异步做题，包含进度显示和错误恢复
    """
    print(f"=== {student.name} 开始做题（增强异步版本）===")
    
    start_time = time.time()
    print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")
    
    try:
        # 分批处理所有题目
        all_answers = await process_questions_in_batches(student, questions_file, batch_size)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # 统计结果
        total_questions = len(all_answers)
        correct_answers = sum(1 for answer in all_answers.values() if answer.get('correct', False))
        accuracy_rate = (correct_answers / total_questions) * 100 if total_questions > 0 else 0
        
        print(f"\n=== 做题完成 ===")
        print(f"完成时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}")
        print(f"总耗时: {duration:.2f} 秒 ({duration/60:.2f} 分钟)")
        print(f"学生: {student.name}")
        print(f"总题目数: {total_questions}")
        print(f"答对题数: {correct_answers}")
        print(f"正确率: {accuracy_rate:.2f}%")
        print(f"平均每题耗时: {duration/total_questions:.2f} 秒")
        
        # 保存最终结果
        final_filename = save_exercise_results(student, all_answers, 150)
        print(f"最终结果已保存到: {final_filename}")
        
        return all_answers
        
    except Exception as e:
        print(f"做题过程中出现严重错误: {e}")
        import traceback
        traceback.print_exc()
        return {}
