import json
import demjson3
import sys
sys.path.append("../../")
import re

from student.cognitive_module.memory import *
from student.knowledge_graph import kg
from student.cognitive_module.scratch import *
from student.cognitive_module.student import *
from student.prompt.run_ds_prompt import *
from student.retrieve import *
from util.BroadcastMessage import *
from util.BroadcastSys import *            


def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks from LLM outputs."""
    try:
        return re.sub(r"(?is)<think>.*?</think>", "", text)
    except Exception:
        return text

def _parse_int_0_10(text: str, default: int = 1) -> int:
    """Parse first integer 0..10 from messy text (after stripping <think> blocks)."""
    try:
        cleaned = _strip_think(str(text)).strip()
        m = re.search(r"(?:^|\D)(10|[0-9])(?:\D|$)", cleaned)
        return int(m.group(1)) if m else default
    except Exception:
        return default

def safe_json_decode(json_str, fallback=None):
    """
    安全的JSON解析函数，使用demjson3提供更好的容错性
    """
    if not json_str or json_str.strip() == "":
        print(f"WARNING: 尝试解析空字符串")
        return fallback
    
    # 清理字符串，移除markdown代码块标记和多余的空白
    cleaned_str = json_str.strip()
    
    # 移除markdown代码块标记
    if cleaned_str.startswith('```json'):
        cleaned_str = cleaned_str[7:]  # 移除 ```json
    elif cleaned_str.startswith('```'):
        cleaned_str = cleaned_str[3:]   # 移除 ```
        
    if cleaned_str.endswith('```'):
        cleaned_str = cleaned_str[:-3]  # 移除结尾的 ```
        
    cleaned_str = cleaned_str.strip()
    
    # 替换中文标点符号为英文标点符号
    cleaned_str = cleaned_str.replace('"', '"').replace('"', '"')  # 中文双引号
    cleaned_str = cleaned_str.replace(''', "'").replace(''', "'")  # 中文单引号
    cleaned_str = cleaned_str.replace('，', ',')  # 中文逗号
    cleaned_str = cleaned_str.replace('：', ':')  # 中文冒号
    
    # 如果清理后是空字符串，返回fallback
    if not cleaned_str:
        print(f"WARNING: 清理后得到空字符串")
        return fallback
    
    try:
        # 首先尝试使用标准json
        return json.loads(cleaned_str)
    except json.JSONDecodeError:
        try:
            # 如果标准json失败，使用demjson3
            print(f"WARNING: 标准JSON解析失败，尝试使用demjson3")
            return demjson3.decode(cleaned_str)
        except Exception as e:
            print(f"ERROR: demjson3解析也失败: {e}")
            print(f"原始字符串: '{json_str}'")
            print(f"清理后字符串: '{cleaned_str}'")
            return fallback


async def perceive(student, information, sender=None, receiver=None, current_time = None, info_type = None):
    """
    感知环境，接收信息。
    根据学生的压力和注意力吸收部分信息，并让学生对信息进行思考。
    并最后处理成ConceptNode类，放入记忆。
    我们此处先假设它每次接受只会接受到一个人发出的一个信息
    （但实际情况是可能有多个人发的消息，因为小组讨论）
    INPUT:
        Student: 学生类
        information: string, 信息内容
        sender: string, 发送者的名字
        receiver: string, 接收者的名字（默认为None）
        current_time: datetime, 当前时间
        info_type: string, 事件类型（可选，默认为None）
    OUTPUT:
        node: ConceptNode类的实例
        absorbed: string, 学生吸收的信息内容
        learned: string, 学生学到的知识内容
    """
        # 如果是knowledge，info如
        # {"message_type": "class",
        #  "active_event": "lecture",
        #  "speaker": self.name,
        #  "content": self.sections[self.current_section_turn]}
        # 如果是event，info如
        # 问答：
        #   "message_type": "class",
        #    "active_event": "ask_question",
        #    "speaker": self.name,
        #    "content": self.q_a[0]
        # 小组讨论：
        #（开始）
        #    "message_type": "class",
        #    "active_event": "group_discussion_start",
        #    "speaker": self.name,
        #    "content": f"请进行小组讨论，讨论内容为：{point}"
        #（结束）
        #    "message_type": "class",
        #    "active_event": "group_discussion_end",
        #    "speaker": self.name,
        #    "content": "小组讨论结束。"

    if information is None or information == "":
        return None, None, None

    # 先判断当前消息是什么类型的消息：event/chat/knowledge
    # info_type = run_ds_prompt_judge_type(information)
    print(f"{student.name}在感知信息：{information}（事件类型为{info_type}）")
    # print(f"信息类型: {info_type}")
    # 我们现在不要LLM判断事件类型，而是通过传入的消息来判断
    # print(f"信息内容: {information}")
    node = None
    absorbed_info = None
    learned = None
    # 1. 如果是event类型，则需要判断event的类型，并且总结此event的主题作为关键词
    # 因为教师端那边对event的定义好像不是很明确，因为他有可能直接发过来一个问题。
    # 所以我需要用它给的参数来判断事件类型
    if info_type == "event":
        event_summary = await run_ds_prompt_summarize_event(information)
        json_event = safe_json_decode(_strip_think(event_summary), {})
        if not json_event:
            print(f"ERROR: 无法解析事件总结，跳过处理")
            return None, None, None
        content = json_event.get("content", "")
        event_type = json_event.get("event_type", "unknown")
        theme = json_event.get("keywords", [])
        if isinstance(theme, str):
            theme = [theme]
        keywords = [event_type] + theme
        importance_text = await run_ds_prompt_importance_event(student, content)
        importance = _parse_int_0_10(importance_text)
        student.scratch.accumulate_importance(importance)
        embedding_pair = (content, await get_local_embedding(content))
        node = student.mem.add_event(student.scratch.current_time, content, keywords, importance, 
                              embedding_pair, event_type, theme)
        # --- 知识图谱：被动学习 ---
        """if theme:
            kg.batch_passive_learn(
                student.name,
                [t for t in theme if isinstance(t, str) and t.strip()],
                base_strength=0.03,
                config_kg=student.knowledge_points_of_the_grade,
                importance=importance
            )"""
    elif info_type == "chat":
        # TODO:
        # 2. 如果是chat类型，则直接使用信息内容作为关键词
        # 并且要存储
        # student.scratch.chat_buffer.append(0, (current_time, sender, information))
        absorb_rate = student.scratch.attention_level * (1 - student.scratch.stress)
        absorbed_info = await run_ds_prompt_absorb_info(student, information, absorb_rate)
        content = absorbed_info
        s = sender if sender else "unknown"
        p = "chat with"
        # 宾语要根据当前事件类型来决定，
        o = student.name
        current_time = current_time if current_time else student.scratch.current_time
        importance_text = await run_ds_prompt_importance_chat(student, absorbed_info)
        importance = _parse_int_0_10(importance_text)
        student.scratch.accumulate_importance(importance)
        keywords = [s, p, o]  # 关键词是发送者、动词和学生名字
        embedding_pair = (absorbed_info, await get_local_embedding(absorbed_info))
        node = student.mem.add_chat(current_time, content, keywords, importance, embedding_pair, s = s, p = p, o = o)
        # --- 知识图谱：把聊天参与者与关键词视为轻度概念标签（可选过滤长度）---
        # candidate_concepts = [k for k in keywords if len(k) <= 20]
        # if candidate_concepts:
            # kg.batch_passive_learn(student.name, candidate_concepts, base_strength=0.01, importance=importance)
        student.scratch.chat_buffer.append(node)
        student.scratch.chat_with.append(s)
    # elif info_type == "knowledge":
    elif info_type == "lecture":
        # 3. 如果是knowledge类型，则让学生在自己吸收的信息中，和当前的信息结合，
        # 总结出其当前学到的知识点，存入知识记忆中
        # 根据学生的压力和注意力吸收部分信息
        attention_level = student.scratch.attention_level
        stress_level = student.scratch.stress
        if attention_level > 0.7 and stress_level < 0.3:
            absorption_desc = "你听得非常认真，几乎抓住了老师讲的所有关键细节。"
        elif attention_level < 0.3 or stress_level > 0.7:
            absorption_desc = "你有些分心和紧张，可能错过了很多细节，只抓到了一些零散的概念和关键词。"
        else:
            absorption_desc = "你基本跟上了老师的节奏，但可能对一些复杂的点理解得不深。"

        # 检索相关记忆的认知。融入当前学习中。
        # 注意：further_retrieve需要的是字符串列表，所以要将information包装成列表
        retrieved_mem = await further_retrieve(
            student, [information], n_count=3
        )


        knowledge_understanding_str = await run_ds_prompt_generate_understanding(
            student, information, absorption_desc, student.knowledge_points_of_the_grade, retrieved_mem
        )

        json_understanding = safe_json_decode(_strip_think(knowledge_understanding_str), {})
        if not json_understanding:
            print(f"ERROR: 无法解析学生理解，跳过处理")
            return

        content = json_understanding.get("understanding_content", "") # 这是学生认为自己学到的东西
        learned = content
        # misconceptions = json_understanding.get("misconceptions", []) # 【新】学生理解错的地方
        # lingering_questions = json_understanding.get("lingering_questions", []) # 【新】学生还存在的疑问
        knowledge_tag = json_understanding.get("knowledge_tag", [])
        importance = json_understanding.get("importance", 1)

        # 产生错误理解/迷思
        misconceptions = await run_ds_prompt_generate_misconceptions(
            student, learned 
        )


        # 存储核心知识（学生的理解版本）
        if content:
            student.scratch.accumulate_importance(importance)
            keywords = knowledge_tag
            embedding_pair = (content, await get_local_embedding(content))
            node = student.mem.add_knowledge(student.scratch.current_time, content, keywords, importance, embedding_pair, knowledge_tag, misconceptions=misconceptions)
            # --- 知识图谱：讲授知识直接增强对应标签 ---
            if knowledge_tag:
                kp_ids = kg.get_batch_id_by_names(knowledge_tag, student.knowledge_points_of_the_grade)
                kg.batch_passive_learn(
                    student.name,
                    kp_ids,
                    base_strength=0.05,
                    config_kg=student.knowledge_points_of_the_grade,
                    misconceptions=misconceptions,
                    importance=importance
                )
            print(f"{student.name}的理解: {content}")
        
        # 将错误认知和疑问也作为一种特殊的记忆存储起来
        # if misconceptions:
            # print(f"{student.name}的错误认知: {misconceptions}")
            # student.mem.add_thought(..., f"我对'{knowledge_tag}'的理解可能错了，我认为是'{misconceptions}'", ...)
        # if lingering_questions:
            # print(f"{student.name}的疑问: {lingering_questions}")
        """absorb_rate = student.scratch.attention_level * (1 - student.scratch.stress)
        absorbed_info = await run_ds_prompt_absorb_info(student, information, absorb_rate)
        # 存储这个记忆
        importance_text = await run_ds_prompt_importance_thought(student, absorbed_info)
        importance = _parse_int_0_10(importance_text)
        student.scratch.accumulate_importance(importance)
        keywords = await run_ds_prompt_thought_keywords(absorbed_info)
        embedding_pair = (absorbed_info, await get_local_embedding(absorbed_info))
        student.mem.add_thought(student.scratch.current_time, absorbed_info, keywords, importance,
                                embedding_pair)
        # 输出此学生吸收的信息
        print(f"{student.name}吸收的信息: {absorbed_info}")

        # 模拟学习这个知识
        # 我此处认为他一次只会总结出一个知识点（不知道大模型是否会总结出多个知识点）
        knowledge_summary_str = await run_ds_prompt_summarize_knowledge(student, absorbed_info, information)
        # print(f"DEBUG: Raw output from run_ds_prompt_summarize_knowledge: '{knowledge_summary_str}'") # 打印原始输出
        
        json_knowledge = safe_json_decode(knowledge_summary_str, {})
        if not json_knowledge:
            print(f"ERROR: 无法解析知识总结，跳过处理")
            return None, None, None

        content = json_knowledge.get("content", "")
        learned = content
        knowledge_tag = json_knowledge.get("knowledge_tag", [])
        importance = json_knowledge.get("importance", 1)
        if isinstance(importance, str):
            try:
                importance = int(importance)
            except ValueError:
                importance = 1
        student.scratch.accumulate_importance(importance)
        keywords = knowledge_tag
        embedding_pair = (content, await get_local_embedding(content))
        node = student.mem.add_knowledge(student.scratch.current_time, content, keywords, importance, embedding_pair, knowledge_tag)
        # 输出此学生学到的知识
        print(f"{student.name}学到的知识: {content}")"""
    elif info_type == "ask_question":
        # 4. 如果是ask_question类型，则需要将问题存入学生的scratch中
        # 这个首先属于event，同时也属于chat
        event_summary = await run_ds_prompt_summarize_event(information)
        json_event = safe_json_decode(_strip_think(event_summary), {})
        if not json_event:
            print(f"ERROR: 无法解析问题事件总结，跳过处理")
            return None, None, None
            
        event_content = json_event.get("content", "")
        # print(f"事件内容: {event_content}")
        # event_type = json_event["event_type"]
        event_theme = json_event.get("keywords", [])
        if isinstance(event_theme, str):
            event_theme = [event_theme]
        event_content = f"{sender}询问{student.name}关于{event_theme}的问题"
        print(f"事件内容: {event_content}")
        
        importance_text = await run_ds_prompt_importance_event(student, event_content)
        importance = _parse_int_0_10(importance_text)
        student.scratch.accumulate_importance(importance)
        embedding_pair = (event_content, await get_local_embedding(event_content))
        s = sender if sender else "unknown"
        p = "asks"
        o = student.name
        keywords = ["ask_question"] + event_theme + [s, p, o]  # 关键词是事件类型、主题、发送者、动词和学生名字
        node = student.mem.add_event(student.scratch.current_time, event_content, keywords, importance, 
                              embedding_pair, info_type, event_theme, s=s, p=p, o=o)
        # --- 知识图谱：问题主题概念轻度强化 ---
        """if event_theme:
            kg.batch_passive_learn(
                student.name,
                [t for t in event_theme if isinstance(t, str) and t.strip()],
                base_strength=0.02,
                config_kg=student.knowledge_points_of_the_grade,
                importance=importance
            )"""
        
        # 然后存入chat
        absorb_rate = student.scratch.attention_level * (1 - student.scratch.stress)
        absorbed_info = await run_ds_prompt_absorb_info(student, information, absorb_rate)
        # chat_content = absorbed_info
        chat_content = information
        print(f"询问的内容：{chat_content}")
        current_time = current_time if current_time else student.scratch.current_time
        importance_text = await run_ds_prompt_importance_chat(student, absorbed_info)
        importance = _parse_int_0_10(importance_text)
        student.scratch.accumulate_importance(importance)
        # 提取这段内容涉及的知识点
        knowledge_tags = await run_ds_prompt_extract_knowledge_tag(absorbed_info, student.knowledge_points_of_the_grade)
        # 确保knowledge_tags是列表
        if not isinstance(knowledge_tags, list):
            knowledge_tags = []
        keywords = knowledge_tags + [s, p, o]  # 关键词是知识点、发送者、动词和学生名字
        embedding_pair = (absorbed_info, await get_local_embedding(absorbed_info))
        node = student.mem.add_chat(current_time, chat_content, keywords, importance, embedding_pair, s = s, p = p, o = o, knowledge_tag=knowledge_tags)
        if knowledge_tags:
            kp_ids = kg.get_batch_id_by_names(knowledge_tags, student.knowledge_points_of_the_grade)
            kg.batch_passive_learn(
                student.name,
                kp_ids,
                base_strength=0.025,
                config_kg=student.knowledge_points_of_the_grade,
                importance=importance
            )
        # 将当前的chat信息存入学生的scratch中
        student.scratch.chat_buffer.append(node)
        student.scratch.chat_with.append(s)  # 添加发送者到聊天列表
    elif info_type == "group_discussion_start" or info_type == "group_discussion" and receiver == student.name:
        # 小组讨论，并且只有对象为自己时才接收
        # 当前默按顺序发言

        # 如果是开始，更新小组
        if info_type == "group_discussion_start":
            student.update_group(student.scratch.group)

        # 如果当前学生的信息列表中存在"group_discussion_end""类型的信息，直接忽略此次信息
        if any(student.infos[i].get("active_event") == "group_discussion_end" for i in range(len(student.infos))):
            print(f"{student.name}忽略小组讨论信息，因为已经有小组讨论结束信息。")
            return None, None, None

        # 要把当前发言的内容都加入scratch的缓冲区中
        s = sender if sender else "unknown"
        p = "talks with"
        # o = f"students in group {student.scratch.group}"
        o = receiver if receiver else "unknown"
        
        keys = await run_ds_prompt_chat_keywords(information)
        # 将字符串拆分为关键词列表
        if isinstance(keys, str):
            keys_list = [key.strip() for key in keys.split(',') if key.strip()]
        else:
            keys_list = keys if isinstance(keys, list) else [keys]
        keywords = ["group_discussion", s, p, o] + keys_list # 关键词是事件类型、发送者、动词、涉及的学生和总结的关键词
        embedding_pair = (information, await get_local_embedding(information))
        importance_text = await run_ds_prompt_importance_chat(student, information)
        importance = _parse_int_0_10(importance_text)
        student.scratch.accumulate_importance(importance)
        node = student.mem.add_chat(student.scratch.current_time, information, keywords, importance, embedding_pair, s = s, p = p, o = o)
        # --- 知识图谱：讨论关键词轻度强化 ---
        # discussion_concepts = [k for k in keys_list if isinstance(k, str)]
        # if discussion_concepts:
            # kg.batch_passive_learn(student.name, discussion_concepts, base_strength=0.015, importance=importance)
        student.scratch.chat_buffer.append(node)
        student.scratch.chat_with.append(s)  # 添加发送者到聊天列表

        # 输出小组讨论的内容
        print(f"当前小组讨论历史：{format_chat_buffer(student.scratch.chat_buffer)}")
    elif info_type == "group_discussion_end":
        # 小组讨论结束
        if student.scratch.isLeader:
            chats = format_chat_buffer(student.scratch.chat_buffer)
            results = await prompt_summarize_group_discussion(student, chats)
            group = "group" + str(student.get_group())
            msg = BroadcastMessage(
                current_time=student.scratch.current_time,
                message_type = MessageType.CLASS,
                active_event = "group_discussion",
                speaker = group,  
                content = results
            )
            student.broadcast_sys.publish_sync("teacher", msg)
            print(f"小组讨论结果: {chats}")
            print(f"{student.name}小组讨论结束，组长总结: {results}")
            student.scratch.isLeader = False  # 结束后不再是组长

        student.scratch.chat_buffer.clear()  # 清空小组讨论的聊天缓冲区
        student.scratch.chat_with.clear()  # 清空小组讨论的聊天列表
        
        
        """elif info_type == "feedback":
            # 老师提问的反馈
            # 1. 生成thought
            absorb_rate = student.scratch.attention_level * (1 - student.scratch.stress)
            absorbed_info = run_ds_prompt_absorb_info(student, information, absorb_rate)
            # 存储这个记忆
            importance = int(run_ds_prompt_importance_thought(student, absorbed_info))
            student.scratch.accumulate_importance(importance)
            keywords = run_ds_prompt_thought_keywords(absorbed_info)
            embedding_pair = (absorbed_info, get_local_embedding(absorbed_info))
            student.mem.add_thought(student.scratch.current_time, absorbed_info, keywords, importance,
                                    embedding_pair)"""
        # 2. 改变学生的scratch状态
    elif info_type == "group_discussion_content":
        # 如果sender和当前学生相同，则跳过处理此信息
        if sender == student.name:
            return None, None, None

        # 如果当前学生的信息列表中存在相同的信息，则跳过
        if any(student.scratch.chat_buffer[i].content == information for i in range(len(student.scratch.chat_buffer))):
            return None, None, None

        # 此消息用于同步更新小组讨论的信息
        s = sender if sender else "unknown"
        p = "talks with"
        # o = f"students in group {student.scratch.group}"
        o = receiver if receiver else "unknown"
        
        keys = await run_ds_prompt_chat_keywords(information)
        # 将字符串拆分为关键词列表
        if isinstance(keys, str):
            keys_list = [key.strip() for key in keys.split(',') if key.strip()]
        else:
            keys_list = keys if isinstance(keys, list) else [keys]
        keywords = ["group_discussion", s, p, o] + keys_list # 关键词是事件类型、发送者、动词、涉及的学生和总结的关键词
        embedding_pair = (information, await get_local_embedding(information))
        importance_text = await run_ds_prompt_importance_chat(student, information)
        importance = _parse_int_0_10(importance_text)
        student.scratch.accumulate_importance(importance)
        node = student.mem.add_chat(student.scratch.current_time, information, keywords, importance, embedding_pair, s = s, p = p, o = o)
        # sync_concepts = [k for k in keys_list if isinstance(k, str)]
        # if sync_concepts:
            # kg.batch_passive_learn(student.name, sync_concepts, base_strength=0.01, importance=importance)
        student.scratch.chat_buffer.append(node)
        student.scratch.chat_with.append(s)  # 添加发送者到聊天列表
    elif info_type == "taught":
        feedback = await run_ds_prompt_feedback_teaching(student, information)
        msg = BroadcastMessage(
                current_time=student.scratch.current_time,
                message_type = MessageType.CLASS,
                active_event = "feedback",
                speaker = student.name,  
                content = feedback
            )
        student.broadcast_sys.publish_sync("teacher", msg)
        print(f"{student.name}对教学的反馈: {feedback}")
    elif info_type == "new_day":
        # 新的一天，更新学生的时间状态
        student.scratch.current_time = current_time if current_time else student.scratch.current_time

    return node, absorbed_info, learned



