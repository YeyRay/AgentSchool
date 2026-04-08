from datetime import datetime, timedelta

class Event:
    _id_counter = -1  # 用于记录当前的 ID 计数器

    def __init__(self, event_type: str, event_name: str, start_time: datetime, end_time: datetime, parent_event_id: str = None):
        """
        初始化事件对象
        ARGS:
            event_type: 事件类型
            event_name: 事件名称
            start_time: 事件开始时间（datetime对象）
            end_time: 事件结束时间（datetime对象）
            parent_event_id: 父事件ID
        type与name的区别，例：group_discussion和math_class的type都为class
        """
        Event._id_counter += 1  # id自增

        self.id = Event._id_counter
        self.type = event_type
        self.name = event_name
        self.start = start_time
        self.end = end_time
        self.parent_event_id = parent_event_id

    def is_conflict(self, other_event) -> bool:
        """检查与另一个事件的时间冲突"""
        if self.parent_event_id ==  other_event.id:
            return False
        return (self.start < other_event.end) and (other_event.start < self.end)

FREE_TIME_EVENT = Event(
    event_type="free_time",
    event_name="空闲时间",
    start_time=None,
    end_time=None
)