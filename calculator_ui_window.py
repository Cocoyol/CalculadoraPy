"""
Ventana principal de la calculadora científica.

Contiene CalculatorApp: construye y gestiona los controles de la
interfaz, el teclado, los toggles y el hilo de cálculo en segundo plano.
"""

import contextlib
import sys
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import font as tkfont

from arbitrary_precision_engine import ArbitraryPrecisionCalculatorEngine
from calculator_config_normalizations import (
    get_decimal_separator_enabled,
    get_visible_chars,
)
from calculator_ui_history import HistoryWindow
from calculator_ui_results import ResultDisplay
from calculator_ui_settings import open_settings_dialog

# ── Continuación posresultado con `A` (sección 3.2 del plan ANS) ────
# Clasificación semántica cerrada: la clase visual de un botón no decide
# la continuación automática; solo estas plantillas y teclas la activan.

# Plantillas de los botones del teclado principal tras un resultado válido
# visible: operadores binarios y postfijos.
_RESULT_CONTINUATION_TEMPLATES = {
    "insert:+": "A+",
    "insert:\u2212": "A\u2212",
    "insert:\u00d7": "A\u00d7",
    "insert:\u00f7": "A\u00f7",
    "insert:^": "A^",
    "insert:!": "A!",
    "insert:%": "A%",
}

# Plantillas del panel científico tras un resultado válido visible,
# indexadas por (columna en SCIENCE_BUTTONS, modo INV).
_SCIENCE_RESULT_TEMPLATES = {
    (0, False): "\u221a(A)",
    (0, True): "A^(2)",
    (1, False): "sin(A)",
    (1, True): "asin(A)",
    (2, False): "cos(A)",
    (2, True): "acos(A)",
    (3, False): "tan(A)",
    (3, True): "atan(A)",
    (4, False): "ln(A)",
    (4, True): "exp(A)",
    (5, False): "log(A)",
    (5, True): "10^(A)",
}

# Únicas teclas físicas que anteponen `A` tras un resultado válido visible.
_PHYSICAL_RESULT_CONTINUATION_KEYS = frozenset("+-\u2212*/\u00d7\u00f7^!%")

# ═════════════════════════════════════════════════════════════════
#  Aplicación principal
# ═════════════════════════════════════════════════════════════════


