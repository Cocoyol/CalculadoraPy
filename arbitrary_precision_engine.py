"""Motor de cálculo con precisión arbitraria, memoria ANS y expansión progresiva."""

from __future__ import annotations

import ast
import io
import math
import re
import threading
import token
import tokenize
from dataclasses import dataclass
from types import CodeType
from typing import Any

from formula_evaluator import ExpressionPositionError, FormulaEvaluator

try:
    from mpmath import mp
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "mpmath no está instalado. Instala con: pip install mpmath"
    ) from exc

# Sentinel inequívoco: las expresiones que no usan `A` no reciben ese nombre
# en su namespace. Un valor inyectado nunca puede coincidir con este objeto.
_ANSWER_VALUE_ABSENT = object()


class ExpressionSyntaxError(ExpressionPositionError):
    """Error sintáctico con posición cero-basada en la fórmula visible."""

    def __init__(self, position: int):
        super().__init__("Error de sintaxis", position)


class _PiScaledTrigTransformer(ast.NodeTransformer):
    """Usa las variantes ``*pi`` cuando el argumento contiene un factor π.

    La transformación conserva π de forma simbólica hasta la función. Así,
    ``cos(pi/2)`` pasa a ``_cospi(1/2)`` y no evalúa primero una aproximación
    finita de π que dejaría un residuo distinto a cada precisión.
    """

    _PI_FUNCTIONS = {"sin": "_sinpi", "cos": "_cospi"}
    _PI_NAMES = {"pi", "π"}

    def visit_Call(self, node: ast.Call) -> ast.AST:
        node = self.generic_visit(node)
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in self._PI_FUNCTIONS
            and len(node.args) == 1
            and not node.keywords
        ):
            pi_coefficient = self._factor_pi(node.args[0])
            if pi_coefficient is not None and not self._contains_pi(pi_coefficient):
                node.func = ast.copy_location(
                    ast.Name(
                        id=self._PI_FUNCTIONS[node.func.id],
                        ctx=ast.Load(),
                    ),
                    node.func,
                )
                node.args[0] = pi_coefficient
        return node

    @classmethod
    def _contains_pi(cls, node: ast.AST) -> bool:
        return any(
            isinstance(part, ast.Name) and part.id in cls._PI_NAMES
            for part in ast.walk(node)
        )

    @classmethod
    def _factor_pi(cls, node: ast.AST) -> ast.AST | None:
        """Devuelve ``node / π`` si puede factorizar un π explícito."""
        if isinstance(node, ast.Name) and node.id in cls._PI_NAMES:
            return ast.copy_location(ast.Constant(value=1), node)

        if isinstance(node, ast.UnaryOp) and isinstance(
            node.op, (ast.UAdd, ast.USub)
        ):
            operand = cls._factor_pi(node.operand)
            if operand is not None:
                return ast.copy_location(
                    ast.UnaryOp(op=node.op, operand=operand),
                    node,
                )
            return None

        if not isinstance(node, ast.BinOp):
            return None

        left = cls._factor_pi(node.left)
        right = cls._factor_pi(node.right)
        if isinstance(node.op, (ast.Add, ast.Sub)):
            if left is None or right is None:
                return None
            return ast.copy_location(
                ast.BinOp(left=left, op=node.op, right=right),
                node,
            )

        if isinstance(node.op, ast.Mult):
            if left is not None:
                return ast.copy_location(
                    ast.BinOp(left=left, op=node.op, right=node.right),
                    node,
                )
            if right is not None:
                return ast.copy_location(
                    ast.BinOp(left=node.left, op=node.op, right=right),
                    node,
                )
            return None

        if isinstance(node.op, ast.Div) and left is not None:
            return ast.copy_location(
                ast.BinOp(left=left, op=node.op, right=node.right),
                node,
            )

        return None


@dataclass(frozen=True, slots=True)
class CalculationRecipe:
    """Receta inmutable y reevaluable de un cálculo (sección 4.1 del plan ANS).

    `source_positions` traduce cada carácter preparado a la fórmula visible.
    `uses_answer` se detecta sobre el nombre compilado exacto (`"A"` en
    `co_names`), nunca buscando la letra dentro del texto. `answer_dependency`
    es `None` tanto para expresiones independientes como para la raíz que usó
    el `A = 0` inicial; `uses_answer` distingue ambos casos y permite volver
    a inyectar ese cero al ampliar precisión.
    """

    source_expression: str
    prepared_expression: str
    compiled_expression: CodeType
    source_positions: tuple[int, ...]
    angle_mode: str
    uses_answer: bool
    answer_dependency: CalculationRecipe | None

    @property
    def depth(self) -> int:
        """Número de nodos de la cadena de dependencias (recorrido iterativo)."""
        count = 0
        node: CalculationRecipe | None = self
        while node is not None:
            count += 1
            node = node.answer_dependency
        return count


