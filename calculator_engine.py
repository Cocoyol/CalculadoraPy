"""
Motor de cálculo para la calculadora científica.

Este módulo provee la clase CalculatorEngine que procesa y evalúa
expresiones matemáticas. Está diseñado como módulo independiente
que puede ser reemplazado por implementaciones alternativas
(e.g., reales constructivos de precisión arbitraria).

Contrato de interfaz:
    - evaluate(expression: str) -> str
    - angle_mode: propiedad 'rad' | 'deg'
"""

import math

from formula_evaluator import FormulaEvaluator, PythonMathProvider


class CalculatorEngine:
    """Evalúa expresiones matemáticas con funciones científicas."""

    def __init__(self):
        self._provider = PythonMathProvider()
        self._evaluator = FormulaEvaluator(self._provider)

    # ── Propiedad: modo angular ──────────────────────────────────

    @property
    def angle_mode(self) -> str:
        return self._provider.angle_mode

    @angle_mode.setter
    def angle_mode(self, mode: str):
        self._provider.angle_mode = mode

    # ── Evaluación principal ─────────────────────────────────────

    def evaluate(self, expression: str) -> str:
        """Evalúa la expresión y devuelve el resultado como cadena.

        Raises:
            ValueError: expresión inválida o función desconocida.
            ZeroDivisionError: división por cero.
            OverflowError: resultado demasiado grande.
        """
        result = self._evaluator.evaluate(expression)
        return self._format_result(result)

    # ── Formato del resultado ────────────────────────────────────

    @staticmethod
    def _format_result(value) -> str:
        if isinstance(value, complex):
            return str(value)

        if isinstance(value, float):
            if math.isnan(value):
                return "NaN"
            if value == float("inf"):
                return "∞"
            if value == float("-inf"):
                return "-∞"
            if value == int(value) and abs(value) < 1e15:
                return str(int(value))
            return f"{value:.15g}"

        return str(value)
