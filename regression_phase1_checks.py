from arbitrary_precision_engine import ArbitraryPrecisionCalculatorEngine
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
    def __init__(self, *, char: str, keysym: str | None = None, state: int = 0, widget=None):
        self.char = char
        self.keysym = keysym if keysym is not None else char
        self.state = state
        self.widget = widget


class _PrecisionFailureEngine:
    def can_expand_precision(self) -> bool:
        return True

    def request_more_precision(self) -> str:
        raise ValueError("fallo de prueba")


class _StalePrecisionFailureEngine:
    def __init__(self, harness):
        self._harness = harness

    def can_expand_precision(self) -> bool:
        return True

    def request_more_precision(self) -> str:
        self._harness._active_background_job_id += 1
        raise ValueError("fallo obsoleto")


class _Harness:
    _expression_is_inactive = CalculatorApp._expression_is_inactive
    _set_expression_editable = CalculatorApp._set_expression_editable
    _focus_expression_if_editable = CalculatorApp._focus_expression_if_editable
    _deactivate_expression_after_result = CalculatorApp._deactivate_expression_after_result
    _activate_expression_for_editing = CalculatorApp._activate_expression_for_editing
    _reset_for_new_formula = CalculatorApp._reset_for_new_formula
    _begin_new_formula_from_inactive_result = CalculatorApp._begin_new_formula_from_inactive_result
    _on_inactive_result_key = CalculatorApp._on_inactive_result_key
    _insert_at_cursor = CalculatorApp._insert_at_cursor

    def __init__(self, engine):
        self.engine = engine
        self.root = _FakeRoot()
        self.expr_var = _FakeStringVar()
        self.expr_entry = _FakeExprEntry()
        self.result_display = _FakeResultDisplay()
        self._last_engine_result: str | None = "0.5"
        self._history = []
        self._history_window = None
        self._expr_inactive_after_result = False
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
    _assert(engine.angle_mode == "rad", "request_more_precision altero el modo angular actual")


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


def check_failed_evaluation_clears_previous_precision_state() -> None:
    engine = ArbitraryPrecisionCalculatorEngine()
    engine.evaluate("1/3")
    _assert(engine.can_expand_precision(), "faltó estado expandible tras un cálculo válido")

    try:
        engine.evaluate("sin(")
    except ValueError as exc:
        _assert(str(exc) == "Error de sintaxis", f"mensaje inesperado tras fallo: {exc!r}")
    else:
        raise AssertionError("sin( debio fallar con Error de sintaxis")

    _assert(not engine.can_expand_precision(), "un fallo dejó expandible el cálculo anterior")

    try:
        engine.request_more_precision()
    except ValueError as exc:
        _assert(str(exc) == "No hay cálculo previo", f"mensaje inesperado al expandir tras error: {exc!r}")
    else:
        raise AssertionError("request_more_precision debio rechazar un error previo")


def check_clear_invalidates_previous_precision_state() -> None:
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())
    harness.engine.evaluate("1/3")
    _assert(harness.engine.can_expand_precision(), "faltó estado expandible previo al clear")

    CalculatorApp._on_key(harness, "clear")

    _assert(not harness.engine.can_expand_precision(), "clear conservó un cálculo expandible obsoleto")
    _assert(harness.result_display.text_updates[-1][0] == "0", "clear no restauró el texto base")
    _assert(harness.result_display.mark_calls == 1, "clear debe bloquear nuevas expansiones")


def check_successful_calculation_deactivates_expression() -> None:
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())
    harness.expr_var.set("1+1")

    CalculatorApp._calculate(harness)

    _assert(harness.result_display.text_updates[-1][0] == "2", "la UI no mostró el resultado esperado")
    _assert(harness._expr_inactive_after_result, "el resultado no dejó inactiva la fórmula")
    _assert(harness.expr_entry.state == "readonly", "la fórmula calculada debe quedar en solo lectura")
    _assert(harness.root.focus_calls == 1, "faltó retirar el foco del campo de entrada")


def check_next_button_after_result_starts_new_formula() -> None:
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())
    harness.engine.evaluate("1/3")
    harness.expr_var.set("1/3")
    harness._expr_inactive_after_result = True
    harness.expr_entry.state = "readonly"

    CalculatorApp._on_key(harness, "insert:7")

    _assert(harness.expr_var.get() == "7", "el primer botón tras el resultado debe iniciar una fórmula nueva")
    _assert(harness.result_display.text_updates[-1][0] == "0", "faltó limpiar el resultado anterior")
    _assert(harness.expr_entry.state == "normal", "la nueva fórmula debe quedar editable")
    _assert(not harness._expr_inactive_after_result, "la nueva fórmula no debe quedar inactiva")
    _assert(not harness.engine.can_expand_precision(), "el nuevo ingreso conservó precisión expandible previa")


