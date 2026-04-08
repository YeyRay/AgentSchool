import random
import string
import csv
import time
import datetime as dt
import pathlib
import os
import sys
import numpy
import math
import shutil, errno
import json

from os import listdir

def check_if_file_exists(curr_file): 
  """
  Checks if a file exists
  ARGS:
    curr_file: path to the current csv file. 
  RETURNS: 
    True if the file exists
    False if the file does not exist
  """
  try: 
    with open(curr_file) as f_analysis_file: pass
    return True
  except: 
    return False

def translate_dict_to_str(dict_obj):
    """
    Translate a single layer dictionary to a string representation.  
    """
    return "\n".join([f"{k}: {v}" for k, v in dict_obj.items()])


def translate_set_to_str(set_obj):
    """
    Translate a set to a string representation.
    """
    return "\n".join(f"- {item}" for item in sorted(set_obj))

def translate_student_to_str(scratch):
   """
   把学生的性格、认知状态、情感状态和学习风格转换成字符串表示。
   """
   personality = scratch.personality
   personality_str = translate_dict_to_str(personality)
   cognitive_state = scratch.cognitive_state
   cognitive_state_str = translate_set_to_str(cognitive_state)
   affective_state = scratch.affective_state
   affective_state_str = translate_set_to_str(affective_state)
   learning_style = scratch.learning_style
   learning_style_str = translate_dict_to_str(learning_style)
   
   return personality_str, cognitive_state_str, affective_state_str, learning_style_str

# 中文数字转整数
def chinese_num_to_int(cn_num):
    mapping = {'一': 1, '二': 2, '三': 3, '四': 4,
               '五': 5, '六': 6, '七': 7, '八': 8,
               '九': 9, '十': 10}
    return mapping.get(cn_num, -1)

# 学期转换
def term_to_int(term_char):
    return 0 if term_char == '上' else 1 if term_char == '下' else -1

# 解析字符串为元组 (年级, 学期)
def parse_grade_term(s):
    grade_char = s[0]  # 如“七”
    term_char = s[-1]  # 如“上”
    return (chinese_num_to_int(grade_char), term_to_int(term_char))

# 比较函数
def compare_grade_terms(a, b):
    return parse_grade_term(a) < parse_grade_term(b)

# 将further_retrieve函数的返回结果转换为prompt可理解的字符串
def format_retrieved_info(retrieved_info):
   """
   INPUT:
      {关注点的问题: [检索到的ConceptNode类的实例列表]}
   OUTPUT:
      "【关注点：AI对就业的影响】
        - 自动化可能会替代重复性高的岗位
        - 新职业类型正在出现，例如AI训练师

      【关注点：AI与伦理问题】
        - AI可能在训练中引入偏见
        - 缺乏统一的AI伦理立法"
   """
   formatted_info = [] 
   for focus_point, nodes in retrieved_info.items():
        nodes_str = "\n".join(f"- {node.content}" for node in nodes)
        formatted_info.append(f"【关注点：{focus_point}】\n{nodes_str}")  
   return "\n\n".join(formatted_info)

# 将student.sratch.chat_buffer转换为prompt可理解的字符串
def format_chat_buffer(chat_buffer):
    """
    INPUT:
        chat_buffer: list of nodes
    OUTPUT:
        "
        - 2023-10-01 10:00:00, Teacher: 请问AI对就业的影响是什么？
        - 2023-10-01 10:01:00, Student1: AI可能会替代重复性高的岗位。
        - 2023-10-01 10:02:00, Student2: 新职业类型正在出现，例如AI训练师。
        "
    """ 
    formatted_buffer = []
    for node in chat_buffer:
        timestamp = node.created
        sender = node.s
        content = node.content
        formatted_buffer.append(f"- {timestamp}, {sender}: {content}")
    return "\n".join(formatted_buffer)

def get_knowledge_points_from_json(student, file):
    """
    从指定的json文件获取该学生student所在年级对应的知识点范围。
    返回列表。

    OUTPUT:
        dedup ：字典，{id: (name, parent_id)}
    """
    with open(file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # 兼容：student.scratch.grade 可能形如 "七上" / "七年级上" / "七年级(上)" 等
    grade_raw = getattr(getattr(student, 'scratch', student), 'grade', None)
    if not grade_raw:
        return []

    chinese_digits = ['一','二','三','四','五','六','七','八','九','十']
    grade_char = None
    term_char = None

    # 提取年级汉字
    for ch in chinese_digits:
        if ch in grade_raw:
            grade_char = ch
            break
    # 提取学期
    if '上' in grade_raw:
        term_char = '上'
    elif '下' in grade_raw:
        term_char = '下'
    # 如果直接就是类似 "七上"
    if len(grade_raw) == 2 and grade_raw[0] in chinese_digits and grade_raw[1] in ['上','下']:
        grade_char = grade_raw[0]
        term_char = grade_raw[1]

    # 构建候选 key
    key_candidates = []
    # 原始 key 直接存在时优先
    if grade_raw in data:
        key_candidates.append(grade_raw)
    if grade_char and term_char:
        key_candidates.append(f"{grade_char}{term_char}知识图谱")
    # 去重保持顺序
    seen = set()
    ordered_keys = []
    for k in key_candidates:
        if k not in seen:
            ordered_keys.append(k)
            seen.add(k)

    # 遍历找到第一个存在的图谱
    nodes_section = None
    selected_key = None
    for k in ordered_keys:
        if k in data and isinstance(data[k], dict):
            nodes_section = data[k].get('nodes', [])
            selected_key = k
            break
    if nodes_section is None:
        return []

    dedup = {}
    for node in nodes_section:
        if isinstance(node, dict):
            kid = node.get('id')
            kname = node.get('name')
            parent_id = node.get('parent_id')
            if kid and kname:
                if kid not in dedup:
                    dedup[kid] = (kname, parent_id)
    return dedup

def load_grade_knowledge_points(student):
    """容错加载：尝试多种文件名，返回知识点 id 列表。
    优先顺序：
      1. student/数学知识点.json
      2. student/教学知识点.json
      3. 数学知识点.json (项目根或当前工作目录)
      4. 教学知识点.json
    若全部缺失，返回 [] 并打印提示。
    """
    from pathlib import Path
    candidates = [
        Path('student/数学知识点.json'),
        Path('student/教学知识点.json'),
        Path('数学知识点.json'),
        Path('教学知识点.json'),
    ]
    tried = []
    for p in candidates:
        if p.exists():
            try:
                # print(get_knowledge_points_from_json(student, str(p)))
                return get_knowledge_points_from_json(student, str(p))
            except Exception as e:
                print(f"加载知识点文件失败 {p}: {e}")
        tried.append(str(p))
    print("警告: 未找到任何知识点文件。已尝试: ", tried)
    return []

