import json
import os
import sys
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))#根目录

from run import main
from teacher.vector_db import VectorDB

script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(script_dir))


def train_experience(ep_level: str ,class_num: int, textbook_file: str):
    model_cache_dir = os.path.join(root_dir, "teacher", "model_cache")
    vector_db = VectorDB(model_cache_dir=model_cache_dir)
    ep_vector_db_file= os.path.join(script_dir, "ep_vector_db", ep_level)
    if not os.path.exists(ep_vector_db_file):
        os.makedirs(ep_vector_db_file)
    vector_db.save(path= ep_vector_db_file)

    if ep_level == "basic":
        return 

    with open(os.path.join(root_dir, 'config', 'schedule.json'), 'r+', encoding='utf-8') as file:
        schedule = json.load(file)
        schedule['total_courses'] = class_num
        file.seek(0)
        file.write(json.dumps(schedule, indent=4, ensure_ascii=False))
        file.truncate()  # 截断文件，确保移除多余内容
    with open(os.path.join(root_dir, 'config', 'teacher.json'), 'r+', encoding='utf-8') as file:
        teacher = json.load(file)
        teacher['experience_level'] = ep_level
        teacher['pck_level'] = "basic"
        teacher['textbook_file'] = textbook_file
        file.seek(0)
        file.write(json.dumps(teacher, indent=4, ensure_ascii=False))
        file.truncate()

    asyncio.run(main())

if __name__ == "__main__":
    ep_level = "basic"  # 选择 "basic", "intermediate", 或 "advanced"
    class_num = 1
    textbook_file = "use last"
    train_experience(ep_level, class_num, textbook_file)