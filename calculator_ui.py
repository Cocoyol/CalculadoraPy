"""
Interfaz gráfica de la calculadora científica.

Módulo de compatibilidad: re-exporta ResultDisplay y CalculatorApp
desde sus respectivos módulos especializados.
"""

from calculator_ui_results import ResultDisplay  # noqa: F401
from calculator_ui_window import CalculatorApp   # noqa: F401

__all__ = ["ResultDisplay", "CalculatorApp"]