def check_physical_key_after_result_starts_new_formula() -> None:
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())
    harness.engine.evaluate("1/3")
    harness.expr_var.set("1/3")
    harness._expr_inactive_after_result = True
    harness.expr_entry.state = "readonly"
    event = _FakeKeyEvent(char="8", widget=harness.expr_entry)

    handled = CalculatorApp._on_inactive_result_key(harness, event)

    _assert(handled == "break", "la tecla física debe detener el manejo por defecto del Entry")
    _assert(harness.expr_var.get() == "8", "la primera tecla física tras el resultado debe iniciar fórmula nueva")
    _assert(harness.result_display.text_updates[-1][0] == "0", "faltó limpiar el resultado anterior")
    _assert(harness.expr_entry.state == "normal", "la tecla física debe restaurar edición para la nueva fórmula")
    _assert(not harness._expr_inactive_after_result, "la fórmula nueva no debe quedar inactiva")


def check_button_insert_keeps_cursor_visible() -> None:
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())
    expression = "12312312312312312312312312312312"
    harness.expr_var.set(expression)
    harness.expr_entry.cursor = len(expression)

    CalculatorApp._insert_at_cursor(harness, "3")

    _assert(harness.expr_var.get() == expression + "3", "el botón no insertó el carácter al final")
    _assert(harness.expr_entry.cursor == len(expression) + 1, "el cursor no quedó tras el carácter insertado")
    _assert(harness.expr_entry.xview_calls[-1] == ("insert",), "el input no desplazó la vista hacia el cursor")


def check_calculate_error_marks_precision_exhausted() -> None:
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())
    harness.engine.evaluate("1/3")
    harness.expr_var.set("sin(")

    CalculatorApp._calculate(harness)

    _assert(harness.result_display.text_updates[-1][0] == "Error: Error de sintaxis", "la UI no mostró el error esperado")
    _assert(harness.result_display.mark_calls == 1, "la UI no bloqueó la expansión sobre el error")
    _assert(harness.result_display._precision_exhausted, "faltó marcar el error como no expandible")
    _assert(not harness.engine.can_expand_precision(), "la UI dejó vivo el cálculo anterior tras el error")


def check_request_more_precision_failure_marks_exhausted() -> None:
    harness = _Harness(_PrecisionFailureEngine())
    CalculatorApp._request_more_precision(harness)

    _assert(harness.result_display.mark_calls == 1, "no se marco precision agotada")
    _assert(harness.result_display.finish_calls == 1, "no se libero el estado de carga")
    _assert(harness.result_display._precision_exhausted, "faltó marcar precision agotada")
    _assert(not harness.result_display._loading_more, "el estado de carga no se libero")


def check_stale_job_does_not_clear_loading() -> None:
    harness = _Harness(None)
    harness.engine = _StalePrecisionFailureEngine(harness)
    CalculatorApp._request_more_precision(harness)

    _assert(harness.result_display.mark_calls == 0, "un trabajo obsoleto marco precision agotada")
    _assert(harness.result_display.finish_calls == 0, "un trabajo obsoleto libero la carga activa")
    _assert(not harness.result_display._precision_exhausted, "un trabajo obsoleto altero el estado agotado")
    _assert(harness.result_display._loading_more, "un trabajo obsoleto limpio el estado de carga")


def run_regressions() -> None:
    checks = [
        ("angle mode persistence", check_angle_mode_persistence),
        ("syntax normalization", check_syntax_normalization),
        ("failed evaluation clears previous precision state", check_failed_evaluation_clears_previous_precision_state),
        ("clear invalidates previous precision state", check_clear_invalidates_previous_precision_state),
        ("successful calculation deactivates expression", check_successful_calculation_deactivates_expression),
        ("next button after result starts new formula", check_next_button_after_result_starts_new_formula),
        ("physical key after result starts new formula", check_physical_key_after_result_starts_new_formula),
        ("button insert keeps cursor visible", check_button_insert_keeps_cursor_visible),
        ("calculate error marks precision exhausted", check_calculate_error_marks_precision_exhausted),
        ("precision failure marks exhausted", check_request_more_precision_failure_marks_exhausted),
        ("stale precision job keeps loading", check_stale_job_does_not_clear_loading),
    ]

    for label, check in checks:
        check()
        print(f"OK: {label}")

    print("\nAll phase 1 regression checks passed.")


if __name__ == "__main__":
    run_regressions()