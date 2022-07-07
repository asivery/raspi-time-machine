from functools import partial
from string import ascii_lowercase, ascii_uppercase, digits, punctuation
from threading import Thread
from time import sleep, time
import types
from config import COPYRIGHT, MODULES, ENCODER_SW_PIN as BTT, ENCODER_DT_PIN as DT, ENCODER_CLK_PIN as CLK
from config_objects import AdditionalEvent, Source
from embed.i2clcd import lcd
from embed.encoder import Encoder
import RPi.GPIO as GPIO
from event_dispatcher import Event, EventDispatcher

def start_embed(dispatcher):
    embed = EmbedThread(dispatcher)
    embed.start()
    return embed

class LcdList:
    def __init__(self, elements, callback=None):
        self.elements = [x if type(x) is tuple else (x, True) for x in elements]
        self.screen_start = 0
        self.selected = 0
        while not self.elements[self.selected][1] and self.selected < len(self.elements) - 1:
            self.selected += 1
        self.callback = callback

    def select(self):
        if self.callback and self.elements[self.selected][1]:
            self.callback(self, self.selected)
    
    def render(self, lcd):
        lcd.clear()
        for i, (elem, selectable) in enumerate(self.elements[self.screen_start:self.screen_start + 2]):
            begin_str = ('>' if self.selected == self.screen_start + i else ' ') if selectable else ''
            max_length = 15 if selectable else 16
            string = f"{begin_str}{elem[:max_length]}"
            lcd.display_string(string, i + 1)
    
    def scroll(self, direction):
        if self.selected + direction not in range(len(self.elements)):
            return False
        
        self.selected += direction

        if self.selected not in range(self.screen_start, self.screen_start + 2):
            self.screen_start += direction

        return True

def nop(*a): pass

