
# Config begin

COPYRIGHT = "(c)2022, Asivery"

LCD_ADDRESS = 0x27
LCD_I2C_BUS = 1 # i2c bus (0 -- original Pi, 1 -- Rev 2 Pi)

ENCODER_SW_PIN = 27
ENCODER_DT_PIN = 24
ENCODER_CLK_PIN = 23

HOST = "0.0.0.0"
PORT = 8088

CONFIG_ROOT = "/etc/configurator"

# Modules' config
from event_dispatcher import Event
from modules.wifi_module import WifiModule
from modules.time_machine.time_machine_module import TimeMachine
from modules.system_module import SystemModule

ADDITIONAL_MODULES = [ TimeMachine ]
BASE_MODULES = [ WifiModule, SystemModule ]

# Config end

MODULES = []

def construct(dispatcher, base_only):
    global MODULES, BASE_MODULES, ADDITIONAL_MODULES
    
    to_load = BASE_MODULES if base_only else [*ADDITIONAL_MODULES, *BASE_MODULES]
    
    for constructor in to_load:
        yield constructor.__name__
        MODULES.append(constructor( dispatcher ))
        dispatcher.handle_event(Event("module_loaded", constructor.__name__))

