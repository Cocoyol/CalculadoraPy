"""Parseo y evaluación de expresiones para la calculadora científica."""

import re


class FormulaEvaluator:
    """Valida y transforma expresiones de la interfaz."""

    _ALLOWED_CHARS = re.compile(r"^[\d\s+\-*/^().,!%πa-zA-Z×÷−√]*$")
    _ALLOWED_IDENTIFIERS = {
        "sin",
        "cos",
        "tan",
        "asin",
        "acos",
        "atan",
        "ln",
        "log",
        "sqrt",
        "factorial",
        "exp",
        "abs",
        "pi",
        "e",
        "π",
    }
    _FUNCTION_IDENTIFIERS = {
        "sin",
        "cos",
        "tan",
        "asin",
        "acos",
        "atan",
        "ln",
        "log",
        "sqrt",
        "factorial",
        "exp",
        "abs",
    }
    _CONSTANT_IDENTIFIERS = {"pi", "e", "π"}

    def prepare(self, expression: str) -> str:
        if not expression or not expression.strip():
            raise ValueError("Expresión vacía")

        self._validate_raw_expression(expression)
        return self._preprocess(expression)

    def _validate_raw_expression(self, expression: str):
        if not self._ALLOWED_CHARS.fullmatch(expression):
            raise ValueError("Expresión contiene caracteres inválidos")
        if "__" in expression or any(c in expression for c in "[]{};:"):
            raise ValueError("Expresión contiene operadores no permitidos")

    def _preprocess(self, expr: str) -> str:
        expr = expr.strip()

        expr = expr.replace("×", "*")
        expr = expr.replace("÷", "/")
        expr = expr.replace("−", "-")

        expr = self._replace_factorial(expr)
        expr = expr.replace("^", "**")
        expr = expr.replace("√(", "sqrt(")
        expr = self._replace_percentage(expr)
        expr = self._insert_implicit_mult(expr)
        self._validate_identifiers(expr)

        return expr

    def _replace_factorial(self, expr: str) -> str:
        chars = list(expr)
        i = len(chars) - 1

        while i >= 0:
            if chars[i] != "!":
                i -= 1
                continue

            j = i - 1

            if j >= 0 and chars[j] == ")":
                depth = 1
                j -= 1
                while j >= 0 and depth > 0:
                    if chars[j] == ")":
                        depth += 1
                    elif chars[j] == "(":
                        depth -= 1
                    j -= 1
                j += 1
                operand = "".join(chars[j:i])
                chars[j : i + 1] = list(f"factorial({operand})")
                i = j - 1
                continue

            if j >= 0 and (chars[j].isdigit() or chars[j] == "."):
                start = j
                while start > 0 and (
                    chars[start - 1].isdigit() or chars[start - 1] == "."
                ):
                    start -= 1
                operand = "".join(chars[start:i])
                chars[start : i + 1] = list(f"factorial({operand})")
                i = start - 1
                continue

            if j >= 0 and (chars[j].isalpha() or chars[j] == "π"):
                start = j
                while start > 0 and (chars[start - 1].isalpha() or chars[start - 1] == "π"):
                    start -= 1
                operand = "".join(chars[start:i])
                chars[start : i + 1] = list(f"factorial({operand})")
                i = start - 1
                continue

            i -= 1

        return "".join(chars)

    @staticmethod
    def _replace_percentage(expr: str) -> str:
        expr = re.sub(
            r"((?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?)%",
            r"(\1*0.01)",
            expr,
        )
        while True:
            updated = re.sub(r"(\([^()]+\))%", r"(\1*0.01)", expr)
            if updated == expr:
                return expr
            expr = updated

    def _insert_implicit_mult(self, expr: str) -> str:
        patterns = [
            (r"\)\(", ")*("),
            (r"(\d)\(", r"\1*("),
            (r"\)([\dπ])", r")*\1"),
            (r"(\d)(π)", r"\1*\2"),
            (r"(π|(?<!\d)e)([\d(])", r"\1*\2"),
            (r"(\d)([a-df-z])", r"\1*\2"),
            (r"(\d)(e)(?![+\-\d])", r"\1*\2"),
            (r"\)([a-zπ])", r")*\1"),
        ]
        for pat, repl in patterns:
            expr = re.sub(pat, repl, expr)
        return expr

    def _validate_identifiers(self, expr: str):
        for name in re.findall(r"[A-Za-zπ]+", expr):
            if name not in self._ALLOWED_IDENTIFIERS:
                raise ValueError(f"Identificador no permitido: {name}")

        for function_name in self._FUNCTION_IDENTIFIERS:
            if re.search(rf"\b{function_name}\b(?!\s*\()", expr):
                raise ValueError(f"Falta '(' después de {function_name}")

        for constant_name in self._CONSTANT_IDENTIFIERS:
            if re.search(rf"\b{constant_name}\b\s*\(", expr):
                raise ValueError(f"{constant_name} no es una función")
