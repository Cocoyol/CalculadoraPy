"""Arnés de regresión para la memoria ANS (`A`).

Fase 1 — Botón `A` e inserción visual.

Comprueba, sin abrir una ventana (fakes de Tk), que:
- la definición del keypad contiene un único botón `A` con acción `insert:A`;
- la cuadrícula reparte 12 columnas lógicas (mcm(6, 4)) entre la fila de
  funciones (6 botones) y las filas de 4, incluida la última `0 . A =`;
- pulsar `A` inserta exactamente un carácter en inicio, medio y final,
  manteniendo la posición del cursor y la vista desplazable.

Fase 2 — Contrato léxico y normalización (tabla 3.3 del plan).

Comprueba, sobre `FormulaEvaluator.prepare()`, que:
- la tabla 3.3 completa produce las normalizaciones esperadas
  (`AAA` -> `A*A*A`, `2A` -> `2*A`, `A!` -> `factorial(A)`, ...);
- las formas combinadas (`AA!`, `AA%`, `A^A`, `(A+1)A`, ...) se resuelven
  conforme a la precedencia implícita;
- los literales científicos completos sobreviven (`1e3A` -> `1e3*A`);
- los alias (`a`, `Ans`, `ANS`, `Ⓐ`) y las concatenaciones mixtas (`Ae`,
  `sinA`, ...) se rechazan con `ValueError`;
- todas las normalizaciones previas sin ANS se conservan intactas.

Fase 3 — Recetas, estado ANS y precisión progresiva (motor síncrono).

Comprueba, sobre `ArbitraryPrecisionCalculatorEngine`, que:
- sin respuesta confirmada, `A` se resuelve como el cero exacto
  (`A -> 0`, `A+2 -> 2`, `AAA -> 0`, `A! -> 1`, `A% -> 0`) y el primer
  éxito crea el ANS;
- la receta raíz que usó el cero inicial conserva esa dependencia al
  ampliar precisión y nunca se enlaza consigo misma;
- enteros, `mpf`, `mpc`, infinito y NaN pueden confirmarse como ANS y
  reutilizarse mediante `A`;
- `A!`, `A%`, `2A`, `AAA` y los grupos implícitos funcionan con respuesta
  confirmada;
- las cadenas de varias generaciones equivalen a la evaluación directa y
  se expanden con precisión idéntica;
- el modo angular se captura por nodo (DEG histórico, RAD nuevo);
- los errores conservan el ANS confirmado o el fallback cero;
- `clear_active_calculation()` conserva el ANS, `clear_answer()` vuelve a
  `A = 0` y una expresión independiente deja profundidad de receta 1;
- las cadenas largas se evalúan y expanden sin `RecursionError`.

Fase 4 — Promoción transaccional y seguridad asíncrona.

Comprueba, sobre el motor y sobre la UI con fakes de Tk, que:
- la solicitud captura ANS (o el fallback `A = 0`), modo angular y
  revisiones de forma estable, y la fase pura no muta el motor;
- un candidato construido con una revisión antigua se rechaza en
  `commit_evaluation()`/`commit_precision()` aunque se confirme directo;
- en la UI con trabajos solapados (envío en cola), solo el candidato
  vigente se confirma: ANS, historial, pantalla y el contexto de resultado
  visible solo cambian tras una confirmación correcta;
- un error obsoleto no limpia el cálculo activo ni el ANS del trabajo
  vigente, y un error vigente no habilita el contexto posresultado;
- una expansión obsoleta no cambia valor, dígitos, scroll ni carga;
- el modo angular se captura al crear la solicitud aunque el toggle
  cambie mientras corre el worker;
- un fallo de envío al executor no cambia el ANS ni bloquea la carga.

Fase 5 — Continuación posresultado condicionada por pantalla.

Comprueba, sobre la UI con fakes de Tk, que:
- tras un resultado válido visible, los botones de operadores binarios y
  postfijos insertan `A+`, `A−`, `A×`, `A÷`, `A^`, `A!`, `A%`, y cada botón
  científico —normal e INV— aplica su plantilla (`√(A)`, `sin(A)`, ...);
- el teclado físico antepone `A` solo ante `+ - − * × / ÷ ^ ! %`;
- dígitos, `.`, `π`, `e`, agrupadores y el botón/tecla `A` empiezan una
  fórmula independiente (referencia manual, sin duplicar);
- con pantalla limpia, fórmula activa, error, edición por clic, AC,
  Backspace/Delete o reconstrucción limpia, ningún control antepone `A`
  aunque el motor conserve ANS;
- el contexto posresultado se consume con la primera entrada, lo habilita
  solo una confirmación vigente y lo desactivan AC, Backspace/Delete, los
  errores y los trabajos obsoletos;
- cuando una función, operador o tecla dispara automáticamente `A`, el valor
  de ANS permanece visible durante toda la preparación; `=`/Enter lo sustituye
  por el nuevo resultado o por el error, mientras una entrada independiente
  conserva el reinicio visual a `0`;
- una `A` manual tras limpiar reutiliza la receta conservada con precisión
  arbitraria, y el cursor/scroll siguen a las plantillas insertadas.

Fase 6 — Historial, configuración y ciclo de vida.

Comprueba, sobre la UI con fakes de Tk y con Tkinter real, que:
- las entradas del historial siguen siendo tuplas literales
  (expresión, resultado), con deduplicación por expresión y sin recetas
  ni valores ocultos;
- el doble clic coloca la expresión y después crea la solicitud, que
  captura el ANS confirmado en ese instante —o el cero si aún no existe—:
  reutilizar `A+1` tras calcular `10` da `11`, no el resultado antiguo;
- reutilizar una fórmula independiente corta la cadena de recetas;
- la copia del historial conserva la expresión literal con `A`;
- limpiar el historial no afecta al ANS y limpiar ANS no altera las
  tuplas históricas;
- el reinicio por configuración conserva motor, ANS e historial, deja la
  pantalla limpia sin continuación posresultado y el botón `A` habilitado;
- una aplicación nueva arranca sin receta ANS, con historial vacío, botón
  habilitado y `A = 0`;
- la ayuda del historial explica el recálculo contextual.

Fase 7 — Endurecimiento y cierre.

Comprueba que:
- una fórmula independiente libera la cadena de recetas anterior (el
  recolector de basura deja de alcanzar sus nodos) y el historial solo
  retiene tuplas de cadenas, nunca recetas;
- los mensajes públicos del motor permanecen en español y estables.

La salida se organiza en grupos etiquetados por fase con recuento total.
El coste de cadenas y expansiones se mide con los benchmarks
`benchmark_ans_chain.py` (lineal en profundidad, sin caché) y
`benchmark_lambertw_ans.py` (W de Lambert por Newton-Raphson como cadena
ANS, verificación contra `mp.lambertw`), sin umbrales dependientes del
equipo.

Con `--gui` se ejecuta además una verificación opcional con Tkinter real
(ventana oculta) que comprueba la geometría de la cuadrícula, que el botón
`A` comparte tamaño de fila con sus vecinos y que el valor de ANS permanece
realmente visible durante una continuación, para anchos visibles 17 y 32.

Uso:
    python regression_ans_checks.py
    python regression_ans_checks.py --gui
"""

from __future__ import annotations

import argparse
import contextlib
import gc
import math
import time
from typing import Any

import calculator_ui_history as _history_module
import calculator_ui_window as _ui_window_module
from arbitrary_precision_engine import (
    ArbitraryPrecisionCalculatorEngine,
    CalculationRecipe,
)
from calculator_ui_window import CalculatorApp
from formula_evaluator import FormulaEvaluator

# ═════════════════════════════════════════════════════════════════
#  Fakes de Tk (mismo enfoque que regression_phase1_checks.py)
# ═════════════════════════════════════════════════════════════════


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
        self.xview_calls: list[tuple] = []
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
    """Evento de teclado mínimo para `_on_inactive_result_key`."""

    def __init__(self, *, char: str, keysym: str | None = None, state: int = 0):
        self.char = char
        self.keysym = keysym if keysym is not None else char
        self.state = state


class _FakeToggleButton:
    """Botón RAD/DEG de prueba para ejercitar `_toggle_angle` sin Tk."""

    def __init__(self):
        self.config_calls: list[dict] = []

    def config(self, **kw):
        self.config_calls.append(kw)


class _Harness:
    """Réplica mínima de CalculatorApp para probar inserción sin Tk.

    Desde la Fase 4 también sostiene el flujo transaccional de cálculo
    (`_calculate`/`_request_more_precision`) con envío síncrono.
    """

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
    _on_key = CalculatorApp._on_key
    _insert_at_cursor = CalculatorApp._insert_at_cursor
    _on_inactive_result_key = CalculatorApp._on_inactive_result_key
    _resolve_button_insertion = CalculatorApp._resolve_button_insertion
    _science_button_insertion = CalculatorApp._science_button_insertion
    _clear_engine_precision_state = CalculatorApp._clear_engine_precision_state
    _engine_can_expand_precision = CalculatorApp._engine_can_expand_precision
    _sync_result_precision_availability = (
        CalculatorApp._sync_result_precision_availability
    )
    _add_to_history = CalculatorApp._add_to_history
    _reuse_history_expr = CalculatorApp._reuse_history_expr
    _calculate = CalculatorApp._calculate
    _request_more_precision = CalculatorApp._request_more_precision
    _toggle_angle = CalculatorApp._toggle_angle
    _toggle_inv = CalculatorApp._toggle_inv

    # Paleta usada por _toggle_angle al reconfigurar el botón.
    C = CalculatorApp.C

    # Definiciones que _toggle_inv recorre para rotular el panel científico.
    SCIENCE_BUTTONS = CalculatorApp.SCIENCE_BUTTONS

    def __init__(self, engine: Any = None):
        # Any: el arnés admite motores reales o nulos sin verificación de tipos.
        self.engine: Any = engine
        self.root = _FakeRoot()
        self.expr_var = _FakeStringVar()
        self.expr_entry = _FakeExprEntry()
        self.result_display = _FakeResultDisplay()
        self.angle_btn = _FakeToggleButton()
        self.inv_btn = _FakeToggleButton()
        self._sci_buttons = [
            _FakeToggleButton() for _ in CalculatorApp.SCIENCE_BUTTONS
        ]
        self._last_engine_result: str | None = None
        self._history: list[tuple[str, str]] = []
        self._history_window = None
        self._expr_inactive_after_result = False
        self._valid_result_visible = False
        self._inv_mode = False
        self._closing = False
        self._background_job_seq = 0
        self._active_background_job_id = 0

    def _next_background_job_id(self) -> int:
        self._background_job_seq += 1
        self._active_background_job_id = self._background_job_seq
        return self._active_background_job_id

    def _is_active_background_job(self, job_id: int) -> bool:
        return not self._closing and job_id == self._active_background_job_id

    def _schedule_on_ui_thread(self, callback, job_id: int | None = None):
        # Equivalente síncrono del planificador real: descarta callbacks
        # de trabajos obsoletos y ejecuta los vigentes en el mismo hilo.
        if self._closing:
            return
        if job_id is not None and not self._is_active_background_job(job_id):
            return
        callback()

    def _submit_background(self, fn) -> bool:
        fn()
        return True


class _QueuedUIHarness(_Harness):
    """Arnés de UI con envío en cola para simular trabajos solapados.

    `_submit_background` encola la fase pura en lugar de ejecutarla, lo que
    permite crear un trabajo nuevo mientras el anterior sigue pendiente y
    comprobar después qué callbacks quedan vigentes (política «última
    solicitud vigente» por `job_id` más revisión del motor).
    """

    def __init__(self, engine: Any = None):
        super().__init__(engine)
        self.queued_jobs: list = []
        self.submit_calls = 0
        self.fail_submissions = False

    def _submit_background(self, fn) -> bool:
        self.submit_calls += 1
        if self.fail_submissions:
            return False
        self.queued_jobs.append(fn)
        return True

    def flush(self):
        """Ejecuta los trabajos encolados en orden de envío."""
        pending, self.queued_jobs = self.queued_jobs, []
        for job in pending:
            job()


