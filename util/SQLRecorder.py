import json
import datetime
import asyncio
import asyncpg
from typing import List, Dict, Optional, Any
from enum import Enum

# 序列化函数（原）
def default_serializer(obj):
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    elif isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, type.MappingProxyType):
        return dict(obj)
    elif isinstance(obj, Enum):
        return obj.value
    elif hasattr(obj, '__dict__'):
        return obj.__dict__
    elif hasattr(obj, 'to_dict') and callable(obj.to_dict):
        return obj.to_dict()
    raise TypeError(f"无法序列化类型: {type(obj)}")

def make_json_serializable(data):
    """递归处理数据，使其可被 JSON 序列化"""
    if isinstance(data, dict):
        return {k: make_json_serializable(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple)):
        return [make_json_serializable(item) for item in data]
    # 修复了这里：原代码是 data.to_to_dict，应为 to_dict
    elif hasattr(data, 'to_dict') and callable(data.to_dict):
        return make_json_serializable(data.to_dict())
    else:
        return data


class Recorder:
    def __init__(
        self,
        dsn: str,
        session_id: str,
        course_id: str,
        frame_id: int = 0,
        table_name: str = "simulation_logs",
        batch_size: int = 100,
        flush_interval: float = 5.0
    ):
        """
        初始化日志记录器
        :param dsn: 数据库连接字符串
        :param session_id: 会话ID（初始化时必须传入）
        :param course_id: 课程ID（初始化时必须传入）
        :param frame_id: 当前帧ID（可选，默认0）
        :param table_name: 数据表名
        :param batch_size: 批量写入阈值
        :param flush_interval: 自动刷新间隔（秒）
        """
        self.dsn = dsn
        self.table_name = table_name
        self.batch_size = batch_size
        self.flush_interval = flush_interval

        # 上下文信息在初始化时传入
        self._session_id = session_id
        self._course_id = course_id
        self._frame_id = frame_id

        # 缓冲区和连接
        self.buffer: List[tuple] = []
        self.pool: Optional[asyncpg.Pool] = None
        self.flush_task: Optional[asyncio.Task] = None

    async def init(self):
        """初始化数据库连接池和后台刷新任务"""
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=10)
        self.flush_task = asyncio.create_task(self._auto_flush_loop())

    async def close(self):
        """关闭资源：取消定时任务、刷新剩余数据、关闭连接池"""
        if self.flush_task:
            self.flush_task.cancel()
            try:
                await self.flush_task
            except asyncio.CancelledError:
                pass
        await self._flush_buffer()  # 确保最后的数据能写入
        if self.pool:
            await self.pool.close()

    # setter
    def set_session_id(self, session_id: str):
        self._session_id = session_id
        return self  # 支持链式调用

    def set_course_id(self, course_id: str):
        self._course_id = course_id
        return self

    def set_frame_id(self, frame_id: int):
        self._frame_id = frame_id
        return self

    async def student_log(self, details: Dict[str, Any], log_time: Optional[datetime.datetime] = None):
        """
        记录学生状态日志
        """
        name = details.get("name")
        stress = details.get("stress")
        attention = details.get("attention")
        absorbed = details.get("absorbed")
        learned = details.get("learned")
        reflection = details.get("reflection", {})

        # 序列化 reflection 为 JSON 字符串
        reflection_str = json.dumps(
            make_json_serializable(reflection),
            ensure_ascii=False,
            default=default_serializer
        )

        record = (
            log_time or datetime.datetime.now(),
            self._session_id,
            self._course_id,
            self._frame_id,
            "student",          # event_type
            name,               # character
            None,               # action
            None,               # speaker
            None,               # receiver
            None,               # message_type
            None,               # active_event
            None,               # content
            stress,
            attention,
            absorbed,
            learned,
            reflection_str
        )
        self.buffer.append(record)
        if len(self.buffer) >= self.batch_size:
            await self._flush_buffer()

    async def action_log(self, details: Dict[str, Any], log_time: Optional[datetime.datetime] = None):
        """
        记录动作日志（如 listen, raise_hand）
        """
        character = details.get("student")  # 注意：输入是 "student": "StudentA"
        action = details.get("action")

        record = (
            log_time or datetime.datetime.now(),
            self._session_id,
            self._course_id,
            self._frame_id,
            "action",           # event_type
            character,          # character
            action,             # action
            None,               # speaker
            None,               # receiver
            None,               # message_type
            None,               # active_event
            None,               # content
            None,               # stress
            None,               # attention
            None,               # absorbed
            None,               # learned
            None,               # reflection
        )
        self.buffer.append(record)
        if len(self.buffer) >= self.batch_size:
            await self._flush_buffer()

    async def broadcast_log(self, details: Dict[str, Any], log_time: Optional[datetime.datetime] = None):
        """
        记录广播消息日志（如发言、系统通知）
        """
        speaker = details.get("speaker")
        receiver = details.get("receiver")
        message_type = details.get("message_type")
        active_event = details.get("active_event")
        content = details.get("content")

        # 推断 character：优先 speaker
        character = speaker

        record = (
            log_time or datetime.datetime.now(),
            self._session_id,
            self._course_id,
            self._frame_id,
            "broadcast",        # event_type
            character,          # character
            None,               # action
            speaker,            # speaker
            receiver,           # receiver
            message_type,       # message_type
            active_event,       # active_event
            content,            # content
            None,               # stress
            None,               # attention
            None,               # absorbed
            None,               # learned
            None,               # reflection
        )
        self.buffer.append(record)
        if len(self.buffer) >= self.batch_size:
            await self._flush_buffer()

    #  批量写入与定时刷新
    async def _flush_buffer(self):
        if not self.buffer:
            return

        columns = [
            'log_time', 'session_id', 'course_id', 'frame_id', 'event_type',
            'name', 'action', 'speaker', 'receiver', 'message_type',
            'active_event', 'content', 'stress', 'attention', 'absorbed',
            'learned', 'reflection'
        ]

        try:
            async with self.pool.acquire() as conn:
                await conn.copy_records_to_table(
                    self.table_name,
                    records=self.buffer,
                    columns=columns
                )
            self.buffer.clear()
        except Exception as e:
            print(f"批量写入失败: {e}")

    async def _auto_flush_loop(self):
        while True:
            await asyncio.sleep(self.flush_interval)
            if self.buffer:
                await self._flush_buffer()