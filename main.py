# -*- coding: utf-8 -*-
import sys
import argparse
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
from student.global_methods import load_grade_knowledge_points
from util.BroadcastSys import BroadcastSys
from datetime import datetime, timedelta
import os
from util.Events import *
from util.Recorder import *

def parse_arguments():
    parser = argparse.ArgumentParser(description='SchoolAgent - 学生智能体系统')
    
    parser.add_argument(
        '--student', '-s',
        type=str,
        default='StudentC',
        help='指定学生名称 (默认: StudentC)'
    )
    
    parser.add_argument(
        '--list-students', '-l',
        action='store_true',
        help='列出所有可用的学生'
    )
    
    return parser.parse_args()

def list_available_students():
    """列出所有可用的学生"""
    students_dir = "student/students"
    if os.path.exists(students_dir):
        students = [d for d in os.listdir(students_dir) 
                   if os.path.isdir(os.path.join(students_dir, d))]
        if students:
            print("可用的学生:")
            for student in students:
                print(f"  - {student}")
        else:
            print("没有找到可用的学生")
    else:
        print(f"学生目录不存在: {students_dir}")


async def main():

    args = parse_arguments()
    # 如果请求列出学生,则显示并退出
    if args.list_students:
        list_available_students()
        return
    # 从json文件中加载数据 - 这一部分需要具体实现如何加载学生数据和初始信息
    # 假设我们创建了一个学生实例
    student_name = "StudentA"
    student_folder = f"student/saving/{student_name}/20250901_0/{student_name}_45_1" # 假设每个学生有一个文件夹存放记忆和临时文件

    # 检查学生文件夹是否存在
    if not os.path.exists(student_folder):
        print(f"错误: 学生 '{student_name}' 不存在!")
        print("可用的学生:")
        list_available_students()
        return
    
    print(f"使用学生: {student_name}")

    

    # # 创建对应的文件夹(如果不存在)
    # import os
    # if not os.path.exists(student_folder):
    #     os.makedirs(f"{student_folder}/memory") # 为memory创建一个子文件夹

    # broadcast_system = BroadcastSys()

    student = Student(name=student_name, folder_mem_saved=student_folder)
    # 加载知识点（容错，多文件名尝试）
    # grade_kps = load_grade_knowledge_points(student)
    # print(f"加载年级知识点数量: {len(grade_kps)}")

    # 打印结点数量
    print(f"学生 {student.name} 的记忆结点数量: {len(student.mem.seq_thought) + len(student.mem.seq_knowledge)}")
    
    # # 初始化scratch中的一些属性,例如retention, current_time等,这些可以从配置文件或默认值加载
    # student.scratch.retention = 100 # 示例值
    # student.scratch.current_time = "2025-05-28T10:00:00" # 示例时间
    # student.scratch.importance_trigger_max = 50 # 示例值

    # 确保 test 目录存在
    """test_output_dir = "test"
    if not os.path.exists(test_output_dir):
        os.makedirs(test_output_dir)"""

    # # 模拟一次信息输入,例如老师讲课的内容


    content = [{"message_type": "class",
            "active_event": "ask_question",
           "speaker": "teacher",
           "content": "现在请你回答问题,在数 $-4, 0, 0.7, -\\frac{13}{3}, 2.5\\%, -1.2$ 中,负数有( )。\n(A) 1 个  \n(B) 2 个  \n(C) 3 个  \n(D) 4 个"}]
    information_from_environment = ["现在请你回答问题,在数 $-4, 0, 0.7, -\\frac{13}{3}, 2.5\\%, -1.2$ 中,负数有( )。\n(A) 1 个  \n(B) 2 个  \n(C) 3 个  \n(D) 4 个"]
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
    
    # 上课结束后,做题
    print(f"\n--- class over ---")
    print(f"{student.name} 开始做题。")
   
    # 异步执行做题任务
    answers_file = "student/data.jsonl"
    # await exercise(student, answers_file)

    # 分析做题结果
    a1, a2 = await analyze_exercise(student)
    # print(f"\n=== 做题分析结果 ===")
    # print(f"正确题目分析:\n{a1}\n")
    # print(f"错误题目分析:\n{a2}\n")

    print(f"=== 生成错误改进分析 ===")
    # result = await run_ds_prompt_improve_from_exercise(student, a1, a2)
    # # 读取json格式回答
    # data = json.loads(result)
    # # 读取各部分内容
    # elimination = data.get("Elimination", [])
    # evolution = data.get("Evolution", {})
    # emergence = data.get("Emergence", [])

    # # 示例输出
    # print("消除的错误认知:", elimination)
    # print("演化的错误认知:", evolution)
    # print("新增的错误认知:", emergence)

    # 改进
    await(improve_after_exercise(student, a1, a2))

    # 测试对老师教学的反馈
    teaching_content = """
    同学们，我们来看数轴上的-6和6这两个点，它们在数轴上的位置有什么共同特点呢？\n同学们观察得很准确，这两对点确实关于原点对称。你们发现-6和6、1.5和-1.5这两组数在数轴上的位置与原点的距离相等，这个特点非常重要。\n像-6和6这样，只有符号不同的两个数互为相反数。观察数轴上这两对数的位置可以发现，-6和6分别位于原点的左右两侧，且与原点的距离都是6个单位长度。同样，1.5和-1.5也是符号相反的两个数，它们在数轴上也分别位于原点的两旁，并且与原点的距离都是1.5个单位长度。因此，互为相反数的两个数具有两个关键特征：一是它们的符号相反，二是它们在数轴上到原点的距离相等。\n为什么互为相反数的两个点必须位于原点两旁？\n同学们刚才在数轴上准确标出了-6和6、1.5和-1.5的位置，老师注意到很多同学都发现了这两组点关于原点对称的特点。特别是小明提到\"这两对数字到原点的距离相同但方向相反\"，这个观察非常到位，从几何特征抓住了相反数的本质特征。小红还补充说\"它们就像镜子里的影像\"，这个比喻形象地体现了数轴的对称性。现在请大家思考：如果两个点在数轴上到原点的距离相等但方向相反，这两个数之间有什么关系？\n如果数轴的正方向改为向左，那么-1.5和1.5的位置关系会发生变化吗？\n同学们，请看数轴上标出的6和-6这两个数，你们能观察到它们在数轴上的位置有什么特点吗？\n同学们刚才在观察数轴上的对称点时，能够准确指出像6和-6这样的数位于原点两侧且距离相等，这非常好。你们发现的这种对称性正是相反数的几何特征——互为相反数的两个数在数轴上关于原点对称，这也是判断两个数是否互为相反数的直观方法。\n在数学中，像6和-6、1.5和-1.5这样，只有正负号不同的两个数称为互为相反数。也就是说，其中一个数是另一个数的相反数。例如，6是-6的相反数，-6也是6的相反数。需要注意的是，0的相反数仍然是0，这是一个特殊的规定。\n我们已经学习了相反数的概念，知道像6和-6这样只有正负号不同的两个数互为相反数。那么，为什么规定0的相反数是0呢？请大家思考一下，这与绝对值的对称性有什么关系？\n同学们刚才对相反数的概念理解得很准确，能够举出像π和-π这样的例子说明互为相反数的两个数符号相反、绝对值相同。接下来我们从数轴的角度进一步观察：互为相反数的两个数在数轴上对应的点有什么共同特征？它们与原点的位置关系是怎样的？\n我们已经学习了像6和-6这样只有正负号不同的两个数互为相反数，并且规定0的相反数是0。现在请大家看1.5和-1.5这对数，谁能用自己的话解释一下它们之间的关系？\n今天我们学习了相反数的概念，像6和-6、1.5和-1.5这样只有正负号不同的两个数互为相反数。相反数的核心特征是它们在数轴上关于原点对称，即到原点的距离相等但方向相反。特别地，0的相反数是它本身。相反数在表示相反量时具有重要应用价值，例如温度的零上零下、收入与支出等实际情境中，都可以用相反数来准确描述具有相反意义的量。\n同学们，请看数轴上标出的+5和-5的位置，你们能发现它们有什么共同特征吗？为什么说这两个数是相反数？\n很好，你注意到了它们在数轴上关于原点对称，且绝对值相等。\n同学们，我们刚刚看到-7的相反数是7，你能说明为什么-7的相反数是7吗？用你自己的话描述这种关系。\n非常好，你们在解决例1时准确地运用了相反数的定义，即只有符号不同的两个数互为相反数。比如，你们正确地指出+5的相反数是-5，-7的相反数是7，-3 1/2的相反数是3 1/2，11.2的相反数是-11.2。这清楚地表明你们抓住了相反数的本质定义。\n我们来看-3 1/2和3 1/2的转换，分数形式的相反数转换有什么需要特别注意的地方？\n非常好，你注意到了在求混合数的相反数时，符号的变化不会改变分数部分本身的值，这个观察非常准确。理解这一点对于正确处理带分数的相反数运算至关重要。\n我们刚刚学习了如何求不同数的相反数，例如+5的相反数是-5，-7的相反数是7，-3 1/2的相反数是3 1/2，11.2的相反数是-11.2。那么，小数和整数的相反数转换规律是否一致？为什么？\n非常好，大家通过比较分析发现，无论是整数还是小数，它们的相反数转换都遵循相同的符号变化规律，这充分体现了数学规律的普适性。接下来，谁能举例说明一个数的相反数在实际生活中的应用场景？\n我们看到-(-4)=4而-(+5.5)=-5.5，为什么负号在不同情况下会产生不同的结果？能解释其中的规律吗？\n你注意到了符号变化的模式，这很好。让我们更深入地看看这个规律背后的数学原理：当我们对一个数添加“-”号时，实际上是求它的相反数，而添加“+”号则保持原数不变，这是由相反数的定义决定的，即一个数与它的相反数相加等于零。\n我们刚刚看到+(-4)=-4和+(+12)=12的例子，有同学认为正号不会改变数值，这是普遍规律吗？其他人有不同见解吗？\n同学B注意到负号会改变数的符号，这个理解非常到位。让我们再来看一个例子：-(-8)等于多少？\n同学们，我们来看教材中的这四个化简例子：(1) -(+10) = -10；(2) +(-0.15) = -0.15；(3) +(+3) = 3；(4) -(-20) = 20。请大家仔细观察这些化简结果，思考一下：括号内外的符号变化有什么规律？\n小张在化简第(4)题时正确地得到了20的结果，这个步骤很规范，因为根据数学规则，两个负号相遇会相互抵消变成正数，这正是“负负得正”的体现。\n同学们，我们来看第一个例子-(+10)=-10，现在请大家思考一下：为什么+10外面的负号会让结果变成-10？能解释你为何这样想吗？\n小王的解释很好，他理解到正号可以省略，所以-(+10)等同于-10，这体现了数学符号的简洁性。同样地，在化简+(-0.15)时，正号与负号结合直接得到-0.15，而+(+3)中正号可以省略简化为3，-(-20)则通过负负得正得到20，这些都是符号化简的基本规则。\n针对+(-0.15)的化简，有人认为可以直接去掉正号，有人觉得需要保留，其他人有不同看法吗？\n现在我们来看例2的化简过程：(1) -(+10) = -10，这里正号遇到负号，异号得负；(2) +(-0.15) = -0.15，正号遇到负号，异号得负；(3) +(+3) = 3，两个正号同号得正；(4) -(-20) = 20，两个负号同号得正。这些化简都体现了符号运算的核心规律——同号得正，异号得负，这正是我们下节课要深入学习的相反数性质。\n同学们，刚才我们通过数轴上的例子了解到，+5的绝对值是5，记作|+5|=5，-6的绝对值是6，记作|-6|=6。现在请大家思考一个问题：为什么+5和-6的绝对值都是正数？这与它们在数轴上的位置有什么关系？\n同学们刚才的回答非常好，特别是注意到绝对值表示的是距离，而距离是没有负值的。正如同学C所说，无论数在数轴的原点左侧还是右侧，它们的绝对值都是非负的。这个观察非常准确，帮助我们更好地理解绝对值的本质。\n同学们，刚才我们学习了绝对值的概念，知道了一个数在数轴上对应的点到原点的距离就是这个数的绝对值。现在请大家思考一下：如果a是一个正数，|a|等于什么？如果a是负数呢？0的绝对值又是什么？请尝试用自己的话解释这些规律。\n同学D的总结非常到位，用“正数绝对值是自己，负数绝对值是相反数”准确概括了绝对值的性质，尤其是补充了“0到原点的距离是0”这一特例，展现了数学思维的严密性。这种简洁清晰的表达方式值得大家学习。\n同学们，我们已经学习了绝对值的概念，知道它表示数轴上某点到原点的距离。那么，为什么绝对值在现实生活中很重要呢？比如导航中的距离计算、温差比较等场景。你们能结合自己的生活经验，举例说明绝对值的应用价值吗？\n同学E提到的海拔高度比较案例很好，因为它展示了绝对值如何帮助我们忽略方向差异，专注比较量的大小。这正是绝对值在科学测量中的核心作用。\n同学们，我们已经知道-5和5在数轴上的位置不同，但它们的绝对值都是5。那么，为什么位置不同的两个数会有相同的绝对值呢？\n“绝对值表示的是数轴上点到原点的距离，因此距离总是非负的。小李注意到绝对值表示距离，这个观察很准确，因为距离没有方向性。那么，谁能举例说明一个负数的绝对值为什么等于它的相反数？”\n绝对值在实际生活中有很多应用，比如温度计上的读数，无论是零上5度还是零下5度，它们与0度的距离都是5，这个距离就是它们的绝对值。同样，海拔高度也是如此，无论你是在海平面以上100米还是以下100米，你与海平面的垂直距离都是100米，这个距离也是绝对值。绝对值就像测量你离家的距离，无论你向东走还是向西走，你离家的距离都是正数，因为它只关心距离的大小，而不关心方向。\n为什么负数的绝对值要用它的相反数表示？这与数轴上的距离有什么关系？\n“小李提到绝对值可以理解为数轴上点到原点的距离，这个观点非常准确，它帮助我们直观地把握绝对值的几何意义。接下来，谁能举例说明一个负数的绝对值如何体现在数轴上？”\n根据绝对值的定义，我们知道任何有理数的绝对值总是非负数，即|a|≥0。谁能举例说明一个数的绝对值不可能是负数？这在实际生活中有何体现？\n同学们，观察例题中-15/2和+15/2的绝对值结果，为什么它们的绝对值相同？这反映了绝对值的什么本质特征？\n小李提到“距离没有方向”这个观点很准确，因为绝对值表示的是数到原点的距离，与方向无关，这正是它的几何意义。绝对值的结果永远是非负数，因为它只关心距离的大小，而不考虑数在数轴上的左右位置。\n除了数轴上的距离，谁能用其他方式解释绝对值的含义？比如温度计或债务的例子？\n小张用\"债务金额不考虑欠谁只算多少\"来类比绝对值的概念非常贴切，这确实帮助我们直观地理解了绝对值就是去掉数的符号，只保留它的大小。就像-15/2和15/2虽然符号相反，但它们的绝对值都是15/2，说明绝对值与数的正负无关，只反映数在数轴上与原点的距离。\n
    """
    # print(await run_ds_prompt_feedback_teaching(student, "老师刚才的讲解非常清晰，我理解了负数的概念和应用，谢谢老师！"))
    
    # 选择做题方式:
    # 方式1:原始的逐题处理(较慢但稳定)
    # 方式2:批量异步处理(更快但需要更多内存)
    
    """use_enhanced_version = True  # 设置为 True 使用增强版异步处理
    
    if use_enhanced_version:
        # 使用增强版异步处理
        from student.async_exercise import enhanced_exercise_with_progress
        try:
            answers = await enhanced_exercise_with_progress(student, answers_file, batch_size=5)
        except Exception as e:
            print(f"增强版处理失败,回退到原始方法: {e}")
            use_enhanced_version = False
    
    if not use_enhanced_version:
        # 使用原始的异步处理
        import time
        start_time = time.time()
        print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")
        
        try:
            # 异步执行做题
            answers = await exercise(student, answers_file)
            
            # 计算耗时
            end_time = time.time()
            duration = end_time - start_time
            print(f"完成时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}")
            print(f"总耗时: {duration:.2f} 秒 ({duration/60:.2f} 分钟)")
            
            # 显示最终结果
            total_questions = len(answers)
            correct_answers = sum(1 for answer in answers.values() if answer.get('correct', False))
            accuracy_rate = (correct_answers / total_questions) * 100 if total_questions > 0 else 0
            
            print(f"\n=== 做题结果总结 ===")
            print(f"学生: {student.name}")
            print(f"总题目数: {total_questions}")
            print(f"答对题数: {correct_answers}")
            print(f"正确率: {accuracy_rate:.2f}%")
            print(f"平均每题耗时: {duration/total_questions:.2f} 秒")
            
            # 将答案保存到json文件
            save_exercise_results(student, answers, 150.1)
            
        except Exception as e:
            print(f"做题过程中出现错误: {e}")
            import traceback
            traceback.print_exc()"""


    # 对做题过程进行反馈,然后根据反馈更新自己。
    feedback = """
总体反馈:优秀的表现!

你在解决这些数学问题时展现了扎实的基础知识、严谨的逻辑思维和细致的验证习惯,值得充分肯定!以下是对你整体表现的总结:

优点:
1. 概念理解清晰
   - 你能准确区分正数、负数和零,并理解它们在具体问题中的含义(如盈利、亏损、基准身高等)。
   - 对百分数、分数和小数的转换处理得当(如2.5%=0.025,-13/3≈-4.333)。

2. 逻辑推理严密
   - 你采用了逐步分析的方法,逐个检查选项或数值,确保不遗漏任何细节。
   - 在"0的性质"问题中,你通过排除法(①③正确,②④错误)得出了正确答案,体现了批判性思维。

3. 验证意识强
   - 你多次使用数轴辅助理解(如盈利/亏损、正负数的分布),这能帮助直观验证答案。
   - 在计算实际身高时,你反复检查计算过程,避免粗心错误。

4. 表达清晰
   - 你的思考过程条理分明,能清晰地解释每一步的推理依据(如"-1.2小于0,是第三个负数")。

可进一步提升的地方:
1. 语言简洁性
   - 部分解释可以更精简(如问题1中"0不是正数也不是负数"只需提一次)。
   - 答案部分可直接列出关键点(如"负数:-4, -13/3, -1.2")。

2. 符号书写规范
   - 注意数学符号的规范性(如"-13/3"应写作-13/3,保持分数形式)。

3. 拓展思考
   - 在类似"基准身高"的问题中,可以进一步思考:"如果某人身高记为-0.10米,实际是多少?"以巩固概念。

总结:
你的解题能力已经非常出色,尤其在概念应用和逻辑推理方面表现突出。继续保持细致和验证的习惯,同时尝试简化表达,你的数学思维会更加高效和精准!如果遇到更复杂的问题(如混合运算或实际应用题),可以进一步练习如何快速提取关键信息。

再接再厉,你做得很好! 🚀
"""

    #adjust(student, feedback)
    
    # 评估学生的表现
    # await evaluate(student, "student/认知风格量表.json", 5)
    # await evaluate_bfi(student, "student/大五人格量表.json", "bfi_2")
    
    

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
    # main()
