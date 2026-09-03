from typing import Any

from arbitrary_precision_engine import (
    ArbitraryPrecisionCalculatorEngine,
    ExpressionSyntaxError,
)
from calculator_ui_window import CalculatorApp


class _FakeResultDisplay:
    def __init__(self):
        self._loading_more = True
        self._precision_exhausted = False
        self.mark_calls = 0
        self.finish_calls = 0
        self.text_updates: list[tuple[str, bool]] = []

    def finish_loading_more(self):
        self._loading_more = False
        self.finish_calls += 1

    def mark_precision_exhausted(self):
        self._precision_exhausted = True
        self.mark_calls += 1

    def reset_precision_exhausted(self):
        self._precision_exhausted = False

    def set_text(self, text: str, preserve_view: bool = False):
        self.text_updates.append((text, preserve_view))


class _FakeStringVar:
    def __init__(self, value: str = ""):
        self._value = value

    def get(self) -> str:
        return self._value

    def set(self, value: str):
        self._value = value


class _FakeExprEntry:
    def __init__(self):
        self.state = "normal"
        self.focus_calls = 0
        self.cursor = 0
        self.xview_calls = []
        self.selection_clear_calls = 0

    def focus_set(self):
        self.focus_calls += 1
        return None

    def index(self, _what):
        return self.cursor

    def icursor(self, pos):
        self.cursor = pos
        return None

    def xview(self, *args):
        self.xview_calls.append(args)
        return None

    def configure(self, **kw):
        if "state" in kw:
            self.state = kw["state"]

    def selection_clear(self):
        self.selection_clear_calls += 1


class _FakeRoot:
    def __init__(self):
        self.focus_calls = 0

    def focus_set(self):
        self.focus_calls += 1


class _FakeKeyEvent:
    def __init__(
        self, *, char: str, keysym: str | None = None, state: int = 0, widget=None
    ):
        self.char = char
        self.keysym = keysym if keysym is not None else char
        self.state = state
        self.widget = widget


class _UnpositionedEvaluationEngine:
    """Motor que falla sin poder asociar el error a una posición."""

    def create_evaluation_request(self, expression: str) -> str:
        return expression

    def evaluate_request(self, _request: str):
        raise ValueError("fallo sin posición")

    def clear_last_calculation(self):
        return None

    def can_expand_precision(self) -> bool:
        return False


class _PrecisionFailureEngine:
    """Motor de prueba por etapas: la fase pura de expansión falla."""

    def can_expand_precision(self) -> bool:
        return True

    def create_precision_request(self) -> object:
        return object()

    def evaluate_precision_request(self, _request: object) -> str:
        raise ValueError("fallo de prueba")


class _StalePrecisionFailureEngine:
    """Motor de prueba por etapas: la expansión queda obsoleta mientras corre
    la fase pura, igual que cuando otro trabajo arranca en medio."""

    def __init__(self, harness):
        self._harness = harness

    def can_expand_precision(self) -> bool:
        return True

    def create_precision_request(self) -> object:
        return object()

    def evaluate_precision_request(self, _request: object) -> str:
        # Otro trabajo arranca mientras este corre: queda obsoleto y falla.
        self._harness._active_background_job_id += 1
        raise ValueError("fallo obsoleto")


class _Harness:
    _expression_is_inactive = CalculatorApp._expression_is_inactive
    _set_expression_editable = CalculatorApp._set_expression_editable
    _focus_expression_if_editable = CalculatorApp._focus_expression_if_editable
    _deactivate_expression_after_result = (
        CalculatorApp._deactivate_expression_after_result
    )
    _activate_expression_for_editing = CalculatorApp._activate_expression_for_editing
    _reset_for_new_formula = CalculatorApp._reset_for_new_formula
    _begin_new_formula_from_inactive_result = (
        CalculatorApp._begin_new_formula_from_inactive_result
    )
    _on_inactive_result_key = CalculatorApp._on_inactive_result_key
    _insert_at_cursor = CalculatorApp._insert_at_cursor
    _resolve_button_insertion = CalculatorApp._resolve_button_insertion
    _science_button_insertion = CalculatorApp._science_button_insertion

    def __init__(self, engine):
        # Los arneses simulan CalculatorApp con fakes; Any evita que el
        # verificador de tipos objete los motores de prueba intercambiables.
        self.engine: Any = engine
        self.root = _FakeRoot()
        self.expr_var = _FakeStringVar()
        self.expr_entry = _FakeExprEntry()
        self.result_display = _FakeResultDisplay()
        self._last_engine_result: str | None = "0.5"
        self._history = []
        self._history_window = None
        self._expr_inactive_after_result = False
        self._valid_result_visible = False
        self._closing = False
        self._background_job_seq = 0
        self._active_background_job_id = 0

    def _next_background_job_id(self) -> int:
        self._background_job_seq += 1
        self._active_background_job_id = self._background_job_seq
        return self._active_background_job_id

    def _is_active_background_job(self, job_id: int) -> bool:
        return not self._closing and job_id == self._active_background_job_id

    def _engine_can_expand_precision(self) -> bool:
        checker = getattr(self.engine, "can_expand_precision", None)
        return bool(checker()) if callable(checker) else True

    def _clear_engine_precision_state(self):
        clearer = getattr(self.engine, "clear_last_calculation", None)
        if callable(clearer):
            clearer()

    def _schedule_on_ui_thread(self, callback, job_id: int | None = None):
        if self._closing:
            return
        if job_id is not None and not self._is_active_background_job(job_id):
            return
        callback()

    def _submit_background(self, fn) -> bool:
        fn()
        return True

    def _sync_result_precision_availability(self):
        if self._engine_can_expand_precision():
            self.result_display.reset_precision_exhausted()
        else:
            self.result_display.mark_precision_exhausted()

    def _add_to_history(self, expr: str, result: str):
        self._history.append((expr, result))