def _assert(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def _make_harness(expression: str, cursor: int) -> _Harness:
    harness = _Harness()
    harness.expr_var.set(expression)
    harness.expr_entry.cursor = cursor
    return harness


def _press_answer(harness: _Harness, times: int = 1):
    """Pulsa el botón `A` tantas veces como se indique."""
    for _ in range(times):
        CalculatorApp._on_key(harness, "insert:A")  # type: ignore[arg-type]


# ═════════════════════════════════════════════════════════════════
#  Fase 1 — definición del keypad y cuadrícula
# ═════════════════════════════════════════════════════════════════


def check_keypad_defines_single_answer_button() -> None:
    keypad = CalculatorApp.KEYPAD

    answer_specs = [spec for row in keypad for spec in row if spec[0] == "A"]
    _assert(
        len(answer_specs) == 1,
        f"el keypad debe definir un único botón 'A', hay {len(answer_specs)}",
    )

    last_row = keypad[-1]
    index = next(i for i, spec in enumerate(last_row) if spec[0] == "A")
    text, action, kind = last_row[index]

    _assert(text == "A", f"texto inesperado en el botón de respuesta: {text!r}")
    _assert(
        action == "insert:A", f"acción inesperada en el botón de respuesta: {action!r}"
    )
    _assert(
        kind == "num",
        f"el botón 'A' debe usar el color de los números 'num', usa {kind!r}",
    )

    _assert(
        index == 2,
        f"'A' debe ocupar el tercer lugar de la última fila, ocupa el {index + 1}º",
    )
    _assert(
        index > 0 and last_row[index - 1][0] == ".",
        "'A' debe quedar a la derecha de '.'",
    )
    _assert(
        index + 1 < len(last_row) and last_row[index + 1][0] == "=",
        "'A' debe quedar a la izquierda de '='",
    )

    actions = [spec[1] for row in keypad for spec in row]
    _assert(
        actions.count("insert:A") == 1,
        "la acción 'insert:A' debe aparecer exactamente una vez",
    )

    first_row_texts = [spec[0] for spec in keypad[0]]
    _assert(
        first_row_texts == ["!", "^", "π", "e", "(", ")"],
        f"la fila de funciones debe quedar como antes sin 'A': {first_row_texts}",
    )

    lengths = [len(row) for row in keypad]
    _assert(lengths == [6, 4, 4, 4, 4, 4], f"forma de filas inesperada: {lengths}")


def check_keypad_grid_spans() -> None:
    keypad = CalculatorApp.KEYPAD
    max_cols = math.lcm(6, 4)
    _assert(max_cols == 12, f"mcm(6, 4) debe ser 12, es {max_cols}")

    # Fila de funciones (6 botones): 2 columnas por botón.
    spans_first = CalculatorApp._compute_spans(len(keypad[0]), max_cols)
    _assert(
        spans_first == [2] * 6,
        f"spans de la fila de funciones incorrectos: {spans_first}",
    )
    _assert(
        sum(spans_first) == max_cols, "la fila de funciones no cubre las 12 columnas"
    )

    # Filas de 4 botones (incluida la última 0, '.', 'A', '='): 3 columnas por botón.
    for row in keypad[1:]:
        spans = CalculatorApp._compute_spans(len(row), max_cols)
        _assert(spans == [3] * 4, f"spans de una fila de 4 incorrectos: {spans}")
        _assert(sum(spans) == max_cols, "una fila de 4 no cubre las 12 columnas")


# ═════════════════════════════════════════════════════════════════
#  Fase 1 — inserción del botón A
# ═════════════════════════════════════════════════════════════════


def check_answer_inserts_at_start_middle_end() -> None:
    cases = [
        ("123", 0, "A123"),  # inicio
        ("123", 2, "12A3"),  # medio
        ("123", 3, "123A"),  # final
    ]

    for expression, cursor, expected in cases:
        harness = _make_harness(expression, cursor)
        _press_answer(harness)

        _assert(
            harness.expr_var.get() == expected,
            f"con cursor {cursor}: {expression!r} + A dio {harness.expr_var.get()!r}",
        )
        _assert(
            len(harness.expr_var.get()) == len(expression) + 1,
            "cada pulsación debe insertar exactamente un carácter",
        )
        _assert(
            harness.expr_entry.cursor == cursor + 1,
            "el cursor no quedó justo tras el carácter insertado",
        )
        _assert(
            harness.expr_entry.xview_calls[-1] == ("insert",),
            "faltó desplazar la vista hacia el cursor",
        )


def check_answer_consecutive_presses_build_aa_and_aaa() -> None:
    two = _make_harness("", 0)
    _press_answer(two, times=2)
    _assert(
        two.expr_var.get() == "AA", f"dos pulsaciones produjeron {two.expr_var.get()!r}"
    )
    _assert(two.expr_entry.cursor == 2, "el cursor no avanzó un carácter por pulsación")

    three = _make_harness("", 0)
    _press_answer(three, times=3)
    _assert(
        three.expr_var.get() == "AAA",
        f"tres pulsaciones produjeron {three.expr_var.get()!r}",
    )
    _assert(
        three.expr_entry.cursor == 3, "el cursor no avanzó un carácter por pulsación"
    )

    appended = _make_harness("1+2", 3)
    _press_answer(appended, times=3)
    _assert(
        appended.expr_var.get() == "1+2AAA",
        "las pulsaciones no se acumulan al final de la fórmula",
    )
    _assert(appended.expr_entry.cursor == 6, "el cursor no quedó tras 'AAA'")


def check_answer_keeps_cursor_visible() -> None:
    long_expression = "1234567890123456789012345678901234567890"
    harness = _make_harness(long_expression, len(long_expression))

    _press_answer(harness, times=1)
    _assert(
        harness.expr_var.get() == long_expression + "A",
        "no insertó al final de una fórmula larga",
    )
    _assert(
        harness.expr_entry.cursor == len(long_expression) + 1,
        "cursor mal posicionado tras insertar",
    )
    _assert(
        harness.expr_entry.xview_calls[-1] == ("insert",),
        "la vista no siguió al cursor",
    )

    middle = _make_harness(long_expression, 10)
    _press_answer(middle, times=2)
    _assert(
        middle.expr_var.get() == long_expression[:10] + "AA" + long_expression[10:],
        "no insertó en medio de una fórmula larga",
    )
    _assert(
        middle.expr_entry.cursor == 12, "cursor mal posicionado tras insertar en medio"
    )
    _assert(
        middle.expr_entry.xview_calls[-1] == ("insert",),
        "la vista no siguió al cursor en inserción media",
    )


def check_answer_after_result_starts_new_formula() -> None:
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())
    harness.engine.evaluate("1/3")
    harness.expr_var.set("1/3")
    harness._expr_inactive_after_result = True
    harness.expr_entry.state = "readonly"

    _press_answer(harness, times=1)

    _assert(
        harness.expr_var.get() == "A",
        "el primer botón tras el resultado debe iniciar la fórmula 'A'",
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

    _press_answer(harness, times=2)
    _assert(
        harness.expr_var.get() == "AAA",
        "las pulsaciones siguientes deben seguir insertando 'A'",
    )


# ═════════════════════════════════════════════════════════════
#  Fase 2 — contrato léxico y normalización del átomo A
# ═════════════════════════════════════════════════════════════

# Tabla 3.3 del plan de desarrollo: entrada admitida -> salida normalizada.
_ANSWER_LEXICAL_TABLE = [
    ("A", "A"),
    ("AA", "A*A"),
    ("AAA", "A*A*A"),
    ("2A", "2*A"),
    ("A2", "A*2"),
    ("A.5", "A*.5"),
    ("2AAA", "2*A*A*A"),
    ("AA2", "A*A*2"),
    ("Aπ", "A*π"),
    ("πA", "π*A"),
    ("A(", "A*("),
    (")A", ")*A"),
    ("A!", "factorial(A)"),
    ("A%", "(A*0.01)"),
    ("1e3A", "1e3*A"),
    ("sin(A)", "sin(A)"),
    ("sqrt(A)", "sqrt(A)"),
]

# Formas combinadas: postfijos encadenados, operadores y literales científicos.
_ANSWER_COMBINED_TABLE = [
    ("AA!", "A*factorial(A)"),
    ("AA%", "A*(A*0.01)"),
    ("AAA!", "A*A*factorial(A)"),
    ("A^A", "A**A"),
    ("A/A", "A/A"),
    ("-A", "-A"),
    ("(A+1)A", "(A+1)*A"),
    ("A(A+1)", "A*(A+1)"),
    ("1e3A", "1e3*A"),
    ("2.5e-4A", "2.5e-4*A"),
    ("A*sqrt(2)", "A*sqrt(2)"),
    ("sin(A)^2", "sin(A)**2"),
    ("2(A)A", "2*(A)*A"),
]

# Alias prohibidos y concatenaciones mixtas, con el fragmento esperado del
# mensaje de diagnóstico.
_ANSWER_REJECTED_EXPRESSIONS = [
    ("a", "Identificador no permitido"),
    ("Ans", "Identificador no permitido"),
    ("ANS", "Identificador no permitido"),
    ("Ⓐ", "caracteres inválidos"),
    ("Ae", "Identificador no permitido"),
    ("eA", "Identificador no permitido"),
    ("Api", "Identificador no permitido"),
    ("piA", "Identificador no permitido"),
    ("Asin(1)", "Identificador no permitido"),
    ("sinA", "Identificador no permitido"),
    ("Alog(2)", "Identificador no permitido"),
    ("2eA", "Identificador no permitido"),
    ("AAe", "Identificador no permitido"),
    ("foo", "Identificador no permitido"),
]

# Normalizaciones previas sin ANS que deben conservarse intactas.
_EXISTING_NORMALIZATIONS = [
    ("2π", "2*π"),
    ("π2", "π*2"),
    ("2sin(1)", "2*sin(1)"),
    ("2(3)", "2*(3)"),
    ("(2)(3)", "(2)*(3)"),
    ("3!", "factorial(3)"),
    ("(1+2)!", "factorial((1+2))"),
    ("50%", "(50*0.01)"),
    ("(2+3)%", "((2+3)*0.01)"),
    ("1e3", "1e3"),
    ("1e3+2", "1e3+2"),
    ("2e", "2*e"),
    ("√(9)", "sqrt(9)"),
    ("sin(30)", "sin(30)"),
    ("2^3", "2**3"),
    ("e^2", "e**2"),
    ("π(3)", "π*(3)"),
]


def check_answer_lexical_table() -> None:
    """Tabla 3.3 completa: cada entrada produce la normalización esperada."""
    evaluator = FormulaEvaluator()
    for expression, expected in _ANSWER_LEXICAL_TABLE:
        try:
            prepared = evaluator.prepare(expression)
        except ValueError as exc:
            raise AssertionError(
                f"tabla 3.3: {expression!r} fue rechazada: {exc}"
            ) from exc
        _assert(
            prepared == expected,
            f"tabla 3.3: {expression!r} -> {prepared!r}, esperado {expected!r}",
        )


def check_answer_combined_forms() -> None:
    """Postfijos encadenados, operadores y notación científica con `A`."""
    evaluator = FormulaEvaluator()
    for expression, expected in _ANSWER_COMBINED_TABLE:
        try:
            prepared = evaluator.prepare(expression)
        except ValueError as exc:
            raise AssertionError(
                f"forma combinada: {expression!r} fue rechazada: {exc}"
            ) from exc
        _assert(
            prepared == expected,
            f"forma combinada: {expression!r} -> {prepared!r}, esperado {expected!r}",
        )


def check_answer_rejects_aliases_and_mixed_runs() -> None:
    """Alias del token único y concatenaciones ambiguas, con `ValueError`."""
    evaluator = FormulaEvaluator()
    for expression, expected_fragment in _ANSWER_REJECTED_EXPRESSIONS:
        try:
            prepared = evaluator.prepare(expression)
        except ValueError as exc:
            _assert(
                expected_fragment in str(exc),
                f"{expression!r}: se esperaba {expected_fragment!r} en el "
                f"diagnóstico, llegó {str(exc)!r}",
            )
        else:
            raise AssertionError(
                f"{expression!r} debe rechazarse, se normalizó a {prepared!r}"
            )


def check_existing_normalizations_preserved() -> None:
    """Todas las normalizaciones previas sin ANS siguen intactas."""
    evaluator = FormulaEvaluator()
    for expression, expected in _EXISTING_NORMALIZATIONS:
        try:
            prepared = evaluator.prepare(expression)
        except ValueError as exc:
            raise AssertionError(
                f"normalización previa: {expression!r} fue rechazada: {exc}"
            ) from exc
        _assert(
            prepared == expected,
            f"normalización previa: {expression!r} -> {prepared!r}, "
            f"esperado {expected!r}",
        )


# ═════════════════════════════════════════════
#  Fase 3 — recetas, estado ANS y precisión progresiva
# ═════════════════════════════════════════════

# Primeras expresiones sobre un motor nuevo: `A` vale el cero exacto.
_FALLBACK_ZERO_CASES = [
    ("A", "0"),
    ("A+2", "2"),
    ("AAA", "0"),
    ("A!", "1"),
    ("A%", "0"),
]


def check_engine_resolves_fallback_zero() -> None:
    """Motor nuevo: `A` vale el cero exacto y el primer éxito crea ANS."""
    _assert(
        not ArbitraryPrecisionCalculatorEngine().has_answer(),
        "un motor nuevo no debe tener una receta ANS confirmada",
    )

    for expression, expected in _FALLBACK_ZERO_CASES:
        fresh = ArbitraryPrecisionCalculatorEngine()
        result = fresh.evaluate(expression)
        _assert(
            result == expected,
            f"motor nuevo: {expression!r} -> {result!r}, esperado {expected!r}",
        )
        _assert(
            fresh.has_answer(),
            f"el primer cálculo correcto {expression!r} debe crear el ANS",
        )


def check_zero_root_recipe_keeps_zero_dependency() -> None:
    """La raíz que usó el cero inicial se reevalúa contra 0, nunca contra sí misma."""
    engine = ArbitraryPrecisionCalculatorEngine(initial_digits=18, precision_step=24)
    engine.evaluate("A + 1/3")

    recipe = engine._answer_recipe
    _assert(recipe is not None, "el primer éxito debe confirmar una receta ANS")
    _assert(
        recipe.uses_answer and recipe.answer_dependency is None,
        "la raíz con cero inicial debe registrar uses_answer sin dependencia",
    )
    _assert(recipe.depth == 1, f"profundidad inesperada: {recipe.depth}")

    expanded = engine.request_more_precision()
    direct = ArbitraryPrecisionCalculatorEngine(initial_digits=42)
    _assert(
        expanded == direct.evaluate("(0)+(1/3)"),
        "la expansión de la raíz con cero debe equivaler a evaluar (0)+(1/3)",
    )
    _assert(
        engine._answer_recipe.answer_dependency is None,
        "la expansión no debe alterar la receta confirmada",
    )

    linked = engine.evaluate("A+1")
    _assert(
        engine._answer_recipe.answer_dependency is not None,
        "una nueva expresión con A debe enlazar la receta confirmada",
    )
    _assert(
        linked == ArbitraryPrecisionCalculatorEngine().evaluate("(1/3)+1"),
        "tras confirmar la raíz, A debe valer la respuesta, no el cero inicial",
    )


def check_answer_accepts_terminal_results() -> None:
    """Enteros, mpf, mpc, infinito y NaN se confirman y reutilizan vía `A`."""
    cases = [
        ("2^10", "A*2", "2048"),
        ("ln(0)", "A+1", "-∞"),
        ("0*ln(0)", "A+2", "NaN"),
    ]
    for seed, follow, expected in cases:
        engine = ArbitraryPrecisionCalculatorEngine()
        first = engine.evaluate(seed)
        _assert(engine.has_answer(), f"{seed!r} debe confirmarse como ANS")
        _assert(
            not engine.can_expand_precision(),
            f"{seed!r} es terminal y no debe expandir precisión",
        )
        result = engine.evaluate(follow)
        _assert(
            result == expected,
            f"{follow!r} sobre ANS={first!r} -> {result!r}, esperado {expected!r}",
        )

    engine = ArbitraryPrecisionCalculatorEngine()
    first = engine.evaluate("sqrt(-1)")
    _assert(first.startswith("("), f"sqrt(-1) debe ser complejo: {first!r}")
    _assert(
        engine.evaluate("A*A") == "(-1.0 + 0.0j)",
        "el cuadrado del ANS complejo debe ser -1",
    )


def check_answer_forms_with_confirmed_answer() -> None:
    """`A!`, `A%`, `2A`, `AAA` y grupos implícitos con respuesta confirmada."""
    cases = [
        ("6", "A!", "720"),
        ("50", "A%", "0.5"),
        ("4", "(A+1)A", "20"),
        ("7", "A^A", "823543"),
    ]
    for seed, expression, expected in cases:
        engine = ArbitraryPrecisionCalculatorEngine()
        engine.evaluate(seed)
        result = engine.evaluate(expression)
        _assert(
            result == expected,
            f"{expression!r} con ANS={seed!r} -> {result!r}, esperado {expected!r}",
        )

    # Formas no enteras: equivalencia con la evaluación directa equivalente.
    for expression, direct_expression in [
        ("A*3", "(1/3)*3"),
        ("2A", "2*(1/3)"),
        ("AAA", "(1/3)*(1/3)*(1/3)"),
    ]:
        engine = ArbitraryPrecisionCalculatorEngine()
        engine.evaluate("1/3")
        result = engine.evaluate(expression)
        expected = ArbitraryPrecisionCalculatorEngine().evaluate(direct_expression)
        _assert(
            result == expected,
            f"{expression!r} -> {result!r}, directo {direct_expression!r} -> {expected!r}",
        )


def check_chain_matches_direct_evaluation() -> None:
    """Cadenas de varias generaciones y ampliaciones sucesivas."""
    engine = ArbitraryPrecisionCalculatorEngine(initial_digits=18, precision_step=24)
    engine.evaluate("1/3")
    engine.evaluate("A+1")
    engine.evaluate("sqrt(A)")
    _assert(
        engine._answer_recipe.depth == 3,
        f"la cadena debe tener profundidad 3, tiene {engine._answer_recipe.depth}",
    )

    first = engine.request_more_precision()
    _assert(
        first
        == ArbitraryPrecisionCalculatorEngine(initial_digits=42).evaluate(
            "sqrt((1/3)+1)"
        ),
        "la primera ampliación debe equivaler a la evaluación directa a 42 dígitos",
    )

    second = engine.request_more_precision()
    _assert(
        second
        == ArbitraryPrecisionCalculatorEngine(initial_digits=66).evaluate(
            "sqrt((1/3)+1)"
        ),
        "la segunda ampliación debe equivaler a la evaluación directa a 66 dígitos",
    )
    _assert(engine.can_expand_precision(), "sqrt(A) debe seguir expandiendo")


def check_angle_mode_captured_per_node() -> None:
    """`sin(30)` en DEG seguido, ya en RAD, de `A+sin(1)` conserva cada modo."""
    engine = ArbitraryPrecisionCalculatorEngine(initial_digits=18, precision_step=24)
    engine.angle_mode = "deg"
    _assert(engine.evaluate("sin(30)") == "0.5", "sin(30) en DEG debe dar 0.5")

    engine.angle_mode = "rad"
    chained = engine.evaluate("A+sin(1)")
    _assert(
        chained == ArbitraryPrecisionCalculatorEngine().evaluate("0.5+sin(1)"),
        "la cadena debe usar DEG para el nodo antiguo y RAD para el nuevo",
    )
    _assert(
        engine.angle_mode == "rad",
        "evaluar la cadena no debe alterar el modo angular actual",
    )

    expanded = engine.request_more_precision()
    _assert(
        expanded
        == ArbitraryPrecisionCalculatorEngine(initial_digits=42).evaluate(
            "0.5+sin(1)"
        ),
        "la expansión debe conservar el modo DEG capturado en la receta antigua",
    )


def check_errors_conserve_answer_or_zero_fallback() -> None:
    """Errores de sintaxis, división por cero y operación inválida."""
    engine = ArbitraryPrecisionCalculatorEngine()
    engine.evaluate("1/3")
    for expression in ("sin(", "1/0", "factorial(-2)"):
        try:
            engine.evaluate(expression)
        except (ValueError, ZeroDivisionError):
            pass
        else:
            raise AssertionError(f"{expression!r} debía fallar")
        _assert(
            engine.has_answer(),
            f"el error en {expression!r} debe conservar el ANS confirmado",
        )
        _assert(
            not engine.can_expand_precision(),
            f"el error en {expression!r} debe limpiar el cálculo activo",
        )
    _assert(
        engine.evaluate("A*3") == "1",
        "el ANS conservado debe seguir siendo reutilizable tras los errores",
    )

    fresh = ArbitraryPrecisionCalculatorEngine()
    try:
        fresh.evaluate("sin(")
    except ValueError:
        pass
    _assert(
        not fresh.has_answer() and fresh.evaluate("A") == "0",
        "sin ANS confirmado, el fallback cero debe seguir activo tras un error",
    )


def check_clear_semantics() -> None:
    """`clear_active_calculation()` conserva ANS; `clear_answer()` vuelve a 0."""
    engine = ArbitraryPrecisionCalculatorEngine()
    engine.evaluate("1/3")
    engine.clear_active_calculation()
    _assert(
        not engine.can_expand_precision(),
        "limpiar el activo debe impedir nuevas expansiones",
    )
    _assert(
        engine.has_answer(),
        "clear_active_calculation() debe conservar la respuesta confirmada",
    )
    _assert(
        engine.evaluate("A*6") == "2",
        "el ANS debe sobrevivir a clear_active_calculation()",
    )

    engine.clear_last_calculation()
    _assert(
        engine.has_answer(),
        "clear_last_calculation() es un alias y no debe eliminar el ANS",
    )

    engine.clear_answer()
    _assert(
        not engine.has_answer(),
        "clear_answer() debe eliminar la receta confirmada",
    )
    _assert(
        not engine.can_expand_precision(),
        "tras clear_answer() no debe haber cálculo expandible",
    )
    _assert(
        engine.evaluate("A") == "0",
        "clear_answer() debe devolver la semántica de A al cero exacto",
    )


def check_independent_recipe_has_depth_one() -> None:
    """Una expresión independiente corta la cadena: profundidad de receta 1."""
    engine = ArbitraryPrecisionCalculatorEngine()
    engine.evaluate("1/3")
    engine.evaluate("A+1")
    _assert(
        engine._answer_recipe.depth == 2,
        "la cadena previa debe tener profundidad 2",
    )

    engine.evaluate("2+2")
    recipe = engine._answer_recipe
    _assert(
        recipe.uses_answer is False and recipe.answer_dependency is None,
        "una expresión independiente no debe usar ni enlazar ANS",
    )
    _assert(recipe.depth == 1, f"profundidad inesperada: {recipe.depth}")


def check_long_chain_without_recursion() -> None:
    """Una cadena larga se evalúa y expande sin `RecursionError`."""
    engine = ArbitraryPrecisionCalculatorEngine(initial_digits=18, precision_step=24)
    engine.evaluate("0.1")
    for _ in range(200):
        engine.evaluate("A+1")

    chain = engine._answer_recipe
    _assert(chain.depth == 201, f"profundidad inesperada: {chain.depth}")

    engine.evaluate("A/3")
    expanded = engine.request_more_precision()
    direct = ArbitraryPrecisionCalculatorEngine(initial_digits=42)
    _assert(
        expanded == direct.evaluate("(0.1+200)/3"),
        "la expansión de la cadena larga debe coincidir con la evaluación directa",
    )


# ═══════════════════════════════════════════
#  Fase 4 — promoción transaccional y seguridad asíncrona
# ═══════════════════════════════════════════


def check_request_without_answer_keeps_zero_fallback_stable() -> None:
    """La solicitud captura `A = 0` de forma estable; su commit viejo se rechaza."""
    engine = ArbitraryPrecisionCalculatorEngine()
    request = engine.create_evaluation_request("A+2")
    _assert(request.answer_recipe is None, "sin ANS la solicitud no debe capturar receta")
    _assert(request.answer_revision == 0, "revisión inicial de ANS inesperada")

    engine.evaluate("9")  # confirmación ajena mientras el worker «correría»
    _assert(engine.has_answer(), "la confirmación ajena debe crear ANS")

    candidate = engine.evaluate_request(request)
    _assert(
        candidate.recipe.uses_answer and candidate.recipe.answer_dependency is None,
        "la dependencia capturada (cero inicial) no debe cambiar tras la confirmación ajena",
    )
    _assert(
        candidate.formatted_result == "2",
        "el candidato debe haberse evaluado contra el cero capturado",
    )
    _assert(
        engine._active_calculation.recipe.source_expression == "9",
        "la fase pura no debe mutar el cálculo activo",
    )

    try:
        engine.commit_evaluation(candidate)
    except ValueError:
        pass
    else:
        raise AssertionError("un candidato con revisión antigua debe rechazarse")

    _assert(
        engine.evaluate("A*2") == "18",
        "el ANS vigente debe seguir siendo el de la confirmación ajena",
    )


def check_stale_evaluation_commit_does_not_replace_answer() -> None:
    """Un candidato construido antes de otra confirmación no promueve ANS."""
    engine = ArbitraryPrecisionCalculatorEngine()
    engine.evaluate("1/3")
    slow_request = engine.create_evaluation_request("A*3")
    engine.evaluate("2+2")  # el cálculo B termina antes que A: revisión nueva

    slow_candidate = engine.evaluate_request(slow_request)
    _assert(
        engine._active_calculation.recipe.source_expression == "2+2",
        "la fase pura no debe mutar el cálculo activo",
    )
    try:
        engine.commit_evaluation(slow_candidate)
    except ValueError:
        pass
    else:
        raise AssertionError("el candidato obsoleto debía rechazarse")

    _assert(
        engine._answer_recipe.source_expression == "2+2",
        "solo el trabajo vigente debe quedar confirmado como ANS",
    )
    _assert(
        engine.evaluate("A+1") == "5",
        "el ANS debe seguir siendo el del cálculo vigente",
    )


def check_request_captures_angle_mode() -> None:
    """El modo angular se captura al crear la solicitud, no al evaluar."""
    engine = ArbitraryPrecisionCalculatorEngine()
    engine.angle_mode = "deg"
    request = engine.create_evaluation_request("sin(30)")
    engine.angle_mode = "rad"  # el usuario cambia el toggle durante el worker

    candidate = engine.evaluate_request(request)
    _assert(
        candidate.request.angle_mode == "deg",
        "la solicitud debe conservar el modo capturado",
    )
    _assert(
        engine.commit_evaluation(candidate) == "0.5",
        "el commit debe usar el modo angular capturado (DEG)",
    )
    _assert(
        engine.angle_mode == "rad",
        "commit_evaluation no debe alterar el modo angular actual",
    )


def check_precision_transaction_matches_sync_api() -> None:
    """create/evaluate/commit de expansión reproduce request_more_precision()."""
    engine = ArbitraryPrecisionCalculatorEngine(initial_digits=18, precision_step=24)
    engine.evaluate("1/3")
    recipe_before = engine._answer_recipe

    request = engine.create_precision_request()
    _assert(
        request.recipe is recipe_before,
        "la solicitud debe capturar la receta del cálculo activo",
    )
    _assert(request.working_digits == 18, "dígitos capturados inesperados")

    candidate = engine.evaluate_precision_request(request)
    _assert(
        candidate.working_digits == 42,
        "la fase pura debe apuntar a los dígitos ampliados",
    )
    _assert(
        engine._active_calculation.working_digits == 18,
        "la fase pura no debe mutar el cálculo activo",
    )

    expanded = engine.commit_precision(candidate)
    _assert(
        expanded
        == ArbitraryPrecisionCalculatorEngine(initial_digits=42).evaluate("1/3"),
        "la expansión transaccional debe equivaler a la evaluación directa",
    )
    _assert(
        engine._answer_recipe is recipe_before,
        "la expansión no debe cambiar la receta confirmada",
    )
    _assert(
        engine._active_calculation.working_digits == 42,
        "el commit debe actualizar los dígitos del cálculo activo",
    )


def check_stale_precision_commit_is_rejected() -> None:
    """Una expansión capturada antes de otro cálculo no puede confirmarse."""
    engine = ArbitraryPrecisionCalculatorEngine(initial_digits=18, precision_step=24)
    engine.evaluate("1/3")
    stale_request = engine.create_precision_request()
    engine.evaluate("2+2")  # el cálculo activo cambia: revisión nueva

    stale_candidate = engine.evaluate_precision_request(stale_request)
    try:
        engine.commit_precision(stale_candidate)
    except ValueError:
        pass
    else:
        raise AssertionError("la expansión obsoleta debía rechazarse")

    _assert(
        engine._active_calculation.working_digits == 18,
        "el commit obsoleto no debe cambiar dígitos ni valor del activo",
    )
    _assert(
        engine._active_calculation.recipe.source_expression == "2+2",
        "el cálculo activo debe seguir siendo el vigente",
    )


def check_ui_obsolete_calculation_confirms_only_latest() -> None:
    """Con dos cálculos solapados, solo el vigente se confirma en el motor."""
    harness = _QueuedUIHarness(ArbitraryPrecisionCalculatorEngine())

    harness.expr_var.set("1/3")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]  # job 1 en cola
    harness.expr_var.set("2+2")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]  # job 2 vigente
    _assert(
        not harness._valid_result_visible,
        "ningún trabajo sin confirmar debe habilitar el resultado visible",
    )

    harness.flush()

    _assert(
        [item[0] for item in harness._history] == ["2+2"],
        f"el historial debe recibir solo el cálculo confirmado: {harness._history!r}",
    )
    _assert(
        harness.result_display.text_updates[-1][0] == "4",
        "la pantalla debe mostrar el resultado del trabajo vigente",
    )
    _assert(
        harness.engine._answer_recipe.source_expression == "2+2",
        "solo el candidato vigente debe promoverse a ANS",
    )
    _assert(
        harness._valid_result_visible,
        "solo el candidato confirmado debe habilitar el resultado visible",
    )
    _assert(
        harness.engine.evaluate("A*3") == "12",
        "el ANS debe corresponder al trabajo vigente",
    )


