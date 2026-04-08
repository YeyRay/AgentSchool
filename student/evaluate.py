import os
import json
import demjson3
import time

from student.prompt.run_ds_prompt import *

async def evaluate(student, file, postfix):
    """
    根据传入的问卷，对学生的表现进行评估。
    INPUT:
        student: Student类
        file: str, 问卷文件路径 
        postfix: str, 用于区分不同评估的后缀
    OUTPUT:

    """
    if not os.path.exists(file):
        print(f"问卷文件 {file} 不存在。")
        return

    # 读取问卷内容
    with open(file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"\n--- 评估开始 ---")
    t_start = time.time()
    print(f"{student.name} 开始回答问卷。")

    personality_description = demjson3.decode(await run_ds_prompt_analyze_personality(student))
    print(f"性格描述：{personality_description}")

    answers = []
    for question in data["量表"]:
        category = question.get("类别")
        period = question.get("阶段", "")
        rate = question.get("评分")
        explanation = question.get("说明", "")
        print(f"现在的类别是: {question['类别']}")
        description = await run_ds_prompt_describe_rate(category, period, rate, explanation)
        print(f"评分说明：{description}")
        if "题目" in question:
            for i in question["题目"]:
                try:
                    a = demjson3.decode(await run_ds_prompt_evaluate(student, i, description, category, personality_description))
                except Exception as e:
                    print(f"处理问题 '{i}' 时发生错误: {e}")
                    a = {"答案": "", "思考过程": ""}
                print(f"问题: {i}")
                print(f"回答: {a}")
                answers.append({
                    "问题" : i,
                    "答案": a.get("答案", ""),
                    "思考过程": a.get("思考过程", ""),
                })
        elif "子类别" in question:
            for sub in question["子类别"]:
                print(f"现在的子类别是: {sub}")
                for i in question["子类别"][sub]:
                    try:
                        a = demjson3.decode(await run_ds_prompt_evaluate(student, i, description, category, personality_description))
                    except Exception as e:
                        print(f"处理问题 '{i}' 时发生错误: {e}")
                        a = {"答案": "", "思考过程": ""}
                    print(f"问题: {i}")
                    print(f"回答: {a}")
                    answers.append({
                        "问题": i,
                        "答案": a.get("答案", ""),
                        "思考过程": a.get("思考过程", ""),
                    })

        save_evaluation_results(student, answers, postfix)
    # 统计耗时
    t_cost = time.time() - t_start
    print(f"[TIME] {student.name} 问卷耗时: {t_cost:.2f}s")