def _assert(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def check_angle_mode_persistence() -> None:
    engine = ArbitraryPrecisionCalculatorEngine(initial_digits=18, precision_step=24)
    engine.angle_mode = "deg"
    initial = engine.evaluate("sin(30)")
    engine.angle_mode = "rad"
    expanded = engine.request_more_precision()

    _assert(initial == "0.5", f"sin(30) en DEG devolvio {initial!r}")
    _assert(expanded.startswith("0.5"), f"mas precision cambio el valor a {expanded!r}")
    _assert(
        engine.angle_mode == "rad",
        "request_more_precision altero el modo angular actual",
    )


def check_syntax_normalization() -> None:
    expressions = ["sin(", "1..2", "2+", "sqrt("]

    for expression in expressions:
        engine = ArbitraryPrecisionCalculatorEngine()
        try:
            engine.evaluate(expression)
        except Exception as exc:  # pragma: no branch - regression harness
            _assert(
                isinstance(exc, ValueError),
                f"{expression!r} produjo {type(exc).__name__} en lugar de ValueError",
            )
            _assert(
                str(exc) == "Error de sintaxis",
                f"{expression!r} produjo mensaje inesperado: {exc!r}",
            )
        else:
            raise AssertionError(f"{expression!r} debio fallar con Error de sintaxis")


def check_syntax_error_positions_use_original_formula() -> None:
    cases = {
        "1+*2": 2,
        "sin(": 3,
        "2+": 2,
        "1..2": 2,
        "5!+*2": 3,
        "A%+*3": 3,
        "√(2+)": 4,
        "2(3+)": 4,
        "  1 + * 2  ": 6,
        "001+sin(": 7,
    }

    for expression, expected_position in cases.items():
        try:
            ArbitraryPrecisionCalculatorEngine().evaluate(expression)
        except ExpressionSyntaxError as exc:
            _assert(
                str(exc) == "Error de sintaxis",
                f"mensaje inesperado para {expression!r}: {exc}",
            )
            _assert(
                exc.position == expected_position,
                f"{expression!r} señaló {exc.position}, esperado {expected_position}",
            )
        else:
            raise AssertionError(f"{expression!r} debió producir error sintáctico")


def check_validation_and_runtime_error_positions() -> None:
    cases = [
        ("1+@2", "Expresión contiene caracteres inválidos", 2),
        ("2+foo", "Identificador no permitido: foo", 2),
        ("1+sin 30", "Falta '(' después de sin", 5),
        ("sin 2+foo", "Falta '(' después de sin", 3),
        ("1+pi(2)", "pi no es una función", 2),
        ("2+1/0", "", 2),
        ("1+factorial(-1)", "factorial requiere entero no negativo", 2),
        ("(-1)!", "factorial requiere entero no negativo", 0),
    ]

    for expression, expected_message, expected_position in cases:
        try:
            ArbitraryPrecisionCalculatorEngine().evaluate(expression)
        except (ValueError, ArithmeticError) as exc:
            _assert(
                str(exc) == expected_message,
                f"mensaje inesperado para {expression!r}: {exc!r}",
            )
            _assert(
                getattr(exc, "position", None) == expected_position,
                f"{expression!r} no señaló la posición {expected_position}",
            )
        else:
            raise AssertionError(f"{expression!r} debió fallar")


def check_failed_evaluation_clears_previous_precision_state() -> None:
    """Un error limpia el cálculo activo y conserva la respuesta confirmada."""
    engine = ArbitraryPrecisionCalculatorEngine()
    engine.evaluate("1/3")
    _assert(
        engine.can_expand_precision(), "faltó estado expandible tras un cálculo válido"
    )
    _assert(
        engine.has_answer(), "un cálculo correcto debe crear la respuesta confirmada"
    )

    try:
        engine.evaluate("sin(")
    except ValueError as exc:
        _assert(
            str(exc) == "Error de sintaxis", f"mensaje inesperado tras fallo: {exc!r}"
        )
    else:
        raise AssertionError("sin( debio fallar con Error de sintaxis")

    _assert(
        not engine.can_expand_precision(),
        "un fallo dejó expandible el cálculo anterior",
    )
    _assert(
        engine.has_answer(),
        "el error debe limpiar solo el activo y conservar el ANS confirmado",
    )

    try:
        engine.request_more_precision()
    except ValueError as exc:
        _assert(
            str(exc) == "No hay cálculo previo",
            f"mensaje inesperado al expandir tras error: {exc!r}",
        )
    else:
        raise AssertionError("request_more_precision debio rechazar un error previo")

    _assert(
        engine.evaluate("A*3") == "1",
        "el ANS conservado tras el error debe seguir siendo reutilizable",
    )


def check_clear_invalidates_previous_precision_state() -> None:
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())
    harness.engine.evaluate("1/3")
    _assert(
        harness.engine.can_expand_precision(), "faltó estado expandible previo al clear"
    )

    CalculatorApp._on_key(harness, "clear")  # type: ignore[arg-type]

    _assert(
        not harness.engine.can_expand_precision(),
        "clear conservó un cálculo expandible obsoleto",
    )
    _assert(
        harness.result_display.text_updates[-1][0] == "0",
        "clear no restauró el texto base",
    )
    _assert(
        harness.result_display.mark_calls == 1, "clear debe bloquear nuevas expansiones"
    )