class EmbedThread(Thread):
    def __init__(self, dispatcher: EventDispatcher):
        super().__init__()
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BTT, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.add_event_detect(BTT, GPIO.BOTH, callback=partial(EmbedThread.handleEncoderPress, self), bouncetime=5)

        self.list_stack = []
        self.encoder = Encoder(CLK, DT, partial(EmbedThread.handleEncoderTurn, self))
        self.lcd = lcd()

        self.press_override = None
        self.lpress_override = None
        self.turn_override = None

        self.press_time = -1
        self.dispatcher = dispatcher

    def render_topmost_list(self):
        if self.list_stack:
            self.list_stack[-1].render(self.lcd)

    def handleEncoderPress(self, e):
        sleep(.1)
        if not GPIO.input(BTT):
            print("DOWN")
            self.press_time = time()
            return
        print("UP")
        time_duration = time() - self.press_time
        self.press_time = -1

        if time_duration > 5:
            return

        if time_duration > 0.5:
            if self.lpress_override:
                self.lpress_override()
                return
                
            if len(self.list_stack) > 1:
                self.list_stack.pop()
                self.list_stack[-1].render(self.lcd)
            return
        if self.press_override:
            self.press_override()
            return
        
        if self.list_stack:
            self.list_stack[-1].select()

    def handleEncoderTurn(self, val, dir):
        if self.turn_override:
            self.turn_override(val, dir)
            return
        if self.list_stack:
            if self.list_stack[-1].scroll(1 if dir == "R" else -1):
                self.render_topmost_list()

    def update_init(self, log):
        log += ".."
        self.lcd.display_string(" " * 16, 2)
        self.lcd.display_string(log, 2, (16 - len(log)) // 2)
        sleep(.5)

    def end_init(self):
        get_field_name = lambda field: field.name if type(field.name) is not tuple else field.name[1]

        currently_edited_path = None
        currently_edited_module = None

        def handle_module_field_select(path, field, update_callback):
            nonlocal currently_edited_path
            currently_edited_path = path
            new_value = field.value if type(field.value) is not tuple else field.value[1]
            def leave():
                nonlocal currently_edited_path
                currently_edited_path = None

                self.press_override = None
                self.lpress_override = None
                self.turn_override = None
                if field.type not in ["menu", "trigger", "label"]:
                    update_callback(path, new_value)
                    self.dispatcher.handle_event(Event("update_value", [Source.embed, currently_edited_module.name, *path]))
                self.render_topmost_list()
            
            self.press_override = leave
            if field.type == "label":
                leave()
            elif field.type == "int":
                def render_number():
                    self.lcd.clear()
                    self.lcd.display_string(get_field_name(field))
                    as_str = str(new_value)
                    as_str = (' ' * ((16 - len(as_str)) // 2)) + as_str
                    self.lcd.display_string(as_str, 2)
                def turn(_, dir):
                    nonlocal new_value
                    new_value += (-1 if dir == "L" else 1)
                    if AdditionalEvent.partial_update in field.additional_event_handlers:
                        field.additional_event_handlers[AdditionalEvent.partial_update](Source.embed, new_value)
                    render_number()
                self.lpress_override = nop
                self.turn_override = turn
                render_number()
            elif field.type == "bool":
                def render_bool():
                    self.lcd.clear()
                    self.lcd.display_string(get_field_name(field))
                    as_str = "YES" if new_value else "NO"
                    as_str = (' ' * ((16 - len(as_str)) // 2)) + as_str
                    self.lcd.display_string(as_str, 2)
                def turn(_, dir):
                    nonlocal new_value
                    new_value = dir == "R"
                    if AdditionalEvent.partial_update in field.additional_event_handlers:
                        field.additional_event_handlers[AdditionalEvent.partial_update](Source.embed, new_value)
                    render_bool()
                self.lpress_override = nop
                self.turn_override = turn
                render_bool()
            elif field.type == "trigger":
                res = new_value()
                if isinstance(res, types.GeneratorType):
                    last_message = None
                    for message in res:
                        print(message)
                        self.lcd.clear()
                        if last_message == None:
                            self.lcd.display_string(message)
                        else:
                            self.lcd.display_string(last_message)
                            self.lcd.display_string(message, 2)
                        last_message = message
                        sleep(1)
                    self.lcd.display_string(last_message)
                    self.lcd.display_string("-Module Fun End-", 2)
                    sleep(2)
                leave()
            elif field.type == "str":
                current_key = 0
                families = [ascii_uppercase, ascii_lowercase, digits, punctuation[:-1], "\x01"]
                keyboard = ''.join(families)
                last_press = time()
                def render_string():
                    self.lcd.clear()
                    temp_str = new_value
                    if len(temp_str) >= 8:
                        temp_str = new_value[:8] + '\x00' + new_value[8:]
                    else:
                        temp_str += (8 - len(temp_str)) * ' ' + '\x00'
                    self.lcd.display_string(temp_str)
                    k_row = ""
                    for i in range(-8, 8):
                        k_row += keyboard[(current_key + i) % len(keyboard)]
                    self.lcd.display_string(k_row, 2)

                def press():
                    nonlocal current_key
                    nonlocal new_value
                    nonlocal last_press
                    if time() - last_press < 0.2:
                        current_family = None
                        for i, famlily in enumerate(families):
                            if keyboard[current_key] in famlily:
                                current_family = i
                                break
                        if current_family == None:
                            return
                        current_family += 1
                        if current_family not in range(len(families)):
                            current_family = 0
                        offset = len(''.join(families[:current_family]))
                        current_key = offset
                        new_value = new_value[:-1]
                        render_string()
                    else:
                        if current_key == len(keyboard) - 1:
                            leave()
                            return
                        new_value += keyboard[current_key]
                        render_string()
                    if AdditionalEvent.partial_update in field.additional_event_handlers:
                        field.additional_event_handlers[AdditionalEvent.partial_update](Source.embed, new_value)
                    last_press = time()
                def turn(_, dir):
                    nonlocal current_key
                    current_key += (1 if dir == "R" else -1)
                    if current_key >= len(keyboard):
                        current_key = 0
                    elif current_key < 0:
                        current_key = len(keyboard) - 1
                    render_string()
                def del_char():
                    nonlocal new_value
                    new_value = new_value[:-1]
                    render_string()
                
                self.press_override = press
                self.lpress_override = del_char
                self.turn_override = turn
                render_string()
            elif field.type == "date":
                year, month, day = [int(x) for x in new_value.split("-")]
                selected = 0
                def pad(s, l, c="0"):
                    s = str(s)
                    return (l - len(s)) * c + s
                def render_date():
                    date_str = f"{pad(year, 4)}-{pad(month, 2)}-{pad(day, 2)}"
                    padded_date_str = (' ' * ((16 - len(date_str)) // 2)) + date_str
                    padding_length = len(padded_date_str) - len(date_str)
                    sel_str = "\x00\x00" if selected > 0 else "\x00\x00\x00\x00"
                    if selected > 0:
                        padding_length += 5
                    if selected > 1:
                        padding_length += 3
                    self.lcd.clear()
                    self.lcd.display_string(padding_length * " " + sel_str)
                    self.lcd.display_string(padded_date_str, 2)
                def press():
                    nonlocal selected
                    selected += 1
                    if selected > 2:
                        selected = 0
                    render_date()
                def turn(_, dir):
                    nonlocal year, month, day
                    dir = 1 if dir == "R" else -1
                    if selected == 0:
                        year += dir
                        if year < 1:
                            year = 1
                    elif selected == 1:
                        month += dir
                        if month < 1: month = 12
                        elif month > 12: month = 1
                    elif selected == 2:
                        day += dir
                        if day < 1: day = 31
                        elif day > 31: day = 1
                    if AdditionalEvent.partial_update in field.additional_event_handlers:
                        field.additional_event_handlers[AdditionalEvent.partial_update](Source.embed, f"{pad(year, 4)}-{pad(month, 2)}-{pad(day, 2)}")
                    render_date()
                def date_leave():
                    nonlocal new_value
                    new_value = f"{pad(year, 4)}-{pad(month, 2)}-{pad(day, 2)}"
                    leave()

                self.turn_override = turn
                self.press_override = press
                self.lpress_override = date_leave
                render_date()
            elif field.type == "menu":
                elements = [get_field_name(x) for x in new_value]
                proxy_field_select = lambda _, index: handle_module_field_select([ *path, index ], new_value[index], update_callback) 
                new_list = LcdList(elements, proxy_field_select)
                self.list_stack.append(new_list)
                leave()


        def handle_module_select(_, index):
            nonlocal currently_edited_module
            def create_label_text(field):
                name = get_field_name(field)
                value = field.value if type(field.value) is not tuple else field.value[1]
                if name: name += ":"
                return f"{name}{value}"
            module = MODULES[index]
            currently_edited_module = module

            proxy_field_select = lambda _, index: handle_module_field_select([ index ], module.get_fields()[index], lambda path, value: module.update(path, value)) 
            elements = [(create_label_text(x), False) if x.type == "label" else get_field_name(x) for x in module.get_fields()]
            new_list = LcdList(elements, proxy_field_select)
            self.list_stack.append(new_list)
            new_list.render(self.lcd)

        self.list_stack.append(LcdList([x.name for x in MODULES], handle_module_select))
        self.lcd.clear()
        self.render_topmost_list()

        def handle_external_update(event: Event):
            source = event.body[0]
            module_name = event.body[1]
            path = event.body[2:]
            if source == Source.embed: return # loopback
            if not currently_edited_module or not currently_edited_path: return
            if module_name != currently_edited_module.name: return
            if len(path) != len(currently_edited_path): return

            for i, e in enumerate(path):
                if e != currently_edited_path[i]: return
            
            # The save value has just been updated via some other interface
            field = currently_edited_module.get_fields()[path[0]]
            for sub_index in path[1:]:
                field = field.value[sub_index]
            handle_module_field_select(path, field, lambda path, value: currently_edited_module.update(path, value))
        
        def handle_shutdown(event):
            self.lcd.clear()
            self.lcd.display_string(event.body)
        
        self.dispatcher.register_handler("system_shutdown", handle_shutdown)
        self.dispatcher.register_handler("update_value", handle_external_update)


    def run(self):
        print("Started embed thread")
        self.lcd.load_custom_chars([
            [
                0b00100,
                0b00100,
                0b00100,
                0b00100,
                0b00100,
                0b11111,
                0b01110,
                0b00100,
            ],
            [
                0b00000,
                0b01000,
                0b01000,
                0b01010,
                0b01111,
                0b00010,
                0b00000,
                0b00000,
            ]
        ])
        self.lcd.display_string(" PIConfigurator ", 1, 0)
        self.lcd.display_string(COPYRIGHT, 2, 0)
        sleep(.5)
