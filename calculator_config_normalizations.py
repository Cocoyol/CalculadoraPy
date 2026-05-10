"""Normalizaciones de valores de configuración para la calculadora."""

from calculator_config import get_config_value

def clamp_int(value: any, min_value: int, max_value: int) -> int:
    """Clampa un valor entero entre min_value y max_value."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return min_value
    return max(min_value, min(max_value, value))


# ───────────────────────────────────────────────────────────────────
# VISIBLE_CHARS: número de caracteres visibles en el campo de resultado, limitado entre 17 y 32.
# ───────────────────────────────────────────────────────────────────

def get_visible_chars() -> int:
    """Obtiene el número de caracteres visibles configurado, limitándolo entre 17 y 32."""
    return clamp_int(get_config_value("VISIBLE_CHARS", 17), 17, 32)