import numpy as np
import sys
sys.path.append("../../")

from student.cognitive_module.memory import *
from student.cognitive_module.scratch import *
from student.cognitive_module.student import *
from student.prompt.run_ds_prompt import *

# TODO: 先基于关键词检索，如果检索不到，则基于加权和检索。
# 如果检索到了关键词，就在
async def retrieve(student, perceived_node):
    """
    从记忆中检索与perceived_node(ConceptNode类)相关的信息。
    此处仅按关键词检索。
    暂时只检索相关的想法和知识类别记忆。（因为事件我们不需要检索，对话现在还没实现）
    INPUT:
        student: Student类
        perceived_node: ConceptNode类
    OUTPUT:
        relevant_mem: {当前结点的描述}: {检索到的结点的类型: 检索到的结点的列表}}

    """
    if perceived_node is None:
        print("未感知到任何信息，无法进行检索。")
        return {}

    print(f"{student.name}在检索")

    relevant_mem = {perceived_node.content: {}}
    keywords = perceived_node.keywords
    print(f"检索结点的关键词: {keywords}")

    # 检索相关的想法
    relevant_thoughts = student.mem.retrieve_relevant_thoughts(keywords)
    if relevant_thoughts:
        relevant_mem[perceived_node.content]["thought"] = relevant_thoughts
    
    print(f"检索到的相关想法: {relevant_thoughts}")
    # 如果没有检索到相关的想法，则可以尝试检索相关的知识
    if not relevant_thoughts:
        print("未检索到相关想法，尝试检索相关知识。")

    # 检索相关的知识
    relevant_knowledge = student.mem.retrieve_relevant_knowledge(keywords)
    if relevant_knowledge:
        relevant_mem[perceived_node.content]["knowledge"] = relevant_knowledge

    print(f"检索到的相关知识: {relevant_knowledge}")

    
    # 还可以根据需要检索其他类型的记忆，例如 event, chat等
    # relevant_events = student.mem.retrieve_relevant_events(keywords)
    # if relevant_events:
    #     relevant_mem[perceived_node.description]["event"] = relevant_events

    return relevant_mem






def cosine_similarity(vec1, vec2):
    """
    计算两个向量的余弦相似度。
    """
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

def extract_recency(student, nodes):
    """
    nodes为一系列按时间顺序的记忆节点
    OUTPUT:
        recency_out: 字典，键为node.node_id， 值为其recency值(float)
    """
    recency_out = {}

    recency_vals = [student.scratch.recency_decay ** i 
                    for i in range(1, len(nodes) + 1)]
    
    for i, node in enumerate(nodes):
        recency_out[node.node_id] = recency_vals[i]

    return recency_out

def extract_importance(student, nodes):
    """
    如上
    """
    importance_out = {}
    for i, node in enumerate(nodes):
        importance_out[node.node_id] = node.importance

    return importance_out

async def extract_relevance(student, nodes, focus):
    """
    其他如上，此处还需要一个focus字符串，用于计算其和各记忆结点的embedding相似度。
    INPUT:
        student: Student类
        nodes: 一系列ConceptNode类的实例
        focus: string, 需要计算相关性的焦点信息
    OUTPUT:
        relevance_out: 字典，键为node.node_id，值为其relevance值(float)
    """
    focus_embedding = await get_local_embedding(focus)

    relevance_out = {}
    for i, node in enumerate(nodes):
        node_embedding = student.mem.embeddings[node.embedding_key]
        relevance_out[node.node_id] = cosine_similarity(focus_embedding, node_embedding)

    return relevance_out

def normalize_dict_floats(d, target_min, target_max):
    """
    标准化一个字典到指定的范围[min_value, max_value]。
    INPUT:
        d: 字典，键为node_id，值为float
        min_value: float, 最小值
        max_value: float, 最大值
    OUTPUT:
        normalized_d: 字典，键为node_id，值为标准化后的float
    """
    if not d or len(d) == 0:
        return {}

    min_val = min(val for val in d.values())
    max_val = max(val for val in d.values())
    range_val = max_val - min_val

    if range_val == 0: 
        for key, val in d.items(): 
            d[key] = (target_max - target_min)/2
    else: 
        for key, val in d.items():
            d[key] = ((val - min_val) * (target_max - target_min) 
                    / range_val + target_min)
    return d

def top_x_values(d, x):
    """
    从字典中提取前x个值最大的项。
    INPUT:
        d: 字典，键为node_id，值为float
        x: int, 需要提取的最大值数量
    OUTPUT:
        top_x: 值最大的x项组成的字典，键为node_id，值为float
    """
    top_x = dict(sorted(d.items(),
                        key=lambda item: item[1],
                        reverse=True)[:x])
    return top_x

