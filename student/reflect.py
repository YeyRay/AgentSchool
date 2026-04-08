import sys
sys.path.append("../../")

from student.cognitive_module.memory import *
from student.cognitive_module.scratch import *
from student.cognitive_module.student import *
from student.prompt.run_ds_prompt import *
from student.retrieve import *

async def generate_focus(student, n = 3):
    """
    生成当前的关注点。
    根据检索到的记忆，生成当前的关注点，
    具体说就是对检索的记忆根据LLM生成三个相关的问题
        student: Student类
        n: int, 生成的关注点数量
    OUTPUT:
        focus: list of string, 生成的关注点列表
    """
    # 获取当前的记忆
    nodes = [[i.last_accessed, i]
             for i in student.mem.seq_thought + student.mem.seq_knowledge]
    nodes.sort(key=lambda x: x[0], reverse=True)
    nodes = [i[1] for i in nodes]

    statements = ""
    for node in nodes[0: student.scratch.retention]:
        statements += node.content + "\n"

    return await run_ds_prompt_generate_focus(statements, n)

def reflection_trigger(student):
    """
    决定是否进行反思。
    """
    if (student.scratch.importance_trigger_curr >= student.scratch.importance_trigger_max and
        [] != student.mem.seq_knowledge + student.mem.seq_thought):
        return True
    return False

def reset_reflection_trigger(student):
    """
    重置反思触发器。
    将当前的importance_trigger_current重置为0。
    """
    student.scratch.importance_trigger_curr = 0

async def run_reflect(student):
    """
    实际进行反思
    OUTPUT:
        thoughts: dict, {focus_point: ConceptNode类的实例(thought)}
    """
    thoughts = {}
    focus_points = await generate_focus(student, n=3)
    retrieved_mem = await further_retrieve(student, focus_points, n_count=10)

    # 对每个关注点，进行思考并且放入其记忆
    for focus_point, nodes in retrieved_mem.items():
        print(f"关注点: {focus_point}")
        xx = [i.embedding_key for i in nodes]
        for xxx in xx: print(f"检索到的记忆: {xxx}")

        thought = await run_ds_prompt_reflect(student, focus_point, nodes)
        # 将思考的内容存入记忆
        importance = int(await run_ds_prompt_importance_thought(student, thought))
        student.scratch.accumulate_importance(importance)
        keywords = await run_ds_prompt_thought_keywords(thought)
        embedding_pair = (thought, await get_local_embedding(thought))
        thoughts[focus_point] = student.mem.add_thought(student.scratch.current_time, thought, keywords, importance,
                                embedding_pair)
    
    return thoughts
    

async def reflect(student, retrieved_mem):
    """
    对检索到的记忆进行反思。
    根据检索到的记忆，生成新的想法，并保存到记忆中。
    INPUT:
        student: Student类
        retrieved_mem: {当前结点的描述}: {检索到的结点的类型: 检索到的结点的列表}}
    OUTPUT:
        thoughts: dict, {关注点: ConceptNode类的实例(thought)}
    """
    
    if reflection_trigger(student):
        print(f"--- {student.name} 开始反思 ---")
        thougts = await run_reflect(student)
        reset_reflection_trigger(student)
        for focus_point, thought in thougts.items():
            print(f"关注点: {focus_point}, 思考内容: {thought.content}")
        print("反思完成，新的想法已存入记忆。")
        return thougts
    else:
        print(f"--- {student.name} 没有进行反思 ---")
        return None
         


async def adjust(student, feedback):
    """
    根据反馈，调整学生的学习策略、压力和注意力等。
    INPUT:
        student: Student类
        feedback: string, 反馈内容
    OUTPUT:
        None
    """
    student.scratch.obstacle_student()

    adjusted = await run_ds_prompt_adjust(student, feedback)
    print(f"调整结果: {adjusted}")

