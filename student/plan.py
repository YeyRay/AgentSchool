import sys
sys.path.append("../../")

from student.cognitive_module.memory import *
from student.cognitive_module.scratch import *
from student.cognitive_module.student import *
from student.prompt.run_ds_prompt import *


def plan(student, students, perceived_node, event_type=None, receiver=None):
    """
    根据学生的记忆和当前感知的信息，生成计划。
    INPUT:
        student: Student类
        students: list of string, 学生的名字列表
        perceived_node: ConceptNode类
        event_type: str, 当前事件的类型（如"ask_question", "group_discussion_start"等）
        receiver: str, 接收者的名字（默认为None）
    OUTPUT:
        objects: list of str, 生成的计划对象列表
    """

    if perceived_node is None:
        print("未感知到任何信息，无法生成计划。")
        return None

    print(f"{student.name}在生成计划")
    
    # 根据感知信息的类型，判断当前要干什么
    """if perceived_node.type == "knowledge" or perceived_node.type == "chat":
        return student.scratch.chat_with  # 知识、对话类型的感知信息不需要生成计划
    elif perceived_node.type == "event":
        # 检索当前记忆中最新的事件
        # 此时相当于我们还没开始处理当前事件
        current_event = student.mem.seq_event[0]
        # event_type = run_ds_prompt_event_type(current_event)
        if event_type == "ask_question":
            # 如果是师生问答
            # TODO: 我要接受老师的信息。
            # 等待老师将问题发送给我，即老师说的话要存储在student.scratch.chat_req中。
            # 我的student.scratch.chat_req中，每个元素都是一个(time, object, content)的三元组。
            # 我要取出time >= student.scratch.current_time and object == "teacher"的元素。
            # 将其放进student.scratch.chat_buffer中。
            # 保留以上想法
            # 此处实现是，我们当前perceived_node中的content即为老师的提问
            student.scratch.chat_with.append("teacher")
            return ["teacher"]
        elif event_type == "group_discussion_start":
            # 如果是小组讨论
            # 遍历学生列表，找到同组的组员返回
            objects = []
            for s in students:
                if s.scratch.group == student.scratch.group and s != student:
                    student.scratch.chat_with.append(s.scratch.name)
                    objects.append(s.scratch.name)
            return objects"""
    if event_type == "group_discussion_start" or event_type == "group_discussion" and receiver == student.name:
        # 如果是小组讨论
        # 随机决定一个讨论的对象
        
        available_students = students.copy()

        # 排除自己
        if student.name in available_students:
            available_students.remove(student.name)
        
        print(f"原始学生列表: {students}")
        print(f"当前学生: {student.name}")
        print(f"可用的讨论对象: {available_students}")

        # 随机选一个讨论对象
        if available_students:  # 确保列表不为空
            discussion_target = random.choice(available_students)
        else:
            discussion_target = None  # 没有其他学生

        
        objects = []
        """for s in students:
            if s.scratch.group == student.scratch.group and s != student:
                student.scratch.chat_with.append(s.scratch.name)
                objects.append(s.scratch.name)"""
        objects = [discussion_target]
        print(f"{student.name} 进行小组讨论，组员: {objects}")
        return objects
    elif event_type == "group_discussion_end":
        # 如果是小组讨论结束
        # 清空学生的聊天记录
        student.scratch.chat_with.clear()
        student.scratch.chat_buffer.clear()
        return []
    elif event_type == "ask_question":
        # 如果是师生问答
        student.scratch.chat_with.append("teacher")
        return ["teacher"]
    return None