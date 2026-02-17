"""Motor de cálculo con precisión arbitraria y expansión progresiva."""

from __future__ import annotations

import io
import math
import re
import token
import tokenize

from formula_evaluator import FormulaEvaluator

try:
    from mpmath import mp
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "mpmath no está instalado. Instala con: pip install mpmath"
    ) from exc


class MPMathProvider:
    """Proveedor matemático basado en mpmath."""

    def __init__(self):
        self._angle_mode = "rad"

    @property
    def angle_mode(self) -> str:
        return self._angle_mode

    @angle_mode.setter
    def angle_mode(self, mode: str):
        if mode not in ("rad", "deg"):
            raise ValueError("El modo debe ser 'rad' o 'deg'")
        self._angle_mode = mode

    def _trig(self, fn):
        mode = self._angle_mode

        def wrapped(x):
            value = mp.radians(x) if mode == "deg" else x
            return fn(value)

        return wrapped

    def _inv_trig(self, fn):
        mode = self._angle_mode

        def wrapped(x):
            result = fn(x)
            return mp.degrees(result) if mode == "deg" else result

        return wrapped

    @staticmethod
    def _factorial(x):
        if not mp.isfinite(x):
            raise ValueError("factorial no admite infinito o NaN")

        if mp.floor(x) == x and x >= 0:
            n = int(x)
            if n <= 5000:
                return mp.factorial(n)

            return mp.exp(mp.loggamma(n + 1))

        raise ValueError("factorial requiere entero no negativo")

    def build_namespace(self) -> dict:
        return {
            "sin": self._trig(mp.sin),
            "cos": self._trig(mp.cos),
            "tan": self._trig(mp.tan),
            "asin": self._inv_trig(mp.asin),
            "acos": self._inv_trig(mp.acos),
            "atan": self._inv_trig(mp.atan),
            "ln": mp.log,
            "log": mp.log10,
            "sqrt": mp.sqrt,
            "factorial": self._factorial,
            "exp": mp.exp,
            "abs": abs,
            "mpf": mp.mpf,
            "π": mp.mpf(mp.pi),
            "pi": mp.mpf(mp.pi),
            "e": mp.mpf(mp.e),
        }


class ArbitraryPrecisionCalculatorEngine:
    """Evalúa expresiones con precisión arbitraria y dígitos progresivos."""

    SCI_NOTATION_EXP_LIMIT = 12

    def __init__(self, initial_digits: int = 18, precision_step: int = 24):
        self._provider = MPMathProvider()
        self._evaluator = FormulaEvaluator(self._provider)

        self._initial_digits = max(8, initial_digits)
        self._precision_step = max(8, precision_step)

        self._working_digits = self._initial_digits
        self._last_expression: str | None = None
        self._last_value = None

    @property
    def angle_mode(self) -> str:
        return self._provider.angle_mode

    @angle_mode.setter
    def angle_mode(self, mode: str):
        self._provider.angle_mode = mode

    def evaluate(self, expression: str) -> str:
        self._last_expression = expression
        self._working_digits = self._initial_digits
        self._last_value = self._evaluate_with_digits(expression, self._working_digits)
        return self._format_result(self._last_value, self._working_digits)

    def can_expand_precision(self) -> bool:
        return self._last_expression is not None

    def request_more_precision(self) -> str:
        if not self._last_expression:
            raise ValueError("No hay cálculo previo")

        self._working_digits += self._precision_step
        self._last_value = self._evaluate_with_digits(
            self._last_expression,
            self._working_digits,
        )
        return self._format_result(self._last_value, self._working_digits)

    def _evaluate_with_digits(self, expression: str, digits: int):
        internal_dps = max(40, digits * 2 + 10)
        with mp.workdps(internal_dps):
            if not expression or not expression.strip():
                raise ValueError("Expresión vacía")

            self._evaluator._validate_raw_expression(expression)
            processed = self._evaluator._preprocess(expression)
            processed = self._promote_numeric_literals(processed)
            namespace = self._provider.build_namespace()

            try:
                return eval(processed, {"__builtins__": {}}, namespace)
            except SyntaxError as exc:
                raise ValueError("Error de sintaxis") from exc
            except NameError as exc:
                raise ValueError(f"Desconocido: {exc}") from exc

    @staticmethod
    def _promote_numeric_literals(expression: str) -> str:
        tokens = []
        stream = io.StringIO(expression)
        previous_token_text = ""

        for tok in tokenize.generate_tokens(stream.readline):
            if tok.type == token.NUMBER and not tok.string.lower().endswith("j"):
                is_integer_literal = bool(re.fullmatch(r"\d+", tok.string))
                if is_integer_literal and previous_token_text == "**":
                    promoted = tok.string
                else:
                    promoted = f'mpf("{tok.string}")'
                tok = tokenize.TokenInfo(tok.type, promoted, tok.start, tok.end, tok.line)
            tokens.append(tok)
            if tok.type in {token.OP, token.NUMBER, token.NAME, token.STRING}:
                previous_token_text = tok.string

        return tokenize.untokenize(tokens)

    @staticmethod
    def _format_result(value, digits: int) -> str:
        if isinstance(value, int):
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

        if isinstance(value, mp.mpc):
            real = mp.nstr(value.real, n=digits)
            imag = mp.nstr(abs(value.imag), n=digits)
            sign = "+" if value.imag >= 0 else "-"
            return f"({real} {sign} {imag}j)"

        if isinstance(value, mp.mpf):
            if not mp.isfinite(value):
                if mp.isnan(value):
                    return "NaN"
                return "∞" if value > 0 else "-∞"

            if value == 0:
                return "0"

            if mp.floor(value) == value and abs(value) < mp.mpf("1e18"):
                return str(int(value))

            exponent = int(mp.floor(mp.log10(abs(value))))
            if abs(exponent) >= ArbitraryPrecisionCalculatorEngine.SCI_NOTATION_EXP_LIMIT:
                scientific = mp.nstr(value, n=digits, min_fixed=0, max_fixed=0)
                if (
                    ".0e" in scientific
                    and mp.fmod(value, 10) != 0
                ):
                    return mp.nstr(
                        value,
                        n=digits,
                        min_fixed=0,
                        max_fixed=0,
                        strip_zeros=False,
                    )
                return scientific

            return mp.nstr(value, n=digits)

        try:
            mp_value = mp.mpf(value)
            return mp.nstr(mp_value, n=digits)
        except (TypeError, ValueError):
            pass

        return str(value)