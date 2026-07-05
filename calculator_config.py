"""Persistencia de la configuración de usuario de la calculadora."""

from __future__ import annotations

import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any


_APP_NAME = "CalculadoraPy"
_CONFIG_FILENAME = "calculator_config.json"
_FALLBACK_CONFIG: dict[str, Any] = {
    "VISIBLE_CHARS": 17,
    "DECIMAL_SEPARATOR": 1,
}


def _get_local_app_data_dir() -> Path:
    """Devuelve el directorio estándar para datos locales del usuario."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data)
    return Path.home() / "AppData" / "Local"


def _get_user_config_path(filename: str = _CONFIG_FILENAME) -> Path:
    return _get_local_app_data_dir() / _APP_NAME / filename


def _get_default_config(filename: str) -> dict[str, Any]:
    if filename == _CONFIG_FILENAME:
        return _FALLBACK_CONFIG.copy()
    return {}


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as config_file:
            data = json.load(config_file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _atomic_write_json(destination: Path, data: dict[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(data, temporary_file, indent=2, ensure_ascii=False)
            temporary_file.write("\n")
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def initialize_config(filename: str = _CONFIG_FILENAME) -> str:
    """Garantiza una configuración válida y editable para el usuario.

    Si el archivo no existe o contiene JSON inválido, se crea desde los valores
    integrados. Las claves nuevas se agregan sin sobrescribir preferencias ni
    claves desconocidas presentes en configuraciones de versiones anteriores.
    """
    user_path = _get_user_config_path(filename)
    stored_config = _read_json_object(user_path)
    default_config = _get_default_config(filename)

    if stored_config is None:
        config = default_config
    else:
        config = default_config.copy()
        config.update(stored_config)
        if config == stored_config:
            return str(user_path)

    try:
        _atomic_write_json(user_path, config)
    except OSError:
        return str(user_path)

    load_config.cache_clear()
    return str(user_path)


def get_config_path(filename: str = _CONFIG_FILENAME) -> str:
    return initialize_config(filename)


@lru_cache(maxsize=4)
def load_config(filename: str = _CONFIG_FILENAME) -> dict[str, Any]:
    config_path = Path(initialize_config(filename))
    return _read_json_object(config_path) or _get_default_config(filename)


def get_config_value(
    key: str,
    default: Any = None,
    filename: str = _CONFIG_FILENAME,
) -> Any:
    return load_config(filename).get(key, default)


def update_config_value(
    key: str,
    value: Any,
    filename: str = _CONFIG_FILENAME,
) -> None:
    data = load_config(filename).copy()
    data[key] = value
    destination = _get_user_config_path(filename)
    try:
        _atomic_write_json(destination, data)
    except OSError:
        return
    load_config.cache_clear()
