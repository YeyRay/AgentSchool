from typing import Dict, Set, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum


class MessageType(Enum):
    """消息类型枚举"""
    EVENT_CHANGE = "event_change"
    COMMAND = "command"
    CLASS = "class"
    ACTIVITY = "activity"
    NEW_DAY = "new_day"

@dataclass
class BroadcastMessage:
    """广播消息类"""
    current_time: Optional[datetime] = None
    message_type: MessageType = None
    active_event: str = ""
    event_id: Optional[int] = None
    speaker: str = ""
    content: str = ""


    def to_dict(self) -> Dict:
        """转换为日志兼容的字典格式"""
        return asdict(self)