async def evaluate_bfi(student, file, postfix):
    """
    针对大五人格量表（如大五人格量表.json）进行评估，并计算五大特质分数（不考虑反向题，直接相加）。
    """
    # 五大特质题号（1-based）
    BFI_TRAITS = {
        "外向性":      [1, 6, 11, 16, 21, 26, 31, 36, 41, 46, 51, 56],
        "宜人性":      [2, 7, 12, 17, 22, 27, 32, 37, 42, 47, 52, 57],
        "尽责性":      [3, 8, 13, 18, 23, 28, 33, 38, 43, 48, 53, 58],
        "负性情绪":    [4, 9, 14, 19, 24, 29, 34, 39, 44, 49, 54, 59],
        "开放性":      [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60],
    }

    if not os.path.exists(file):
        print(f"问卷文件 {file} 不存在。")
        return

    with open(file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"\n--- 大五人格评估开始 ---")
    print(f"{student.name} 开始回答大五人格量表。")

    scale_info = data["量表"][0]
    rate = scale_info.get("评分", "")
    print(f"评分说明：{rate}")

    answers = []
    trait_scores = {trait: [] for trait in BFI_TRAITS}

    # personality_description = demjson3.decode(await run_ds_prompt_analyze_personality(student))
    personality_description = demjson3.decode(await run_ds_prompt_analyze_personality_MBTI(student))
    print(f"性格描述：{personality_description}")

     # 内部函数，用于处理单个问题
    async def process_question(idx, q_text):
        try:
            # 让学生作答，答案需为1-5分整数，LLM已处理反向题
            a = demjson3.decode(await run_ds_prompt_evaluate_MBTI(student, q_text, rate, "大五人格", personality_description))
            score = int(float(a.get("答案", 3)))  # 先转float再转int，兼容小数
            return {"idx": idx, "q_text": q_text, "score": score, "raw_answer": a, "status": "success"}
        except Exception as e:
            print(f"处理问题 '{q_text}' 时发生错误: {e}")
            score = 3
            a = {"答案": str(score), "思考过程": ""}
            return {"idx": idx, "q_text": q_text, "score": score, "raw_answer": a, "status": "error"}
    
    # 创建所有问题的处理任务
    tasks = [process_question(idx, q_text) for idx, q_text in enumerate(scale_info["题目"], 1)]
    
    # 并行执行所有任务
    results = await asyncio.gather(*tasks)

    # 处理并收集结果
    answers = []
    trait_scores = {trait: [] for trait in BFI_TRAITS}
    
    # 对结果进行排序，确保顺序与原始问题一致
    results.sort(key=lambda r: r['idx'])

    for result in results:
        idx = result['idx']
        q_text = result['q_text']
        score = result['score']
        a = result['raw_answer']

        print(f"问题{idx}: {q_text}")
        print(f"回答: {a}")
        
        answers.append({
            "序号": idx,
            "问题": q_text,
            "原始题干": scale_info["题目"][idx-1],
            "答案": score,
            "思考过程": a.get("思考过程", ""),
        })
        
        # 统计分数
        for trait, qlist in BFI_TRAITS.items():
            if idx in qlist:
                trait_scores[trait].append(score)


    """for idx, question in enumerate(scale_info["题目"], 1):
        q_text = question
        try:
            # 让学生作答，答案需为1-5分整数，LLM已处理反向题
            a = demjson3.decode(await run_ds_prompt_evaluate_MBTI(student, q_text, rate, "大五人格", personality_description))
            score = int(a.get("答案", 3))  # 默认3分
        except Exception as e:
            print(f"处理问题 '{q_text}' 时发生错误: {e}")
            score = 3
            a = {"答案": str(score), "思考过程": ""}
        print(f"问题{idx}: {q_text}")
        print(f"回答: {a}")
        answers.append({
            "序号": idx,
            "问题": q_text,
            "原始题干": question,
            "答案": score,
            "思考过程": a.get("思考过程", ""),
        })
        # 统计分数
        for trait, qlist in BFI_TRAITS.items():
            if idx in qlist:
                trait_scores[trait].append(score)"""

    # 计算每个特质的总分和均分
    trait_summary = {
        trait: {
            "总分": sum(scores),
            "均分": round(sum(scores)/len(scores), 2) if scores else 0,
            "明细": scores
        }
        for trait, scores in trait_scores.items()
    }

    # 保存结果
    memory_folder = f"student/evaluation/test_{student.name}"
    os.makedirs(memory_folder, exist_ok=True)
    memory_file = f"{memory_folder}/evaluate_results_{postfix}.json"
    with open(memory_file, 'w', encoding='utf-8') as f:
        json.dump({
            "answers": answers,
            "trait_scores": trait_summary
        }, f, indent=2, ensure_ascii=False)
    print(f"评估结果已保存到 {memory_file}")
    print(f"\n--- 大五人格评估结束 ---")


def save_evaluation_results(student, answers, postfix):
    # 将答案保存到json文件
    # memory_folder = f"student/evaluation/test_{student.name}"
    # os.makedirs(memory_folder, exist_ok=True)  # 确保目录存在
    # memory_file = f"{memory_folder}/evaluate_results_{postfix}.json"
    memory_file = f"stu_questionnaire/{student.name}_evaluate_results_{postfix}.json"
    os.makedirs(os.path.dirname(memory_file), exist_ok=True)

    with open(memory_file, 'w', encoding='utf-8') as f:
        json.dump(answers, f, indent=2, ensure_ascii=False)

    print(f"评估结果已保存到 {memory_file}")

    print(f"\n--- 评估结束 ---")

