import json
import os
import platform


def load_config():
    try:
        with open("config.json", "r", encoding="utf-8") as base_config_file:
            config = json.load(base_config_file)
    except FileNotFoundError:
        raise FileNotFoundError("Base configuration file not found.")

    if platform.system() == "Windows" and os.path.exists("config.dev.json"):
        try:
            with open("config.dev.json", "r", encoding="utf-8") as dev_config_file:
                dev_config = json.load(dev_config_file)
                config.update(dev_config)
        except FileNotFoundError:
            raise FileNotFoundError("Development configuration file not found.")

    return config