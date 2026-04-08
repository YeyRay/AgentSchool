import asyncio
import time
from datetime import datetime

from util.BroadcastSys import BroadcastSys
from util.Recorder import Recorder
from run import initialize_students_from_config
from student.evaluate import evaluate
from student.exercise import exercise


QUESTIONNAIRE_FILE = "student/问卷.json"
EXERCISE_FILE = "student/data.jsonl"


async def main():
    rec = Recorder("")
    bs = BroadcastSys(rec)
    students = initialize_students_from_config("config/student", bs, rec)

    postfix = datetime.now().strftime("%Y%m%d_%H%M%S")
    t_all_start = time.time()

    # 问卷阶段（并发，统计总耗时）
    t_q_start = time.time()
    await asyncio.gather(*[evaluate(s, QUESTIONNAIRE_FILE, postfix) for s in students.values()])
    t_q_cost = time.time() - t_q_start
    print(f"[TIME] 问卷总耗时: {t_q_cost:.2f}s")

    # 练习阶段（并发，统计总耗时）
    t_ex_start = time.time()
    await asyncio.gather(*[exercise(s, EXERCISE_FILE) for s in students.values()])
    t_ex_cost = time.time() - t_ex_start
    print(f"[TIME] 练习总耗时: {t_ex_cost:.2f}s")

    t_all_cost = time.time() - t_all_start
    print(f"[TIME] 评教整体耗时: {t_all_cost:.2f}s")
    print("评教与做题完成。")


if __name__ == "__main__":
    asyncio.run(main())