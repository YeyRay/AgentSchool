import sys
sys.path.append("../../")


from student.cognitive_module.student import *
from student.cognitive_module.scratch import *
from student.cognitive_module.memory import *
from student.prompt.run_ds_prompt import *
from util.BroadcastSys import *
from util.Recorder import *
from student.retrieve import *
from util.BroadcastMessage import *

# TODO: 现在有个问题在于，老师发出指令和发出对话是否是同时的。
# 1.
# 如果是分开的，则先发出指令，我在感知阶段会将其放入event事件，并且也会在chat_with中添加"teacher"。
# 但是这一阶段应该还回不了话。因为老师没有发出问题。所以此轮到execute应该什么都不干，即使我们现在`chat_with`中有"teacher"。
# 但此处chat_buffer应该为空（所以我们回话的时机应该是判断对话缓冲区中是否有对话，而非chat_with是否有对象）
# 然后在下一轮，老师发出问题，我在感知阶段会将其放入chat_buffer中。
# 此时chat_with中已经有"teacher"了，然后再chat_buffer中有内容时，我就可以回话了。
# 2.
# 如果是同时的，则老师发出指令和问题，我在感知阶段会将其放入event事件和chat_buffer中。
# 此时chat_with中已经有"teacher"了，然后再chat_buffer中有内容时，我就可以回话了

# 所以其实没关系，因为我的move函数是遍历当前所有信息。
# 只要chat_buffer中有内容，我就可以回话了。
async def execute(student, object, retrieved=None, info=None):
    """
    根据学生当前的对象列表，来判断到底要做什么
    有三种可能：
    1. None
    2. ["teacher"]
    3. ["group_member1", "group_member2", ...]
    INPUT:
        student: Student类
        object: list of str, 当前的对象列表
    OUTPUT:
        None
    """
    if object is None:
        # 如果对象列表为空，则不需要做任何事情
        return None
    
    if student.scratch.chat_buffer is None:
        # 如果chat_buffer为空，则不需要做任何事情
        return None
    
    print(f"{student.name}在执行阶段")

    if object == ["teacher"]:
        # 此时我们需要从chat_buffer中获取老师的问题，并进行回答
        # chat_buffer里面现在可能有老师的问题、自己的回答。
        # 我们检索最后一条，如果是老师的问题，则回答，或者不回答
        # 但如果是自己的回答，则判断自己是否还要继续回答。（这种情况说明这一轮老师啥都没说）
        # 如果是其他人的回答，暂时处理成直接结束（不回答）
        last_chat = student.scratch.chat_buffer[-1]
        # 首先我们把当前对话历史全部拿到

        if last_chat.s == student.teacher_name:
            # 如果最后一条是老师的问题，则回答
            # 首先检索相关记忆
            print(f"{student.name} 收到老师的问题: {last_chat.content}")
            relevant_mem = await further_retrieve(student, [last_chat.content])
            mems = [i.embedding_key for i in relevant_mem[last_chat.content]]
            mems_str = "\n".join(mems)
            response = await run_ds_prompt_answer_question(student, object, last_chat.content, mems_str)

            msg = BroadcastMessage(
                current_time=student.scratch.current_time,
                message_type = MessageType.CLASS,
                active_event = "answer",
                speaker = student.name,
                content = response
            )
            """content = {"message_type": "class",
                       "active_event": "response_question",
                       "speaker": student.name,
                       "content": response,
                       "current_time": student.scratch.current_time}"""

            student.broadcast_sys.publish_sync("teacher", msg)
            print(f"{student.name} 回答: {response}")
            # 假设只回答一轮，因此清空
            student.scratch.chat_buffer.clear()
            student.scratch.chat_with.clear()
    elif info.get("active_event") == "group_discussion_start" or info.get("active_event") == "group_discussion" and info.get("receiver") == student.name:
        # 如果对象列表中有其他人，则进行小组讨论
        # 根据当前对话框中的内容，进行小组讨论
        
        print(f"{student.name} 进行小组讨论")
        last_chat = student.scratch.chat_buffer[-1]
        try:
                relevant_mem = await further_retrieve(student, [last_chat.content])
                
                if relevant_mem and last_chat.content in relevant_mem:
                    mems = [i.embedding_key for i in relevant_mem[last_chat.content]]
                    mems_str = "\n".join(mems) if mems else ""
                else:
                    mems_str = ""
                    
        except Exception as e:
            print(f"{student.name}检索记忆时出错: {e}")
            mems_str = ""
        discussion_content = format_chat_buffer(student.scratch.chat_buffer)

        try:
            response = await run_ds_prompt_group_discussion(student, discussion_content, mems_str, object, isLeader=student.scratch.isLeader)
        except json.JSONDecodeError as e:
            response = ""
        except Exception as e:
            print(f"{student.name}运行小组讨论提示时出错: {e}")
            response = ""

        s = student.name if student.name else "unknown"
        p = "talks with"
        # o = f"students in group {student.scratch.group}"
        o = object[0] if object[0] else "unknown"
        
        keys = await run_ds_prompt_chat_keywords(response)
        # 将字符串拆分为关键词列表
        if isinstance(keys, str):
            keys_list = [key.strip() for key in keys.split(',') if key.strip()]
        else:
            keys_list = keys if isinstance(keys, list) else [keys]
        keywords = ["group_discussion", s, p, o] + keys_list # 关键词是事件类型、发送者、动词、涉及的学生和总结的关键词
        embedding_pair = (response, await get_local_embedding(response))
        importance = int(await run_ds_prompt_importance_chat(student, response))
        student.scratch.accumulate_importance(importance)
        node = student.mem.add_chat(student.scratch.current_time, response, keywords, importance, embedding_pair, s = s, p = p, o = o)
        student.scratch.chat_buffer.append(node)
        student.scratch.chat_with.append(s)  # 添加发送者到聊天列表

        msg = BroadcastMessage(
            current_time=student.scratch.current_time,
            message_type = MessageType.CLASS,
            active_event = "group_discussion",
            speaker = student.name,  
            content = response
        )
        student.broadcast_sys.publish_sync(object[0], msg)
        # student.broadcast_sys.publish("teacher", msg)

        msg2 = BroadcastMessage(
            current_time=student.scratch.current_time,
            message_type = MessageType.CLASS,
            active_event = "group_discussion_content",
            speaker = student.name,  
            content = response
        )
        group = "group" + str(student.scratch.group)
        student.broadcast_sys.publish_sync(group, msg2)
        print(f"{student.name} 进行了小组讨论: {response}")
        