@dataclass(frozen=True, slots=True)
class _ActiveCalculation:
    """Cálculo activo mostrado, independiente de la respuesta confirmada.

    Contiene la receta en pantalla, los dígitos de trabajo, el último valor
    calculado y una revisión monotónica propia; una expansión de precisión
    crea una instancia nueva en lugar de mutar la anterior.
    """

    recipe: CalculationRecipe
    working_digits: int
    value: Any
    revision: int


@dataclass(frozen=True, slots=True)
class EvaluationRequest:
    """Solicitud inmutable de evaluación capturada antes del trabajo asíncrono.

    Se crea en el hilo de interfaz (sección 4.4 del plan ANS): fija la
    expresión, el modo angular, la receta ANS confirmada y las revisiones
    vigentes en ese instante. Una ausencia de receta es estable —significa
    `A = 0` durante todo el trabajo— y no puede convertirse en una
    dependencia posterior a mitad de evaluación.
    """

    expression: str
    angle_mode: str
    answer_recipe: CalculationRecipe | None
    answer_revision: int
    active_revision: int


@dataclass(frozen=True, slots=True)
class EvaluationCandidate:
    """Resultado puro de evaluar una solicitud; no muta estado confirmado.

    Lo produce la fase pura del worker. Solo `commit_evaluation()` puede
    promoverlo a cálculo activo y respuesta ANS.
    """

    request: EvaluationRequest
    recipe: CalculationRecipe
    working_digits: int
    value: Any
    formatted_result: str


@dataclass(frozen=True, slots=True)
class PrecisionRequest:
    """Solicitud inmutable de expansión de precisión del cálculo activo.

    Captura la receta mostrada, sus dígitos de trabajo y la revisión del
    cálculo activo en el momento de crear la solicitud.
    """

    recipe: CalculationRecipe
    working_digits: int
    active_revision: int


@dataclass(frozen=True, slots=True)
class PrecisionCandidate:
    """Resultado puro de reevaluar la cadena a mayor precisión.

    Lo produce la fase pura del worker; solo `commit_precision()` puede
    sustituir con él el cálculo activo.
    """

    request: PrecisionRequest
    working_digits: int
    value: Any
    formatted_result: str


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

    @staticmethod
    def _trig(fn, mode: str, *, pi_scaled_fn=None):
        """Adapta una función directa al modo angular del nodo.

        En DEG, ``sinpi`` y ``cospi`` aplican directamente la equivalencia
        ``x grados = (x/180)·π`` y conservan exactos los ángulos notables.
        En RAD, los múltiplos explícitos de π se transforman al compilar la
        receta; los demás argumentos mantienen la evaluación habitual.
        """

        def wrapped(x):
            if mode == "deg" and pi_scaled_fn is not None:
                return pi_scaled_fn(x / mp.mpf(180))

            return fn(x)

        return wrapped

    @staticmethod
    def _inv_trig(fn, mode: str):
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
                return math.factorial(n)

            return mp.exp(mp.loggamma(n + 1))

        raise ValueError("factorial requiere entero no negativo")

    def build_namespace(
        self,
        *,
        angle_mode: str | None = None,
        answer_value: Any = _ANSWER_VALUE_ABSENT,
    ) -> dict:
        """Construye el namespace de evaluación de una expresión.

        `angle_mode` fija el modo de las funciones trigonométricas del nodo
        sin alterar el modo global del proveedor; `None` conserva el modo
        actual (compatibilidad). Un `answer_value` distinto del sentinel
        inyecta el valor de `A` en el namespace; el cero por defecto llega
        construido desde un entero exacto dentro del contexto `workdps`,
        nunca desde un `float`. Las constantes y los literales se
        materializan a la precisión vigente del contexto del llamador.
        """
        mode = self._angle_mode if angle_mode is None else angle_mode
        if mode not in ("rad", "deg"):
            raise ValueError("El modo debe ser 'rad' o 'deg'")

        namespace = {
            "sin": self._trig(mp.sin, mode, pi_scaled_fn=mp.sinpi),
            "cos": self._trig(mp.cos, mode, pi_scaled_fn=mp.cospi),
            "tan": self._trig(mp.tan, mode),
            "asin": self._inv_trig(mp.asin, mode),
            "acos": self._inv_trig(mp.acos, mode),
            "atan": self._inv_trig(mp.atan, mode),
            "ln": mp.log,
            "log": mp.log10,
            "sqrt": mp.sqrt,
            "factorial": self._factorial,
            "exp": mp.exp,
            "abs": abs,
            "mpf": mp.mpf,
            "_sinpi": mp.sinpi,
            "_cospi": mp.cospi,
            "π": mp.mpf(mp.pi),
            "pi": mp.mpf(mp.pi),
            "e": mp.mpf(mp.e),
        }
        if answer_value is not _ANSWER_VALUE_ABSENT:
            namespace["A"] = answer_value
        return namespace


