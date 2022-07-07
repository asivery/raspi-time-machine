from config_objects import Module, Field
import os

from event_dispatcher import Event

def shutdown_command(dispathcer, info, command):
    def _cb():
        dispathcer.handle_event(Event("system_shutdown", info))
        os.system(command)
    return _cb

class SystemModule(Module):
    def __init__(self, dispatcher):
        super().__init__("System", dispatcher)
    def get_fields(self):
        return [
                Field("Shut Down", "trigger", shutdown_command(self.dispatcher, "Shutting down...", "shutdown now")),
                Field("Reboot", "trigger", shutdown_command(self.dispatcher, "Restarting...", "reboot")),
        ]