def check_successful_calculation_deactivates_expression() -> None:
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())
    harness.expr_var.set("1+1")

    CalculatorApp._calculate(harness)  # type: ignore[arg-type]

    _assert(
        harness.result_display.text_updates[-1][0] == "2",
        "la UI no mostró el resultado esperado",
    )
    _assert(
        harness._expr_inactive_after_result, "el resultado no dejó inactiva la fórmula"
    )
    _assert(
        harness.expr_entry.state == "readonly",
        "la fórmula calculada debe quedar en solo lectura",
    )
    _assert(harness.root.focus_calls == 1, "faltó retirar el foco del campo de entrada")


def check_next_button_after_result_starts_new_formula() -> None:
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())
    harness.engine.evaluate("1/3")
    harness.expr_var.set("1/3")
    harness._expr_inactive_after_result = True
    harness.expr_entry.state = "readonly"

    CalculatorApp._on_key(harness, "insert:7")  # type: ignore[arg-type]

    _assert(
        harness.expr_var.get() == "7",
        "el primer botón tras el resultado debe iniciar una fórmula nueva",
    )
    _assert(
        harness.result_display.text_updates[-1][0] == "0",
        "faltó limpiar el resultado anterior",
    )
    _assert(
        harness.expr_entry.state == "normal", "la nueva fórmula debe quedar editable"
    )
    _assert(
        not harness._expr_inactive_after_result,
        "la nueva fórmula no debe quedar inactiva",
    )
    _assert(
        not harness.engine.can_expand_precision(),
        "el nuevo ingreso conservó precisión expandible previa",
    )


def check_physical_key_after_result_starts_new_formula() -> None:
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())
    harness.engine.evaluate("1/3")
    harness.expr_var.set("1/3")
    harness._expr_inactive_after_result = True
    harness.expr_entry.state = "readonly"
    event = _FakeKeyEvent(char="8", widget=harness.expr_entry)

    handled = CalculatorApp._on_inactive_result_key(harness, event)  # type: ignore[arg-type]

    _assert(
        handled == "break",
        "la tecla física debe detener el manejo por defecto del Entry",
    )
    _assert(
        harness.expr_var.get() == "8",
        "la primera tecla física tras el resultado debe iniciar fórmula nueva",
    )
    _assert(
        harness.result_display.text_updates[-1][0] == "0",
        "faltó limpiar el resultado anterior",
    )
    _assert(
        harness.expr_entry.state == "normal",
        "la tecla física debe restaurar edición para la nueva fórmula",
    )
    _assert(
        not harness._expr_inactive_after_result,
        "la fórmula nueva no debe quedar inactiva",
    )