def check_ui_obsolete_error_does_not_clear_current_work() -> None:
    """Un error de un trabajo viejo no toca el estado del trabajo vigente."""
    harness = _QueuedUIHarness(ArbitraryPrecisionCalculatorEngine())

    harness.expr_var.set("1/3")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    harness.flush()
    _assert(
        harness.engine.can_expand_precision(),
        "precondición: el cálculo vigente debe expandir",
    )

    harness.expr_var.set("sin(")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]  # error en cola
    expected = ArbitraryPrecisionCalculatorEngine().evaluate("2/3")
    harness.expr_var.set("2/3")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]  # vigente
    harness.flush()

    _assert(
        harness.result_display.text_updates[-1][0] == expected,
        "la pantalla debe quedar con el resultado vigente, no con el error obsoleto",
    )
    _assert(
        all("Error" not in text for text, _view in harness.result_display.text_updates),
        "un error obsoleto no debe mostrarse en pantalla",
    )
    _assert(
        harness.engine.can_expand_precision(),
        "el error obsoleto no debió limpiar el cálculo activo vigente",
    )
    _assert(harness.engine.has_answer(), "el ANS debe seguir confirmado")
    _assert(
        [item[0] for item in harness._history] == ["1/3", "2/3"],
        f"el historial solo debe contener confirmaciones: {harness._history!r}",
    )
    _assert(
        harness._valid_result_visible,
        "solo el trabajo vigente y confirmado habilita el resultado visible",
    )


