import asyncio
import os
import sys
import json
import random
import time
from datetime import datetime, timedelta, time as dt_time

from util.BroadcastSys import BroadcastSys
from util.Events import Event
from util.Recorder import Recorder
from util.TimeManager import *
from student.cognitive_module.student import Student
from teacher.teacher import Teacher
from util.BroadcastMessage import *
from student.exercise import *
from student.evaluate import *


# 日志重定向类
class Tee:
    def __init__(self, file):
        self.file = file
        self.original_stdout = sys.__stdout__

    def write(self, data):
        self.file.write(data)
        self.file.flush()
        self.original_stdout.write(data)
        self.original_stdout.flush()

    def flush(self):
        self.file.flush()
        self.original_stdout.flush()


def initialize_students_from_config(config_dir, broadcast_system, recorder):
    students = {}
    for filename in os.listdir(config_dir):
        if filename.endswith(".json"):
            file_path = os.path.join(config_dir, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception as e:
                print(f"无法加载文件 {filename}: {e}")
                continue

            folder_path = config.get("folder")
            if not folder_path:
                print(f"警告：{filename} 缺少 folder 字段，跳过。")
                continue

            os.makedirs(folder_path, exist_ok=True)

            scratch_content = {k: v for k, v in config.items() if k != "folder"}
            scratch_path = os.path.join(folder_path, "scratch.json")
            with open(scratch_path, "w", encoding="utf-8") as f:
                json.dump(scratch_content, f, ensure_ascii=False, indent=4)

            for fname in ["nodes.json", "embeddings.json"]:
                path = os.path.join(folder_path, fname)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({}, f)

            student_name = config.get("name")
            if not student_name:
                print(f"警告：{filename} 缺少 name 字段，跳过实例化。")
                continue

            student_instance = Student(
                name=student_name,
                broadcast_sys=broadcast_system,
                recorder=recorder,
                folder_mem_saved=folder_path
            )
            students[student_name] = student_instance
            print(f"已处理学生：{student_name}，文件保存在：{folder_path}")
    return students


# 全局变量
log_file = None
action_recorder = None
broadcast_recorder = None
student_recorder = None
base_log_dir = None


def switch_log_file(event_id=None):
    global log_file, action_recorder, broadcast_recorder, student_recorder, base_log_dir

    if log_file:
        log_file.close()

    current_log_dir = f"{base_log_dir}/{event_id}" if event_id else base_log_dir
    os.makedirs(current_log_dir, exist_ok=True)
    log_path = f'{current_log_dir}/output.txt'
    log_file = open(log_path, 'w', encoding='utf-8')
    sys.stdout = Tee(log_file)

    if action_recorder:
        action_recorder.set_file_path(f"{current_log_dir}/action_log.jsonl")
    if broadcast_recorder:
        broadcast_recorder.set_file_path(f"{current_log_dir}/broadcast_log.jsonl")
    if student_recorder:
        student_recorder.set_file_path(f"{current_log_dir}/student_log.jsonl")


# 学生反馈任务的异步包装函数
async def student_feedback(student, feedback_type, feedback_func, file, postfix):
    print(f"{student.name} 开始{feedback_type}。")
    try:
        await feedback_func(student, file, postfix)
        print(f"{student.name} 完成{feedback_type}。")
    except Exception as e:
        print(f"错误: {student.name} 的{feedback_type}失败: {str(e)}")


# ========== 观察者功能 ==========

async def observer_command_listener(pause_flag, command_file="observer_cmd.json"):
    """
    监听观察者命令文件的变化
    
    Args:
        pause_flag: 暂停标志字典
        command_file: 命令文件路径
    """
    last_modified = 0  # 保留但不强依赖 mtime（兼容某些编辑器保存不更新时间戳的问题）
    
    # 创建初始命令文件并提供说明
    command_template = {
        "command": "",
        "info": "在此文件中输入命令",
        "available_commands": {
            "pause": "暂停仿真",
            "resume": "继续仿真",
            "status": "查看当前状态",
            "intervene": "打断并调整教学计划（需配合intervention字段）",
            "rollback": "回溯到第k轮（需配合rollback字段）",
            "exit": "退出仿真"
        },
        "example": {
            "command": "pause",
            "note": "保存此文件后命令会立即生效"
        }
    }
    
    if not os.path.exists(command_file):
        with open(command_file, 'w', encoding='utf-8') as f:
            json.dump(command_template, f, indent=2, ensure_ascii=False)
    
    command_file_abs = os.path.abspath(command_file)
    print(f"\n{'='*70}")
    print(f"📝 [观察者模式] 已启动")
    print(f"{'='*70}")
    print(f"命令文件: {command_file_abs}")
    print(f"\n可用命令:")
    print(f"  • pause     - 暂停仿真")
    print(f"  • resume    - 继续仿真")
    print(f"  • status    - 查看当前状态")
    print(f"  • intervene - 打断并调整教学计划（预留接口）")
    print(f"  • rollback  - 回溯到第k轮（需在JSON中提供rollback.turn与可选class）")
    print(f"  • exit      - 退出仿真")
    print(f"\n使用方法: 编辑 {command_file} 文件，修改 'command' 字段并保存")
    print(f"{'='*70}\n")
    
    while True:
        try:
            if os.path.exists(command_file):
                # 不再依赖 mtime，直接读取并基于 last_command 去抖
                with open(command_file, 'r', encoding='utf-8') as f:
                    command_data = json.load(f)
                command = command_data.get("command", "").strip().lower()
                
                if command and command != pause_flag.get("last_command"):
                    print(f"\n{'='*70}")
                    print(f"📝 [观察者] 收到命令: {command}")
                    print(f"{'='*70}")
                    
                    pause_flag["command"] = command
                    pause_flag["last_command"] = command
                    
                    if command == "pause":
                        pause_flag["paused"] = True
                        print(f"⏸️  仿真将在当前轮次结束后暂停...\n")
                    elif command == "resume":
                        pause_flag["paused"] = False
                        print(f"▶️  仿真继续...\n")
                    elif command == "status":
                        pause_flag["show_status"] = True
                    elif command == "intervene":
                        pause_flag["paused"] = True
                        pause_flag["intervention"] = command_data.get("intervention", {})
                        print(f"🔧 [预留功能] 打断干预已接收，等待处理...\n")
                    elif command == "rollback":
                        pause_flag["paused"] = True
                        pause_flag["rollback"] = command_data.get("rollback", {})
                        print(f"🔙 回溯指令已接收，等待处理...\n")
                    elif command == "exit":
                        pause_flag["exit"] = True
                        print(f"🛑 正在优雅退出仿真...\n")
                        break
                    
                    # 清空命令文件，防止重复触发
                    with open(command_file, 'w', encoding='utf-8') as f:
                        json.dump({
                            "command": "",
                            "info": "命令已处理",
                            "last_executed": command,
                            "timestamp": datetime.now().isoformat(),
                            "available_commands": command_template["available_commands"]
                        }, f, indent=2, ensure_ascii=False)
            
            await asyncio.sleep(0.5)  # 每0.5秒检查一次
            
        except json.JSONDecodeError:
            # JSON格式错误，跳过
            await asyncio.sleep(1)
        except Exception as e:
            print(f"[错误] 文件监听异常: {e}")
            await asyncio.sleep(1)


def show_simulation_status(teacher, students, time_manager, runtime_snapshot=None):
    """显示当前仿真状态"""
    print(f"\n{'='*70}")
    print(f"📊 当前仿真状态")
    print(f"{'='*70}")
    
    # 时间信息
    current_time = time_manager.current_time
    print(f"\n⏱️  时间信息:")
    print(f"  • 当前时间: {current_time.strftime('%Y-%m-%d %H:%M:%S %A')}")
    current_event = time_manager.get_current_active_event()
    print(f"  • 当前事件: {current_event.type} (ID: {current_event.id})")
    
    # 教师信息
    print(f"\n👨‍🏫 教师状态:")
    print(f"  • 姓名: {teacher.name}")
    print(f"  • 课程进度: 第 {teacher.class_number} 节课")
    print(f"  • 教学阶段: {teacher.period}")
    print(f"  • 当前轮次: {teacher.current_turn}/{teacher.class_turns}")
    
    # 显示当前教学内容（截断过长内容）
    content = teacher.content if hasattr(teacher, 'content') else "无"
    if len(content) > 100:
        content = content[:100] + "..."
    print(f"  • 当前内容: {content}")
    # 教师上一动作（若有）
    if runtime_snapshot and isinstance(runtime_snapshot, dict):
        teacher_snap = runtime_snapshot.get("teacher", {})
        last_action = teacher_snap.get("action")
        if last_action:
            print(f"  • 上一动作: {last_action}")
    
    # 学生信息
    print(f"\n👥 学生状态:")
    for student_name, student in students.items():
        # 优先使用 attention_level，其次回退到 attention
        attention = getattr(student.scratch, 'attention_level', None)
        if attention is None:
            attention = getattr(student.scratch, 'attention', 0.0)
        action = getattr(student.scratch, 'action', '')
        if (attention is None or attention == 0.0 or attention == 0) and runtime_snapshot and isinstance(runtime_snapshot, dict):
            snap = runtime_snapshot.get("students", {}).get(student_name, {})
            attention = snap.get("attention", attention)
        if (not action) and runtime_snapshot and isinstance(runtime_snapshot, dict):
            snap = runtime_snapshot.get("students", {}).get(student_name, {})
            action = snap.get("action", action) or ""
        print(f"  • {student_name}:")
        try:
            print(f"      - 注意力: {float(attention):.2f}")
        except Exception:
            print(f"      - 注意力: {attention}")
        print(f"      - 当前行为: {action}")
        print(f"      - 记忆节点数: {len(student.mem.seq_thought) + len(student.mem.seq_knowledge)}")
    
    print(f"\n{'='*70}\n")


async def handle_observer_intervention(pause_flag, teacher, students, time_manager, runtime_snapshot=None):
    """
    处理观察者干预（预留接口）
    
    Args:
        pause_flag: 暂停标志字典
        teacher: 教师实例
        students: 学生字典
        time_manager: 时间管理器
    """
    command = pause_flag.get("command")
    
    if command == "status":
        show_simulation_status(teacher, students, time_manager, runtime_snapshot)
        pause_flag["show_status"] = False
        pause_flag["command"] = None
        
    elif command == "intervene":
        # 调用教师的观察者干预处理方法
        intervention_data = pause_flag.get("intervention", {})
        
        print(f"\n{'='*70}")
        print(f"🔧 [观察者干预] 正在处理...")
        print(f"{'='*70}")
        print(f"干预内容: {json.dumps(intervention_data, indent=2, ensure_ascii=False)}")
        
        # 调用教师的预留接口
        response = await teacher.handle_observer_intervention(intervention_data)
        
        print(f"\n🤖 教师响应: {response}")
        print(f"{'='*70}\n")
        
        pause_flag["intervention"] = None
        pause_flag["command"] = None

    elif command == "rollback":
        rollback_data = pause_flag.get("rollback", {}) or {}
        turn = rollback_data.get("turn") or rollback_data.get("k")
        cls = rollback_data.get("class") or teacher.class_number
        print(f"\n{'='*70}")
        print(f"🔙 [回溯] 正在尝试回溯到: 第{cls}节 第{turn}轮")
        print(f"{'='*70}")
        try:
            if turn is None:
                raise ValueError("缺少 rollback.turn")
            turn = int(turn)
            cls = int(cls)
            status_file = os.path.join(teacher.status_file_dirname, f"status_{cls}_{turn}.json")
            if not os.path.exists(status_file):
                raise FileNotFoundError(f"状态文件不存在: {status_file}")
            ok = teacher.jump(status_file)
            if ok:
                runtime_snapshot["teacher"] = {
                    "action": f"rollback to turn {turn}",
                    "turn": teacher.current_turn,
                    "content": getattr(teacher, "content", "")
                }
                print(f"✅ 已回溯到状态文件: {status_file}")
                print(f"⚠️ 提示: 回溯仅恢复教师状态，学生状态未回滚")
                # 回溯后自动重生成剩余计划（不改变已执行部分）
                try:
                    msg = teacher.regenerate_remaining_plan()
                    print(f"🧠 {msg}")
                except Exception as e2:
                    print(f"⚠️ 重生成剩余计划失败: {e2}")
        except Exception as e:
            print(f"❌ 回溯失败: {e}")
        finally:
            pause_flag["rollback"] = None
            pause_flag["command"] = None
            # 回溯完成后自动继续运行（取消暂停）
            if pause_flag.get("paused", False):
                pause_flag["paused"] = False
                print(f"\n{'='*70}")
                print(f"▶️  回溯完成，自动继续仿真")
                print(f"{'='*70}\n")


async def main():
    global base_log_dir, action_recorder, broadcast_recorder, student_recorder
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base_log_dir = f'logs/{timestamp}'
    sim_wall_start = time.time()

    # 初始化系统组件
    action_recorder = Recorder("")
    broadcast_recorder = Recorder("")
    student_recorder = Recorder("")
    broadcast_system = BroadcastSys(broadcast_recorder)

    # 时间管理器
    time_manager = TimeManager(
        daily_schedule_path="config/schedule.json",
        broadcast_system=broadcast_system,
        day_start_time="08:00"
    )

    # 初始日志设置
    course_id = 1
    switch_log_file(course_id)
    print(f"日志开始记录，初始目录：{base_log_dir}/{course_id}")

    # 初始化学生和教师
    students = initialize_students_from_config("config/student", broadcast_system, student_recorder)
    teacher = await Teacher.initialize_teacher_async(broadcast_system, "config/teacher.json", list(students.values()))

    # 订阅广播系统
    broadcast_system.subscribe(teacher, "teacher")
    for student_name in students:
        student = students[student_name]
        broadcast_system.subscribe(student, "student")
        broadcast_system.subscribe(student, student_name)

    # ========== 启动观察者功能 ==========
    pause_flag = {
        "paused": False,
        "command": None,
        "last_command": None,
        "show_status": False,
        "intervention": None,
        "rollback": None,
        "exit": False
    }
    runtime_snapshot = {"teacher": {}, "students": {}}
    
    # 启动观察者命令监听任务（与主循环并发运行）
    observer_task = asyncio.create_task(
        observer_command_listener(pause_flag, command_file="observer_cmd.json")
    )

    # 主循环
    print("===== 教学场景模拟开始 =====")
    finished_courses = 0
    # 新增：修改了主循环逻辑
    while finished_courses < time_manager.total_courses:
        # ========== 检查观察者命令 ==========
        # 检查退出标志
        if pause_flag.get("exit", False):
            print(f"\n{'='*70}")
            print(f"🛑 [观察者] 收到退出指令，仿真终止")
            print(f"{'='*70}\n")
            observer_task.cancel()
            break
        
        # 检查暂停标志
        if pause_flag.get("paused", False):
            print(f"\n{'='*70}")
            print(f"⏸️  [观察者] 仿真已暂停")
            print(f"{'='*70}")
            
            # 显示当前状态（使用快照填充可能缺失的信息）
            show_simulation_status(teacher, students, time_manager, runtime_snapshot)
            
            print(f"💡 提示: 编辑 observer_cmd.json 文件，设置 'command': 'resume' 以继续")
            print(f"         或设置 'command': 'status' 查看最新状态")
            print(f"{'='*70}\n")
            
            # 等待恢复命令
            while pause_flag.get("paused", False) and not pause_flag.get("exit", False):
                # 处理其他命令（如status、intervene、rollback）
                if pause_flag.get("show_status", False) or pause_flag.get("command") in ["status", "intervene", "rollback"]:
                    await handle_observer_intervention(pause_flag, teacher, students, time_manager, runtime_snapshot)
                
                await asyncio.sleep(0.5)
            
            # 检查是否在暂停期间收到退出命令
            if pause_flag.get("exit", False):
                continue
            
            print(f"\n{'='*70}")
            print(f"▶️  [观察者] 仿真继续")
            print(f"{'='*70}\n")
        
        # 处理非暂停状态下的status/rollback/干预命令
        if pause_flag.get("show_status", False) or pause_flag.get("command") in ["status", "intervene", "rollback"]:
            await handle_observer_intervention(pause_flag, teacher, students, time_manager, runtime_snapshot)
        
        current_date = time_manager.current_time.date()
        print(f"\n=== 日期: {current_date} {current_date.strftime('%A')} ===")

        while True:
            current_time = time_manager.current_time
            print(f"\n时间: {current_time.strftime('%H:%M:%S')}")

            # 即时退出检查（内层循环）
            if pause_flag.get("exit", False):
                break

            current_event = time_manager.get_current_active_event()

            # 小组讨论处理
            if current_event.type == "class":
                # 教师行为
                teacher_action = teacher.move()
                print(teacher_action)
                await action_recorder.log(current_time, "teacher_action",
                                  {"teacher": teacher.name, "action": teacher_action})
                # 更新教师快照
                runtime_snapshot["teacher"] = {
                    "action": teacher_action,
                    "turn": teacher.current_turn,
                    "content": getattr(teacher, "content", "")
                }
                decide_leader = False
                infos = students["StudentA"].infos
                for info in infos:
                    if info.get("active_event") == "group_discussion_start" and info.get("receiver") == "student":
                        decide_leader = True
                        discussion_content = info.get("content", "")
                        break

                if decide_leader:
                    for student in students.values():
                        student.scratch.action = "group_discussion"
                        student.infos = [info for info in student.infos if not (
                                info.get("active_event") == "group_discussion_start" and
                                info.get("receiver") == "student"
                        )]

                    leader_student = random.choice(list(students.values()))
                    leader_student.scratch.isLeader = True
                    msg = BroadcastMessage(
                        message_type=MessageType.COMMAND,
                        active_event="group_discussion_start",
                        speaker=teacher.name,
                        content=discussion_content
                    )
                    teacher.broadcast_sys.publish_sync(leader_student.name, msg)
                    print(msg)

                # 学生行为（异步并发）
                for student in students.values():
                    student.update_students_list(list(students.values()))

                tasks = [student.move() for student in students.values()]
                student_actions = await asyncio.gather(*tasks)

                # 记录学生行为
                for student, action in zip(students.values(), student_actions):
                    if action:
                        print(action)
                        await action_recorder.log(current_time, "student_action",
                                                  {"student": student.name, "action": action})
                    # 更新学生快照
                    runtime_snapshot["students"][student.name] = {
                        "action": action or "",
                        "attention": (
                            getattr(student.scratch, "attention_level", None)
                            if getattr(student.scratch, "attention_level", None) is not None
                            else getattr(student.scratch, "attention", 0.0)
                        )
                    }

            # 课程结束处理
            if current_event.end == current_time:
                overtime_minutes = teacher.delay_turns()
                # 新增：其实不是新增，这里设置了最久只能拖堂9分钟，想修改在这里，但不要超过课间时长
                if overtime_minutes >= 10:
                    overtime_minutes = 9

                action = time_manager.handle_class_end(
                    current_event=current_event,
                    overtime_minutes=overtime_minutes
                )

                if action == ClassEndAction.CLASS_OVER:
                    current_log_dir = f"{base_log_dir}/{current_event.parent_event_id or current_event.id}"
                    os.makedirs(current_log_dir, exist_ok=True)
                    target_path = f'{current_log_dir}/target.txt'
                    with open(target_path, 'w', encoding='utf-8') as target_file:
                        target_file.write(teacher.target)

                    # print("=" * 60)
                    # print("当前课程结束，进行学生反馈环节用于评教")
                    # postfix = f"{timestamp}_{current_event.id}"

                    # 异步执行所有学生的反馈任务
                    # feedback_tasks = []
                    # for student in students.values():
                    #     # 添加做题任务
                    #     exercise_task = asyncio.create_task(
                    #         student_feedback(
                    #             student,
                    #             "做题",
                    #             exercise,
                    #             "student/data.jsonl",
                    #             postfix
                    #         )
                    #     )
                    #     feedback_tasks.append(exercise_task)
                    #
                    #     # 添加问卷任务
                    #     evaluate_task = asyncio.create_task(
                    #         student_feedback(
                    #             student,
                    #             "问卷",
                    #             evaluate,
                    #             "student/问卷.json",
                    #             postfix
                    #         )
                    #     )
                    #     feedback_tasks.append(evaluate_task)
                    #
                    # # 并发执行所有反馈任务
                    # await asyncio.gather(*feedback_tasks)

                    simulation_end = False
                    # 新增：检查课程是否上完
                    finished_courses += 1

                    # 更新所有学生的课程编号
                    for student in students.values():
                        student.set_for_new_class()
                    
                    print(f"=" * 60)
                    print(f"课程 {finished_courses} 结束 (编号: {finished_courses - 1})")
                    print(f"学生状态已保存到: student/saving/{{StudentName}}/{current_time.strftime('%Y%m%d')}_{finished_courses - 1}/")
                    print(f"=" * 60)
                    

                    if finished_courses >= time_manager.total_courses:
                        simulation_end = True
                        break  # 跳出内层循环

                    course_id += 1
                    switch_log_file(course_id)
                    print(f"日志已切换至新目录：{base_log_dir}/{course_id}")

                    # 检查今天是否还有后续课程
                    remaining_today_classes = [
                        e for e in time_manager.events
                        if e.type == "class" and not e.parent_event_id
                            and e.start.date() == current_date
                            and e.start > current_time
                    ]
                    if not remaining_today_classes:
                        print(f"[INFO] {current_date} 的课程已全部结束，进入下一天。")
                        break  # 跳出内层循环

            # === 在推进时间前处理软暂停：先完成当前轮次，再暂停 ===
            if pause_flag.get("paused", False):
                print(f"\n{'='*70}")
                print(f"⏸️  [观察者] 仿真已暂停（当前轮次已完成）")
                print(f"{'='*70}")

                # 展示此刻的最新状态（包含本轮 teacher/student 行为结果）
                show_simulation_status(teacher, students, time_manager, runtime_snapshot)
                print(f"💡 提示: 编辑 observer_cmd.json 文件，设置 'command': 'resume' 以继续")
                print(f"         或设置 'command': 'status' 查看最新状态")
                print(f"{'='*70}\n")

                while pause_flag.get("paused", False) and not pause_flag.get("exit", False):
                    if pause_flag.get("show_status", False) or pause_flag.get("command") in ["status", "intervene", "rollback"]:
                        await handle_observer_intervention(pause_flag, teacher, students, time_manager, runtime_snapshot)
                    await asyncio.sleep(0.2)

                if pause_flag.get("exit", False):
                    break

                print(f"\n{'='*70}")
                print(f"▶️  [观察者] 仿真继续")
                print(f"{'='*70}\n")

            # 时间推进
            time_manager.current_time += timedelta(seconds=time_manager.round_time)
            await asyncio.sleep(0.1)  # 异步等待

        # 新增：检查课程是否上完
        if simulation_end:
            break   # 结束模拟

        # 进入下一天
        time_manager.proceed_to_next_day()

    # ========== 仿真结束清理 ==========
    print("\n===== 模拟完成 =====")
    
    # 取消观察者任务
    if not observer_task.cancelled():
        observer_task.cancel()
        try:
            await observer_task
        except asyncio.CancelledError:
            pass
    
    sim_wall_cost = time.time() - sim_wall_start
    print(f"[TIME] 仿真总耗时: {sim_wall_cost:.2f}s")
    print(f"\n{'='*70}")
    print(f"✅ 仿真已正常结束")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())