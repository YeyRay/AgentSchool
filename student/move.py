from cognitive_module.memory import *
from cognitive_module.scratch import *
from cognitive_module.student import *
from prompt.run_ds_prompt import *
from perceive import *
from retrieve import *
from reflect import *
from plan import *
from exercise import *
from datetime import datetime, timedelta
import os

def move(student, file, i, info):
    """
    INPUT:
        student
        file: 存入的文件
        i: 轮次
        info: 字符串，当前信息
    """
    print(f"--- 现在是 {student.scratch.current_time} ---")
    node = perceive(student, info)
    retrieved = retrieve(student, node)
    if retrieved and retrieved[node.content]:
        print(f"检索到相关记忆: {retrieved[node.content]}")
    else:
        print("没有检索到相关记忆。")
    
    reflect(student, retrieved)

    student.scratch.current_time = student.scratch.current_time + timedelta(seconds=30) # 假设每次感知后时间增加30秒

    
    student.scratch.save(f"test/{student.name}_scratch_{i}.json")  # 保存当前scratch状态到文件

    memory_file = f"test/{student.name}_memory_{i}"
    if not os.path.exists(memory_file):
        os.makedirs(memory_file, exist_ok=True) #确保 memory_file 作为目录存在
    student.mem.save(memory_file)