def check_ui_current_error_does_not_enable_result_context() -> None:
    """Un error vigente limpia el activo pero no habilita la continuación."""
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())
    harness.engine.evaluate("1/3")
    _assert(harness.engine.has_answer(), "precondición: ANS confirmado")

    harness.expr_var.set("sin(")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]

    _assert(
        harness.result_display.text_updates[-1][0] == "Error: Error de sintaxis",
        "la UI no mostró el error esperado",
    )
    _assert(
        not harness._expr_inactive_after_result,
        "un error sintáctico vigente debe devolver la fórmula a edición",
    )
    _assert(
        harness.expr_entry.state == "normal" and harness.expr_entry.cursor == 3,
        "la fórmula errónea debe quedar editable en el primer punto señalado",
    )
    _assert(
        not harness._valid_result_visible,
        "un error no debe habilitar el contexto de resultado visible",
    )
    _assert(
        not harness.engine.can_expand_precision(),
        "el error vigente debe limpiar el cálculo activo",
    )
    _assert(harness.engine.has_answer(), "el error vigente debe conservar el ANS")


def check_ui_obsolete_expansion_changes_nothing() -> None:
    """Una expansión obsoleta no toca texto, dígitos, carga ni agotado."""
    harness = _QueuedUIHarness(ArbitraryPrecisionCalculatorEngine())
    harness.expr_var.set("1/3")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    harness.flush()

    text_updates_before = list(harness.result_display.text_updates)
    finish_before = harness.result_display.finish_calls
    mark_before = harness.result_display.mark_calls

    CalculatorApp._request_more_precision(harness)  # type: ignore[arg-type]
    harness._next_background_job_id()  # otro trabajo deja obsoleta la expansión
    harness.flush()

    _assert(
        harness.result_display.text_updates == text_updates_before,
        "una expansión obsoleta no debe cambiar el texto",
    )
    _assert(
        harness.result_display.finish_calls == finish_before,
        "una expansión obsoleta no debe liberar el estado de carga",
    )
    _assert(
        harness.result_display.mark_calls == mark_before,
        "una expansión obsoleta no debe marcar precisión agotada",
    )
    _assert(
        harness.engine._active_calculation.working_digits == 18,
        "una expansión obsoleta no debe cambiar los dígitos del activo",
    )


def check_ui_angle_toggle_during_worker_uses_captured_mode() -> None:
    """El toggle cambia durante el worker; el commit usa el modo capturado."""
    harness = _QueuedUIHarness(ArbitraryPrecisionCalculatorEngine())
    CalculatorApp._toggle_angle(harness)  # type: ignore[arg-type]  # RAD -> DEG
    _assert(harness.engine.angle_mode == "deg", "precondición: modo DEG")

    harness.expr_var.set("sin(30)")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    CalculatorApp._toggle_angle(harness)  # type: ignore[arg-type]  # DEG -> RAD
    _assert(harness.engine.angle_mode == "rad", "precondición: toggle a RAD")

    harness.flush()

    _assert(
        harness.result_display.text_updates[-1][0] == "0.5",
        "el commit debe usar el modo angular capturado al crear la solicitud",
    )


def check_ui_submit_failure_keeps_answer_and_releases_loading() -> None:
    """Si el envío falla, no se muta el motor ni queda la carga bloqueada."""
    harness = _QueuedUIHarness(ArbitraryPrecisionCalculatorEngine())
    harness.expr_var.set("1/3")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    harness.flush()
    answer_recipe = harness.engine._answer_recipe

    history_before = list(harness._history)
    harness.fail_submissions = True

    harness.expr_var.set("2+2")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    finish_before = harness.result_display.finish_calls
    mark_before = harness.result_display.mark_calls
    _assert(
        harness.engine._answer_recipe is answer_recipe,
        "un envío fallido no debe cambiar el ANS",
    )
    _assert(
        harness._history == history_before,
        "un envío fallido no debe añadir historial",
    )

    CalculatorApp._request_more_precision(harness)  # type: ignore[arg-type]
    _assert(
        harness.result_display.finish_calls == finish_before + 1,
        "un envío fallido de expansión debe liberar el estado de carga",
    )
    _assert(
        harness.result_display.mark_calls == mark_before,
        "un envío fallido no debe marcar precisión agotada",
    )
    _assert(
        harness.engine._active_calculation.working_digits == 18,
        "un envío fallido no debe cambiar los dígitos del activo",
    )


# ═════════════════════════════════════════════════════════════════
#  Fase 5 — continuación posresultado condicionada por pantalla
# ═════════════════════════════════════════════════════════════════

# Botones del teclado principal que construyen continuación con `A` tras
# un resultado válido visible (sección 3.2 del plan).
_KEYPAD_CONTINUATION_CASES = [
    ("insert:+", "A+"),
    ("insert:−", "A−"),
    ("insert:×", "A×"),
    ("insert:÷", "A÷"),
    ("insert:^", "A^"),
    ("insert:!", "A!"),
    ("insert:%", "A%"),
]

# Botones que, aun con resultado visible, empiezan fórmula independiente:
# operandos, agrupadores y la referencia manual `A`.
_KEYPAD_INDEPENDENT_CASES = [
    ("insert:7", "7"),
    ("insert:.", "."),
    ("insert:π", "π"),
    ("insert:e", "e"),
    ("insert:(", "("),
    ("insert:)", ")"),
    ("insert:A", "A"),
]

# Teclas físicas disparadoras y no disparadoras (sección 3.2).
_PHYSICAL_CONTINUATION_CHARS = ["+", "-", "−", "*", "×", "/", "÷", "^", "!", "%"]
_PHYSICAL_INDEPENDENT_CHARS = ["7", ".", "π", "e", "A", "(", "s", "n"]

# Plantillas posresultado del panel científico: normal e INV.
_SCIENCE_NORMAL_TEMPLATES = ["√(A)", "sin(A)", "cos(A)", "tan(A)", "ln(A)", "log(A)"]
_SCIENCE_INV_TEMPLATES = ["A^(2)", "asin(A)", "acos(A)", "atan(A)", "exp(A)", "10^(A)"]


def _make_result_harness(expression: str = "1/3") -> _Harness:
    """Arnés con un resultado confirmado visible, como justo tras «=»."""
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())
    harness.expr_var.set(expression)
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    _assert(
        harness._valid_result_visible,
        "precondición: la confirmación debe habilitar el resultado visible",
    )
    _assert(
        harness._expr_inactive_after_result,
        "precondición: el resultado debe dejar la fórmula inactiva",
    )
    return harness


