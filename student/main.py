import sys
# sys.path.append("../")

from student.cognitive_module.memory import *
from student.cognitive_module.scratch import *
from student.cognitive_module.student import *
from student.prompt.run_ds_prompt import *
from student.perceive import *
from student.retrieve import *
from student.reflect import *
from student.plan import *
from student.execute import *
from student.exercise import *
from student.evaluate import *
from util.BroadcastSys import BroadcastSys
from datetime import datetime, timedelta
import os
from util.Events import *
from util.Recorder import *


def main():
    # 从json文件中加载数据 - 这一部分需要具体实现如何加载学生数据和初始信息
    # 假设我们创建了一个学生实例
    student_name = "StudentA" 
    student_folder = f"student/students/{student_name}" # 假设每个学生有一个文件夹存放记忆和临时文件

    

    # # 创建对应的文件夹（如果不存在）
    # import os
    # if not os.path.exists(student_folder):
    #     os.makedirs(f"{student_folder}/memory") # 为memory创建一个子文件夹

    # broadcast_system = BroadcastSys()

    student = Student(name=student_name, folder_mem_saved=student_folder)

    # 打印结点数量
    print(f"学生 {student.name} 的记忆结点数量: {len(student.mem.seq_thought) + len(student.mem.seq_knowledge)}")
    
    # # 初始化scratch中的一些属性，例如retention, current_time等，这些可以从配置文件或默认值加载
    # student.scratch.retention = 100 # 示例值
    # student.scratch.current_time = "2025-05-28T10:00:00" # 示例时间
    # student.scratch.importance_trigger_max = 50 # 示例值

    # 确保 test 目录存在
    test_output_dir = "test"
    if not os.path.exists(test_output_dir):
        os.makedirs(test_output_dir)

    # # 模拟一次信息输入，例如老师讲课的内容
    information_from_environment = ["同学们，今天我们学习七年级上册数学第一章《有理数》。首先看1.1节“有理数的引入”。正数是大于0的数，例如+3和500；负数是小于0的数，例如-12和-0.7。0既不 是正数也不是负数。现在大家回答：-5是正数还是负数？对，是负数。再问：收入100元记作+100，支出80元应该怎么表示？正确，记作-80元。", 
        "接下来学习有理数的分类。整数包括正整数、0和负整数，例如1、0、-3；分数包括正分数和负分数，例如1/3和-2/7。有理数就是整数和分数的统称。提问：5属于整数还是分数？很好，是整数。再问：-0.5是有理数吗？没错，因为它属于负分数。",
        "现在讲1.2节“数轴”。数轴必须有三个要素：原点、正方向和单位长度。例如画数轴时，先在直线上标出0，向右画箭头表示正方向，均匀刻度表示单位长度。提问：数 轴上-4应该在原点的哪一侧？回答正确，左侧。再问：比较-2和3的大小，哪个数在右边？很好，3更大所以在右侧。",
        "进入1.3节“相反数”。只有符号不同的两个数互为相反数，例如5和-5。特别强调，0的相反数是0。提问：-7的相反数是什么？正确，是7。再问：如果a和b互为相反数，那么a+b等于多少？对，等于0。",
        "接下来是1.4节“绝对值”。绝对值表示数在数轴上与原点的距离，例如|-4.5|=4.5。提问：|0|等于多少？没错，是0。再问：比较-5和-3的大小，哪个更小？正确，-5更小，因为绝对值大的负数反而小。",
        "关于1.5节“有理数的大小比较”，记住正数>0>负数。比较两个负数时，绝对值大的反而小。例如-1/2和-1/3哪个大？先通分比较绝对值，-1/3的绝对值更小，所以-1/3 比-1/2大。提问：-10和-5哪个更大？回答正确，是-5。", 
        "现在预习1.6-1.8节“有理数的加减法”。加法法则中，同号相加取相同符号，绝对值相加，例如(-3)+(-5)=-8。异号相加取绝对值较大数的符号，绝对值相减，例如5+(-3)=2。减法转化为加法，例如7-10=7+(-10)=-3。提问：(-4)+(-6)等于多少？正确，-10。再问：9-12等于多少？对，-3。"]


    content = [{"message_type": "class",
            "active_event": "ask_question",
           "speaker": "teacher",
           "content": "现在请你回答问题，在数 $-4, 0, 0.7, -\\frac{13}{3}, 2.5\\%, -1.2$ 中，负数有（ ）。\n(A) 1 个  \n(B) 2 个  \n(C) 3 个  \n(D) 4 个"}]
    information_from_environment = ["现在请你回答问题，在数 $-4, 0, 0.7, -\\frac{13}{3}, 2.5\\%, -1.2$ 中，负数有（ ）。\n(A) 1 个  \n(B) 2 个  \n(C) 3 个  \n(D) 4 个"]
    """   print(f"--- {student.name} 开始上课 ---")
    for i, information in enumerate(content):
        info = information.get("content", "")
        info_type = information.get("active_event", "")
        print(f"--- 现在是 {student.scratch.current_time} ---")
        node = perceive(student, info, sender="teacher", info_type=info_type)
        retrieved = retrieve(student, node)
        if retrieved and retrieved[node.content]:
            print(f"检索到相关记忆: {retrieved[node.content]}")
        else:
            print("没有检索到相关记忆。")
        
        reflect(student, retrieved)

        objects = plan(student, [student], node)

        print(f"--- {student.name} 现在的对象列表: {objects} ---")

        execute(student, objects)

        student.scratch.current_time = student.scratch.current_time + timedelta(seconds=30) # 假设每次感知后时间增加30秒

        
        #student.scratch.save(f"test/{student.name}_scratch_{i}.json")  # 保存当前scratch状态到文件

        #memory_file = f"test/{student.name}_memory_{i}"
        #if not os.path.exists(memory_file):
            #os.makedirs(memory_file, exist_ok=True) #确保 memory_file 作为目录存在
        #student.mem.save(memory_file)"""
    
    # 上课结束后，做题
    print(f"\n--- class over ---")
    print(f"{student.name} 开始做题。")
    exercise_questions = ["1. 在数 $-4, 0, 0.7, -\frac{13}{3}, 2.5\%, -1.2$ 中，负数有（ ）。\n(A) 1 个  \n(B) 2 个  \n(C) 3 个  \n(D) 4 个  ",
                          "2. 如果盈利 2 万元记作 $+2$ 万元，那么亏损 5 万元记作（ ）。\n(A) 5 万元  \n(B) 7 万元  \n(C) $-5$ 万元  \n(D) $-3$ 万元  ",
                          "3. 下列关于“0”的说法中，正确的有 ________。（填序号）\n① 0 是正数与负数的分界；  \n② 0 是正数；  \n③ 0 是自然数；  \n④ 0 不是整数。  ",
                          "4. 将下列各数填在相应的横线上：\n$$\n-10, 1, -0.5, 0, 36, -\\frac{2}{5}, 15\\%, -60, -\\frac{1}{53}, 22.8.\n$$\n正数：________________________；  \n负数：________________________。  ",
                          "5. 某老师要测量全班学生的身高，他以 1.60 米为基准，将某一小组 5 名学生的身高（单位：米）简记为：$+0.12, -0.05, 0, +0.07, -0.02$。这里的正数、负数分别表示什么意思？这 5 名学生的实际身高分别为多少？"]
    
    # answers_file = "questions/1.json"
    answers_file = "data.jsonl"
    # answers = exercise(student, answers_file)
    # 将答案保存到json文件
    # save_exercise_results(student, answers, 150)


    # 对做题过程进行反馈，然后根据反馈更新自己。
    feedback = """
总体反馈：优秀的表现！

你在解决这些数学问题时展现了扎实的基础知识、严谨的逻辑思维和细致的验证习惯，值得充分肯定！以下是对你整体表现的总结：

优点：
1. 概念理解清晰
   - 你能准确区分正数、负数和零，并理解它们在具体问题中的含义（如盈利、亏损、基准身高等）。
   - 对百分数、分数和小数的转换处理得当（如2.5%=0.025，-13/3≈-4.333）。

2. 逻辑推理严密
   - 你采用了逐步分析的方法，逐个检查选项或数值，确保不遗漏任何细节。
   - 在"0的性质"问题中，你通过排除法（①③正确，②④错误）得出了正确答案，体现了批判性思维。

3. 验证意识强
   - 你多次使用数轴辅助理解（如盈利/亏损、正负数的分布），这能帮助直观验证答案。
   - 在计算实际身高时，你反复检查计算过程，避免粗心错误。

4. 表达清晰
   - 你的思考过程条理分明，能清晰地解释每一步的推理依据（如"-1.2小于0，是第三个负数"）。

可进一步提升的地方：
1. 语言简洁性
   - 部分解释可以更精简（如问题1中"0不是正数也不是负数"只需提一次）。
   - 答案部分可直接列出关键点（如"负数：-4, -13/3, -1.2"）。

2. 符号书写规范
   - 注意数学符号的规范性（如"-13/3"应写作-13/3，保持分数形式）。

3. 拓展思考
   - 在类似"基准身高"的问题中，可以进一步思考："如果某人身高记为-0.10米，实际是多少？"以巩固概念。

总结：
你的解题能力已经非常出色，尤其在概念应用和逻辑推理方面表现突出。继续保持细致和验证的习惯，同时尝试简化表达，你的数学思维会更加高效和精准！如果遇到更复杂的问题（如混合运算或实际应用题），可以进一步练习如何快速提取关键信息。

再接再厉，你做得很好！ 🚀
"""

    #adjust(student, feedback)
    
    # 评估学生的表现
    evaluate(student, "问卷.json", 2)
    
    

if __name__ == "__main__":
    main()

