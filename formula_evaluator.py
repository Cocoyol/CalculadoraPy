"""Parseo y evaluación de expresiones para la calculadora científica."""

import re
from difflib import SequenceMatcher


class ExpressionPositionError(ValueError):
    """Error de fórmula asociado a un índice cero-basado del texto original."""

    def __init__(self, message: str, position: int):
        super().__init__(message)
        self.position = position


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
        prepared, _source_positions = self.prepare_with_source_map(expression)
        return prepared

    def prepare_with_source_map(
        self, expression: str
    ) -> tuple[str, tuple[int, ...]]:
        """Normaliza y conserva el origen de cada carácter resultante.

        El mapa permite traducir el ``SyntaxError.offset`` de Python a un
        índice de la fórmula visible, incluso cuando la normalización agregó
        multiplicaciones implícitas o expandió factoriales y porcentajes.
        """
        if not expression or not expression.strip():
            raise ValueError("Expresión vacía")

        self._validate_raw_expression(expression)
        return self._preprocess_with_source_map(expression)

    def _validate_raw_expression(self, expression: str):
        for position, char in enumerate(expression):
            if not self._ALLOWED_CHARS.fullmatch(char):
                raise ExpressionPositionError(
                    "Expresión contiene caracteres inválidos",
                    position,
                )

        forbidden_positions = [
            position
            for position in (
                expression.find("__"),
                *(expression.find(char) for char in "[]{};:"),
            )
            if position >= 0
        ]
        if forbidden_positions:
            raise ExpressionPositionError(
                "Expresión contiene operadores no permitidos",
                min(forbidden_positions),
            )

    def _preprocess(self, expr: str) -> str:
        prepared, _source_positions = self._preprocess_with_source_map(expr)
        return prepared

    def _preprocess_with_source_map(
        self, expr: str
    ) -> tuple[str, tuple[int, ...]]:
        source_length = len(expr)
        source_positions = list(range(source_length))

        def update(updated: str):
            nonlocal expr, source_positions
            source_positions = self._realign_source_positions(
                expr,
                updated,
                source_positions,
                source_length=source_length,
            )
            expr = updated

        update(expr.strip())
        update(expr.replace("×", "*"))
        update(expr.replace("÷", "/"))
        update(expr.replace("−", "-"))
        update(self._normalize_answer_atom(expr))
        update(self._replace_factorial(expr))
        update(expr.replace("^", "**"))
        update(expr.replace("√(", "sqrt("))
        update(self._replace_percentage(expr))
        update(self._insert_implicit_mult(expr))
        self._validate_identifiers(
            expr,
            tuple(source_positions),
            source_length=source_length,
        )

        return expr, tuple(source_positions)

    @staticmethod
    def _realign_source_positions(
        before: str,
        after: str,
        source_positions: list[int],
        *,
        source_length: int,
    ) -> list[int]:
        """Propaga posiciones de origen a través de una transformación.

        Los bloques conservados mantienen su posición exacta. En reemplazos,
        los caracteres nuevos se distribuyen sobre el tramo original; las
        inserciones puras se asocian al límite derecho. Así, por ejemplo, los
        dos ``*`` producidos por ``^`` siguen apuntando al ``^`` visible.
        """
        if before == after:
            return list(source_positions)

        # Ruta lineal para las pasadas que solo insertan caracteres, como
        # `AAA -> A*A*A` y la multiplicación implícita. Evita el coste
        # cuadrático de SequenceMatcher sobre fórmulas repetitivas largas.
        insertion_aligned = [-1] * len(after)
        after_cursor = 0
        for before_index, char in enumerate(before):
            match_index = after.find(char, after_cursor)
            if match_index < 0:
                break
            insertion_aligned[match_index] = source_positions[before_index]
            after_cursor = match_index + 1
        else:
            next_boundary: int | None = None
            for index in range(len(insertion_aligned) - 1, -1, -1):
                if insertion_aligned[index] >= 0:
                    next_boundary = insertion_aligned[index]
                elif next_boundary is not None:
                    insertion_aligned[index] = next_boundary
                elif source_positions:
                    insertion_aligned[index] = min(
                        source_positions[-1] + 1,
                        source_length,
                    )
                else:
                    insertion_aligned[index] = 0
            return insertion_aligned

        aligned = [0] * len(after)
        matcher = SequenceMatcher(None, before, after)

        for tag, before_start, before_end, after_start, after_end in matcher.get_opcodes():
            if tag == "equal":
                aligned[after_start:after_end] = source_positions[
                    before_start:before_end
                ]
                continue
            if tag == "delete":
                continue

            new_count = after_end - after_start
            old_positions = source_positions[before_start:before_end]
            if tag == "replace" and old_positions:
                old_count = len(old_positions)
                for new_offset in range(new_count):
                    old_offset = min(
                        new_offset * old_count // new_count,
                        old_count - 1,
                    )
                    aligned[after_start + new_offset] = old_positions[old_offset]
                continue

            if before_start < len(source_positions):
                boundary = source_positions[before_start]
            elif before_start > 0:
                boundary = min(
                    source_positions[before_start - 1] + 1,
                    source_length,
                )
            else:
                boundary = 0
            aligned[after_start:after_end] = [boundary] * new_count

        return aligned

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

    def _validate_identifiers(
        self,
        expr: str,
        source_positions: tuple[int, ...],
        *,
        source_length: int,
    ):
        errors: list[tuple[int, str, int]] = []

        for match in re.finditer(r"[A-Za-zπ]+", expr):
            name = match.group()
            if name not in self._ALLOWED_IDENTIFIERS:
                errors.append(
                    (
                        match.start(),
                        f"Identificador no permitido: {name}",
                        self._source_cursor_position(
                            source_positions,
                            match.start(),
                            source_length=source_length,
                        ),
                    )
                )

        for function_name in self._FUNCTION_IDENTIFIERS:
            for match in re.finditer(
                rf"\b{function_name}\b(?!\s*\()",
                expr,
            ):
                errors.append(
                    (
                        match.start(),
                        f"Falta '(' después de {function_name}",
                        self._source_cursor_position(
                            source_positions,
                            match.end(),
                            source_length=source_length,
                        ),
                    )
                )

        for non_invocable_name in self._NON_INVOCABLE_IDENTIFIERS:
            for match in re.finditer(
                rf"\b{non_invocable_name}\b\s*\(",
                expr,
            ):
                errors.append(
                    (
                        match.start(),
                        f"{non_invocable_name} no es una función",
                        self._source_cursor_position(
                            source_positions,
                            match.start(),
                            source_length=source_length,
                        ),
                    )
                )

        if errors:
            _prepared_start, message, position = min(errors, key=lambda item: item[0])
            raise ExpressionPositionError(message, position)

    @staticmethod
    def _source_cursor_position(
        source_positions: tuple[int, ...],
        prepared_index: int,
        *,
        source_length: int,
    ) -> int:
        if prepared_index < len(source_positions):
            return max(0, min(source_positions[prepared_index], source_length))
        if source_positions:
            return min(source_positions[-1] + 1, source_length)
        return 0
