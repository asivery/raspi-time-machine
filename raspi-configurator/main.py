#!/usr/bin/env python3
from time import sleep
from config import MODULES, construct
from event_dispatcher import EventDispatcher
from webeditor import start_server
from embed.embed import start_embed
from sys import argv

def main(base_only):
    dispatcher = EventDispatcher()

    start_server(dispatcher)
    embed = start_embed(dispatcher)
    sleep(1)
    for log in construct(dispatcher, base_only):
        embed.update_init(log)
        print(f"Initializing {log}...")
    embed.update_init("Init Done")
    print("Init Done")
    embed.end_init()

if __name__ == "__main__":
    base_only = False
    if len(argv) > 1:
        for arg in argv[1:]:
            if arg == "--base-only":
                base_only = True
                print("! Loading only base modules !")
    main(base_only)