class CalculatorApp:
    """Ventana principal de la calculadora científica."""

    # ── Paleta de colores (Nord) ──────────────────────────────────
    # Polar Night: #2E3440 #3B4252 #434C5E #4C566A
    # Snow Storm:  #D8DEE9 #E5E9F0 #ECEFF4
    # Frost:       #8FBCBB #88C0D0 #81A1C1 #5E81AC
    # Aurora:      #BF616A #D08770 #EBCB8B #A3BE8C #B48EAD
    C = {
        "bg": "#2E3440",  # Polar Night 1  – fondo general
        "display_bg": "#242933",  # más oscuro para la pantalla
        "num": "#3B4252",  # Polar Night 2  – dígitos (oscuro)
        "num_fg": "#ECEFF4",  # Snow Storm 3
        "op": "#D08770",  # Aurora Orange  – operadores básicos
        "op_fg": "#2E3440",
        "func": "#4C566A",  # Polar Night 4  – funciones (más claro que num)
        "func_fg": "#ECEFF4",
        "special": "#BF616A",  # Aurora Red     – AC / borrar (destructivo)
        "special_fg": "#ECEFF4",
        "equals": "#A3BE8C",  # Aurora Green   – igual (confirmar)
        "equals_fg": "#2E3440",
        "toggle_on": "#88C0D0",  # Frost          – modo activo
        "toggle_off": "#434C5E",  # Polar Night 3  – modo inactivo
        "active": "#cdb5cd",  # Aurora Pink    – fondo botón activo (hover o toggle on)
        "expr_fg": "#D8DEE9",  # Snow Storm 1
        "result_fg": "#88C0D0",  # Frost          – resultado
    }

    # ── Definiciones de botones científicos ──────────────────────
    #  (texto_normal, inserta_normal, texto_inv, inserta_inv)

    SCIENCE_BUTTONS = [
        ("\u221a", "\u221a(", "x\u00b2", "^(2)"),  # √  / x²
        ("sin", "sin(", "sin\u207b\u00b9", "asin("),  # sin / asin
        ("cos", "cos(", "cos\u207b\u00b9", "acos("),  # cos / acos
        ("tan", "tan(", "tan\u207b\u00b9", "atan("),  # tan / atan
        ("ln", "ln(", "e\u02e3", "exp("),  # ln  / eˣ
        ("log", "log(", "10\u02e3", "10^("),  # log / 10ˣ
    ]

    # ── Definiciones del teclado principal ────────────────────────
    #  Cada fila es una lista de (texto, acción, tipo_color)
    #  tipo_color: "num", "op", "func", "special", "equals"

    KEYPAD = [
        [
            ("!", "insert:!", "func"),
            ("^", "insert:^", "func"),
            ("\u03c0", "insert:\u03c0", "func"),
            ("e", "insert:e", "func"),
            ("(", "insert:(", "func"),
            (")", "insert:)", "func"),
        ],
        [
            ("AC", "clear", "special"),
            ("\u232b", "backspace", "special"),
            ("%", "insert:%", "func"),
            ("\u00f7", "insert:\u00f7", "op"),
        ],
        [
            ("7", "insert:7", "num"),
            ("8", "insert:8", "num"),
            ("9", "insert:9", "num"),
            ("\u00d7", "insert:\u00d7", "op"),
        ],
        [
            ("4", "insert:4", "num"),
            ("5", "insert:5", "num"),
            ("6", "insert:6", "num"),
            ("\u2212", "insert:\u2212", "op"),
        ],
        [
            ("1", "insert:1", "num"),
            ("2", "insert:2", "num"),
            ("3", "insert:3", "num"),
            ("+", "insert:+", "op"),
        ],
        [
            ("0", "insert:0", "num"),
            (".", "insert:.", "num"),
            ("A", "insert:A", "num"),
            ("=", "equals", "equals"),
        ],
    ]

    # ────────────────────────────────────────────────────────────

    def __init__(self, root: tk.Tk, engine=None):
        self._reload_result_display_config()
        self.root = root
        self.root.title("Calculadora Cient\u00edfica")
        self.root.configure(bg=self.C["bg"])
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._apply_window_icon()

        self.engine = (
            engine if engine is not None else ArbitraryPrecisionCalculatorEngine()
        )
        self._inv_mode = False
        self._last_engine_result: str | None = None
        self._history: list[tuple[str, str]] = []
        self._history_window: HistoryWindow | None = None
        self._shift_copy = False
        self._ctrl_copy = False
        self._expr_inactive_after_result = False
        # Contexto de continuación posresultado (Fase 5): solo se activa al
        # confirmar el trabajo vigente y nunca se deriva de `has_answer()`,
        # de la receta ANS ni del texto o color de ningún control.
        self._valid_result_visible = False
        self._background_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="calculator"
        )
        self._background_futures = []
        self._background_job_seq = 0
        self._active_background_job_id = 0
        self._closing = False

        self._init_fonts()
        self._create_display()
        self._create_toggle_bar()
        self._create_science_panel()
        self._create_keypad()
        self._bind_keyboard()

        # Tamaño mínimo derivado del layout real: se adapta a VISIBLE_CHARS y tamaños de fuente
        self._apply_minimum_window_geometry()

        # Foco inicial en el campo de expresión
        self.expr_entry.focus_set()

        # Escalado de fuentes al redimensionar
        self._base_size: tuple[int, int] | None = None
        self._resize_pending: str | None = None
        self.root.after(250, self._record_base_size)
        self.root.bind("<Configure>", self._on_root_configure)

    # ── Icono de ventana ─────────────────────────────────────────

    def _icon_base_dir(self) -> Path:
        """Directorio donde buscar los recursos de icono.

        Con Nuitka onefile, los datos incluidos se extraen junto al módulo,
        por lo que `Path(__file__).parent` resuelve correctamente tanto en
        ejecución desde fuente como empaquetado.
        """
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).parent
            if (exe_dir / "icon-calculator.ico").exists() or (
                exe_dir / "icons"
            ).exists():
                return exe_dir
        return Path(__file__).resolve().parent

    def _apply_window_icon(self):
        """Asigna el icono multi-resolución a la ventana.

        En Windows, `iconbitmap(default=...)` con un .ico multi-res ofrece la
        mejor calidad para la barra de tareas y el título; complementamos con
        `iconphoto` cargando varios PNG para que Tk elija el mejor tamaño
        (incluido el mini-icono junto al título) preservando transparencia.
        """
        base = self._icon_base_dir()
        ico_path = base / "icon-calculator.ico"
        if ico_path.exists():
            with contextlib.suppress(tk.TclError):
                self.root.iconbitmap(default=str(ico_path))

        icons_dir = base / "icons"
        png_sizes = (16, 24, 32, 48, 64, 128, 256)
        photos: list[tk.PhotoImage] = []
        for size in png_sizes:
            png_path = icons_dir / f"icon-{size}.png"
            if not png_path.exists():
                continue
            try:
                photos.append(tk.PhotoImage(file=str(png_path)))
            except tk.TclError:
                continue
        if photos:
            # Mantener referencias para que Tk no libere las imágenes.
            self._icon_photos = photos
            with contextlib.suppress(tk.TclError):
                self.root.iconphoto(True, *photos)

    # ── Fuentes ──────────────────────────────────────────────────

    def _init_fonts(self):
        self._f_expr = tkfont.Font(family="Consolas", size=19)
        self._f_result = tkfont.Font(family="Consolas", size=25, weight="bold")
        self._f_btn = tkfont.Font(family="Segoe UI", size=18)
        self._f_func = tkfont.Font(family="Segoe UI", size=14)
        self._f_small = tkfont.Font(family="Segoe UI", size=12)
        self._base_font_sizes = {
            "expr": 19,
            "result": 25,
            "btn": 18,
            "func": 14,
            "small": 12,
        }

    # ── Pantalla ─────────────────────────────────────────────────

    def _create_display(self):
        frame = tk.Frame(self.root, bg=self.C["display_bg"], padx=12, pady=8)
        frame.pack(fill="x", padx=6, pady=(6, 2))

        # Campo de expresión (editable)
        self.expr_var = tk.StringVar()
        self.expr_entry = tk.Entry(
            frame,
            textvariable=self.expr_var,
            font=self._f_expr,
            bg=self.C["display_bg"],
            fg=self.C["expr_fg"],
            insertbackground=self.C["expr_fg"],
            readonlybackground=self.C["display_bg"],
            relief="flat",
            justify="right",
            bd=0,
        )
        self.expr_entry.bind("<Button-1>", self._on_expression_click)
        self.expr_entry.bind("<Key>", self._on_inactive_result_key)
        self.expr_entry.pack(fill="x", pady=(4, 0))

        # Fila del resultado + botón copiar
        row = tk.Frame(frame, bg=self.C["display_bg"])
        row.pack(fill="x", pady=(2, 4))
        self._result_row = row

        self.result_display = ResultDisplay(
            row,
            request_more_callback=self._request_more_precision,
            font=self._f_result,
            bg=self.C["display_bg"],
            fg=self.C["result_fg"],
            readonlybackground=self.C["display_bg"],
            relief="flat",
            justify="right",
            bd=0,
        )

        self._copy_btn = tk.Button(
            row,
            text="Copiar",
            font=self._f_small,
            bg=self.C["func"],
            fg=self.C["func_fg"],
            activebackground=self.C["active"],
            relief="flat",
            cursor="hand2",
            command=self._copy_result,
            padx=8,
        )
        self._copy_btn.bind("<Button-1>", self._on_copy_press)
        self._copy_btn.pack(side="right", padx=(6, 0))

        self.result_display.widget.pack(side="right", fill="y")
        self._fix_result_row_height()

    def _fix_result_row_height(self):
        if not hasattr(self, "_result_row") or not hasattr(self, "_copy_btn"):
            return

        probe = tk.Entry(
            self._result_row,
            font=self._f_result,
            width=getattr(
                self.result_display,
                "_base_entry_width_chars",
                ResultDisplay.VISIBLE_CHARS + 1,
            ),
            relief="flat",
            bd=0,
        )
        entry_height = probe.winfo_reqheight()
        entry_width = probe.winfo_reqwidth()
        probe.destroy()

        row_height = max(entry_height, self._copy_btn.winfo_reqheight())
        row_width = entry_width + self._copy_btn.winfo_reqwidth() + 6
        self._result_row.configure(width=row_width, height=row_height)
        self._result_row.pack_propagate(False)

    # ── Barra de toggles (RAD/DEG · INV) ────────────────────────

    def _create_toggle_bar(self):
        frame = tk.Frame(self.root, bg=self.C["bg"])
        frame.pack(fill="x", padx=6, pady=(2, 2))

        self.angle_btn = tk.Button(
            frame,
            text="RAD",
            font=self._f_small,
            width=6,
            bg=self.C["toggle_on"],
            fg=self.C["bg"],
            activebackground=self.C["toggle_on"],
            relief="flat",
            command=self._toggle_angle,
        )
        self.angle_btn.pack(side="left", padx=(0, 4))

        self.inv_btn = tk.Button(
            frame,
            text="INV",
            font=self._f_small,
            width=6,
            bg=self.C["toggle_off"],
            fg=self.C["special_fg"],
            activebackground=self.C["toggle_off"],
            relief="flat",
            command=self._toggle_inv,
        )
        self.inv_btn.pack(side="left")

        self._settings_btn = tk.Button(
            frame,
            text="\u2699",
            font=self._f_small,
            bg=self.C["toggle_off"],
            fg="#EBCB8B",
            activebackground=self.C["active"],
            relief="flat",
            cursor="hand2",
            command=self._open_settings,
        )
        self._settings_btn.pack(side="right")

        self._history_btn = tk.Button(
            frame,
            text="Historial",
            font=self._f_small,
            bg=self.C["toggle_off"],
            fg=self.C["special_fg"],
            activebackground=self.C["active"],
            relief="flat",
            cursor="hand2",
            command=self._open_history,
        )
        self._history_btn.pack(side="right", padx=(0, 4))

    # ── Panel de funciones científicas ───────────────────────────

    def _create_science_panel(self):
        frame = tk.Frame(self.root, bg=self.C["bg"])
        frame.pack(fill="x", padx=6, pady=2)
        for col in range(6):
            frame.columnconfigure(col, weight=1, uniform="sci")

        self._sci_buttons: list[tk.Button] = []

        for col, spec in enumerate(self.SCIENCE_BUTTONS):
            text_norm, ins_norm, _text_inv, _ins_inv = spec
            btn = tk.Button(
                frame,
                text=text_norm,
                font=self._f_func,
                bg=self.C["func"],
                fg=self.C["func_fg"],
                activebackground=self.C["active"],
                relief="flat",
                command=lambda c=col: self._on_science(c),
            )
            btn.grid(row=0, column=col, sticky="nsew", padx=1, pady=1, ipady=0)
            self._sci_buttons.append(btn)

    # ── Teclado numérico / operadores ────────────────────────────

    def _create_keypad(self):
        frame = tk.Frame(self.root, bg=self.C["bg"])
        frame.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        # 12 columnas lógicas: mcm(6, 4) → fila de 6 botones [2×6] y filas de 4 botones [3×4]
        # (la última fila es 0, '.', 'A', '=' con el mismo reparto de 3×4)
        max_cols = 12
        for c in range(max_cols):
            frame.columnconfigure(c, weight=1, uniform="key")

        # Referencias a los botones por acción para sincronizar su estado
        # en fases posteriores (p. ej. disponibilidad del botón A según ANS).
        self._keypad_buttons: dict[str, tk.Button] = {}

        for r, row_def in enumerate(self.KEYPAD):
            spans = self._compute_spans(len(row_def), max_cols)
            col_pos = 0
            for idx, (text, action, kind) in enumerate(row_def):
                bg = self.C[kind]
                fg = self.C[f"{kind}_fg"]
                btn = tk.Button(
                    frame,
                    text=text,
                    font=self._f_btn,
                    bg=bg,
                    fg=fg,
                    activebackground=self.C["active"],
                    relief="flat",
                    command=lambda a=action: self._on_key(a),
                )
                btn.grid(
                    row=r,
                    column=col_pos,
                    columnspan=spans[idx],
                    sticky="nsew",
                    padx=1,
                    pady=1,
                    ipady=0,
                )
                self._keypad_buttons[action] = btn
                col_pos += spans[idx]

        for r in range(len(self.KEYPAD)):
            frame.rowconfigure(r, weight=1)

        # Referencia directa al botón de respuesta anterior (A). Se mantiene
        # habilitado provisionalmente; la sincronización con el estado real
        # de ANS se integrará en fases posteriores del plan.
        self._answer_btn = self._keypad_buttons.get("insert:A")

    @staticmethod
    def _compute_spans(cols_in_row: int, max_cols: int) -> list[int]:
        """Reparte max_cols entre cols_in_row botones."""
        base, extra = divmod(max_cols, cols_in_row)
        spans = [base] * cols_in_row
        # Asignar columnas extra al último botón (generalmente '=')
        spans[-1] += extra
        return spans

    # ── Atajos de teclado ────────────────────────────────────────

    def _bind_keyboard(self):
        self.expr_entry.bind("<Return>", lambda _e: self._calculate())
        self.expr_entry.bind("<KP_Enter>", lambda _e: self._calculate())
        self.root.bind("<Escape>", lambda _e: self._on_key("clear"))
        self.root.bind("<F5>", lambda _e: self._open_history())
        self.root.bind("<Key>", self._on_inactive_result_key, add="+")
        # Permitir escritura libre en el campo de expresión

    def _expression_is_inactive(self) -> bool:
        return getattr(self, "_expr_inactive_after_result", False)

    def _set_expression_editable(self, editable: bool):
        with contextlib.suppress(tk.TclError):
            self.expr_entry.configure(state="normal" if editable else "readonly")

    def _focus_expression_if_editable(self):
        if self._expression_is_inactive():
            with contextlib.suppress(tk.TclError):
                self.root.focus_set()
            return
        self.expr_entry.focus_set()

    def _deactivate_expression_after_result(self):
        self._expr_inactive_after_result = True
        self._set_expression_editable(False)
        with contextlib.suppress(tk.TclError):
            self.expr_entry.selection_clear()
        with contextlib.suppress(tk.TclError):
            self.root.focus_set()

    def _activate_expression_for_editing(self):
        if not self._expression_is_inactive():
            return
        self._expr_inactive_after_result = False
        # Editar la expresión antigua (clic o historial) limpia el cálculo
        # activo, cancela expansiones pendientes y desactiva la continuación
        # automática; el ANS confirmado permanece (Fase 5).
        self._valid_result_visible = False
        self._next_background_job_id()
        self._clear_engine_precision_state()
        self._set_expression_editable(True)

    def _reset_for_new_formula(self, *, preserve_answer_result: bool = False):
        """Prepara una fórmula nueva y descarta el cálculo activo.

        Una continuación automática con `A` conserva únicamente su valor
        visible como referencia mientras se compone la fórmula. El cálculo
        activo y su precisión se invalidan igual que en cualquier reinicio;
        AC, borrado y entradas independientes siguen mostrando `0`.
        """
        self._next_background_job_id()
        self._clear_engine_precision_state()
        self._activate_expression_for_editing()
        self.expr_var.set("")
        if not preserve_answer_result:
            self.result_display.set_text("0")
        self.result_display.finish_loading_more()
        self.result_display.mark_precision_exhausted()
        self._last_engine_result = None
        self._valid_result_visible = False

    def _begin_new_formula_from_inactive_result(
        self, *, preserve_answer_result: bool = False
    ):
        if self._expression_is_inactive():
            self._reset_for_new_formula(
                preserve_answer_result=preserve_answer_result
            )

    def _on_expression_click(self, _event):
        self._activate_expression_for_editing()

    def _on_inactive_result_key(self, event: tk.Event):
        if not self._expression_is_inactive():
            return None
        if event.keysym in ("Escape", "Return", "KP_Enter", "Tab"):
            return None
        # Solo Ctrl: en Windows el bit 0x0008 es NumLock (no Alt), por lo que
        # usar 0x000C bloqueaba la entrada con NumLock activado.
        if getattr(event, "state", 0) & 0x0004:
            return None
        if event.keysym in ("BackSpace", "Delete"):
            self._begin_new_formula_from_inactive_result()
            self._focus_expression_if_editable()
            return "break"

        char = getattr(event, "char", "")
        if not char or not char.isprintable() or char.isspace():
            return None

        # Teclado físico: solo los disparadores cerrados anteponen `A` tras
        # un resultado válido visible; cualquier otro carácter imprimible
        # empieza una fórmula independiente (sección 3.2 del plan ANS).
        text = char
        is_answer_continuation = (
            self._valid_result_visible
            and char in _PHYSICAL_RESULT_CONTINUATION_KEYS
        )
        if is_answer_continuation:
            text = "A" + char
        self._begin_new_formula_from_inactive_result(
            preserve_answer_result=is_answer_continuation
        )
        self._insert_at_cursor(text)
        self._focus_expression_if_editable()
        return "break"

    # ── Redimensionamiento ────────────────────────────────────────

    def _record_base_size(self):
        """Captura el tamaño inicial de la ventana para el escalado proporcional."""
        self.root.update_idletasks()
        self._base_size = (self.root.winfo_width(), self.root.winfo_height())

    def _on_root_configure(self, event: tk.Event):
        if event.widget is not self.root:
            return
        if self._base_size is None:
            return
        if self._resize_pending is not None:
            self.root.after_cancel(self._resize_pending)
        self._resize_pending = self.root.after(60, self._apply_font_scale_to_current)

    def _apply_font_scale_to_current(self):
        self._resize_pending = None
        if self._base_size is None:
            return
        bw, bh = self._base_size
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        if bw <= 0 or bh <= 0 or w <= 0 or h <= 0:
            return
        scale = min(w / bw, h / bh)
        scale = max(0.5, min(scale, 4.0))
        for name, base in self._base_font_sizes.items():
            new_size = max(8, round(base * scale))
            getattr(self, f"_f_{name}").config(size=new_size)
        self._fix_result_row_height()
        self.result_display.refresh_font_adjustment()

    def _apply_minimum_window_geometry(self):
        self.root.update_idletasks()
        width = self.root.winfo_reqwidth()
        height = self.root.winfo_reqheight()
        self.root.minsize(width, height)
        self.root.geometry(f"{width}x{height}")

    def _next_background_job_id(self) -> int:
        self._cancel_pending_background_jobs()
        self._background_job_seq += 1
        self._active_background_job_id = self._background_job_seq
        return self._active_background_job_id

    def _is_active_background_job(self, job_id: int) -> bool:
        return not self._closing and job_id == self._active_background_job_id

    def _engine_can_expand_precision(self) -> bool:
        if not hasattr(self.engine, "request_more_precision"):
            return False

        checker = getattr(self.engine, "can_expand_precision", None)
        if callable(checker):
            return bool(checker())

        return True

    def _sync_result_precision_availability(self):
        if self._engine_can_expand_precision():
            self.result_display.reset_precision_exhausted()
        else:
            self.result_display.mark_precision_exhausted()

    def _clear_engine_precision_state(self):
        clearer = getattr(self.engine, "clear_last_calculation", None)
        if callable(clearer):
            clearer()

    def _schedule_on_ui_thread(self, callback, job_id: int | None = None):
        if self._closing:
            return

        def _run_if_valid():
            if self._closing:
                return
            if job_id is not None and not self._is_active_background_job(job_id):
                return
            callback()

        with contextlib.suppress(tk.TclError):
            self.root.after(0, _run_if_valid)

    def _cancel_pending_background_jobs(self):
        active_futures = []
        for future in self._background_futures:
            if future.done():
                continue
            if future.running():
                active_futures.append(future)
                continue
            if not future.cancel():
                active_futures.append(future)
        self._background_futures = active_futures

    def _submit_background(self, fn) -> bool:
        if self._closing:
            return False
        try:
            future = self._background_executor.submit(fn)
        except RuntimeError:
            return False
        self._background_futures = [
            tracked for tracked in self._background_futures if not tracked.done()
        ]
        self._background_futures.append(future)
        return True

    def _on_close(self):
        if self._closing:
            return
        self._closing = True
        self._background_executor.shutdown(wait=False, cancel_futures=True)
        self._background_futures.clear()
        self.root.destroy()

    # ── Acciones ─────────────────────────────────────────────────

    def _on_key(self, action: str):
        if action == "clear":
            self._reset_for_new_formula()
        elif action == "backspace":
            if self._expression_is_inactive():
                self._reset_for_new_formula()
                self._focus_expression_if_editable()
                return
            cur = self.expr_var.get()
            pos = self.expr_entry.index(tk.INSERT)
            if pos > 0:
                self.expr_var.set(cur[: pos - 1] + cur[pos:])
                self.expr_entry.icursor(pos - 1)
        elif action == "equals":
            self._calculate()
        elif action.startswith("insert:"):
            # La plantilla se resuelve ANTES de consumir el contexto: con un
            # resultado válido visible, operadores y postfijos construyen la
            # continuación con `A` (sección 3.2 del plan ANS). En ese único
            # caso el valor visible de A permanece hasta confirmar la fórmula.
            is_answer_continuation = (
                self._valid_result_visible
                and action in _RESULT_CONTINUATION_TEMPLATES
            )
            text = self._resolve_button_insertion(action)
            self._begin_new_formula_from_inactive_result(
                preserve_answer_result=is_answer_continuation
            )
            self._insert_at_cursor(text)
        self._focus_expression_if_editable()

    def _on_science(self, col: int):
        is_answer_continuation = (
            self._valid_result_visible
            and (col, self._inv_mode) in _SCIENCE_RESULT_TEMPLATES
        )
        text_to_insert = self._science_button_insertion(col)
        self._begin_new_formula_from_inactive_result(
            preserve_answer_result=is_answer_continuation
        )
        self._insert_at_cursor(text_to_insert)
        self._focus_expression_if_editable()

    def _insert_at_cursor(self, text: str):
        pos = self.expr_entry.index(tk.INSERT)
        cur = self.expr_var.get()
        self.expr_var.set(cur[:pos] + text + cur[pos:])
        self.expr_entry.icursor(pos + len(text))
        self.expr_entry.xview(tk.INSERT)

    # ── Continuación posresultado con `A` (Fase 5) ──────────────

    def _resolve_button_insertion(self, action: str) -> str:
        """Texto que inserta un botón del teclado según la pantalla.

        Con un resultado válido visible, los operadores binarios y los
        postfijos construyen la continuación con `A` de la sección 3.2 del
        plan; el botón `A` es una referencia manual que nunca se duplica;
        dígitos, `.`, `π`, `e` y agrupadores empiezan una fórmula
        independiente con su inserción normal. Con pantalla limpia o fórmula
        activa, todo botón se comporta como siempre aunque el motor tenga
        ANS en memoria.
        """
        text = action[7:]
        if not self._valid_result_visible or action == "insert:A":
            return text
        return _RESULT_CONTINUATION_TEMPLATES.get(action, text)

    def _science_button_insertion(self, col: int) -> str:
        """Texto que inserta un botón científico según la pantalla.

        Con un resultado válido visible, cada botón —normal o INV— aplica su
        plantilla posresultado (`√(A)`, `sin(A)`, `A^(2)`, `exp(A)`, ...);
        en cualquier otro caso inserta su plantilla vacía habitual aunque el
        motor tenga ANS en memoria.
        """
        if self._valid_result_visible:
            template = _SCIENCE_RESULT_TEMPLATES.get((col, self._inv_mode))
            if template is not None:
                return template
        spec = self.SCIENCE_BUTTONS[col]
        return spec[3] if self._inv_mode else spec[1]

    # ── Toggles ──────────────────────────────────────────────────

    def _toggle_angle(self):
        if self.engine.angle_mode == "rad":
            self.engine.angle_mode = "deg"
            self.angle_btn.config(text="DEG", bg=self.C["op"], fg=self.C["op_fg"])
        else:
            self.engine.angle_mode = "rad"
            self.angle_btn.config(text="RAD", bg=self.C["toggle_on"], fg=self.C["bg"])
        self._focus_expression_if_editable()

    def _toggle_inv(self):
        self._inv_mode = not self._inv_mode
        if self._inv_mode:
            self.inv_btn.config(bg=self.C["toggle_on"], fg=self.C["bg"])
            for col, spec in enumerate(self.SCIENCE_BUTTONS):
                self._sci_buttons[col].config(text=spec[2])
        else:
            self.inv_btn.config(bg=self.C["toggle_off"], fg=self.C["special_fg"])
            for col, spec in enumerate(self.SCIENCE_BUTTONS):
                self._sci_buttons[col].config(text=spec[0])
        self._focus_expression_if_editable()

    # ── Diálogo de configuración ─────────────────────────────────

    def _open_settings(self):
        open_settings_dialog(self)

    # ── Historial ─────────────────────────────────────────────────

    def _open_history(self):
        """Abre (o trae al frente) la ventana de historial.

        La ventana comparte `self._history` (tuplas simples) y recibe los
        callbacks de reutilización y cálculo; ver `_reuse_history_expr`
        para la semántica contextual del doble clic (Fase 6).
        """
        if self._history_window is not None and self._history_window.is_open():
            self._history_window.refresh()
            self._history_window.lift()
            return
        self._history_window = HistoryWindow(
            self.root,
            self._history,
            on_reuse=self._reuse_history_expr,
            on_calculate=self._calculate,
        )

    def _reuse_history_expr(self, expr: str):
        """Coloca una expresión del historial y deja listo su recálculo.

        El doble clic del historial invoca esto antes de `_calculate()`, de
        modo que la solicitud se crea después de colocar la expresión y
        captura el ANS confirmado en ese instante —o el cero por defecto si
        aún no existe receta—. Una expresión con `A` se recalcula con el
        ANS actual, por lo que el resultado puede diferir del guardado en
        la entrada histórica (Fase 6). Como `_activate_expression_for_editing`,
        reutilizar del historial limpia el cálculo activo y cancela
        expansiones pendientes conservando el ANS.
        """
        self._activate_expression_for_editing()
        self.expr_var.set(expr)
        self.expr_entry.icursor(tk.END)
        self.expr_entry.focus_set()

    def _add_to_history(self, expr: str, result: str):
        """Registra (expresión, resultado) con deduplicación por expresión.

        `self._history` sigue siendo `list[tuple[str, str]]`: nunca guarda
        recetas ni valores ocultos (Fase 6). Una nueva evaluación de la
        misma fórmula reemplaza su entrada anterior por el resultado más
        reciente; la expresión se almacena literal, con `A` incluida.
        """
        normalized_expr = expr.replace(" ", "")
        self._history[:] = [
            item for item in self._history if item[0] != normalized_expr
        ]
        self._history.append((normalized_expr, result))
        if self._history_window is not None and self._history_window.is_open():
            self._history_window.refresh()

    def _reload_result_display_config(self):
        ResultDisplay.VISIBLE_CHARS = get_visible_chars()
        ResultDisplay.DECIMAL_SEPARATOR = get_decimal_separator_enabled()

    def restart_ui_after_config_change(self):
        """Reconstruye la interfaz tras un cambio de configuración.

        Conserva el motor —y con él la respuesta ANS confirmada— y el
        historial (Fase 6); limpia solo el cálculo activo, el contexto de
        continuación posresultado y los trabajos pendientes. La pantalla
        reconstruida queda limpia: aunque la memoria sobreviva, no se
        reactiva la inserción automática de `A`, y el botón `A` se
        reconstruye habilitado. Una instancia nueva del motor arrancaría
        sin receta ANS, con `A = 0`.
        """
        if getattr(self, "_closing", False):
            return

        engine = self.engine
        history = list(getattr(self, "_history", []))
        self._next_background_job_id()
        self._clear_engine_precision_state()

        with contextlib.suppress(tk.TclError):
            self.root.state("normal")

        pending_after_id = getattr(self, "_resize_pending", None)
        if pending_after_id is not None:
            with contextlib.suppress(tk.TclError):
                self.root.after_cancel(pending_after_id)
            self._resize_pending = None

        with contextlib.suppress(AttributeError, RuntimeError):
            self._background_executor.shutdown(wait=False, cancel_futures=True)
        self._background_futures = []

        for child in self.root.winfo_children():
            child.destroy()

        self.__init__(self.root, engine=engine)
        self._history = history

    # ── Cálculo en hilo separado ─────────────────────────────────

    def _calculate(self):
        expr = self.expr_var.get().strip()
        if not expr:
            return

        job_id = self._next_background_job_id()
        self.result_display.finish_loading_more()
        # Solicitud inmutable creada en el hilo de UI antes del envío:
        # captura ANS (o el fallback 0), modo angular y revisiones exactos.
        request = self.engine.create_evaluation_request(expr)

        def _run():
            # Fase pura: el worker valida, compila y evalúa sin mutar el motor.
            try:
                candidate = self.engine.evaluate_request(request)
            except (
                ValueError,
                ZeroDivisionError,
                OverflowError,
                ArithmeticError,
                TypeError,
            ) as exc:
                error_name = type(exc).__name__
                msg = str(exc) if str(exc) else error_name

                def _apply_error():
                    # Error vigente: limpia solo el cálculo activo y el
                    # contexto de continuación; ANS (o el fallback 0) queda.
                    self._clear_engine_precision_state()
                    self._last_engine_result = None
                    self.result_display.set_text(f"Error: {msg}")
                    self.result_display.mark_precision_exhausted()
                    self._valid_result_visible = False

                self._schedule_on_ui_thread(_apply_error, job_id=job_id)
            else:

                def _apply_candidate():
                    try:
                        result = self.engine.commit_evaluation(candidate)
                    except ValueError:
                        # Candidato obsoleto a nivel de motor: un trabajo
                        # viejo nunca toca ANS, pantalla ni historial.
                        return
                    # Único punto que actualiza resultado, disponibilidad de
                    # precisión, historial y estado de la expresión; solo una
                    # confirmación correcta habilita el resultado visible.
                    self._last_engine_result = result
                    self.result_display.set_text(result)
                    self._sync_result_precision_availability()
                    self._add_to_history(expr, result)
                    self._deactivate_expression_after_result()
                    # Único punto que habilita la continuación posresultado:
                    # el resultado válido queda visible en pantalla (Fase 5).
                    self._valid_result_visible = True

                self._schedule_on_ui_thread(_apply_candidate, job_id=job_id)

        self._submit_background(_run)

    # ── Copiar resultado ─────────────────────────────────────────

    def _on_copy_press(self, event):
        self._shift_copy = bool(event.state & 0x1)  # bit 0 = Shift
        self._ctrl_copy = bool(event.state & 0x4)  # bit 2 = Ctrl

    def _copy_result(self):
        standard_scientific = self._ctrl_copy
        plain_decimal = self._shift_copy and not standard_scientific
        self._shift_copy = False
        self._ctrl_copy = False
        text = self.result_display.get_copy_text(
            plain_decimal=plain_decimal,
            standard_scientific=standard_scientific,
        )
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._focus_expression_if_editable()

    def _request_more_precision(self):
        if not self._engine_can_expand_precision():
            self.result_display.mark_precision_exhausted()
            self.result_display.finish_loading_more()
            return

        job_id = self._next_background_job_id()

        try:
            # Solicitud inmutable capturada en el hilo de UI antes del envío.
            request = self.engine.create_precision_request()
        except (
            ValueError,
            ZeroDivisionError,
            OverflowError,
            ArithmeticError,
            TypeError,
        ):
            # Sin cálculo ampliable: ANS intacto y sin carga bloqueada.
            self.result_display.mark_precision_exhausted()
            self.result_display.finish_loading_more()
            return

        def _run():
            # Fase pura: reevalúa la cadena completa sin mutar el motor.
            try:
                candidate = self.engine.evaluate_precision_request(request)
            except (
                ValueError,
                ZeroDivisionError,
                OverflowError,
                ArithmeticError,
                TypeError,
            ):

                def _apply_precision_error():
                    self.result_display.mark_precision_exhausted()

                self._schedule_on_ui_thread(_apply_precision_error, job_id=job_id)
            else:

                def _apply_expanded():
                    try:
                        updated = self.engine.commit_precision(candidate)
                    except ValueError:
                        # Expansión obsoleta a nivel de motor: sin cambios
                        # de valor, dígitos, scroll ni estado de carga.
                        return
                    if (
                        self._last_engine_result is not None
                        and updated == self._last_engine_result
                    ):
                        self.result_display.mark_precision_exhausted()
                        return
                    # La confirmación de una expansión actualiza solo el
                    # texto y el valor activos; la receta ANS ya es la misma.
                    self._last_engine_result = updated
                    self.result_display.set_text(updated, preserve_view=True)

                self._schedule_on_ui_thread(_apply_expanded, job_id=job_id)
            finally:
                self._schedule_on_ui_thread(
                    self.result_display.finish_loading_more, job_id=job_id
                )

        submitted = self._submit_background(_run)
        if not submitted:
            self.result_display.finish_loading_more()
