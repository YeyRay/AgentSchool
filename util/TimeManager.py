import json
from enum import Enum
from datetime import datetime, timedelta, time as dt_time
from typing import List
from util.BroadcastMessage import BroadcastMessage
from util.BroadcastMessage import MessageType
from util.BroadcastSys import BroadcastSys
from util.Events import Event
from util.Events import FREE_TIME_EVENT


class ClassEndAction(Enum):
    OVERTIME = 0
    CLASS_OVER = 1


class TimeManager:
    def __init__(self, daily_schedule_path, broadcast_system: BroadcastSys, day_start_time):
        self.current_time = None
        self.events: List[Event] = []
        self.last_active_event = None
        self.broadcast_system = broadcast_system
        self.day_start_time = day_start_time
        self.path = daily_schedule_path
        self.round_time = 60  # 默认值
        self.total_courses = None  # 总共要模拟多少节课
        self._load_schedule()  # 初始化时加载日程

    def _load_schedule(self):
        """从 JSON 加载日程，并根据其中的 start_date 设置当前时间"""
        self.events.clear()
        try:
            with open(self.path, "r") as f:
                schedule_data = json.load(f)

            # 获取轮询时间，如果未设置则使用默认值
            self.round_time = schedule_data.get("round_time", self.round_time)

            # 新增：读取要模拟的课程总数
            self.total_courses = schedule_data.get("total_courses", None)

            # 获取 JSON 中指定的 start_date
            if "start_date" not in schedule_data:
                raise ValueError("JSON 文件中必须包含 'start_date' 字段")

            start_date_str = schedule_data["start_date"]
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()

            # 设置 current_time（默认时间为当天 day_start_time）
            day_start_time_obj = datetime.strptime(self.day_start_time, "%H:%M").time()
            self.current_time = datetime.combine(start_date, day_start_time_obj)

            # 获取星期几
            weekday = self.current_time.strftime("%A")
            print(f"[DEBUG] 使用日期：{start_date}，星期：{weekday}")

            daily_events = schedule_data.get(weekday, [])

            print(f"[DEBUG] 加载 {weekday} 的日程: {len(daily_events)} 个事件")

            for event_data in daily_events:
                # 解析时间字符串为时间对象
                start_time_obj = datetime.strptime(event_data["start"], "%H:%M").time()
                end_time_obj = datetime.strptime(event_data["end"], "%H:%M").time()

                # 创建完整的时间日期对象
                event_start = datetime.combine(start_date, start_time_obj)
                event_end = datetime.combine(start_date, end_time_obj)

                new_event = Event(
                    event_type=event_data["type"],
                    event_name=event_data["name"],
                    start_time=event_start,
                    end_time=event_end
                )

                print(
                    f"[DEBUG] 创建事件: {new_event.name} ({event_start.strftime('%H:%M')} - {event_end.strftime('%H:%M')})")
                self.events.append(new_event)

            self.events.sort(key=lambda x: x.start)

            # 打印所有事件用于调试
            print("[DEBUG] 当日事件列表:")
            for event in self.events:
                print(f"  - {event.name}: {event.start.strftime('%H:%M')} 到 {event.end.strftime('%H:%M')}")

        except Exception as e:
            print(f"[ERROR] 加载日程表失败: {str(e)}")
            # 确保即使出错也有一个合理的时间设置
            self.current_time = datetime.combine(datetime.now().date(),
                                                 datetime.strptime(self.day_start_time, "%H:%M").time())

    def get_current_active_event(self) -> Event:
        """获取当前活动的事件"""
        # 使用半开区间 [start, end) 判断事件是否在进行中
        for event in self.events:
            if event.start <= self.current_time <= event.end:
                # 如果有父事件ID，说明是子事件（如拖堂）
                if event.parent_event_id:
                    return event

        # 检查主事件
        for event in self.events:
            if event.start <= self.current_time <= event.end:
                return event

        # 没有事件时返回空闲状态
        return FREE_TIME_EVENT

    def publish_event(self):
        """检测并广播事件变更，若变更返回 True"""
        current_event = self.get_current_active_event()
        changed = False

        # 只有当事件发生变化时才广播
        if current_event != self.last_active_event:
            if self.last_active_event is not None:
                print(f"[EVENT] 活动事件变更: {self.last_active_event.name} -> {current_event.name}")
            else:
                print(f"[EVENT] 初始活动事件: {current_event.name}")

            msg = BroadcastMessage(
                current_time=self.current_time,
                message_type=MessageType.EVENT_CHANGE,
                active_event=current_event.name,
                event_id=current_event.id,
                speaker="time_manager",
                content=f"当前活动已变更为: {current_event.name}",
            )

            # 使用同步广播确保事件立即处理
            self.broadcast_system.publish_sync("all", msg)
            # await self.broadcast_system.publish("all", msg)

            # 更新最后记录的事件
            self.last_active_event = current_event
            changed = True

        return changed

    def add_event(self, new_event: Event):
        """动态添加事件"""
        try:
            # 检查冲突
            for existing_event in self.events:
                if new_event.is_conflict(existing_event):
                    if existing_event.parent_event_id:
                        continue  # 允许覆盖子事件
                    else:
                        raise ValueError(f"事件冲突: {new_event.name} 与 {existing_event.name}")

            # 添加新事件
            self.events.append(new_event)
            self.events.sort(key=lambda x: x.start)
            print(
                f"[EVENT] 添加新事件: {new_event.name} ({new_event.start.strftime('%H:%M')}-{new_event.end.strftime('%H:%M')})")

            # 立即检查事件变更
            self.publish_event()

        except ValueError as e:
            print(f"[ERROR] {str(e)}")

    def handle_class_end(
            self,
            current_event: Event,
            overtime_minutes: int  # 已经算好的拖堂时间
    ) -> ClassEndAction:
        """
        根据 overtime_minutes 决定是否拖堂
        """
        # 只处理课程结束
        if current_event.type != "class":
            return ClassEndAction.OVERTIME  # 不做处理

        # 主课程结束需要拖堂
        if overtime_minutes > 0 and current_event.parent_event_id is None:
            overtime_end = current_event.end + timedelta(minutes=overtime_minutes)
            print(f"[OVERTIME] 检测到拖堂！将延长 {overtime_minutes} 分钟，至 {overtime_end.strftime('%H:%M')}")

            overtime_event = Event(
                event_type="class",
                event_name=f"{current_event.name}[拖堂]",
                start_time=current_event.end,
                end_time=overtime_end,
                parent_event_id=current_event.id
            )
            self.add_event(overtime_event)
            return ClassEndAction.OVERTIME

        # 拖堂结束或课程正常结束不需要拖堂，返回课程结束
        else:
            return ClassEndAction.CLASS_OVER

    def proceed_to_next_day(self):
        """进入下一天"""
        print("\n===== 进入下一天 =====")

        # 计算下一天的日期
        next_day = self.current_time.date() + timedelta(days=1)

        # 更新 current_time 为下一天的 day_start_time
        hour, minute = map(int, self.day_start_time.split(":"))
        self.current_time = datetime.combine(next_day, dt_time(hour, minute))

        # 重置最后活跃事件
        self.last_active_event = None

        # 广播新的一天开始（包含精确时间）
        msg = BroadcastMessage(
            message_type=MessageType.NEW_DAY,
            active_event="new_day",
            speaker="time_manager",
            content=f"新的一天开始了: {self.current_time.strftime('%Y-%m-%d %H:%M')}",
        )
        self.broadcast_system.publish_sync("all", msg)