async def further_retrieve(student, focus_info, n_count=10):
    """
    从记忆中进一步检索与focus_info相关的信息。
    INPUT:
        student: Student类
        focus_info: list of string, 根据学生
    OUTPUT: 
        relevant_mem: {关注点的问题: [检索到的ConceptNode类的实例列表]}
    """
    retrieved_mem = {}
    for focus_point in focus_info:
        # 一个nodes列表，其中每个元素又是[i.last_accessed, i]的形式
        # 这里的i是ConceptNode类的实例
        nodes = [[i.last_accessed, i]
                 for i in student.mem.seq_thought + student.mem.seq_knowledge]
        # 按照时间顺序排序
        nodes.sort(key=lambda x: x[0], reverse=True)
        # 提取节点
        nodes = [i[1] for i in nodes]

        # 提取recency, importance, relevance
        recency_out = extract_recency(student, nodes)
        recency_out = normalize_dict_floats(recency_out, 0, 1)
        importance_out = extract_importance(student, nodes)
        importance_out = normalize_dict_floats(importance_out, 0, 1)
        relevance_out = await extract_relevance(student, nodes, focus_point)
        relevance_out = normalize_dict_floats(relevance_out, 0, 1)

        weights = [0.5, 2, 2]
        master_out = dict()
        for key in recency_out.keys():
            master_out[key] = (weights[0] * recency_out[key] * student.scratch.recency_w +
                                weights[1] * importance_out[key] * student.scratch.importance_w +
                                weights[2] * relevance_out[key] * student.scratch.relevance_w)
            
        # 按照master_out的值进行排序
        master_out = top_x_values(master_out, n_count)
        master_nodes = [student.mem.id_to_node[i] for i in list(master_out.keys())]

        # 更新检索到的记忆节点被最近访问的时间
        for node in master_nodes:
            node.last_accessed = student.scratch.current_time

        retrieved_mem[focus_point] = master_nodes

    return retrieved_mem

async def further_retrieve_with_precomputed_embedding(student, focus_text, focus_embedding, n_count=10):
    """
    使用预计算的 embedding 进行检索，避免重复计算
    INPUT:
        student: Student类
        focus_text: str, 焦点文本（用于显示）
        focus_embedding: list, 预计算的 embedding 向量
        n_count: int, 检索数量
    OUTPUT:
        master_nodes: list, 检索到的ConceptNode实例列表
    """
    # 获取所有记忆节点
    nodes = [[i.last_accessed, i] for i in student.mem.seq_thought + student.mem.seq_knowledge]
    
    if not nodes:
        print(f"学生 {student.name} 没有任何记忆节点")
        return []
    
    # 按时间排序
    nodes.sort(key=lambda x: x[0], reverse=True)
    nodes = [i[1] for i in nodes]
    
    # 计算各维度分数
    recency_out = extract_recency(student, nodes)
    recency_out = normalize_dict_floats(recency_out, 0, 1)
    
    importance_out = extract_importance(student, nodes)
    importance_out = normalize_dict_floats(importance_out, 0, 1)
    
    # 使用预计算的 embedding 计算相关性
    relevance_out = extract_relevance_with_precomputed_embedding(
        student, nodes, focus_embedding
    )
    relevance_out = normalize_dict_floats(relevance_out, 0, 1)
    
    # 综合评分
    weights = [0.5, 2, 2]
    master_out = dict()
    for key in recency_out.keys():
        master_out[key] = (
            weights[0] * recency_out[key] * student.scratch.recency_w +
            weights[1] * importance_out[key] * student.scratch.importance_w +
            weights[2] * relevance_out[key] * student.scratch.relevance_w
        )
    
    # 选择 top-N
    master_out = top_x_values(master_out, n_count)
    master_nodes = [student.mem.id_to_node[i] for i in list(master_out.keys())]
    
    # 更新访问时间
    for node in master_nodes:
        node.last_accessed = student.scratch.current_time
    
    return master_nodes

