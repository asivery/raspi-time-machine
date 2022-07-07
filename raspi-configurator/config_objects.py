from enum import Enum
from typing import Any, Callable, Dict, List
from dataclasses import dataclass, field

from event_dispatcher import EventDispatcher

class AdditionalEvent(Enum):
    partial_update = 0

class Source(Enum):
    embed = "embed"
    web = "web"

@dataclass
class Field:
    name: str
    type: str
    value: Any
    additional_event_handlers: Dict[AdditionalEvent, Callable[[Source, Any], None]] = field(default_factory=dict)

class Module:
    def __init__(self, name: str, dispatcher: EventDispatcher):
        self.name = name
        self.dispatcher = dispatcher

    def get_fields(self) -> List[Field]:
        return []

    def update(self, path: List[int], value: Any):
        pass
