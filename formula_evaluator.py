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
        "A",
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
    # Token único de la memoria ANS (sección 2 del plan): sensible a
    # mayúsculas, sin alias (`a`, `Ans`, `ANS`, `Ⓐ` quedan rechazados).
    _ANSWER_IDENTIFIER = "A"
    # Valores que no aceptan llamada: constantes y el átomo de respuesta `A`.
    # `A(...)` se normaliza como multiplicación por un grupo; una llamada con
    # espacio (`A (2)`) se diagnostica aquí como valor no invocable.
    _NON_INVOCABLE_IDENTIFIERS = _CONSTANT_IDENTIFIERS | {_ANSWER_IDENTIFIER}

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

        expr = self._normalize_answer_atom(expr)
        expr = self._replace_factorial(expr)
        expr = expr.replace("^", "**")
        expr = expr.replace("√(", "sqrt(")
        expr = self._replace_percentage(expr)
        expr = self._insert_implicit_mult(expr)
        self._validate_identifiers(expr)

        return expr

    def _normalize_answer_atom(self, expr: str) -> str:
        """Pasada léxica del átomo de respuesta `A` (tabla 3.3 del plan ANS).

        Se ejecuta antes de factorial, porcentaje, multiplicación implícita
        y validación final, y realiza tres transformaciones dirigidas:

        - separa cada secuencia pura de `A` en átomos independientes
          (`AAA` -> `A*A*A`);
        - inserta multiplicación en los límites aprobados (`2A`, `A2`,
          `A.5`, `Aπ`, `πA`, `A(`, `)A`);
        - preserva los literales científicos completos (`1e3A` -> `1e3*A`),
          pues nunca reescribe el interior de un número.

        `A!` y `A%` se delegan a sus pasadas específicas y las
        concatenaciones alfabéticas mixtas (`Ae`, `sinA`, `Api`, ...) se
        dejan intactas para que la validación final las rechace con su
        diagnóstico habitual.
        """
        chars = list(expr)
        out: list[str] = []
        total = len(chars)

        for i, ch in enumerate(chars):
            if ch != self._ANSWER_IDENTIFIER:
                out.append(ch)
                continue

            prev = out[-1] if out else ""
            nxt = chars[i + 1] if i + 1 < total else ""

            if self._answer_needs_mult_before(prev):
                out.append("*")
            out.append(ch)
            if self._answer_needs_mult_after(nxt):
                out.append("*")

        return "".join(out)

    @staticmethod
    def _answer_needs_mult_before(prev: str) -> bool:
        """Límites con multiplicación a la izquierda de `A`.

        `2A` -> `2*A`, `5.A` -> `5.*A`, `)A` -> `)*A`, `πA` -> `π*A` y la
        separación de runs puros (`AA` -> `A*A`). Una letra distinta de `A`
        delante delata una concatenación mixta que validará el final.
        """
        return prev.isdigit() or prev in {".", ")", "π", "A"}

    @staticmethod
    def _answer_needs_mult_after(nxt: str) -> bool:
        """Límites con multiplicación a la derecha de `A`.

        `A2` -> `A*2`, `A.5` -> `A*.5`, `A(` -> `A*(` y `Aπ` -> `A*π`.
        `!` y `%` se reservan a las pasadas de factorial y porcentaje; las
        letras vecinas quedan para el diagnóstico de validación.
        """
        return nxt.isdigit() or nxt in {".", "(", "π"}

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

            # Rama alfabética: acepta el átomo `A` (`A!` -> `factorial(A)`) y
            # cualquier identificador permitido; los runs mixtos que absorbiera
            # se rechazan después en la validación de identificadores.
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
                break
            expr = updated
        # Postfijo `%` sobre el átomo `A` (`A%` -> `(A*0.01)`). El lookbehind
        # evita tocar el átomo cuando una letra vecina delata un run mixto
        # (`eA%`) que debe llegar intacto al diagnóstico de validación.
        return re.sub(r"(?<![A-Za-zπ])A%", r"(A*0.01)", expr)

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

        for non_invocable_name in self._NON_INVOCABLE_IDENTIFIERS:
            if re.search(rf"\b{non_invocable_name}\b\s*\(", expr):
                raise ValueError(f"{non_invocable_name} no es una función")
