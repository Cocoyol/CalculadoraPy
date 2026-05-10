"""Utilidades para leer la configuración JSON de la calculadora."""

import json
import os
import sys
from functools import lru_cache
from typing import Any


_CONFIG_FILENAME = "calculator_config.json"


def _get_base_path() -> str:
    if getattr(sys, 'frozen', False) or '__compiled__' in globals():
        ruta_base = os.path.dirname(sys.executable)
    else:
        ruta_base = os.path.dirname(__file__)
    return ruta_base


def get_config_path(filename: str = _CONFIG_FILENAME) -> str:
    return os.path.join(_get_base_path(), filename)


@lru_cache(maxsize=4)
def load_config(filename: str = _CONFIG_FILENAME) -> dict[str, Any]:
    config_path = get_config_path(filename)
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            data = json.load(config_file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}

    return data if isinstance(data, dict) else {}


# ── Obtención de clave de configuración ─────────────────────────────────────────
def get_config_value(key: str, default: Any = None, filename: str = _CONFIG_FILENAME) -> Any:
    return load_config(filename).get(key, default)


# ── Actualización ───────────────────────────────────────────
def update_config_value(key: str, value: Any, filename: str = _CONFIG_FILENAME) -> None:
    data = load_config(filename).copy()
    data[key] = value
    config_path = get_config_path(filename)
    try:
        with open(config_path, "w", encoding="utf-8") as config_file:
            json.dump(data, config_file, indent=2)
    except OSError:
        pass
    load_config.cache_clear()

    