"""
Ventana principal de la calculadora científica.

Contiene CalculatorApp: construye y gestiona los controles de la
interfaz, el teclado, los toggles y el hilo de cálculo en segundo plano.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tkinter as tk
from tkinter import font as tkfont

from arbitrary_precision_engine import ArbitraryPrecisionCalculatorEngine
from calculator_config_normalizations import get_decimal_separator_enabled, get_visible_chars
from calculator_ui_results import ResultDisplay
from calculator_ui_settings import open_settings_dialog
from calculator_ui_history import HistoryWindow


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
        "bg":         "#2E3440",   # Polar Night 1  – fondo general
        "display_bg": "#242933",   # más oscuro para la pantalla
        "num":        "#3B4252",   # Polar Night 2  – dígitos (oscuro)
        "num_fg":     "#ECEFF4",   # Snow Storm 3
        "op":         "#D08770",   # Aurora Orange  – operadores básicos
        "op_fg":      "#2E3440",
        "func":       "#4C566A",   # Polar Night 4  – funciones (más claro que num)
        "func_fg":    "#ECEFF4",
        "special":    "#BF616A",   # Aurora Red     – AC / borrar (destructivo)
        "special_fg": "#ECEFF4",
        "equals":     "#A3BE8C",   # Aurora Green   – igual (confirmar)
        "equals_fg":  "#2E3440",
        "toggle_on":  "#88C0D0",   # Frost          – modo activo
        "toggle_off": "#434C5E",   # Polar Night 3  – modo inactivo
        "active":     "#cdb5cd",   # Aurora Pink    – fondo botón activo (hover o toggle on)
        "expr_fg":    "#D8DEE9",   # Snow Storm 1
        "result_fg":  "#88C0D0",   # Frost          – resultado
    }

    # ── Definiciones de botones científicos ──────────────────────
    #  (texto_normal, inserta_normal, texto_inv, inserta_inv)

    SCIENCE_BUTTONS = [
        ("\u221A",   "\u221A(",   "x\u00B2",       "^(2)"),    # √  / x²
        ("sin",      "sin(",      "sin\u207B\u00B9","asin("),   # sin / asin
        ("cos",      "cos(",      "cos\u207B\u00B9","acos("),   # cos / acos
        ("tan",      "tan(",      "tan\u207B\u00B9","atan("),   # tan / atan
        ("ln",       "ln(",       "e\u02E3",        "exp("),    # ln  / eˣ
        ("log",      "log(",      "10\u02E3",       "10^("),    # log / 10ˣ
    ]

    # ── Definiciones del teclado principal ────────────────────────
    #  Cada fila es una lista de (texto, acción, tipo_color)
    #  tipo_color: "num", "op", "func", "special", "equals"

    KEYPAD = [
        [("!",  "insert:!",  "func"),  ("^", "insert:^", "func"),
         ("\u03C0","insert:\u03C0","func"), ("e","insert:e","func"),
         ("(",  "insert:(",  "func"),  (")", "insert:)", "func")],

        [("AC", "clear",     "special"), ("\u232B","backspace","special"),
         ("%",  "insert:%",  "func"),    ("\u00F7","insert:\u00F7","op")],

        [("7",  "insert:7",  "num"), ("8","insert:8","num"),
         ("9",  "insert:9",  "num"), ("\u00D7","insert:\u00D7","op")],

        [("4",  "insert:4",  "num"), ("5","insert:5","num"),
         ("6",  "insert:6",  "num"), ("\u2212","insert:\u2212","op")],

        [("1",  "insert:1",  "num"), ("2","insert:2","num"),
         ("3",  "insert:3",  "num"), ("+","insert:+","op")],

        [("0",  "insert:0",  "num"), (".",  "insert:.",  "num"),
         ("=",  "equals",    "equals")],
    ]

    # ────────────────────────────────────────────────────────────

    def __init__(self, root: tk.Tk, engine=None):
        self._reload_result_display_config()
        self.root = root
        self.root.title("Calculadora Cient\u00EDfica")
        self.root.configure(bg=self.C["bg"])
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._apply_window_icon()

        self.engine = engine if engine is not None else ArbitraryPrecisionCalculatorEngine()
        self._inv_mode = False
        self._last_engine_result: str | None = None
        self._history: list[tuple[str, str]] = []
        self._history_window: HistoryWindow | None = None
        self._shift_copy = False
        self._ctrl_copy = False
        self._expr_inactive_after_result = False
        self._background_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="calculator")
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
            if (exe_dir / "icon-calculator.ico").exists() or (exe_dir / "icons").exists():
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
        try:
            if ico_path.exists():
                self.root.iconbitmap(default=str(ico_path))
        except tk.TclError:
            pass

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
            try:
                self.root.iconphoto(True, *photos)
            except tk.TclError:
                pass

    # ── Fuentes ──────────────────────────────────────────────────

    def _init_fonts(self):
        self._f_expr   = tkfont.Font(family="Consolas", size=19)
        self._f_result = tkfont.Font(family="Consolas", size=25, weight="bold")
        self._f_btn    = tkfont.Font(family="Segoe UI", size=18)
        self._f_func   = tkfont.Font(family="Segoe UI", size=14)
        self._f_small  = tkfont.Font(family="Segoe UI", size=12)
        self._base_font_sizes = {"expr": 19, "result": 25, "btn": 18, "func": 14, "small": 12}

    # ── Pantalla ─────────────────────────────────────────────────

    def _create_display(self):
        frame = tk.Frame(self.root, bg=self.C["display_bg"], padx=12, pady=8)
        frame.pack(fill="x", padx=6, pady=(6, 2))

        # Campo de expresión (editable)
        self.expr_var = tk.StringVar()
        self.expr_entry = tk.Entry(
            frame, textvariable=self.expr_var,
            font=self._f_expr, bg=self.C["display_bg"],
            fg=self.C["expr_fg"], insertbackground=self.C["expr_fg"],
            readonlybackground=self.C["display_bg"],
            relief="flat", justify="right", bd=0,
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
            font=self._f_result, bg=self.C["display_bg"],
            fg=self.C["result_fg"],
            readonlybackground=self.C["display_bg"],
            relief="flat", justify="right", bd=0,
        )

        self._copy_btn = tk.Button(
            row, text="Copiar", font=self._f_small,
            bg=self.C["func"], fg=self.C["func_fg"],
            activebackground=self.C["active"], relief="flat",
            cursor="hand2", command=self._copy_result, padx=8,
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
            width=getattr(self.result_display, "_base_entry_width_chars", ResultDisplay.VISIBLE_CHARS + 1),
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
            frame, text="RAD", font=self._f_small, width=6,
            bg=self.C["toggle_on"], fg=self.C["bg"],
            activebackground=self.C["toggle_on"], relief="flat",
            command=self._toggle_angle,
        )
        self.angle_btn.pack(side="left", padx=(0, 4))

        self.inv_btn = tk.Button(
            frame, text="INV", font=self._f_small, width=6,
            bg=self.C["toggle_off"], fg=self.C["special_fg"],
            activebackground=self.C["toggle_off"], relief="flat",
            command=self._toggle_inv,
        )
        self.inv_btn.pack(side="left")

        self._settings_btn = tk.Button(
            frame, text="\u2699", font=self._f_small,
            bg=self.C["toggle_off"], fg="#EBCB8B",
            activebackground=self.C["active"], relief="flat",
            cursor="hand2", command=self._open_settings,
        )
        self._settings_btn.pack(side="right")

        self._history_btn = tk.Button(
            frame, text="Historial", font=self._f_small,
            bg=self.C["toggle_off"], fg=self.C["special_fg"],
            activebackground=self.C["active"], relief="flat",
            cursor="hand2", command=self._open_history,
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
                frame, text=text_norm, font=self._f_func,
                bg=self.C["func"], fg=self.C["func_fg"],
                activebackground=self.C["active"], relief="flat",
                command=lambda c=col: self._on_science(c),
            )
            btn.grid(row=0, column=col, sticky="nsew", padx=1, pady=1,
                     ipady=0)
            self._sci_buttons.append(btn)

    # ── Teclado numérico / operadores ────────────────────────────

    def _create_keypad(self):
        frame = tk.Frame(self.root, bg=self.C["bg"])
        frame.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        # 12 columnas lógicas: LCM(4, 6) → filas de 6 botones [2×6] y de 4 botones [3×4]
        max_cols = 12
        for c in range(max_cols):
            frame.columnconfigure(c, weight=1, uniform="key")

        for r, row_def in enumerate(self.KEYPAD):
            cols_in_row = len(row_def)
            # Última fila: 0 ocupa 2 espacios de botón, '.' y '=' ocupan 1 cada uno
            if r == len(self.KEYPAD) - 1:
                spans = [6, 3, 3]
            else:
                spans = self._compute_spans(cols_in_row, max_cols)
            col_pos = 0
            for idx, (text, action, kind) in enumerate(row_def):
                bg = self.C[kind]
                fg = self.C[f"{kind}_fg"]
                btn = tk.Button(
                    frame, text=text, font=self._f_btn,
                    bg=bg, fg=fg, activebackground=self.C["active"],
                    relief="flat",
                    command=lambda a=action: self._on_key(a),
                )
                btn.grid(row=r, column=col_pos, columnspan=spans[idx],
                         sticky="nsew", padx=1, pady=1, ipady=0)
                col_pos += spans[idx]

        for r in range(len(self.KEYPAD)):
            frame.rowconfigure(r, weight=1)

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
        try:
            self.expr_entry.configure(state="normal" if editable else "readonly")
        except tk.TclError:
            pass

    def _focus_expression_if_editable(self):
        if self._expression_is_inactive():
            try:
                self.root.focus_set()
            except tk.TclError:
                pass
            return
        self.expr_entry.focus_set()

    def _deactivate_expression_after_result(self):
        self._expr_inactive_after_result = True
        self._set_expression_editable(False)
        try:
            self.expr_entry.selection_clear()
        except tk.TclError:
            pass
        try:
            self.root.focus_set()
        except tk.TclError:
            pass

    def _activate_expression_for_editing(self):
        if not self._expression_is_inactive():
            return
        self._expr_inactive_after_result = False
        self._set_expression_editable(True)

    def _reset_for_new_formula(self):
        self._next_background_job_id()
        self._clear_engine_precision_state()
        self._activate_expression_for_editing()
        self.expr_var.set("")
        self.result_display.set_text("0")
        self.result_display.finish_loading_more()
        self.result_display.mark_precision_exhausted()
        self._last_engine_result = None

    def _begin_new_formula_from_inactive_result(self):
        if self._expression_is_inactive():
            self._reset_for_new_formula()

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

        self._begin_new_formula_from_inactive_result()
        self._insert_at_cursor(char)
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

        try:
            self.root.after(0, _run_if_valid)
        except tk.TclError:
            pass

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
        self._background_futures = [tracked for tracked in self._background_futures if not tracked.done()]
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
                self.expr_var.set(cur[:pos - 1] + cur[pos:])
                self.expr_entry.icursor(pos - 1)
        elif action == "equals":
            self._calculate()
        elif action.startswith("insert:"):
            self._begin_new_formula_from_inactive_result()
            text = action[7:]
            self._insert_at_cursor(text)
        self._focus_expression_if_editable()

    def _on_science(self, col: int):
        self._begin_new_formula_from_inactive_result()
        spec = self.SCIENCE_BUTTONS[col]
        if self._inv_mode:
            text_to_insert = spec[3]   # ins_inv
        else:
            text_to_insert = spec[1]   # ins_norm
        self._insert_at_cursor(text_to_insert)
        self._focus_expression_if_editable()

    def _insert_at_cursor(self, text: str):
        pos = self.expr_entry.index(tk.INSERT)
        cur = self.expr_var.get()
        self.expr_var.set(cur[:pos] + text + cur[pos:])
        self.expr_entry.icursor(pos + len(text))
        self.expr_entry.xview(tk.INSERT)

    # ── Toggles ──────────────────────────────────────────────────

    def _toggle_angle(self):
        if self.engine.angle_mode == "rad":
            self.engine.angle_mode = "deg"
            self.angle_btn.config(text="DEG", bg=self.C["op"],
                                  fg=self.C["op_fg"])
        else:
            self.engine.angle_mode = "rad"
            self.angle_btn.config(text="RAD", bg=self.C["toggle_on"],
                                  fg=self.C["bg"])
        self._focus_expression_if_editable()

    def _toggle_inv(self):
        self._inv_mode = not self._inv_mode
        if self._inv_mode:
            self.inv_btn.config(bg=self.C["toggle_on"], fg=self.C["bg"])
            for col, spec in enumerate(self.SCIENCE_BUTTONS):
                self._sci_buttons[col].config(text=spec[2])
        else:
            self.inv_btn.config(bg=self.C["toggle_off"],
                                fg=self.C["special_fg"])
            for col, spec in enumerate(self.SCIENCE_BUTTONS):
                self._sci_buttons[col].config(text=spec[0])
        self._focus_expression_if_editable()

    # ── Diálogo de configuración ─────────────────────────────────

    def _open_settings(self):
        open_settings_dialog(self)

    # ── Historial ─────────────────────────────────────────────────

    def _open_history(self):
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
        self._activate_expression_for_editing()
        self.expr_var.set(expr)
        self.expr_entry.icursor(tk.END)
        self.expr_entry.focus_set()

    def _add_to_history(self, expr: str, result: str):
        normalized_expr = expr.replace(" ", "")
        self._history[:] = [
            item for item in self._history
            if item[0] != normalized_expr
        ]
        self._history.append((normalized_expr, result))
        if self._history_window is not None and self._history_window.is_open():
            self._history_window.refresh()

    def _reload_result_display_config(self):
        ResultDisplay.VISIBLE_CHARS = get_visible_chars()
        ResultDisplay.DECIMAL_SEPARATOR = get_decimal_separator_enabled()

    def restart_ui_after_config_change(self):
        if getattr(self, "_closing", False):
            return

        engine = self.engine
        history = list(getattr(self, "_history", []))
        self._next_background_job_id()
        self._clear_engine_precision_state()

        try:
            self.root.state("normal")
        except tk.TclError:
            pass

        if getattr(self, "_resize_pending", None) is not None:
            try:
                self.root.after_cancel(self._resize_pending)
            except tk.TclError:
                pass
            self._resize_pending = None

        try:
            self._background_executor.shutdown(wait=False, cancel_futures=True)
        except (AttributeError, RuntimeError):
            pass
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

        def _run():
            try:
                result = self.engine.evaluate(expr)

                def _apply_result():
                    self._last_engine_result = result
                    self.result_display.set_text(result)
                    self._sync_result_precision_availability()
                    self._add_to_history(expr, result)
                    self._deactivate_expression_after_result()

                self._schedule_on_ui_thread(_apply_result, job_id=job_id)
            except (ValueError, ZeroDivisionError, OverflowError,
                    ArithmeticError, TypeError) as exc:
                error_name = type(exc).__name__
                msg = str(exc) if str(exc) else error_name

                def _apply_error():
                    self._clear_engine_precision_state()
                    self._last_engine_result = None
                    self.result_display.set_text(f"Error: {msg}")
                    self.result_display.mark_precision_exhausted()

                self._schedule_on_ui_thread(_apply_error, job_id=job_id)

        self._submit_background(_run)

    # ── Copiar resultado ─────────────────────────────────────────

    def _on_copy_press(self, event):
        self._shift_copy = bool(event.state & 0x1)  # bit 0 = Shift
        self._ctrl_copy = bool(event.state & 0x4)   # bit 2 = Ctrl

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

        def _run():
            try:
                updated = self.engine.request_more_precision()
                if self._last_engine_result is not None and updated == self._last_engine_result:
                    self._schedule_on_ui_thread(
                        self.result_display.mark_precision_exhausted,
                        job_id=job_id,
                    )
                    return

                def _apply_updated_result():
                    self._last_engine_result = updated
                    self.result_display.set_text(
                        updated,
                        preserve_view=True,
                    )

                self._schedule_on_ui_thread(_apply_updated_result, job_id=job_id)
            except (ValueError, ZeroDivisionError, OverflowError,
                    ArithmeticError, TypeError):
                self._schedule_on_ui_thread(
                    self.result_display.mark_precision_exhausted,
                    job_id=job_id,
                )
            finally:
                self._schedule_on_ui_thread(
                    self.result_display.finish_loading_more,
                    job_id=job_id,
                )

        submitted = self._submit_background(_run)
        if not submitted:
            self.result_display.finish_loading_more()