def check_operator_buttons_after_result_prepend_answer() -> None:
    """Operadores binarios y postfijos tras resultado → continuación con `A`."""
    for action, expected in _KEYPAD_CONTINUATION_CASES:
        harness = _make_result_harness()
        result_updates_before = list(harness.result_display.text_updates)
        CalculatorApp._on_key(harness, action)  # type: ignore[arg-type]

        _assert(
            harness.expr_var.get() == expected,
            f"{action!r} tras resultado dio {harness.expr_var.get()!r}, "
            f"esperado {expected!r}",
        )
        _assert(
            harness.result_display.text_updates == result_updates_before,
            f"{action!r} debe conservar visible el valor de A, no mostrar 0",
        )
        _assert(
            not harness._valid_result_visible,
            "la primera entrada debe consumir el contexto posresultado",
        )
        _assert(
            harness.expr_entry.cursor == len(expected),
            "el cursor no quedó tras la plantilla insertada",
        )
        _assert(
            harness.expr_entry.xview_calls[-1] == ("insert",),
            "la vista no siguió al cursor",
        )


def check_science_templates_after_result() -> None:
    """Cada botón científico aplica su plantilla posresultado, normal e INV."""
    for col, expected in enumerate(_SCIENCE_NORMAL_TEMPLATES):
        harness = _make_result_harness()
        result_updates_before = list(harness.result_display.text_updates)
        CalculatorApp._on_science(harness, col)  # type: ignore[arg-type]
        _assert(
            harness.expr_var.get() == expected,
            f"columna {col} normal tras resultado dio "
            f"{harness.expr_var.get()!r}, esperado {expected!r}",
        )
        _assert(
            harness.result_display.text_updates == result_updates_before,
            f"la función normal {col} debe conservar visible el valor de A",
        )
        _assert(
            not harness._valid_result_visible,
            "la primera entrada debe consumir el contexto posresultado",
        )

    for col, expected in enumerate(_SCIENCE_INV_TEMPLATES):
        harness = _make_result_harness()
        CalculatorApp._toggle_inv(harness)  # type: ignore[arg-type]
        _assert(harness._inv_mode, "precondición: modo INV activado")
        result_updates_before = list(harness.result_display.text_updates)
        CalculatorApp._on_science(harness, col)  # type: ignore[arg-type]
        _assert(
            harness.expr_var.get() == expected,
            f"columna {col} INV tras resultado dio "
            f"{harness.expr_var.get()!r}, esperado {expected!r}",
        )
        _assert(
            harness.result_display.text_updates == result_updates_before,
            f"la función INV {col} debe conservar visible el valor de A",
        )


def check_independent_buttons_after_result() -> None:
    """Operandos, agrupadores y `A` manual empiezan fórmula independiente."""
    for action, expected in _KEYPAD_INDEPENDENT_CASES:
        harness = _make_result_harness()
        CalculatorApp._on_key(harness, action)  # type: ignore[arg-type]
        _assert(
            harness.expr_var.get() == expected,
            f"{action!r} tras resultado dio {harness.expr_var.get()!r}, "
            f"esperado {expected!r}",
        )
        _assert(
            not harness._valid_result_visible,
            "la primera entrada consume el contexto también para independientes",
        )
        _assert(
            harness.result_display.text_updates[-1][0] == "0",
            f"{action!r} es independiente y debe reiniciar el resultado a 0",
        )


def check_answer_button_after_result_is_manual_reference() -> None:
    """El botón `A` tras resultado inserta una referencia y permite AA/AAA."""
    harness = _make_result_harness()
    _press_answer(harness)
    _assert(
        harness.expr_var.get() == "A",
        f"el botón A tras resultado debe insertar una sola A, dio "
        f"{harness.expr_var.get()!r}",
    )

    _press_answer(harness, times=2)
    _assert(
        harness.expr_var.get() == "AAA",
        "las pulsaciones siguientes deben editar normalmente (AA/AAA)",
    )


def check_clean_screen_keeps_normal_insertion_with_answer_in_memory() -> None:
    """Con ANS en memoria y pantalla limpia, ningún control antepone `A`."""
    engine = ArbitraryPrecisionCalculatorEngine()
    engine.evaluate("1/3")
    _assert(engine.has_answer(), "precondición: ANS confirmado")

    for action, expected in [
        ("insert:+", "+"),
        ("insert:−", "−"),
        ("insert:^", "^"),
        ("insert:!", "!"),
        ("insert:%", "%"),
        ("insert:7", "7"),
    ]:
        fresh = _Harness(engine)
        CalculatorApp._on_key(fresh, action)  # type: ignore[arg-type]
        _assert(
            fresh.expr_var.get() == expected,
            f"pantalla limpia con ANS: {action!r} dio "
            f"{fresh.expr_var.get()!r}, esperado {expected!r}",
        )

    for col, expected in [(0, "√("), (1, "sin("), (4, "ln(")]:
        fresh = _Harness(engine)
        CalculatorApp._on_science(fresh, col)  # type: ignore[arg-type]
        _assert(
            fresh.expr_var.get() == expected,
            f"pantalla limpia con ANS: ciencia col {col} dio "
            f"{fresh.expr_var.get()!r}, esperado {expected!r}",
        )

    inv = _Harness(engine)
    CalculatorApp._toggle_inv(inv)  # type: ignore[arg-type]
    CalculatorApp._on_science(inv, 0)  # type: ignore[arg-type]
    _assert(
        inv.expr_var.get() == "^(2)",
        f"pantalla limpia con ANS: INV x² dio {inv.expr_var.get()!r}, "
        f"esperado '^(2)'",
    )


def check_physical_keys_after_result() -> None:
    """Teclado físico: solo los disparadores cerrados anteponen `A`."""
    for char in _PHYSICAL_CONTINUATION_CHARS:
        harness = _make_result_harness()
        result_updates_before = list(harness.result_display.text_updates)
        handled = CalculatorApp._on_inactive_result_key(
            harness, _FakeKeyEvent(char=char)
        )  # type: ignore[arg-type]
        _assert(
            handled == "break",
            f"la tecla {char!r} debe detener el manejo por defecto del Entry",
        )
        _assert(
            harness.expr_var.get() == "A" + char,
            f"tecla {char!r} tras resultado dio {harness.expr_var.get()!r}, "
            f"esperado {'A' + char!r}",
        )
        _assert(
            harness.result_display.text_updates == result_updates_before,
            f"la tecla {char!r} debe conservar visible el valor de A",
        )
        _assert(
            not harness._valid_result_visible,
            "la primera tecla consume el contexto posresultado",
        )

    for char in _PHYSICAL_INDEPENDENT_CHARS:
        harness = _make_result_harness()
        CalculatorApp._on_inactive_result_key(
            harness, _FakeKeyEvent(char=char)
        )  # type: ignore[arg-type]
        _assert(
            harness.expr_var.get() == char,
            f"tecla {char!r} tras resultado dio {harness.expr_var.get()!r}, "
            f"esperado {char!r} (independiente)",
        )
        _assert(
            harness.result_display.text_updates[-1][0] == "0",
            f"la tecla independiente {char!r} debe reiniciar el resultado a 0",
        )


def check_answer_result_stays_visible_until_confirmation() -> None:
    """El valor de A solo cambia al confirmar el nuevo resultado o error."""
    valid = _make_result_harness("9")
    answer_update = list(valid.result_display.text_updates)
    CalculatorApp._on_key(valid, "insert:+")  # type: ignore[arg-type]
    CalculatorApp._on_key(valid, "insert:1")  # type: ignore[arg-type]
    _assert(valid.expr_var.get() == "A+1", "la continuación válida debe ser A+1")
    _assert(
        valid.result_display.text_updates == answer_update,
        "el resultado 9 debe permanecer visible mientras se prepara A+1",
    )

    CalculatorApp._on_key(valid, "equals")  # type: ignore[arg-type]
    _assert(
        valid.result_display.text_updates[-1][0] == "10",
        "al confirmar A+1 debe mostrarse el resultado real 10",
    )

    invalid = _make_result_harness("9")
    answer_update = list(invalid.result_display.text_updates)
    CalculatorApp._on_key(invalid, "insert:÷")  # type: ignore[arg-type]
    CalculatorApp._on_key(invalid, "insert:0")  # type: ignore[arg-type]
    _assert(
        invalid.result_display.text_updates == answer_update,
        "el resultado 9 debe permanecer visible mientras se prepara A÷0",
    )

    CalculatorApp._on_key(invalid, "equals")  # type: ignore[arg-type]
    _assert(
        invalid.result_display.text_updates[-1][0].startswith("Error:"),
        "al confirmar A÷0 debe mostrarse el error real",
    )


def check_backspace_delete_and_ac_deactivate_continuation() -> None:
    """Backspace, Delete y AC dejan fórmula vacía sin continuación."""
    ac_harness = _make_result_harness()
    CalculatorApp._on_key(ac_harness, "clear")  # type: ignore[arg-type]
    _assert(
        not ac_harness._valid_result_visible,
        "AC debe desactivar la continuación posresultado",
    )
    CalculatorApp._on_key(ac_harness, "insert:+")  # type: ignore[arg-type]
    _assert(
        ac_harness.expr_var.get() == "+",
        "tras AC los operadores no deben anteponer A",
    )

    backspace_harness = _make_result_harness()
    CalculatorApp._on_key(backspace_harness, "backspace")  # type: ignore[arg-type]
    _assert(
        not backspace_harness._valid_result_visible,
        "Backspace debe desactivar la continuación posresultado",
    )
    _assert(
        backspace_harness.expr_var.get() == "",
        "Backspace tras resultado debe dejar la fórmula vacía",
    )

    delete_harness = _make_result_harness()
    CalculatorApp._on_inactive_result_key(
        delete_harness, _FakeKeyEvent(char="", keysym="Delete")
    )  # type: ignore[arg-type]
    _assert(
        not delete_harness._valid_result_visible,
        "Delete debe desactivar la continuación posresultado",
    )
    _assert(
        delete_harness.expr_var.get() == "",
        "Delete tras resultado debe dejar la fórmula vacía",
    )


def check_click_edit_deactivates_continuation_and_clears_active() -> None:
    """Editar la expresión antigua por clic limpia el activo y conserva el ANS."""
    harness = _make_result_harness()
    _assert(
        harness.engine.can_expand_precision(),
        "precondición: el cálculo activo debe expandir",
    )
    harness.expr_entry.cursor = 3  # clic al final de «1/3»

    CalculatorApp._on_expression_click(harness, None)  # type: ignore[arg-type]

    _assert(
        not harness._valid_result_visible,
        "la edición por clic debe desactivar la continuación",
    )
    _assert(
        not harness.engine.can_expand_precision(),
        "la edición por clic debe limpiar el cálculo activo",
    )
    _assert(
        harness.engine.has_answer(),
        "la edición por clic debe conservar el ANS confirmado",
    )

    CalculatorApp._on_key(harness, "insert:+")  # type: ignore[arg-type]
    _assert(
        harness.expr_var.get() == "1/3+",
        "tras editar por clic el operador se inserta sin A: "
        f"{harness.expr_var.get()!r}",
    )


def check_error_after_result_conserves_answer_but_not_continuation() -> None:
    """Un error tras un resultado conserva el ANS y desactiva la continuación."""
    harness = _make_result_harness()
    harness.expr_var.set("sin(")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]

    _assert(
        harness.result_display.text_updates[-1][0] == "Error: Error de sintaxis",
        "la UI no mostró el error esperado",
    )
    _assert(
        harness.engine.has_answer(),
        "el error debe conservar el ANS confirmado",
    )
    _assert(
        not harness._valid_result_visible,
        "el error debe desactivar la continuación posresultado",
    )

    CalculatorApp._on_key(harness, "insert:+")  # type: ignore[arg-type]
    _assert(
        harness.expr_var.get() == "sin+(",
        "tras un error sintáctico el operador debe editar la fórmula sin anteponer A",
    )


def check_obsolete_work_never_enables_result_context() -> None:
    """Un trabajo obsoleto nunca deja activado el contexto posresultado."""
    harness = _QueuedUIHarness(ArbitraryPrecisionCalculatorEngine())
    harness.expr_var.set("1/3")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]  # job 1 en cola
    harness._next_background_job_id()  # un trabajo nuevo lo deja obsoleto
    harness.flush()

    _assert(
        not harness._valid_result_visible,
        "un trabajo obsoleto no debe habilitar la continuación posresultado",
    )
    _assert(
        not harness._expr_inactive_after_result,
        "un trabajo obsoleto no debe dejar la fórmula inactiva",
    )
    # El campo queda como estaba (el trabajo en cola nunca lo limpió); se
    # vacía para comprobar la continuación desde una fórmula nueva.
    harness.expr_var.set("")
    harness.expr_entry.cursor = 0
    CalculatorApp._on_key(harness, "insert:+")  # type: ignore[arg-type]
    _assert(
        harness.expr_var.get() == "+",
        "con un trabajo obsoleto los operadores no anteponen A",
    )


