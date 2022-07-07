from dataclasses import dataclass
from typing import Any, Callable

@dataclass
class Event:
    type: str
    body: Any = None

class EventDispatcher:
    def __init__(self):
        self.handlers = {}

    def register_handler(self, name: str, handler: Callable[[Event], None]):
        if name not in self.handlers:
            self.handlers[name] = []
        self.handlers[name].append(handler)
    
    def unregister_handler(self, name: str, handler: Callable[[Event], None]):
        if name not in self.handlers: return False
        try:
            self.handlers[name].remove(handler)
            return True
        except:
            return False

    def register_handler_once(self, name: str, handler: Callable[[Event], None]):
        def proxy(event):
            self.unregister_handler(name, proxy)
            handler(event)
        self.register_handler(name, proxy)
    
    def handle_event(self, event: Event):
        print(f"Dispatching event {event.type}:{event.body}")
        for handler in self.handlers.get(event.type, []):
            handler(event)
