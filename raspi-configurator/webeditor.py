from threading import Thread, Lock, Event as ThreadingEvent
from config import MODULES, COPYRIGHT, HOST, PORT
from config_objects import Field, Source
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import unquote, parse_qs
from types import GeneratorType
from socketserver import ThreadingMixIn

from event_dispatcher import Event, EventDispatcher

def find(array, parameter):
    matching = [x for x in array if parameter(x)]
    if len(matching):
        return matching[0]
    else:
        return None

def get_field_html(field: Field, parent_path: str, field_idx: int):
    field_name = field.name if type(field.name) is not tuple else field.name[0]
    field_value = field.value if type(field.value) is not tuple else field.value[0]
    if field.type == "menu":
        return get_module_html(field_name, field_value, f"{parent_path}/{field_idx}")
    if field.type == "trigger":
        return f"""
            <form action="/{parent_path}/{field_idx}" method="post">
                <input type="submit" value="{field_name}">
            </form><br>
        """
    if field.type == "label":
        return f"""
            <p>{(field_name + ": ") if field_name else ''}<strong>{field_value}</strong></p>
        """
    
    mapped_type = {
        "str": "text",
        "int": "number",
        "bool": "checkbox",
        "date": "date",
    }.get(field.type, None)
    if not mapped_type:
        return f"<p>Invalid type ({field.type}) for field {field_name}</p>"

    return f"""
        <label>
            {field_name}
            <input type="{mapped_type}" name="{field_idx}" {'' if mapped_type == "checkbox" else f'value="{field_value}"'} {'checked' if field_value == True else ''}><br>
        </label>
    """

def get_module_html(name, fields, link_name = None):
    menu_fields = [[i, x] for i, x in enumerate(fields) if x.type in ["menu", "trigger"]]
    fields = [[i, x] for i, x in enumerate(fields) if x.type not in ["menu", "trigger"]]
    return f"""
        <div>
            <fieldset>
                <legend>{name}</legend>
                <form action="/{link_name or name}" method="post">
                    {''.join(get_field_html(x[1], link_name or name, x[0]) for x in fields)}
                    {'<input type="submit" value="Update">' if fields else ''}
                </form>
                {''.join(get_field_html(x[1], link_name or name, x[0]) for x in menu_fields)}
            </fieldset>
        </div>
    """

def get_modules_html():
    return ''.join(get_module_html(x.name, x.get_fields()) for x in MODULES)

reload_lock = Lock()
awaiting_reload = []

class ModuleRequestHandler(BaseHTTPRequestHandler):

    def err(self, code, text):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain;charset=UTF-8")
        self.end_headers()
        self.wfile.write(bytes(text, 'UTF-8'))

    def redirect_root(self):
        self.send_response(301)
        self.send_header("Location", "/")
        self.end_headers()


    def do_POST(self):
        path = [x for x in self.path.split("/") if x]
        module_name = unquote(path[0])
        module = find(MODULES, lambda x: x.name == module_name)
        if not module:
            return self.err(404, f"Cannot find module {module_name}")
        
        path = [int(x) for x in path[1:]]

        fieldset = module.get_fields()
        for idx, path_element in enumerate(path):
            field = fieldset[path_element] if path_element < len(fieldset) else None
            if not field:
                return self.err(404, f"Cannot find field #{path_element} in module {module_name} / {'/'.join(path[:idx])}")
            field_value = field.value if type(field.value) is not tuple else field.value[0]
            if field.type == "menu":
                fieldset = field_value
            elif field.type == "trigger":
                res = field_value()
                if type(res) is GeneratorType:
                    for message in res:
                        print(message)
                return self.redirect_root()
            else:
                return self.err(400, f"Cannot treat field {path_element} of type {field.type} as a fieldset root")
        
        content = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")
        print(content)
        parsed = parse_qs(content, True, encoding="utf-8")
        for idx, field in enumerate(fieldset):
            from_parsed = parsed.get(str(idx))
            field_value = field.value if type(field.value) is not tuple else field.value[0]
            field_value = str(field_value) if field.type != "bool" else field_value
            if not from_parsed or not len(from_parsed):
                if field.type == "bool" and field_value == True:
                    module.update([*path, idx], False)
                    dispatcher.handle_event(Event("update_value", [Source.web, module_name, *path, idx]))
                continue
            
            form_value = from_parsed[0] if field.type != "bool" else from_parsed[0] == "on"
            if field_value != form_value:
                module.update([*path, idx], form_value)
                dispatcher.handle_event(Event("update_value", [Source.web, module_name, *path, idx]))
        return self.redirect_root()


    def do_GET(self):
        if self.path == "/reload.js":
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Access-Control-Allow-Origin", "*")
            content = bytes(f"""
                if (typeof(XMLHttpRequest) != 'undefined') {{
                    var xhr = new XMLHttpRequest()
                    xhr.onreadystatechange = function() {{
                        if(this.readyState == 4 && this.status == 200) {{
                            window.location.reload();
                        }}
                    }};
                    xhr.open("GET", "http://{self.headers.get("Host", "")}/await_reload.js", true);
                    xhr.send();
                }} else {{
                    function load() {{
                        if(document.readyState != "complete") return;
                        var script = window.document.createElement("SCRIPT");
                        script.src = "http://{self.headers.get("Host", "")}/await_reload.js";
                        window.document.body.appendChild(script);
                    }}
                    document.attachEvent("onreadystatechange", load);
                }}
            """, 'ascii')
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
            return
        if self.path == "/await_reload.js":
            reload_lock.acquire()
            awaiter = ThreadingEvent()
            awaiting_reload.append(lambda: awaiter.set())
            reload_lock.release()
            awaiter.wait()
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b"window.location = window.location")
            return

        if self.path != "/":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(bytes(f"The only valid page is the root page. Cannot get {self.path}", "UTF-8"))
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(bytes(f"""
            <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">
            <html>
                <head>
                    <title>Configurator Webview</title>
                </head>
                <body>
                    {get_modules_html()}
                    <hr>
                    <p>{COPYRIGHT}</p>
                    <script src="/reload.js"></script>
                </body>
            </html>
        """, 'utf-8'))

dispatcher = None

def handle_any_updated(_):
    global awaiting_reload
    reload_lock.acquire()
    for e in awaiting_reload:
        try:
            e()
        except:
            pass
    awaiting_reload = []
    reload_lock.release()

def start_server(_dispatcher: EventDispatcher):
    global dispatcher
    dispatcher = _dispatcher
    print("Starting webserver...")
    Thread(None, target=_run_server).start()
    _dispatcher.register_handler("update_value", handle_any_updated)
    _dispatcher.register_handler("module_loaded", handle_any_updated)

class MTHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

def _run_server():
    server = MTHTTPServer((HOST, PORT), ModuleRequestHandler)
    print(f"Server running at {HOST}:{PORT}")
    server.serve_forever()