def extract_relevance_with_precomputed_embedding(student, nodes, focus_embedding):
    """
    使用预计算的 embedding 计算相关性
    INPUT:
        student: Student类
        nodes: list, ConceptNode实例列表
        focus_embedding: list, 预计算的 embedding 向量
    OUTPUT:
        relevance_out: dict, 相关性分数字典
    """
    relevance_out = {}
    
    for node in nodes:
        try:
            node_embedding = student.mem.embeddings[node.embedding_key]
            relevance_out[node.node_id] = cosine_similarity(focus_embedding, node_embedding)
        except KeyError:
            # 如果节点的 embedding 不存在，给予默认低分
            relevance_out[node.node_id] = 0.0
        except Exception as e:
            print(f"计算节点 {node.node_id} 相关性时出错: {e}")
            relevance_out[node.node_id] = 0.0
    
    return relevance_out

async def further_retrieve_personalized(student, focus_text, focus_embedding, base_n_count=10):
    """
    个性化的记忆检索函数
    INPUT:
        student: Student类
        focus_text: str, 焦点文本
        focus_embedding: list, 预计算的 embedding 向量
        base_n_count: int, 基础检索数量
    OUTPUT:
        master_nodes: list, 个性化检索到的ConceptNode实例列表
    """
    # 获取个性化参数
    params = student.get_personalized_retrieval_params()
    n_count = params["n_count"]
    
    print(f"[检索] {student.name} 个性化参数: 数量={n_count}, 相关性权重={params['relevance_weight']:.1f}")
    
    # 获取所有记忆节点
    nodes = [[i.last_accessed, i] for i in student.mem.seq_thought + student.mem.seq_knowledge]
    
    if not nodes:
        print(f"学生 {student.name} 没有任何记忆节点")
        return []
    
    # 按时间排序
    nodes.sort(key=lambda x: x[0], reverse=True)
    nodes = [i[1] for i in nodes]
    
    # 计算各维度分数（使用个性化权重）
    recency_out = extract_recency(student, nodes)
    recency_out = normalize_dict_floats(recency_out, 0, 1)
    
    importance_out = extract_importance(student, nodes)
    importance_out = normalize_dict_floats(importance_out, 0, 1)
    
    relevance_out = extract_relevance_with_precomputed_embedding(
        student, nodes, focus_embedding
    )
    relevance_out = normalize_dict_floats(relevance_out, 0, 1)
    
    # 应用相似度阈值过滤
    similarity_threshold = params["similarity_threshold"]
    filtered_relevance = {k: v for k, v in relevance_out.items() 
                         if v >= similarity_threshold}
    
    if not filtered_relevance:
        print(f"[检索] {student.name} 没有找到相似度 ≥ {similarity_threshold} 的记忆，降低阈值")
        similarity_threshold = 0.05
        filtered_relevance = {k: v for k, v in relevance_out.items() 
                             if v >= similarity_threshold}
    
    # 使用个性化权重进行综合评分
    master_out = dict()
    for key in filtered_relevance.keys():
        if key in recency_out and key in importance_out:
            master_out[key] = (
                params["recency_weight"] * recency_out[key] * student.scratch.recency_w +
                params["importance_weight"] * importance_out[key] * student.scratch.importance_w +
                params["relevance_weight"] * relevance_out[key] * student.scratch.relevance_w
            )
    
    if not master_out:
        print(f"[检索] {student.name} 没有找到合适的记忆")
        return []
    
    # 多样性处理（如果需要）
    diversity_factor = params["diversity_factor"]
    if diversity_factor > 0:
        master_out = apply_diversity_penalty(student, master_out, diversity_factor)
    
    # 选择 top-N
    master_out = top_x_values(master_out, n_count)
    master_nodes = [student.mem.id_to_node[i] for i in list(master_out.keys())]
    
    # 更新访问时间
    for node in master_nodes:
        node.last_accessed = student.scratch.current_time
    
    print(f"[检索] {student.name} 最终检索到 {len(master_nodes)} 条记忆")
    return master_nodes

def apply_diversity_penalty(student, master_out, diversity_factor):
    """
    应用多样性惩罚，避免检索过于相似的记忆
    """
    if diversity_factor <= 0:
        return master_out
    
    # 简单的多样性策略：惩罚关键词重叠过多的记忆
    diverse_out = master_out.copy()
    selected_keywords = set()
    
    for node_id in sorted(master_out.keys(), key=lambda x: master_out[x], reverse=True):
        try:
            node = student.mem.id_to_node[node_id]
            node_keywords = set(getattr(node, 'keywords', []))
            
            # 计算与已选记忆的关键词重叠度
            overlap = len(node_keywords & selected_keywords)
            penalty = diversity_factor * overlap
            
            diverse_out[node_id] = max(0, diverse_out[node_id] - penalty)
            selected_keywords.update(node_keywords)
            
        except Exception:
            continue
    
    return diverse_out