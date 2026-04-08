import json
import sys

import aiofiles

from datetime import datetime

sys.path.append("../")

from student.global_methods import *

class ConceptNode:
    def __init__(self, 
                 node_id, node_count, type_count, node_type, depth,
                 created, expiration,
                content, embedding_key, importance, keywords, event_type=None, s=None, p=None, o=None, knowledge_tag=None, theme=None, misconceptions=None):
        self.node_id = node_id
        self.node_count = node_count
        self.type_count = type_count
        self.type = node_type
        self.depth = depth

        self.created = created
        self.expiration = expiration
        self.last_accessed = self.created

        # self.description = description
        self.content = content
        self.embedding_key = embedding_key
        self.importance = importance
        # 这里的关键词应该由(s, p, o, knowledge_tag)组成
        # 前三者在node_type为event, chat, thought时出现
        # 最后一个在node_type为knowledge, thought时出现
        # 但是thought类型是不是有两种可能？比如对于知识点的思考，以及对事件、对话的思考；不同情况也许要分类处理？
        self.keywords = keywords
        # self.filling = filling

        self.event_type = event_type
        self.s = s
        self.p = p
        self.o = o
        self.knowledge_tag = knowledge_tag # 用于存储知识的标签(list)
        self.theme = theme # 用于存储事件的主题(list)

        self.misconceptions = misconceptions  # 用于存储与该节点相关的误解或错误信息的列表(知识结点下)