def check_lateral_arrows_recover_finished_formula() -> None:
    cases = [
        (ArbitraryPrecisionCalculatorEngine, "1/3", "resultado"),
        (_UnpositionedEvaluationEngine, "1+1", "error sin posición"),
    ]
    arrows = [
        ("Left", lambda expression: len(expression), "derecho"),
        ("Right", lambda _expression: 0, "izquierdo"),
    ]

    for engine_factory, expression, outcome in cases:
        for keysym, expected_cursor, edge in arrows:
            harness = _Harness(engine_factory())
            harness.expr_var.set(expression)
            CalculatorApp._calculate(harness)  # type: ignore[arg-type]
            result_updates = list(harness.result_display.text_updates)

            _assert(
                harness._expr_inactive_after_result,
                f"el {outcome} debe dejar la fórmula lista para recuperarse",
            )
            handled = CalculatorApp._on_inactive_result_key(
                harness,
                _FakeKeyEvent(char="", keysym=keysym),
            )  # type: ignore[arg-type]

            _assert(handled == "break", f"{keysym} debe consumir el evento")
            _assert(
                harness.expr_var.get() == expression,
                f"{keysym} no debe borrar la fórmula tras un {outcome}",
            )
            _assert(
                not harness._expr_inactive_after_result
                and harness.expr_entry.state == "normal",
                f"{keysym} debe restaurar la edición tras un {outcome}",
            )
            _assert(
                harness.expr_entry.cursor == expected_cursor(expression),
                f"{keysym} debe colocar el cursor en el extremo {edge}",
            )
            _assert(
                harness.expr_entry.xview_calls[-1] == ("insert",),
                f"{keysym} debe hacer visible el extremo {edge}",
            )
            _assert(
                harness.expr_entry.focus_calls == 1,
                f"{keysym} debe devolver el foco a la fórmula",
            )
            _assert(
                harness.result_display.text_updates == result_updates,
                f"{keysym} no debe reemplazar el {outcome} visible",
            )

    active = _Harness(ArbitraryPrecisionCalculatorEngine())
    active.expr_var.set("123")
    active.expr_entry.cursor = 2
    handled = CalculatorApp._on_inactive_result_key(
        active,
        _FakeKeyEvent(char="", keysym="Left"),
    )  # type: ignore[arg-type]
    _assert(handled is None, "una fórmula activa debe conservar el manejo normal")
    _assert(active.expr_entry.cursor == 2, "el handler alteró una fórmula activa")


def check_button_insert_keeps_cursor_visible() -> None:
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())
    expression = "12312312312312312312312312312312"
    harness.expr_var.set(expression)
    harness.expr_entry.cursor = len(expression)

    CalculatorApp._insert_at_cursor(harness, "3")  # type: ignore[arg-type]

    _assert(
        harness.expr_var.get() == expression + "3",
        "el botón no insertó el carácter al final",
    )
    _assert(
        harness.expr_entry.cursor == len(expression) + 1,
        "el cursor no quedó tras el carácter insertado",
    )
    _assert(
        harness.expr_entry.xview_calls[-1] == ("insert",),
        "el input no desplazó la vista hacia el cursor",
    )


def check_calculate_error_marks_precision_exhausted() -> None:
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())
    harness.engine.evaluate("1/3")
    harness.expr_var.set("sin(")

    CalculatorApp._calculate(harness)  # type: ignore[arg-type]

    _assert(
        harness.result_display.text_updates[-1][0] == "Error: Error de sintaxis",
        "la UI no mostró el error esperado",
    )
    _assert(
        harness.result_display.mark_calls == 1,
        "la UI no bloqueó la expansión sobre el error",
    )
    _assert(
        harness.result_display._precision_exhausted,
        "faltó marcar el error como no expandible",
    )
    _assert(
        not harness.engine.can_expand_precision(),
        "la UI dejó vivo el cálculo anterior tras el error",
    )
    _assert(
        not harness._expr_inactive_after_result,
        "el error sintáctico debe devolver la fórmula a edición",
    )
    _assert(
        harness.expr_entry.state == "normal",
        "la fórmula errónea debe quedar editable",
    )
    _assert(
        harness.expr_entry.cursor == 3,
        "el cursor debe señalar el paréntesis no cerrado de 'sin('",
    )
    _assert(
        harness.expr_entry.xview_calls[-1] == ("insert",),
        "la posición del error debe quedar visible",
    )
    _assert(
        harness.expr_entry.focus_calls == 1 and harness.root.focus_calls == 0,
        "el error sintáctico debe devolver el foco al campo de fórmula",
    )