def check_manual_answer_after_clear_reuses_recipe() -> None:
    """Tras limpiar, una `A` manual reutiliza la receta conservada."""
    harness = _make_result_harness("1/3")
    CalculatorApp._on_key(harness, "clear")  # type: ignore[arg-type]
    _assert(
        not harness._valid_result_visible,
        "AC debe desactivar la continuación posresultado",
    )
    _assert(
        harness.engine.has_answer(),
        "AC debe conservar el ANS confirmado",
    )

    # Referencia manual: A, ÷, 7 y ejecutar con el botón «=». Se usa un
    # cociente no entero porque (1/3)*3 redondea al entero exacto 1, que es
    # terminal y no admitiría expansión de precisión.
    _press_answer(harness)
    CalculatorApp._on_key(harness, "insert:÷")  # type: ignore[arg-type]
    CalculatorApp._on_key(harness, "insert:7")  # type: ignore[arg-type]
    _assert(
        harness.expr_var.get() == "A÷7",
        f"la fórmula manual quedó como {harness.expr_var.get()!r}",
    )
    CalculatorApp._on_key(harness, "equals")  # type: ignore[arg-type]

    expected = ArbitraryPrecisionCalculatorEngine().evaluate("(1/3)/7")
    _assert(
        harness.result_display.text_updates[-1][0] == expected,
        "la A manual debe reutilizar la receta conservada de 1/3",
    )
    _assert(
        harness.engine._answer_recipe.depth == 2,
        "la receta nueva debe enlazar la de 1/3 (profundidad 2)",
    )

    expanded = harness.engine.request_more_precision()
    direct = ArbitraryPrecisionCalculatorEngine(initial_digits=42)
    _assert(
        expanded == direct.evaluate("(1/3)/7"),
        "la expansión de la reutilización manual debe mantener la precisión arbitraria",
    )


def check_cursor_and_scroll_after_result_templates() -> None:
    """El cursor y la vista siguen a las plantillas posresultado."""
    harness = _make_result_harness()
    CalculatorApp._on_key(harness, "insert:+")  # type: ignore[arg-type]
    _assert(
        harness.expr_entry.cursor == 2,
        "el cursor debe quedar tras «A+»",
    )
    _assert(
        harness.expr_entry.xview_calls[-1] == ("insert",),
        "la vista debe desplazarse hacia el cursor",
    )

    long_digits = "1234567890" * 4
    for digit in long_digits:
        CalculatorApp._on_key(harness, f"insert:{digit}")  # type: ignore[arg-type]
    _assert(
        harness.expr_var.get() == "A+" + long_digits,
        "la fórmula larga debe construirse tras la plantilla",
    )
    _assert(
        harness.expr_entry.cursor == len("A+") + len(long_digits),
        "el cursor debe avanzar hasta el final de la fórmula larga",
    )
    _assert(
        harness.expr_entry.xview_calls[-1] == ("insert",),
        "la vista debe seguir al cursor en fórmulas largas",
    )


# ═════════════════════════════════════════════
#  Fase 6 — historial, configuración y ciclo de vida
# ═════════════════════════════════════════════


def check_history_hint_text_explains_contextual_reuse() -> None:
    """La ayuda del historial explica el recálculo contextual con `A`."""
    expected = "Doble clic para recalcular; A usa la respuesta actual (0 si aún no existe)"
    _assert(
        _history_module._HINT_TEXT == expected,
        f"la ayuda del historial debe ser {expected!r}, es "
        f"{_history_module._HINT_TEXT!r}",
    )


def check_history_minimal_scenario_reuse_uses_current_answer() -> None:
    """Escenario mínimo: 2 → A+1 (3) → 10 → reutilizar A+1 (11, no 3)."""
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())

    harness.expr_var.set("2")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    _assert(
        harness.result_display.text_updates[-1][0] == "2",
        "calcular 2 debe confirmar ANS=2",
    )
    _assert(
        harness._history == [("2", "2")],
        f"historial tras calcular 2: {harness._history!r}",
    )

    harness.expr_var.set("A+1")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    _assert(
        harness.result_display.text_updates[-1][0] == "3",
        "A+1 sobre ANS=2 debe dar 3",
    )
    _assert(
        [item[0] for item in harness._history] == ["2", "A+1"],
        f"la entrada debe guardarse con la expresión literal con A: "
        f"{harness._history!r}",
    )
    _assert(
        harness.engine._answer_recipe.depth == 2,
        "A+1 debe enlazar la receta de 2 (profundidad 2)",
    )

    harness.expr_var.set("10")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    _assert(
        harness.engine._answer_recipe.source_expression == "10"
        and harness.engine._answer_recipe.depth == 1,
        "una fórmula independiente debe sustituir el ANS y cortar la cadena",
    )

    # Doble clic sobre «A+1»: coloca la expresión y calcula con el ANS actual.
    CalculatorApp._reuse_history_expr(harness, "A+1")  # type: ignore[arg-type]
    _assert(
        harness.expr_var.get() == "A+1",
        "la reutilización debe colocar la expresión en el campo",
    )
    _assert(
        not harness._expr_inactive_after_result,
        "la fórmula reutilizada debe quedar editable",
    )
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]

    _assert(
        harness.result_display.text_updates[-1][0] == "11",
        "reutilizar A+1 con ANS=10 debe dar 11, no el 3 histórico",
    )
    _assert(
        [item for item in harness._history if item[0] == "A+1"] == [("A+1", "11")],
        "la deduplicación debe reemplazar la entrada antigua de A+1",
    )
    _assert(
        [item[0] for item in harness._history] == ["2", "10", "A+1"],
        f"orden del historial tras la reutilización: {harness._history!r}",
    )
    _assert(
        harness._valid_result_visible and harness._expr_inactive_after_result,
        "el resultado recalculado debe quedar visible y apto para continuar",
    )


def check_history_reuse_captures_answer_at_request_time() -> None:
    """La solicitud del doble clic captura el ANS confirmado en ese instante."""
    harness = _QueuedUIHarness(ArbitraryPrecisionCalculatorEngine())

    harness.expr_var.set("9")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    harness.flush()
    _assert(harness.engine.has_answer(), "precondición: ANS=9 confirmado")

    # Entrada histórica creada cuando el ANS era otro (resultado viejo «3»);
    # el plan permite que el recálculo difiera de la entrada seleccionada.
    harness._history[:] = [("9", "9"), ("A+1", "3")]

    # Un cálculo queda en cola y el doble clic sobre el historial lo deja
    # obsoleto: la solicitud del recálculo se crea después de colocar la
    # expresión, ya con el ANS vigente capturado.
    harness.expr_var.set("1/3")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]

    CalculatorApp._reuse_history_expr(harness, "A+1")  # type: ignore[arg-type]
    _assert(
        harness.expr_var.get() == "A+1",
        "el doble clic debe colocar la expresión antes de calcular",
    )
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    harness.flush()

    _assert(
        harness.result_display.text_updates[-1][0] == "10",
        "el recálculo debe usar el ANS vigente (9), dando 10 y no 3",
    )
    _assert(
        all("Error" not in text for text, _view in harness.result_display.text_updates),
        "ningún trabajo obsoleto debe mostrar errores",
    )
    _assert(
        harness.engine._answer_recipe.source_expression == "A+1"
        and harness.engine._answer_recipe.depth == 2,
        "la receta confirmada debe ser A+1 enlazando la de 9",
    )
    _assert(
        [item for item in harness._history if item[0] == "A+1"] == [("A+1", "10")],
        f"la entrada histórica debe actualizar su resultado: {harness._history!r}",
    )
    _assert(
        all(item[0] != "1/3" for item in harness._history),
        "el cálculo obsoleto no debe entrar en el historial",
    )
    _assert(
        harness._valid_result_visible,
        "solo el recálculo confirmado debe habilitar el resultado visible",
    )


def check_history_reuse_of_independent_formula_cuts_chain() -> None:
    """Reutilizar una fórmula independiente del historial corta la cadena."""
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())

    harness.expr_var.set("1/3")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    harness.expr_var.set("A+1")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    _assert(
        harness.engine._answer_recipe.depth == 2,
        "precondición: cadena de profundidad 2",
    )

    harness.expr_var.set("2+2")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    _assert(
        harness.engine._answer_recipe.depth == 1,
        "la fórmula independiente debe dejar profundidad 1",
    )

    CalculatorApp._reuse_history_expr(harness, "2+2")  # type: ignore[arg-type]
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    recipe = harness.engine._answer_recipe
    _assert(
        recipe.source_expression == "2+2"
        and recipe.depth == 1
        and not recipe.uses_answer,
        "la reutilización independiente debe mantener profundidad 1 sin usar A",
    )
    _assert(
        harness.engine.evaluate("A*2") == "8",
        "el ANS debe ser 4 (2+2), no un eslabón de la cadena de 1/3",
    )


def check_clear_answer_conserves_history_tuples() -> None:
    """`clear_answer()` elimina la receta pero no altera el historial."""
    harness = _Harness(ArbitraryPrecisionCalculatorEngine())
    harness.expr_var.set("1/3")
    CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    history_before = list(harness._history)
    _assert(harness.engine.has_answer(), "precondición: ANS confirmado")

    harness.engine.clear_answer()
    _assert(
        not harness.engine.has_answer(),
        "clear_answer() debe eliminar la receta confirmada",
    )
    _assert(
        harness._history == history_before,
        "limpiar ANS no debe alterar las tuplas del historial",
    )
    _assert(
        harness.engine.evaluate("A") == "0",
        "sin receta confirmada, A vuelve al cero exacto",
    )


# ═══════════════════════════════════════════
#  Fase 7 — endurecimiento y cierre
# ═══════════════════════════════════════════


def _reachable_recipe_instances() -> int:
    """Número de instancias de `CalculationRecipe` que alcanza el recolector."""
    return sum(
        1 for obj in gc.get_objects() if isinstance(obj, CalculationRecipe)
    )


def check_independent_formula_releases_previous_chain() -> None:
    """Una fórmula independiente libera la cadena; el historial no la retiene."""
    engine = ArbitraryPrecisionCalculatorEngine()
    engine.evaluate("0.1")
    for _ in range(50):
        engine.evaluate("A+1")
    gc.collect()
    before = _reachable_recipe_instances()
    _assert(
        before >= 51,
        f"la cadena de 51 nodos debe ser alcanzable antes del corte, hay {before}",
    )

    engine.evaluate("2+2")
    gc.collect()
    after = _reachable_recipe_instances()
    _assert(
        after <= 2,
        f"la fórmula independiente debe liberar la cadena anterior, quedan {after}",
    )

    # La UI tampoco retiene recetas: el historial solo guarda cadenas.
    harness = _Harness(engine)
    for expression in ("1/3", "A+2", "10"):
        harness.expr_var.set(expression)
        CalculatorApp._calculate(harness)  # type: ignore[arg-type]
    _assert(
        all(
            isinstance(expr, str) and isinstance(result, str)
            for expr, result in harness._history
        ),
        f"el historial debe contener solo tuplas de cadenas: {harness._history!r}",
    )
    gc.collect()
    ui_after = _reachable_recipe_instances()
    _assert(
        ui_after <= 3,
        f"el historial no debe retener recetas de cadenas liberadas, hay {ui_after}",
    )


