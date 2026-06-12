import json
import os
import platform


def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    if platform.system() == "Windows" and os.path.exists("config.dev.json"):
        with open("config.dev.json", "r", encoding="utf-8") as f:
            config.update(json.load(f))

    return config