async def analyze_exercise(student):
    """
    分析学生的做题情况，找出错误并进行反思和调整。
    INPUT:
        student: Student类
    OUTPUT:
        None
    """
    import os
    from pathlib import Path
    
    name = student.name
    results_base = f"results/{name}/"
    
    # 1. 找到最新日期的文件夹
    results_path = Path(results_base)
    if not results_path.exists():
        print(f"未找到 {name} 的结果目录")
        return None
    
    # 获取所有日期文件夹，按日期排序
    date_folders = [d for d in results_path.iterdir() if d.is_dir() and d.name.count('-') == 2]
    if not date_folders:
        print(f"未找到 {name} 的日期文件夹")
        return None
    
    latest_date_folder = sorted(date_folders, key=lambda x: x.name)[-1]
    print(f"最新日期文件夹: {latest_date_folder.name}")
    
    # 2. 在最新日期下找 exercises 文件夹
    exercises_folder = latest_date_folder / "exercises"
    if not exercises_folder.exists():
        print(f"未找到 exercises 文件夹: {exercises_folder}")
        return None
    
    # 3. 找到所有 final_true_concurrent 文件
    final_files = list(exercises_folder.glob(f"{name}_exercise_results_final_true_concurrent_*.json"))
    if not final_files:
        print(f"未找到 final_true_concurrent 文件")
        return None
    
    # 4. 按文件名中的时间戳排序，取最新的
    latest_final_file = sorted(final_files, key=lambda x: x.stem.split('_')[-1])[-1]
    print(f"最新的 final_true_concurrent 文件: {latest_final_file.name}")
    
    # 5. 读取文件内容
    exercise_data = await read_exercise_file(str(latest_final_file))

    # 分析正确回答的部分
    correct_answers = exercise_data['correct_answers']
    correct_answers_content = [answer['thought_process'] for answer in correct_answers]

    # print(f"部分正确答案的思考过程示例:{correct_answers_content[0:2]}")

    analyze_1 = await run_ds_prompt_analyze_exercise_correct(correct_answers_content)

    # 分析错误回答的部分
    wrong_answers = exercise_data['wrong_answers']
    wrong_answers_content = [answer['thought_process'] for answer in wrong_answers]

    print(f"部分错误答案的思考过程示例:{wrong_answers_content[0:2]}")

    analyze_2 = await run_ds_prompt_analyze_exercise_wrong(wrong_answers_content)
    
    return analyze_1, analyze_2

async def read_exercise_file(exercise_file):
    """
    读取学生做题文件
    INPUT:
        exercise_file: str, 存放学生做题数据的文件路径
    OUTPUT:
        exercise_data: dict, 包含完整的做题数据
        {
            "correct_answers": [...],  # 正确答案列表
            "wrong_answers": [...],     # 错误答案列表
            "statistics": {...},        # 统计信息
            "raw_data": {...}          # 原始完整数据
        }
    """
    import json
    
    with open(exercise_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    
    # 提取详细答案部分
    detailed_answers = raw_data.get('data', {}).get('detailed_answers', {})
    
    # 分类存储正确和错误的答案
    correct_answers = []
    wrong_answers = []
    
    for question_id, answer_data in detailed_answers.items():
        if not isinstance(answer_data, dict):
            continue
        
        # 构建单题数据结构
        question_record = {
            'question_id': answer_data.get('question_id', question_id),
            'question': answer_data.get('question', ''),
            'student_answer': answer_data.get('answer', ''),
            'correct_answer': answer_data.get('correct_answer', ''),
            'is_correct': answer_data.get('correct', False),
            'thought_process': answer_data.get('thought_process', ''),
            'retrieved_memories': answer_data.get('retrieved_memories', []),
            'retrieved_memories_count': answer_data.get('retrieved_memories_count', 0),
            'memory_summary': answer_data.get('memory_summary', ''),
            'misconceptions': answer_data.get('misconceptions', []),
            'processing_time': answer_data.get('processing_time', 0),
            'timestamp': answer_data.get('timestamp', '')
        }
        
        # 根据正确与否分类
        if answer_data.get('correct', False):
            correct_answers.append(question_record)
        else:
            wrong_answers.append(question_record)
    
    # 提取统计信息
    statistics = raw_data.get('data', {}).get('statistics', {})
    
    # 构建返回的结构化数据
    exercise_data = {
        'correct_answers': correct_answers,
        'wrong_answers': wrong_answers,
        'statistics': {
            'performance': statistics.get('performance', {}),
            'memory_usage': statistics.get('memory_usage', {}),
            'personalization': statistics.get('personalization', {}),
            'total_correct': len(correct_answers),
            'total_wrong': len(wrong_answers),
            'total_questions': len(correct_answers) + len(wrong_answers),
            'accuracy': len(correct_answers) / (len(correct_answers) + len(wrong_answers)) * 100 if (len(correct_answers) + len(wrong_answers)) > 0 else 0
        },
        'metadata': raw_data.get('metadata', {}),
        'raw_data': raw_data  # 保留完整原始数据以备需要
    }
    
    return exercise_data

async def improve_after_exercise(student, analyze_correct, analyze_wrong):
    """
    从做题分析中生成错误改进分析。
    INPUT:
        student: Student类
        analyze_correct: 分析正确答案的结果
        analyze_wrong: 分析错误答案的结果
    OUTPUT:
        None
    """
    await(student.improve_from_exercise(analyze_correct, analyze_wrong))

    # 保存到新的saving中
    await(student.save_student_state())
