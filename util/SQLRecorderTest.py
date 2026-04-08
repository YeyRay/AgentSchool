import asyncio
from util.SQLRecorder import Recorder

async def demo():
    recorder = Recorder(
        dsn="postgresql://postgres:qwe123@localhost:5432/simulation_db",
        session_id="sess_001",
        course_id="course_math_101",
        frame_id=0
    )
    await recorder.init()

    # 1. 学生日志
    await recorder.student_log({
        "name": "StudentC",
        "stress": 0.0914601073985886,
        "attention": 0.25320364773599846,
        "absorbed": "",
        "learned": "",
        "reflection": {}
    })

    # 2. 动作日志
    await recorder.action_log({
        "student": "StudentA",
        "action": "listen"
    })

    # 3. 广播日志
    await recorder.broadcast_log({
        "current_time": "2025-09-01T08:01:00",
        "message_type": "class",
        "active_event": "group_discussion",
        "event_id": None,
        "speaker": "StudentC",
        "content": "我们先看第一个数吧，比如-3，它应该是负整数。",
        "receiver": "StudentA"
    })

    await asyncio.sleep(0.1)
    await recorder.close()
    print("✅ 所有日志写入完成")

if __name__ == "__main__":
    asyncio.run(demo())