def check_public_messages_remain_in_spanish() -> None:
    """Los mensajes públicos del motor permanecen en español y estables."""
    engine = ArbitraryPrecisionCalculatorEngine()
    try:
        engine.create_precision_request()
    except ValueError as exc:
        _assert(
            str(exc) == "No hay cálculo previo",
            f"mensaje de expansión sin cálculo inesperado: {exc}",
        )
    else:
        raise AssertionError("expansionar sin cálculo previo debía fallar")

    engine.evaluate("2+2")
    try:
        engine.create_precision_request()
    except ValueError as exc:
        _assert(
            str(exc) == "Este resultado no admite más precisión",
            f"mensaje de resultado terminal inesperado: {exc}",
        )
    else:
        raise AssertionError("expansionar un entero debía fallar")

    engine.evaluate("sqrt(-1)")
    try:
        engine.create_precision_request()
    except ValueError as exc:
        _assert(
            str(exc) == "Los resultados complejos no expanden precisión",
            f"mensaje de resultado complejo inesperado: {exc}",
        )
    else:
        raise AssertionError("expansionar un complejo debía fallar")

    try:
        engine.evaluate("(")
    except ValueError as exc:
        _assert(
            str(exc) == "Error de sintaxis",
            f"mensaje de sintaxis inesperado: {exc}",
        )
    else:
        raise AssertionError("'(' debía fallar con error de sintaxis")

    # Commits obsoletos: mensajes de revisión por separado.
    engine = ArbitraryPrecisionCalculatorEngine()
    engine.evaluate("1/3")
    stale_precision = engine.create_precision_request()
    engine.evaluate("2+2")
    precision_candidate = engine.evaluate_precision_request(stale_precision)
    try:
        engine.commit_precision(precision_candidate)
    except ValueError as exc:
        _assert(
            str(exc) == "El cálculo activo cambió durante la expansión",
            f"mensaje de expansión obsoleta inesperado: {exc}",
        )
    else:
        raise AssertionError("la expansión obsoleta debía rechazarse")

    engine = ArbitraryPrecisionCalculatorEngine()
    engine.evaluate("1/3")
    stale_request = engine.create_evaluation_request("A*3")
    engine.clear_last_calculation()  # solo la revisión del activo cambia
    evaluation_candidate = engine.evaluate_request(stale_request)
    try:
        engine.commit_evaluation(evaluation_candidate)
    except ValueError as exc:
        _assert(
            str(exc) == "El cálculo activo cambió durante la evaluación",
            f"mensaje de evaluación obsoleta (activo) inesperado: {exc}",
        )
    else:
        raise AssertionError("la evaluación obsoleta debía rechazarse")

    engine = ArbitraryPrecisionCalculatorEngine()
    engine.evaluate("1/3")
    stale_request = engine.create_evaluation_request("A*3")
    engine.evaluate("7")  # la revisión de la respuesta cambia
    evaluation_candidate = engine.evaluate_request(stale_request)
    try:
        engine.commit_evaluation(evaluation_candidate)
    except ValueError as exc:
        _assert(
            str(exc) == "La respuesta cambió durante el cálculo",
            f"mensaje de evaluación obsoleta (respuesta) inesperado: {exc}",
        )
    else:
        raise AssertionError("la evaluación obsoleta debía rechazarse")


# ═════════════════════════════════════════════════════════════════
#  Fase 1 — verificación geométrica opcional con Tk real (--gui)
# ═════════════════════════════════════════════════════════════════


def _destroy_test_root(root) -> None:
    """Cancela callbacks Tk pendientes antes de destruir la ventana de prueba."""
    with contextlib.suppress(_ui_window_module.tk.TclError):
        for after_id in root.tk.call("after", "info"):
            with contextlib.suppress(_ui_window_module.tk.TclError):
                root.after_cancel(after_id)
    with contextlib.suppress(_ui_window_module.tk.TclError):
        root.destroy()


def _build_app_for_visible_width(visible_chars: int):
    """Construye CalculatorApp con una ventana real (oculta) y ancho fijado."""
    original_visible = _ui_window_module.get_visible_chars
    original_separator = _ui_window_module.get_decimal_separator_enabled
    _ui_window_module.get_visible_chars = lambda: visible_chars
    _ui_window_module.get_decimal_separator_enabled = lambda: False
    try:
        root = _ui_window_module.tk.Tk()
        root.withdraw()
        try:
            app = CalculatorApp(root)
            root.update_idletasks()
        except Exception:
            _destroy_test_root(root)
            raise
        return app, root
    finally:
        _ui_window_module.get_visible_chars = original_visible
        _ui_window_module.get_decimal_separator_enabled = original_separator


def check_answer_button_layout_geometry(visible_chars: int) -> None:
    app, root = _build_app_for_visible_width(visible_chars)
    try:
        from calculator_ui_results import ResultDisplay

        _assert(
            visible_chars == ResultDisplay.VISIBLE_CHARS,
            f"VISIBLE_CHARS no se fijó a {visible_chars}",
        )

        answer_btn = app._answer_btn
        assert answer_btn is not None, "faltó la referencia al botón 'A'"
        _assert(answer_btn.cget("text") == "A", "el botón referenciado no muestra 'A'")
        _assert(
            str(answer_btn.cget("state")) == "normal",
            "el botón 'A' debe permanecer habilitado en la Fase 1",
        )

        frame = answer_btn.master
        columns, rows = frame.grid_size()
        _assert(columns == 12, f"la cuadrícula debe tener 12 columnas, tiene {columns}")
        _assert(
            rows == len(CalculatorApp.KEYPAD), f"número de filas inesperado: {rows}"
        )

        for c in range(columns):
            config = frame.columnconfigure(c)
            _assert(
                config.get("uniform") == "key" and config.get("weight") == 1,
                f"la columna {c} no es uniforme",
            )

        first_row_actions = [spec[1] for spec in CalculatorApp.KEYPAD[0]]
        for idx, action in enumerate(first_row_actions):
            info = app._keypad_buttons[action].grid_info()
            _assert(
                info.get("columnspan") == 2,
                f"{action!r} debe ocupar 2 columnas, ocupa {info.get('columnspan')}",
            )
            _assert(
                info.get("column") == idx * 2,
                f"{action!r} mal colocado en la columna {info.get('column')}",
            )

        for row_index in range(1, len(CalculatorApp.KEYPAD)):
            row_actions = [spec[1] for spec in CalculatorApp.KEYPAD[row_index]]
            for idx, action in enumerate(row_actions):
                info = app._keypad_buttons[action].grid_info()
                _assert(
                    info.get("columnspan") == 3,
                    f"{action!r} debe ocupar 3 columnas, ocupa {info.get('columnspan')}",
                )
                _assert(
                    info.get("column") == idx * 3,
                    f"{action!r} mal colocado en la columna {info.get('column')}",
                )

        # El botón A usa el mismo color que los dígitos.
        _assert(
            str(answer_btn.cget("bg")) == CalculatorApp.C["num"],
            "el botón 'A' debe tener el color de los números",
        )

        # El botón A comparte altura solicitada con los botones de su fila.
        last_row_actions = [spec[1] for spec in CalculatorApp.KEYPAD[-1]]
        heights = {
            app._keypad_buttons[action].winfo_reqheight() for action in last_row_actions
        }
        _assert(len(heights) == 1, f"alturas desiguales en la última fila: {heights}")
    finally:
        _destroy_test_root(root)


def check_clean_rebuild_keeps_answer_without_continuation(visible_chars: int) -> None:
    """Arranque y reconstrucción limpia: ANS en memoria, sin continuación."""
    original_visible = _ui_window_module.get_visible_chars
    original_separator = _ui_window_module.get_decimal_separator_enabled
    _ui_window_module.get_visible_chars = lambda: visible_chars
    _ui_window_module.get_decimal_separator_enabled = lambda: False
    root = None
    try:
        root = _ui_window_module.tk.Tk()
        root.withdraw()
        app = CalculatorApp(root)
        root.update_idletasks()

        _assert(
            app._valid_result_visible is False,
            "el arranque con pantalla limpia no debe habilitar la continuación",
        )

        # ANS en memoria con pantalla limpia: ningún botón antepone `A`.
        app.engine.evaluate("1/3")
        CalculatorApp._on_key(app, "insert:+")  # type: ignore[arg-type]
        _assert(
            app.expr_var.get() == "+",
            "con ANS en memoria y pantalla limpia no se antepone A",
        )
        _assert(
            str(app._answer_btn.cget("state")) == "normal",
            "el botón A debe permanecer habilitado sin respuesta visible",
        )

        # Reconstrucción por configuración: conserva ANS, pantalla limpia.
        app.restart_ui_after_config_change()
        root.withdraw()
        root.update_idletasks()
        _assert(
            app.engine.has_answer(),
            "la reconstrucción debe conservar el ANS confirmado",
        )
        _assert(
            app._valid_result_visible is False,
            "la pantalla reconstruida no debe habilitar la continuación",
        )
        _assert(
            app.expr_var.get() == "",
            "la pantalla reconstruida debe quedar limpia",
        )
        CalculatorApp._on_science(app, 1)  # type: ignore[arg-type]
        _assert(
            app.expr_var.get() == "sin(",
            "tras la reconstrucción las funciones insertan su plantilla vacía",
        )
    finally:
        if root is not None:
            _destroy_test_root(root)
        _ui_window_module.get_visible_chars = original_visible
        _ui_window_module.get_decimal_separator_enabled = original_separator


# ═════════════════════════════════════════════════════════════════
#  Fases 5–6 — verificaciones opcionales con Tk real (--gui)
# ═════════════════════════════════════════════════════════════════


def _enable_synchronous_app_calculations(app: CalculatorApp) -> None:
    """Sustituye el envío al executor por ejecución síncrona en la UI.

    La fase pura corre al instante en el propio hilo de la interfaz y los
    callbacks quedan programados con `after(0)`, de modo que cada
    `root.update()` los aplica de forma determinista, sin hilos reales.
    """
    app._submit_background = lambda fn: (fn(), True)[1]


def _calculate_and_pump(app: CalculatorApp, expression: str) -> None:
    """Calcula en la app real y drena los `after` pendientes de la vista."""
    app.expr_var.set(expression)
    app._calculate()
    app.root.update()
    # ResultDisplay programa la restauración de vista con after(10): se deja
    # vencer el temporizador mientras los widgets siguen vivos para que
    # ningún callback antiguo sobreviva a un reinicio posterior.
    time.sleep(0.02)
    app.root.update()


def check_contextual_answer_result_stays_visible_with_real_tk(
    visible_chars: int,
) -> None:
    """Tk real: ANS sigue visible hasta que `=` muestra resultado o error."""
    app, root = _build_app_for_visible_width(visible_chars)
    try:
        _enable_synchronous_app_calculations(app)
        _calculate_and_pump(app, "9")
        _assert(
            app.result_display.get_text() == "9",
            "precondición: el resultado confirmado 9 debe estar visible",
        )

        CalculatorApp._on_science(app, 0)  # type: ignore[arg-type]  # √(A)
        _assert(app.expr_var.get() == "√(A)", "la función debe preparar √(A)")
        _assert(
            app.result_display.get_text() == "9",
            "√(A) debe conservar visible el valor 9 de ANS",
        )

        CalculatorApp._on_key(app, "equals")  # type: ignore[arg-type]
        root.update()
        time.sleep(0.02)
        root.update()
        _assert(
            app.result_display.get_text() == "3",
            "al confirmar √(A) debe aparecer el resultado real 3",
        )

        CalculatorApp._on_key(app, "insert:÷")  # type: ignore[arg-type]
        CalculatorApp._on_key(app, "insert:0")  # type: ignore[arg-type]
        _assert(app.expr_var.get() == "A÷0", "la fórmula de error debe ser A÷0")
        _assert(
            app.result_display.get_text() == "3",
            "A÷0 debe conservar visible ANS mientras se prepara",
        )

        CalculatorApp._on_key(app, "equals")  # type: ignore[arg-type]
        root.update()
        time.sleep(0.02)
        root.update()
        _assert(
            app.result_display.get_text().startswith("Error:"),
            "al confirmar A÷0 debe aparecer el error real",
        )
    finally:
        app._closing = True
        app._background_executor.shutdown(wait=False, cancel_futures=True)
        _destroy_test_root(root)


def check_config_restart_conserves_answer_history_and_clean_screen(
    visible_chars: int,
) -> None:
    """Reinicio por configuración: conserva motor, ANS e historial; sin continuación."""
    original_visible = _ui_window_module.get_visible_chars
    original_separator = _ui_window_module.get_decimal_separator_enabled
    _ui_window_module.get_visible_chars = lambda: visible_chars
    _ui_window_module.get_decimal_separator_enabled = lambda: False
    root = None
    try:
        root = _ui_window_module.tk.Tk()
        root.withdraw()
        app = CalculatorApp(root)
        root.update_idletasks()
        _enable_synchronous_app_calculations(app)

        _calculate_and_pump(app, "1/3")
        expected_first = ArbitraryPrecisionCalculatorEngine().evaluate("1/3")
        _assert(app.engine.has_answer(), "precondición: ANS confirmado")
        _assert(app._valid_result_visible, "precondición: resultado visible")
        _assert(
            app._history == [("1/3", expected_first)],
            f"precondición: historial con la entrada de 1/3, {app._history!r}",
        )

        engine_before = app.engine
        history_before = list(app._history)

        app.restart_ui_after_config_change()
        root.withdraw()
        root.update_idletasks()

        _assert(app.engine is engine_before, "el reinicio debe conservar el motor")
        _assert(app.engine.has_answer(), "el reinicio debe conservar el ANS")
        _assert(
            app._history == history_before,
            "el reinicio debe conservar el historial",
        )
        _assert(app.expr_var.get() == "", "la pantalla reconstruida queda limpia")
        _assert(
            app._valid_result_visible is False,
            "la pantalla reconstruida no habilita la continuación posresultado",
        )
        _assert(
            str(app._answer_btn.cget("state")) == "normal",
            "el botón A se reconstruye habilitado",
        )
        CalculatorApp._on_key(app, "insert:+")  # type: ignore[arg-type]
        _assert(
            app.expr_var.get() == "+",
            "la pantalla limpia reconstruida no antepone A automáticamente",
        )

        # La memoria conservada sigue reutilizable de forma manual.
        _calculate_and_pump(app, "A*6")
        _assert(
            app._last_engine_result == "2",
            "tras el reinicio, una A manual debe reutilizar la receta conservada",
        )
        _assert(
            app.engine._answer_recipe.depth == 2,
            "A*6 debe enlazar la receta de 1/3 (profundidad 2)",
        )
    finally:
        if root is not None:
            _destroy_test_root(root)
        _ui_window_module.get_visible_chars = original_visible
        _ui_window_module.get_decimal_separator_enabled = original_separator


