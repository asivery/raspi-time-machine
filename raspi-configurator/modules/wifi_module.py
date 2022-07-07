from event_dispatcher import Event
from config import CONFIG_ROOT
from config_objects import Field, Module
import json
from os.path import join
from dbus.mainloop.glib import DBusGMainLoop
DBusGMainLoop(set_as_default=True)
from time import sleep
from NetworkManager import *
from gi.repository import GObject
from threading import Thread

connectivity_states = {
    0: "Unknown",
    1: "Activating",
    2: "Activated",
    3: "Deactivating",
    4: "Deactivated",
}

transition_states = [1, 3]

CONFIG = join(CONFIG_ROOT, "wifi.json")
loop = None
class MyAgent(SecretAgent):
    def __init__(self, wifi_module):
        super().__init__("_configurator_wifi")
        self.wifi_module = wifi_module
    def GetSecrets(self, settings, connection, setting_name, hints, flags):
        print(f"Agent call! {setting_name}")
        return {setting_name: {'psk': self.wifi_module.password}}

class WifiModule(Module):
    def __init__(self, dispatcher):
        super().__init__("WiFi", dispatcher)
        self.read_config()
        self.agent = MyAgent(self)
        loop = GObject.MainLoop()
        Thread(target=lambda: loop.run()).start()
        self.activeConnection = None
        for x in self.connect_to_wifi(): print(x)

    def read_config(self):
        data = {}
        try:
            with open(CONFIG, 'r') as f:
                data = json.load(f)
        except: pass
        self.ssid = data.get("ssid", "")
        self.password = data.get("pass", "")
        self.interface = data.get("iface", "wlan0")
        self.use_wpa = data.get("useWPA", False)

    def write_config(self):
        with open(CONFIG, 'w') as f:
            json.dump({
                "ssid": self.ssid,
                "pass": self.password,
                "iface": self.interface,
                "useWPA": self.use_wpa,
            }, f)

    def get_fields(self):
        currentState = "Not Configured"
        address = "<None>"
        for conn in NetworkManager.ActiveConnections:
            if conn.Id == "_configurator":
                currentState = connectivity_states[conn.State]
                address = conn.Ip4Config.Addresses[0][0]
                break
        return [
            Field("State", "label", currentState),
            Field("SSID", "str", self.ssid),
            Field("Password", "str", ("X" * 10, self.password)),
            Field("Use WPA2-PSK", "bool", self.use_wpa),
            Field("Interface", "str", self.interface),
            Field("Connect", "trigger", lambda: self.connect_to_wifi()),
            Field(("IP", ""), "label", address),
        ]

    def update(self, path, value):
        if path[0] == 1:
            self.ssid = value
        elif path[0] == 2:
            self.password = value
        elif path[0] == 3:
            self.use_wpa = value if type(value) is bool else value == "on"
        elif path[0] == 4:
            self.interface = value
        self.write_config()

    def connect_to_wifi(self):
        yield "Connecting..."
        device = [x for x in NetworkManager.GetAllDevices() if x.Interface == self.interface]
        if not device:
            yield "No such iface"
            return
        device = device[0]
        conn = {'802-11-wireless': {
                     'mode': 'infrastructure',
                     'security': '802-11-wireless-security',
                     'ssid': self.ssid},
                '802-11-wireless-security': {'auth-alg': 'open',
                              'key-mgmt': 'wpa-psk' if self.use_wpa else 'none',
                              'psk': '_',
                              'psk-flags': 1},
                'connection': {'id': '_configurator',
                'type': '802-11-wireless',
                'uuid': '3dd3d5af-e876-42b7-854d-8f8349dab149'}}
        for x in NetworkManager.ActiveConnections:
            if x.Id == "_configurator":
                print("Deactivated connection " + x.Uuid)
                NetworkManager.DeactivateConnection(x)
        sleep(5)
        yield "Deact prev conns"
        try:
            conn, act, _ = NetworkManager.AddAndActivateConnection2(conn, device, "/", {"persist": "volatile"})
            prev = None
            while act.State in transition_states:
                if prev != act.State:
                    yield f"{connectivity_states[act.State]}..."
                prev = act.State
                sleep(1)
            yield connectivity_states[act.State]
        except:
            yield "Error!"
        self.dispatcher.handle_event(Event("network_changed"))