class ArbitraryPrecisionCalculatorEngine:
    """Evalúa expresiones con precisión arbitraria, ANS reevaluable y dígitos progresivos."""

    SCI_NOTATION_EXP_LIMIT = 12
    COMPLEX_DISPLAY_DIGITS = 8

    def __init__(self, initial_digits: int = 18, precision_step: int = 24):
        self._provider = MPMathProvider()
        self._evaluator = FormulaEvaluator()

        self._initial_digits = max(8, initial_digits)
        self._precision_step = max(8, precision_step)

        # Respuesta confirmada: receta del último cálculo correcto y su
        # revisión monotónica. Mientras sea `None`, toda aparición de `A`
        # se resuelve como el cero exacto (decisión 6 del plan ANS).
        self._answer_recipe: CalculationRecipe | None = None
        self._answer_revision = 0

        # Cálculo activo: receta mostrada, dígitos de trabajo, último valor
        # y revisión monotónica propia.
        self._active_calculation: _ActiveCalculation | None = None
        self._active_revision = 0

        # Bloqueo corto para capturas y confirmaciones (sección 4.4 del plan
        # ANS); nunca se mantiene durante un cálculo de mpmath.
        self._state_lock = threading.RLock()

    @property
    def angle_mode(self) -> str:
        return self._provider.angle_mode

    @angle_mode.setter
    def angle_mode(self, mode: str):
        self._provider.angle_mode = mode

    def has_answer(self) -> bool:
        """Indica si existe una receta ANS confirmada.

        Un valor falso no hace inválida a `A` (vale `0`), no deshabilita su
        botón y no autoriza ni impide por sí solo la continuación
        automática de la interfaz.
        """
        return self._answer_recipe is not None

    def clear_active_calculation(self):
        """Limpia la expansión y el resultado activo; conserva la respuesta confirmada."""
        with self._state_lock:
            self._active_calculation = None
            self._active_revision += 1

    def clear_answer(self):
        """Reinicio total explícito: elimina la receta confirmada y el activo.

        Devuelve la semántica de `A` a su valor por defecto `0`. No se usa
        desde `AC`; la interfaz solo limpia el cálculo activo.
        """
        with self._state_lock:
            self._answer_recipe = None
            self._answer_revision += 1
            self.clear_active_calculation()

    def clear_last_calculation(self):
        """Alias de compatibilidad de `clear_active_calculation()`."""
        self.clear_active_calculation()

    # ── Flujo transaccional: solicitud → fase pura → confirmación ────

    def create_evaluation_request(self, expression: str) -> EvaluationRequest:
        """Captura el contexto de una evaluación en el hilo llamador.

        Fija el modo angular, la receta ANS confirmada y las revisiones
        vigentes en este instante; la interfaz lo invoca antes de enviar el
        trabajo al executor. La captura nunca evalúa la expresión ni muta
        estado confirmado.
        """
        with self._state_lock:
            return EvaluationRequest(
                expression=expression,
                angle_mode=self._provider.angle_mode,
                answer_recipe=self._answer_recipe,
                answer_revision=self._answer_revision,
                active_revision=self._active_revision,
            )

    def evaluate_request(self, request: EvaluationRequest) -> EvaluationCandidate:
        """Fase pura: valida, compila y evalúa sin mutar el motor.

        Pensada para ejecutarse en el worker; nunca promueve ANS ni altera
        el cálculo activo. La dependencia de la receta es la capturada en la
        solicitud, por lo que una confirmación ajena posterior no puede
        cambiarla.
        """
        prepared, compiled, source_positions = (
            self._compile_expression_with_source_map(
                request.expression,
                angle_mode=request.angle_mode,
            )
        )
        uses_answer = "A" in compiled.co_names
        recipe = CalculationRecipe(
            source_expression=request.expression,
            prepared_expression=prepared,
            compiled_expression=compiled,
            source_positions=source_positions,
            angle_mode=request.angle_mode,
            uses_answer=uses_answer,
            answer_dependency=request.answer_recipe if uses_answer else None,
        )
        working_digits = self._initial_digits
        value = self._evaluate_recipe_chain(recipe, working_digits)
        return EvaluationCandidate(
            request=request,
            recipe=recipe,
            working_digits=working_digits,
            value=value,
            formatted_result=self._format_result(value, working_digits),
        )

    def commit_evaluation(self, candidate: EvaluationCandidate) -> str:
        """Confirma un candidato vigente como cálculo activo y respuesta ANS.

        Verifica que las revisiones capturadas en la solicitud sigan siendo
        las actuales; un candidato construido con una revisión antigua se
        rechaza con `ValueError` sin tocar estado. Solo esta confirmación —
        nunca la fase pura del worker— puede promover ANS.
        """
        request = candidate.request
        with self._state_lock:
            if self._answer_revision != request.answer_revision:
                raise ValueError("La respuesta cambió durante el cálculo")
            if self._active_revision != request.active_revision:
                raise ValueError("El cálculo activo cambió durante la evaluación")
            self._active_calculation = _ActiveCalculation(
                recipe=candidate.recipe,
                working_digits=candidate.working_digits,
                value=candidate.value,
                revision=self._next_active_revision(),
            )
            self._confirm_answer(candidate.recipe)
        return candidate.formatted_result

    def create_precision_request(self) -> PrecisionRequest:
        """Captura el cálculo activo para una expansión de precisión.

        Aplica las mismas validaciones y mensajes que `request_more_precision()`:
        sin cálculo activo o con un resultado terminal no se puede ampliar.
        """
        with self._state_lock:
            active = self._active_calculation
            if active is None:
                raise ValueError("No hay cálculo previo")
            if self._is_terminal_precision_value(active.value, active.working_digits):
                if self._is_complex_value(active.value):
                    raise ValueError("Los resultados complejos no expanden precisión")
                raise ValueError("Este resultado no admite más precisión")
            return PrecisionRequest(
                recipe=active.recipe,
                working_digits=active.working_digits,
                active_revision=self._active_revision,
            )

    def evaluate_precision_request(
        self, request: PrecisionRequest
    ) -> PrecisionCandidate:
        """Fase pura: reevalúa la cadena completa a la siguiente precisión.

        No muta el motor; la receta confirmada como ANS no interviene
        porque la expansión solo afecta al cálculo activo.
        """
        expanded_digits = request.working_digits + self._precision_step
        value = self._evaluate_recipe_chain(request.recipe, expanded_digits)
        return PrecisionCandidate(
            request=request,
            working_digits=expanded_digits,
            value=value,
            formatted_result=self._format_result(value, expanded_digits),
        )

    def commit_precision(self, candidate: PrecisionCandidate) -> str:
        """Confirma una expansión vigente del cálculo activo.

        Verifica la revisión del cálculo activo capturada en la solicitud;
        si otra operación la modificó, el candidato se rechaza con
        `ValueError` sin cambios. `_answer_recipe` no cambia porque la
        receta ya confirmada es la misma.
        """
        request = candidate.request
        with self._state_lock:
            if self._active_revision != request.active_revision:
                raise ValueError("El cálculo activo cambió durante la expansión")
            self._active_calculation = _ActiveCalculation(
                recipe=request.recipe,
                working_digits=candidate.working_digits,
                value=candidate.value,
                revision=self._next_active_revision(),
            )
        return candidate.formatted_result

    def evaluate(self, expression: str) -> str:
        """Evalúa una expresión y, si termina sin error, la confirma como ANS.

        Envoltorio síncrono del flujo transaccional: limpia el cálculo
        activo, crea la solicitud, evalúa en fase pura y confirma. Si la
        fórmula usa `A` y no existe respuesta confirmada, se evalúa con el
        cero exacto; el primer éxito crea el ANS y su receta registra que
        dependió del cero inicial. Un error limpia solo el cálculo activo y
        conserva la respuesta confirmada anterior.
        """
        self.clear_active_calculation()
        request = self.create_evaluation_request(expression)
        candidate = self.evaluate_request(request)
        return self.commit_evaluation(candidate)

    def can_expand_precision(self) -> bool:
        active = self._active_calculation
        return active is not None and not self._is_terminal_precision_value(
            active.value, active.working_digits
        )

    def request_more_precision(self) -> str:
        """Reevalúa la receta activa completa a la siguiente precisión.

        Envoltorio síncrono del flujo transaccional de expansión. Nunca
        parte del valor finito anterior ni del texto en pantalla: se
        recalcula toda la cadena de dependencias dentro de un único
        contexto de precisión. La receta confirmada como ANS no cambia.
        """
        request = self.create_precision_request()
        candidate = self.evaluate_precision_request(request)
        return self.commit_precision(candidate)

    def _confirm_answer(self, recipe: CalculationRecipe):
        """Confirma una receta como respuesta ANS con una revisión nueva."""
        self._answer_recipe = recipe
        self._answer_revision += 1

    def _next_active_revision(self) -> int:
        self._active_revision += 1
        return self._active_revision

    def _evaluate_recipe_chain(self, recipe: CalculationRecipe, digits: int) -> Any:
        """Evalúa iterativamente la receta y su cadena de dependencias.

        Recorre `answer_dependency` hasta la raíz, invierte la lista y
        evalúa de la más antigua a la más nueva dentro de un único contexto
        `workdps`. Cada nodo construye su namespace con el modo angular
        guardado en la receta; si el nodo usa `A`, se inyecta el valor de su
        dependencia ya evaluada, o el cero exacto cuando es una raíz con
        `uses_answer=True` y sin dependencia. Una receta raíz creada a
        partir de `A` sin respuesta previa se reevalúa contra `0`, nunca
        contra el ANS que ella misma produjo. La evaluación no es recursiva,
        por lo que una cadena larga no depende del límite de recursión de
        Python, y todas las `A` de un mismo nodo leen el mismo valor.
        """
        chain: list[CalculationRecipe] = []
        node: CalculationRecipe | None = recipe
        while node is not None:
            chain.append(node)
            node = node.answer_dependency
        chain.reverse()  # de la más antigua a la más nueva

        internal_dps = max(40, digits * 2 + 10)
        with mp.workdps(internal_dps):
            value: Any = None
            for index, node in enumerate(chain):
                answer_value = _ANSWER_VALUE_ABSENT
                if node.uses_answer:
                    # El nodo anterior de la cadena es exactamente su
                    # dependencia; la raíz inyecta el cero exacto construido
                    # desde un entero dentro del contexto de precisión.
                    answer_value = value if index > 0 else mp.mpf(0)
                namespace = self._provider.build_namespace(
                    angle_mode=node.angle_mode,
                    answer_value=answer_value,
                )
                value = self._eval_recipe_in_namespace(node, namespace)
            return value

    @classmethod
    def _eval_recipe_in_namespace(
        cls,
        recipe: CalculationRecipe,
        namespace: dict,
    ) -> Any:
        try:
            return eval(
                recipe.compiled_expression,
                {"__builtins__": {}},
                namespace,
            )
        except SyntaxError as exc:
            position = cls._runtime_error_source_position(exc, recipe)
            positioned_error = ExpressionSyntaxError(
                len(recipe.source_expression) if position is None else position
            )
            positioned_error.source_expression = recipe.source_expression
            raise positioned_error from exc
        except NameError as exc:
            position = cls._runtime_error_source_position(exc, recipe)
            if position is None:
                raise ValueError(f"Desconocido: {exc}") from exc
            positioned_error = ExpressionPositionError(
                f"Desconocido: {exc}",
                position,
            )
            positioned_error.source_expression = recipe.source_expression
            raise positioned_error from exc
        except (ValueError, ArithmeticError, TypeError) as exc:
            position = cls._runtime_error_source_position(exc, recipe)
            if position is not None and getattr(exc, "position", None) is None:
                try:
                    exc.position = position
                    exc.source_expression = recipe.source_expression
                except (AttributeError, TypeError):
                    pass
            raise

    @staticmethod
    def _runtime_error_source_position(
        error: BaseException,
        recipe: CalculationRecipe,
    ) -> int | None:
        traceback = error.__traceback__
        while traceback is not None:
            if traceback.tb_frame.f_code is recipe.compiled_expression:
                code_positions = list(recipe.compiled_expression.co_positions())
                code_index = traceback.tb_lasti // 2
                if not 0 <= code_index < len(code_positions):
                    return None
                line, _end_line, column, _end_column = code_positions[code_index]
                if line is None or column is None or line <= 0:
                    return None

                lines = recipe.prepared_expression.splitlines(keepends=True)
                if line > len(lines):
                    return None
                prepared_index = sum(len(text) for text in lines[: line - 1]) + column
                if prepared_index >= len(recipe.source_positions):
                    return len(recipe.source_expression)
                return max(
                    0,
                    min(
                        recipe.source_positions[prepared_index],
                        len(recipe.source_expression),
                    ),
                )
            traceback = traceback.tb_next
        return None

    @staticmethod
    def _is_complex_value(value) -> bool:
        return isinstance(value, mp.mpc)

    @staticmethod
    def _is_exact_integer_value(value) -> bool:
        if isinstance(value, int):
            return True

        if isinstance(value, float):
            return math.isfinite(value) and value.is_integer()

        if isinstance(value, mp.mpf):
            return mp.isfinite(value) and mp.fmod(value, 1) == 0

        try:
            mp_value = mp.mpf(value)
        except (TypeError, ValueError):
            return False

        return mp.isfinite(mp_value) and mp.fmod(mp_value, 1) == 0

    @staticmethod
    def _integer_digit_count(value) -> int:
        if value == 0:
            return 1

        return max(1, int(mp.floor(mp.log10(abs(value)))) + 1)

    @staticmethod
    def _is_terminal_precision_value(value, working_digits: int | None = None) -> bool:
        if isinstance(value, mp.mpc):
            return True

        if isinstance(value, int):
            return True

        if isinstance(value, float):
            if not math.isfinite(value):
                return True
            return ArbitraryPrecisionCalculatorEngine._is_exact_integer_value(value)

        if isinstance(value, mp.mpf):
            if not mp.isfinite(value):
                return True
            if not ArbitraryPrecisionCalculatorEngine._is_exact_integer_value(value):
                return False
            if working_digits is None:
                return True

            return ArbitraryPrecisionCalculatorEngine._integer_digit_count(value) <= working_digits

        try:
            mp_value = mp.mpf(value)
        except (TypeError, ValueError):
            return False

        if not mp.isfinite(mp_value):
            return True
        if not ArbitraryPrecisionCalculatorEngine._is_exact_integer_value(mp_value):
            return False
        if working_digits is None:
            return True

        return ArbitraryPrecisionCalculatorEngine._integer_digit_count(mp_value) <= working_digits

    def _prepare_expression(self, expression: str) -> str:
        processed = self._evaluator.prepare(expression)
        return self._promote_numeric_literals(processed)

    def _compile_expression(self, expression: str):
        prepared, compiled, _source_positions = (
            self._compile_expression_with_source_map(expression)
        )
        return prepared, compiled

    def _compile_expression_with_source_map(
        self,
        expression: str,
        *,
        angle_mode: str | None = None,
    ):
        processed, source_positions = self._evaluator.prepare_with_source_map(
            expression
        )
        try:
            prepared, prepared_positions = (
                self._promote_numeric_literals_with_source_map(
                    processed,
                    source_positions,
                    source_length=len(expression),
                )
            )
        except tokenize.TokenError as exc:
            position = self._source_position_from_token_error(
                expression,
                processed,
                source_positions,
            )
            raise ExpressionSyntaxError(position) from exc

        try:
            syntax_tree = ast.parse(prepared, "<calculator>", "eval")
        except (SyntaxError, IndentationError) as exc:
            position = self._source_position_from_syntax_error(
                expression,
                prepared_positions,
                exc,
            )
            raise ExpressionSyntaxError(position) from exc

        mode = self._provider.angle_mode if angle_mode is None else angle_mode
        if mode == "rad":
            syntax_tree = _PiScaledTrigTransformer().visit(syntax_tree)
            ast.fix_missing_locations(syntax_tree)

        compiled = compile(syntax_tree, "<calculator>", "eval")
        return prepared, compiled, prepared_positions

    @staticmethod
    def _source_position_from_syntax_error(
        expression: str,
        source_positions: tuple[int, ...],
        error: SyntaxError,
    ) -> int:
        offset = getattr(error, "offset", None)
        if not isinstance(offset, int) or offset <= 0:
            return len(expression)

        prepared_index = offset - 1
        if prepared_index >= len(source_positions):
            return len(expression)
        return max(0, min(source_positions[prepared_index], len(expression)))

    @staticmethod
    def _source_position_from_token_error(
        expression: str,
        processed: str,
        source_positions: tuple[int, ...],
    ) -> int:
        open_parentheses: list[int] = []
        for index, char in enumerate(processed):
            if char == "(":
                open_parentheses.append(index)
            elif char == ")" and open_parentheses:
                open_parentheses.pop()

        if open_parentheses:
            processed_index = open_parentheses[0]
            return max(
                0,
                min(source_positions[processed_index], len(expression)),
            )
        return len(expression)

    @staticmethod
    def _promote_numeric_literals(expression: str) -> str:
        promoted, _source_positions = (
            ArbitraryPrecisionCalculatorEngine._promote_numeric_literals_with_source_map(
                expression,
                tuple(range(len(expression))),
                source_length=len(expression),
            )
        )
        return promoted

    @staticmethod
    def _promote_numeric_literals_with_source_map(
        expression: str,
        source_positions: tuple[int, ...],
        *,
        source_length: int,
    ) -> tuple[str, tuple[int, ...]]:
        """Promueve números a ``mpf`` sin perder su posición de origen."""
        line_offsets = [0]
        for match in re.finditer(r"\n", expression):
            line_offsets.append(match.end())

        def absolute_index(row: int, column: int) -> int:
            line_index = row - 1
            if line_index >= len(line_offsets):
                return len(expression)
            return min(line_offsets[line_index] + column, len(expression))

        parts: list[str] = []
        promoted_positions: list[int] = []
        stream = io.StringIO(expression)
        previous_token_text = ""
        cursor = 0

        for tok in tokenize.generate_tokens(stream.readline):
            start = absolute_index(*tok.start)
            end = absolute_index(*tok.end)
            if start < cursor or end < start:
                continue

            if start > cursor:
                parts.append(expression[cursor:start])
                promoted_positions.extend(source_positions[cursor:start])

            replacement = tok.string
            token_positions = list(source_positions[start:end])
            if tok.type == token.NUMBER and not tok.string.lower().endswith("j"):
                is_integer_literal = bool(re.fullmatch(r"\d+", tok.string))
                if not (is_integer_literal and previous_token_text == "**"):
                    prefix = 'mpf("'
                    suffix = '")'
                    replacement = f"{prefix}{tok.string}{suffix}"
                    start_origin = (
                        token_positions[0]
                        if token_positions
                        else min(source_length, source_positions[start])
                    )
                    if end < len(source_positions):
                        end_origin = source_positions[end]
                    elif token_positions:
                        end_origin = min(token_positions[-1] + 1, source_length)
                    else:
                        end_origin = source_length
                    token_positions = (
                        [start_origin] * len(prefix)
                        + token_positions
                        + [end_origin] * len(suffix)
                    )

            parts.append(replacement)
            promoted_positions.extend(token_positions)
            cursor = end
            if tok.type in {token.OP, token.NUMBER, token.NAME, token.STRING}:
                previous_token_text = replacement

        if cursor < len(expression):
            parts.append(expression[cursor:])
            promoted_positions.extend(source_positions[cursor:])

        return "".join(parts), tuple(promoted_positions)

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
            complex_digits = min(digits, ArbitraryPrecisionCalculatorEngine.COMPLEX_DISPLAY_DIGITS)
            real = mp.nstr(value.real, n=complex_digits)
            imag = mp.nstr(abs(value.imag), n=complex_digits)
            sign = "+" if value.imag >= 0 else "-"
            return f"({real} {sign} {imag}j)"

        if isinstance(value, mp.mpf):
            if not mp.isfinite(value):
                if mp.isnan(value):
                    return "NaN"
                return "∞" if value > 0 else "-∞"

            if value == 0:
                return "0"

            if (
                ArbitraryPrecisionCalculatorEngine._is_exact_integer_value(value)
                and abs(value) < mp.mpf("1e18")
            ):
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