def check_new_app_instance_starts_without_answer(visible_chars: int) -> None:
    """Cierre y nueva aplicación: sin receta ANS, historial vacío y A = 0."""
    app1, root1 = _build_app_for_visible_width(visible_chars)
    try:
        result = app1.engine.evaluate("1/3")
        app1._add_to_history("1/3", result)
        _assert(app1.engine.has_answer(), "precondición: ANS confirmado")
        _assert(app1._history, "precondición: historial con entradas")
    finally:
        _destroy_test_root(root1)  # cierre de la aplicación: el motor se descarta

    app2, root2 = _build_app_for_visible_width(visible_chars)
    try:
        _assert(
            app2.engine is not app1.engine,
            "una aplicación nueva debe usar una instancia nueva del motor",
        )
        _assert(
            not app2.engine.has_answer(),
            "una aplicación nueva no debe restaurar una receta ANS",
        )
        _assert(
            app2._history == [],
            "una aplicación nueva debe arrancar con el historial vacío",
        )
        _assert(
            app2.engine.evaluate("A") == "0",
            "una aplicación nueva debe resolver A como el cero exacto",
        )
        _assert(
            str(app2._answer_btn.cget("state")) == "normal",
            "el botón A debe estar habilitado en una aplicación nueva",
        )
        _assert(
            app2._valid_result_visible is False
            and not app2._expr_inactive_after_result,
            "una aplicación nueva arranca limpia y sin continuación posresultado",
        )
    finally:
        _destroy_test_root(root2)


def check_history_window_help_copy_and_clear(visible_chars: int) -> None:
    """Ventana de historial: ayuda contextual, copia literal y limpiar sin tocar ANS."""
    app, root = _build_app_for_visible_width(visible_chars)
    try:
        result_first = app.engine.evaluate("1/3")
        app._add_to_history("1/3", result_first)
        app._add_to_history("A+1", "3")  # entrada histórica con A literal
        app._add_to_history("10", "10")

        app._open_history()
        window = app._history_window
        _assert(window is not None and window.is_open(), "la ventana de historial debe abrirse")
        window._win.withdraw()

        _assert(
            window._hint_label.cget("text") == _history_module._HINT_TEXT,
            "la ayuda de la ventana debe explicar el recálculo contextual con A",
        )

        # La copia conserva la expresión literal con A, sin sustituirla.
        _assert(
            window._entries[1][0] == "A+1",
            f"precondición: la entrada con A es la segunda en pantalla, "
            f"{window._entries!r}",
        )
        window._selected_idx = 1
        window._on_copy(None)
        _assert(
            window._win.clipboard_get() == "A+1",
            "copiar debe llevar al portapapeles la expresión literal con A",
        )

        # Limpiar el historial no afecta al ANS confirmado.
        window._on_clear()
        _assert(app._history == [], "limpiar debe vaciar el historial compartido")
        _assert(window._entries == [], "la ventana debe quedar sin entradas")
        _assert(
            app.engine.has_answer(),
            "limpiar el historial no debe afectar al ANS confirmado",
        )
        _assert(
            app.engine.evaluate("A*6") == "2",
            "el ANS debe seguir reutilizable tras limpiar el historial",
        )
    finally:
        _destroy_test_root(root)


def run_regressions(run_gui_checks: bool) -> None:
    """Ejecuta los checks agrupados por fase e informa el recuento total."""
    phase_groups = [
        (
            "Fase 1 — botón A e inserción visual",
            [
                ("keypad defines a single A button", check_keypad_defines_single_answer_button),
                ("keypad grid spans over 12 logical columns", check_keypad_grid_spans),
                (
                    "A inserts at start, middle and end",
                    check_answer_inserts_at_start_middle_end,
                ),
                (
                    "consecutive presses build AA and AAA",
                    check_answer_consecutive_presses_build_aa_and_aaa,
                ),
                ("A keeps cursor position and view", check_answer_keeps_cursor_visible),
                (
                    "A after a result starts a new formula",
                    check_answer_after_result_starts_new_formula,
                ),
            ],
        ),
        (
            "Fase 2 — contrato léxico y normalización",
            [
                (
                    "lexical table 3.3 for the answer atom",
                    check_answer_lexical_table,
                ),
                (
                    "combined answer forms (AA!, AA%, A^A, ...)",
                    check_answer_combined_forms,
                ),
                (
                    "aliases and mixed runs are rejected",
                    check_answer_rejects_aliases_and_mixed_runs,
                ),
                (
                    "existing normalizations without ANS are preserved",
                    check_existing_normalizations_preserved,
                ),
            ],
        ),
        (
            "Fase 3 — recetas, estado ANS y precisión progresiva",
            [
                (
                    "engine resolves the fallback zero without an answer",
                    check_engine_resolves_fallback_zero,
                ),
                (
                    "zero-root recipe keeps its zero dependency on expansion",
                    check_zero_root_recipe_keeps_zero_dependency,
                ),
                (
                    "terminal results (int, mpf, mpc, inf, NaN) become reusable answers",
                    check_answer_accepts_terminal_results,
                ),
                (
                    "answer forms with a confirmed answer (A!, A%, 2A, AAA, groups)",
                    check_answer_forms_with_confirmed_answer,
                ),
                (
                    "multi-generation chains match direct evaluation and expand",
                    check_chain_matches_direct_evaluation,
                ),
                (
                    "angle mode is captured per node (DEG history, RAD new)",
                    check_angle_mode_captured_per_node,
                ),
                (
                    "errors conserve the answer or the zero fallback",
                    check_errors_conserve_answer_or_zero_fallback,
                ),
                (
                    "clear semantics: active conserved, answer reset to zero",
                    check_clear_semantics,
                ),
                (
                    "independent recipe has depth one",
                    check_independent_recipe_has_depth_one,
                ),
                (
                    "long chain evaluates and expands without RecursionError",
                    check_long_chain_without_recursion,
                ),
            ],
        ),
        (
            "Fase 4 — promoción transaccional y seguridad asíncrona",
            [
                (
                    "request without answer keeps the zero fallback stable",
                    check_request_without_answer_keeps_zero_fallback_stable,
                ),
                (
                    "stale evaluation commit does not replace the answer",
                    check_stale_evaluation_commit_does_not_replace_answer,
                ),
                (
                    "request captures the angle mode at creation time",
                    check_request_captures_angle_mode,
                ),
                (
                    "precision transaction matches the synchronous API",
                    check_precision_transaction_matches_sync_api,
                ),
                (
                    "stale precision commit is rejected",
                    check_stale_precision_commit_is_rejected,
                ),
                (
                    "obsolete calculation confirms only the latest job",
                    check_ui_obsolete_calculation_confirms_only_latest,
                ),
                (
                    "obsolete error does not clear current work",
                    check_ui_obsolete_error_does_not_clear_current_work,
                ),
                (
                    "current error does not enable the result context",
                    check_ui_current_error_does_not_enable_result_context,
                ),
                (
                    "obsolete expansion changes nothing in the UI",
                    check_ui_obsolete_expansion_changes_nothing,
                ),
                (
                    "angle toggle during the worker uses the captured mode",
                    check_ui_angle_toggle_during_worker_uses_captured_mode,
                ),
                (
                    "submit failure keeps the answer and releases loading",
                    check_ui_submit_failure_keeps_answer_and_releases_loading,
                ),
            ],
        ),
        (
            "Fase 5 — continuación posresultado",
            [
                (
                    "operator and postfix buttons prepend A after a result",
                    check_operator_buttons_after_result_prepend_answer,
                ),
                (
                    "science templates after a result (normal and INV)",
                    check_science_templates_after_result,
                ),
                (
                    "operand, grouping and manual-A buttons start independent after a result",
                    check_independent_buttons_after_result,
                ),
                (
                    "answer button after a result is a manual reference (AA/AAA allowed)",
                    check_answer_button_after_result_is_manual_reference,
                ),
                (
                    "clean screen keeps normal insertion with an answer in memory",
                    check_clean_screen_keeps_normal_insertion_with_answer_in_memory,
                ),
                (
                    "physical continuation keys prepend A after a result",
                    check_physical_keys_after_result,
                ),
                (
                    "answer result stays visible until confirmation or error",
                    check_answer_result_stays_visible_until_confirmation,
                ),
                (
                    "backspace, delete and AC deactivate the continuation",
                    check_backspace_delete_and_ac_deactivate_continuation,
                ),
                (
                    "click-to-edit deactivates continuation and clears the active calculation",
                    check_click_edit_deactivates_continuation_and_clears_active,
                ),
                (
                    "error after a result conserves the answer but not the continuation",
                    check_error_after_result_conserves_answer_but_not_continuation,
                ),
                (
                    "obsolete work never enables the result context",
                    check_obsolete_work_never_enables_result_context,
                ),
                (
                    "manual A after clear reuses the conserved recipe with full precision",
                    check_manual_answer_after_clear_reuses_recipe,
                ),
                (
                    "cursor and scroll follow the posresult templates",
                    check_cursor_and_scroll_after_result_templates,
                ),
            ],
        ),
        (
            "Fase 6 — historial, configuración y ciclo de vida",
            [
                (
                    "history hint text explains the contextual reuse",
                    check_history_hint_text_explains_contextual_reuse,
                ),
                (
                    "history minimal scenario: reuse recalculates with the current answer",
                    check_history_minimal_scenario_reuse_uses_current_answer,
                ),
                (
                    "history reuse captures the answer at request time",
                    check_history_reuse_captures_answer_at_request_time,
                ),
                (
                    "reusing an independent formula from history cuts the chain",
                    check_history_reuse_of_independent_formula_cuts_chain,
                ),
                (
                    "clear_answer conserves the history tuples",
                    check_clear_answer_conserves_history_tuples,
                ),
            ],
        ),
        (
            "Fase 7 — endurecimiento y cierre",
            [
                (
                    "independent formula releases the previous chain (gc)",
                    check_independent_formula_releases_previous_chain,
                ),
                (
                    "public engine messages remain in Spanish and stable",
                    check_public_messages_remain_in_spanish,
                ),
            ],
        ),
    ]

    total = 0
    for title, group_checks in phase_groups:
        print(f"── {title} ({len(group_checks)} checks) " + "─" * 18)
        for label, check in group_checks:
            check()
            print(f"OK: {label}")
            total += 1

    print(
        f"\nTotal: {total} checks en {len(phase_groups)} fases "
        f"(sin la verificación geométrica opcional)."
    )

    if run_gui_checks:
        for visible_chars in (17, 32):
            check_answer_button_layout_geometry(visible_chars)
            print(f"OK: A button geometry with real Tk (VISIBLE_CHARS={visible_chars})")
            check_clean_rebuild_keeps_answer_without_continuation(visible_chars)
            print(
                f"OK: clean rebuild keeps ANS without continuation "
                f"(VISIBLE_CHARS={visible_chars})"
            )
            check_contextual_answer_result_stays_visible_with_real_tk(
                visible_chars
            )
            print(
                f"OK: contextual A keeps its visible result until confirmation "
                f"(VISIBLE_CHARS={visible_chars})"
            )
            check_config_restart_conserves_answer_history_and_clean_screen(
                visible_chars
            )
            print(
                f"OK: config restart conserves engine, ANS and history "
                f"(VISIBLE_CHARS={visible_chars})"
            )
            check_new_app_instance_starts_without_answer(visible_chars)
            print(
                f"OK: new app instance starts without an answer (A = 0) "
                f"(VISIBLE_CHARS={visible_chars})"
            )
            check_history_window_help_copy_and_clear(visible_chars)
            print(
                f"OK: history window help, literal copy and clear keep the answer "
                f"(VISIBLE_CHARS={visible_chars})"
            )
    else:
        print("OK: geometric check skipped (use --gui to run it with real Tk)")

    print("\nAll ANS phase 1-7 regression checks passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Regresiones de las Fases 1-7 del plan ANS"
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="verificación opcional con Tkinter real (ventana oculta), anchos 17 y 32",
    )
    run_regressions(run_gui_checks=parser.parse_args().gui)
