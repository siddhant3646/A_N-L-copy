from enum import Enum
from typing import Optional, List
from dataclasses import dataclass, field

class ManagerIntent(str, Enum):
    CLICK = "CLICK"
    TYPE = "TYPE"
    SCROLL = "SCROLL"
    WAIT = "WAIT"
    DONE = "DONE"
    VERIFY = "VERIFY"



@dataclass
class ActionResult:
    action_type: ManagerIntent
    success: bool
    details: str = ""
    error: Optional[str] = None

@dataclass
class SentinelState:
    step_count: int = 0
    task_complete: bool = False
    errors: List[str] = field(default_factory=list)
    last_action: Optional[ManagerIntent] = None
    last_action_result: str = ""