class Memory:
    def __init__(self, f_saved):
        self.id_to_node = dict()

        # 每次都插入头部，从而保证记忆的顺序
        # 并可用 `retention` 参数来控制其遗忘因数
        # 直接将其作为下标，因此我们每次所能记住的记忆都是最新的 retention 个
        # 因此直接拿到0——retention - 1的记忆即可
        self.seq_event = []
        self.seq_thought = []
        self.seq_chat = []
        self.seq_knowledge = []

        self.kw_to_event = dict()
        self.kw_to_thought = dict()
        self.kw_to_chat = dict()
        self.kw_to_knowledge = dict()

        # 每当一个新的事件或思考被添加到记忆中时，代码会遍历与之关联的关键词，并在相应的字典中增加该关键词的计数。
        self.kw_strength_event = dict()
        self.kw_strength_thought = dict()
        
        # embeddings是一个字典，键为记忆结点的content, 值为对应的embedding向量
        embeddings_file_path = f_saved + "/embeddings.json"
        with open(embeddings_file_path, 'r', encoding='utf-8') as f:
            self.embeddings = json.load(f)

    
        nodes_file_path = f_saved + "/nodes.json"
        with open(nodes_file_path, 'r', encoding='utf-8') as f:
            nodes_load = json.load(f)
        for cnt in range(len(nodes_load.keys())):
            node_id = f"node_{str(cnt+1)}"
            node_details = nodes_load[node_id]

            node_count = node_details["node_count"]
            type_count = node_details["type_count"]
            node_type = node_details["type"]
            depth = node_details["depth"]

            # created = datetime.datetime.strptime(node_details["created"], "%Y-%m-%d %H:%M:%S")
            created = datetime.strptime(node_details["created"], "%Y-%m-%d %H:%M:%S")

            expiration = None
            if node_details["expiration"]:
                # expiration = datetime.datetime.strptime(node_details["expiration"], "%Y-%m-%d %H:%M:%S")
                expiration = datetime.strptime(node_details["expiration"], "%Y-%m-%d %H:%M:%S")

            """s = node_details["s"]
            p = node_details["p"]
            o = node_details["o"]

            knowledge_tag = node_details["knowledge_tag"]
            event_type = node_details["event_type"]"""
        
            # 此处的变量是有可能不存在的，因此需要使用get方法来获取
            event_type = node_details.get("event_type", None)
            theme = node_details.get("theme", None)
            knowledge_tag = node_details.get("knowledge_tag", None)
        

            # description = node_details["description"]
            content = node_details["content"]
            embedding_pair = (node_details["embedding_key"], self.embeddings[node_details["embedding_key"]])
            importance = node_details["importance"]
            keywords = node_details["keywords"]
            misconceptions = node_details.get("misconceptions", None)
            

            if node_type == "event":
                self.add_event(created, content, keywords, importance,
                                embedding_pair, event_type, theme)
            elif node_type == "thought":
                self.add_thought(created, 
                                content, keywords, importance,
                                embedding_pair)
            elif node_type == "chat":
                self.add_chat(created, 
                                content, keywords, importance,
                                embedding_pair)
            elif node_type == "knowledge":
                self.add_knowledge(created, 
                                    content, keywords, importance,
                                    embedding_pair, knowledge_tag, misconceptions=misconceptions)

    def save(self, out_json):
        r = dict()
        for cnt in range(len(self.id_to_node.keys())):
            node_id = f"node_{str(cnt+1)}"
            node = self.id_to_node[node_id]

            r[node_id] = dict()
            r[node_id]["node_count"] = node.node_count
            r[node_id]["type_count"] = node.type_count
            r[node_id]["type"] = node.type
            r[node_id]["depth"] = node.depth

            r[node_id]["created"] = node.created.strftime("%Y-%m-%d %H:%M:%S")
            if node.expiration:
                r[node_id]["expiration"] = node.expiration.strftime("%Y-%m-%d %H:%M:%S")
            else:
                r[node_id]["expiration"] = None

            r[node_id]["s"] = node.s
            r[node_id]["p"] = node.p
            r[node_id]["o"] = node.o

            r[node_id]["knowledge_tag"] = node.knowledge_tag
            r[node_id]["event_type"] = node.event_type
            # r[node_id]["description"] = node.description
            r[node_id]["content"] = node.content
            r[node_id]["embedding_key"] = node.embedding_key
            r[node_id]["importance"] = node.importance
            r[node_id]["keywords"] = node.keywords
            r[node_id]["misconceptions"] = node.misconceptions

        with open(out_json + "/nodes.json", "w", encoding='utf-8') as f:
            json.dump(r, f, ensure_ascii=False, indent=4)
        
        with open(out_json+"/embeddings.json", "w", encoding='utf-8') as outfile:
            json.dump(self.embeddings, outfile, ensure_ascii=False, indent=4)

    async def save_async(self, out_json):
        r = dict()
        for cnt in range(len(self.id_to_node.keys())):
            node_id = f"node_{str(cnt+1)}"
            node = self.id_to_node[node_id]

            r[node_id] = dict()
            r[node_id]["node_count"] = node.node_count
            r[node_id]["type_count"] = node.type_count
            r[node_id]["type"] = node.type
            r[node_id]["depth"] = node.depth

            r[node_id]["created"] = node.created.strftime("%Y-%m-%d %H:%M:%S")
            if node.expiration:
                r[node_id]["expiration"] = node.expiration.strftime("%Y-%m-%d %H:%M:%S")
            else:
                r[node_id]["expiration"] = None

            r[node_id]["s"] = node.s
            r[node_id]["p"] = node.p
            r[node_id]["o"] = node.o

            r[node_id]["knowledge_tag"] = node.knowledge_tag
            r[node_id]["event_type"] = node.event_type
            # r[node_id]["description"] = node.description
            r[node_id]["content"] = node.content
            r[node_id]["embedding_key"] = node.embedding_key
            r[node_id]["importance"] = node.importance
            r[node_id]["keywords"] = node.keywords
            r[node_id]["misconceptions"] = node.misconceptions

        async with aiofiles.open(out_json + "/nodes.json", "w", encoding='utf-8') as f:
            await f.write(json.dump(r, f, ensure_ascii=False, indent=4))
        
        async with aiofiles.open(out_json+"/embeddings.json", "w", encoding='utf-8') as outfile:
            await f.write(json.dump(self.embeddings, outfile, ensure_ascii=False, indent=4))



    # 事件的keywords应该是此事件的类型+主题
    # embedding_pair是一个元组，包括event.content和对应的embedding向量
    def add_event(self, created, content, keywords, importance, 
                   embedding_pair, event_type, theme,
                   expiration = None, s = None, p = None, o = None):
        """
        保存事件。
        """
        node_count = len(self.id_to_node.keys()) + 1
        type_count = len(self.seq_event) + 1
        node_type = "event"
        node_id = f"node_{str(node_count)}"
        depth = 0
    
        node = ConceptNode(node_id, node_count, type_count, node_type, depth, 
                           created, expiration,
                           content, embedding_pair[0],
                            importance, keywords, event_type=event_type, theme=theme, s=s, p=p, o=o)
        
        # 插入头部
        self.seq_event.insert(0, node)
        keywords = [i for i in keywords if i]  # 去除空关键词
        for kw in keywords:
            if kw in self.kw_to_event:
                self.kw_to_event[kw][0:0] = [node]
            else:
                self.kw_to_event[kw] = [node]
        self.id_to_node[node_id] = node

        self.embeddings[embedding_pair[0]] = embedding_pair[1]

        return node

    def add_thought(self, created, content, keywords, importance, 
                     embedding_pair, 
                     expiration = None, s = None, p = None, o = None):
        """
        保存想法。
        """
        node_count = len(self.id_to_node.keys()) + 1
        type_count = len(self.seq_thought) + 1
        node_type = "thought"
        node_id = f"node_{str(node_count)}"
        depth = 1

        node = ConceptNode(node_id, node_count, type_count, node_type, depth,
                            created, expiration,
                            content, embedding_pair[0],
                            importance, keywords, s=s, p=p, o=o)
        # 插入头部  
        self.seq_thought.insert(0, node)
        keywords = [i for i in keywords if i]
        for kw in keywords:
            if kw in self.kw_to_thought:
                self.kw_to_thought[kw][0:0] = [node]
            else:
                self.kw_to_thought[kw] = [node]
        self.id_to_node[node_id] = node

        self.embeddings[embedding_pair[0]] = embedding_pair[1]
        return node

    def add_chat(self, created, content, keywords, importance,
                     embedding_pair,
                     expiration = None, s = None, p = None, o = None, knowledge_tag = None):
        """
        保存对话。
        """
        node_count = len(self.id_to_node.keys()) + 1
        type_count = len(self.seq_chat) + 1
        node_type = "chat"
        node_id = f"node_{str(node_count)}"
        depth = 0

        node = ConceptNode(node_id, node_count, type_count, node_type, depth,
                            created, expiration,
                            content, embedding_pair[0],
                            importance, keywords, s=s, p=p, o=o, knowledge_tag=knowledge_tag)
        # 插入头部
        self.seq_chat.insert(0, node)
        keywords = [i for i in keywords if i]
        for kw in keywords:
            if kw in self.kw_to_chat:
                self.kw_to_chat[kw][0:0] = [node]
            else:
                self.kw_to_chat[kw] = [node]
        self.id_to_node[node_id] = node

        self.embeddings[embedding_pair[0]] = embedding_pair[1]

        return node

    def add_knowledge(self, created, content, keywords, importance,
                      embedding_pair, knowledge_tag, misconceptions=None,
                     expiration = None):       
        """
        保存知识。
        """
        node_count = len(self.id_to_node.keys()) + 1
        type_count = len(self.seq_knowledge) + 1
        node_type = "knowledge"
        node_id = f"node_{str(node_count)}"
        depth = 0
        node = ConceptNode(node_id, node_count, type_count, node_type, depth,
                            created, expiration,
                            content, embedding_pair[0],
                            importance, keywords, knowledge_tag=knowledge_tag, misconceptions=misconceptions)
        
        # 插入头部
        self.seq_knowledge.insert(0, node)
        keywords = [i for i in keywords if i]
        for kw in keywords:
            if kw in self.kw_to_knowledge:
                self.kw_to_knowledge[kw][0:0] = [node]
            else:
                self.kw_to_knowledge[kw] = [node]
        self.id_to_node[node_id] = node
        self.embeddings[embedding_pair[0]] = embedding_pair[1]
        return node
    

    def retrieve_relevant_thoughts(self, keywords):
        """
        检索与给定关键词相关的想法。
        """
        relevant_thoughts = []
        for kw in keywords:
            if kw in self.kw_to_thought:
                relevant_thoughts.extend(self.kw_to_thought[kw])
        
        # 去重并保持顺序（如果需要的话，但set会打乱顺序）
        # 如果需要保持插入顺序的去重，可以使用 OrderedDict 或者其他方法
        # 这里简单用 set 去重，然后转回 list
        # 注意：如果 ConceptNode 对象不可哈希，直接用 set 会报错，需要确保 ConceptNode 可哈希或存储其 id
        # 假设 ConceptNode 的 id 是唯一的且可哈希
        # relevant_thoughts = list(set(relevant_thoughts)) 
        # 更安全的做法是基于 node_id 去重
        seen_ids = set()
        unique_thoughts = []
        for thought_node in relevant_thoughts:
            if thought_node.node_id not in seen_ids:
                unique_thoughts.append(thought_node)
                seen_ids.add(thought_node.node_id)
        return unique_thoughts

    def retrieve_relevant_knowledge(self, keywords):
        """
        检索与给定关键词相关的知识。
        """
        relevant_knowledge = []
        for kw in keywords:
            if kw in self.kw_to_knowledge:
                relevant_knowledge.extend(self.kw_to_knowledge[kw])
        
        seen_ids = set()
        unique_knowledge = []
        for knowledge_node in relevant_knowledge:
            if knowledge_node.node_id not in seen_ids:
                unique_knowledge.append(knowledge_node)
                seen_ids.add(knowledge_node.node_id)
        return unique_knowledge

