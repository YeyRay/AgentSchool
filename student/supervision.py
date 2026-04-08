import json
import sys
from student.global_methods import *
sys.path.append("../../")

from student.prompt.run_ds_supervisor import *

async def supervise_exercise(student, knowledge_points_file, answer):
    """
    监督学生的练习过程，检查答案是否符合学生当前掌握的知识点。
    INPUT:
        student: Student类
        knowledge_points_file: str, 知识点文件路径
        answer: dict, 学生的答案
    OUTPUT:
        supervision: dict, 监督结果，包含是否越级、使用的年级知识点和理由
        {
        "exceeds_grade": true 或 false,
        "used_which_grade_knowledge": "X年级上/下",
        }
    """
    # 读取知识点文件
    with open(knowledge_points_file, 'r', encoding='utf-8') as f:
        knowledge_points = json.load(f)

    # 检查学生的作答是否符合知识点要求
    print(f"\n--- 监督开始 ---")
    supervision = await run_ds_supervise_exercise(knowledge_points, answer)
    supervision["exceeds_grade"] = compare_grade_terms(student.scratch.grade, supervision["grade"])
    print(f"监督结果: {supervision}")
    print(f"--- 监督结束 ---\n")
    return supervision
    

async def supervise_knowledge_used(knowledge_points, student_answer, question):
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
    supervision = await run_ds_check_knowledge_used(knowledge_points, student_answer, question)
    print(f"学生使用的知识点的分析: {supervision}")
    return supervision