def check_positioned_errors_focus_original_formula() -> None:
    cases = [
        ("1+@2", "Error: Expresión contiene caracteres inválidos", 2),
        ("2+foo", "Error: Identificador no permitido: foo", 2),
        ("1+sin 30", "Error: Falta '(' después de sin", 5),
        ("1+pi(2)", "Error: pi no es una función", 2),
        ("2+1/0", "Error: ZeroDivisionError", 2),
        (
            "1+factorial(-1)",
            "Error: factorial requiere entero no negativo",
            2,
        ),
    ]

    for expression, expected_error, expected_position in cases:
        harness = _Harness(ArbitraryPrecisionCalculatorEngine())
        harness.expr_var.set(expression)
        CalculatorApp._calculate(harness)  # type: ignore[arg-type]

        _assert(
            harness.result_display.text_updates[-1][0] == expected_error,
            f"mensaje de UI inesperado para {expression!r}",
        )
        _assert(
            not harness._expr_inactive_after_result
            and harness.expr_entry.state == "normal",
            f"{expression!r} debe volver a edición",
        )
        _assert(
            harness.expr_entry.cursor == expected_position,
            f"{expression!r} debe enfocar la posición {expected_position}",
        )
        _assert(
            harness.expr_entry.focus_calls == 1 and harness.root.focus_calls == 0,
            f"{expression!r} no devolvió el foco a la fórmula",
        )


def check_request_more_precision_failure_marks_exhausted() -> None:
    harness = _Harness(_PrecisionFailureEngine())
    CalculatorApp._request_more_precision(harness)  # type: ignore[arg-type]

    _assert(harness.result_display.mark_calls == 1, "no se marco precision agotada")
    _assert(harness.result_display.finish_calls == 1, "no se libero el estado de carga")
    _assert(
        harness.result_display._precision_exhausted, "faltó marcar precision agotada"
    )
    _assert(not harness.result_display._loading_more, "el estado de carga no se libero")


def check_stale_job_does_not_clear_loading() -> None:
    harness = _Harness(None)
    harness.engine = _StalePrecisionFailureEngine(harness)
    CalculatorApp._request_more_precision(harness)  # type: ignore[arg-type]

    _assert(
        harness.result_display.mark_calls == 0,
        "un trabajo obsoleto marco precision agotada",
    )
    _assert(
        harness.result_display.finish_calls == 0,
        "un trabajo obsoleto libero la carga activa",
    )
    _assert(
        not harness.result_display._precision_exhausted,
        "un trabajo obsoleto altero el estado agotado",
    )
    _assert(
        harness.result_display._loading_more,
        "un trabajo obsoleto limpio el estado de carga",
    )


def run_regressions() -> None:
    checks = [
        ("angle mode persistence", check_angle_mode_persistence),
        ("syntax normalization", check_syntax_normalization),
        (
            "syntax errors use positions from the original formula",
            check_syntax_error_positions_use_original_formula,
        ),
        (
            "validation and runtime errors expose original positions",
            check_validation_and_runtime_error_positions,
        ),
        (
            "failed evaluation clears active and conserves answer",
            check_failed_evaluation_clears_previous_precision_state,
        ),
        (
            "clear invalidates previous precision state",
            check_clear_invalidates_previous_precision_state,
        ),
        (
            "successful calculation deactivates expression",
            check_successful_calculation_deactivates_expression,
        ),
        (
            "next button after result starts new formula",
            check_next_button_after_result_starts_new_formula,
        ),
        (
            "physical key after result starts new formula",
            check_physical_key_after_result_starts_new_formula,
        ),
        (
            "lateral arrows recover finished formula",
            check_lateral_arrows_recover_finished_formula,
        ),
        (
            "button insert keeps cursor visible",
            check_button_insert_keeps_cursor_visible,
        ),
        (
            "calculate error marks precision exhausted",
            check_calculate_error_marks_precision_exhausted,
        ),
        (
            "positioned errors focus the original formula",
            check_positioned_errors_focus_original_formula,
        ),
        (
            "precision failure marks exhausted",
            check_request_more_precision_failure_marks_exhausted,
        ),
        ("stale precision job keeps loading", check_stale_job_does_not_clear_loading),
    ]

    for label, check in checks:
        check()
        print(f"OK: {label}")

    print("\nAll phase 1 regression checks passed.")


if __name__ == "__main__":
    run_regressions()
