"""
Ventana principal de la calculadora científica.

Contiene CalculatorApp: construye y gestiona los controles de la
interfaz, el teclado, los toggles y el hilo de cálculo en segundo plano.
"""

from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import font as tkfont

from calculator_engine import CalculatorEngine
from calculator_ui_results import ResultDisplay


# ═════════════════════════════════════════════════════════════════
#  Aplicación principal
# ═════════════════════════════════════════════════════════════════

class CalculatorApp:
    """Ventana principal de la calculadora científica."""

    # ── Paleta de colores ────────────────────────────────────────
    C = {
        "bg":         "#1E1E2E",
        "display_bg": "#181825",
        "num":        "#313244",
        "num_fg":     "#CDD6F4",
        "op":         "#F38BA8",
        "op_fg":      "#1E1E2E",
        "func":       "#45475A",
        "func_fg":    "#CDD6F4",
        "special":    "#585B70",
        "special_fg": "#CDD6F4",
        "equals":     "#89B4FA",
        "equals_fg":  "#1E1E2E",
        "toggle_on":  "#A6E3A1",
        "toggle_off": "#585B70",
        "expr_fg":    "#BAC2DE",
        "result_fg":  "#A6E3A1",
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
        self.root = root
        self.root.title("Calculadora Cient\u00EDfica")
        self.root.configure(bg=self.C["bg"])
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.engine = engine if engine is not None else CalculatorEngine()
        self._inv_mode = False
        self._last_engine_result: str | None = None
        self._shift_copy = False
        self._ctrl_copy = False
        self._background_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="calculator")
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
        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_reqwidth(), self.root.winfo_reqheight())

        # Foco inicial en el campo de expresión
        self.expr_entry.focus_set()

        # Escalado de fuentes al redimensionar
        self._base_size: tuple[int, int] | None = None
        self._resize_pending: str | None = None
        self.root.after(250, self._record_base_size)
        self.root.bind("<Configure>", self._on_root_configure)

    # ── Fuentes ──────────────────────────────────────────────────

    def _init_fonts(self):
        self._f_expr   = tkfont.Font(family="Consolas", size=16)
        self._f_result = tkfont.Font(family="Consolas", size=22, weight="bold")
        self._f_btn    = tkfont.Font(family="Segoe UI", size=15)
        self._f_func   = tkfont.Font(family="Segoe UI", size=12)
        self._f_small  = tkfont.Font(family="Segoe UI", size=11)
        self._base_font_sizes = {"expr": 16, "result": 22, "btn": 15, "func": 12, "small": 11}

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
            relief="flat", justify="right", bd=0,
        )
        self.expr_entry.pack(fill="x", pady=(4, 0))

        # Fila del resultado + botón copiar
        row = tk.Frame(frame, bg=self.C["display_bg"])
        row.pack(fill="x", pady=(2, 4))

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
            activebackground=self.C["special"], relief="flat",
            cursor="hand2", command=self._copy_result, padx=8,
        )
        self._copy_btn.bind("<Button-1>", self._on_copy_press)
        self._copy_btn.pack(side="right", padx=(6, 0))

        self.result_display.widget.pack(side="right")

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
                activebackground=self.C["special"], relief="flat",
                command=lambda c=col: self._on_science(c),
            )
            btn.grid(row=0, column=col, sticky="nsew", padx=2, pady=2,
                     ipady=6)
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
                    bg=bg, fg=fg, activebackground=self.C["special"],
                    relief="flat",
                    command=lambda a=action: self._on_key(a),
                )
                btn.grid(row=r, column=col_pos, columnspan=spans[idx],
                         sticky="nsew", padx=2, pady=2, ipady=8)
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
        # Permitir escritura libre en el campo de expresión

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

    def _next_background_job_id(self) -> int:
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

    def _submit_background(self, fn) -> bool:
        if self._closing:
            return False
        try:
            self._background_executor.submit(fn)
        except RuntimeError:
            return False
        return True

    def _on_close(self):
        if self._closing:
            return
        self._closing = True
        self._background_executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()

    # ── Acciones ─────────────────────────────────────────────────

    def _on_key(self, action: str):
        if action == "clear":
            self._next_background_job_id()
            self.expr_var.set("")
            self.result_display.set_text("0")
            self.result_display.finish_loading_more()
            self.result_display.reset_precision_exhausted()
            self._last_engine_result = None
        elif action == "backspace":
            cur = self.expr_var.get()
            pos = self.expr_entry.index(tk.INSERT)
            if pos > 0:
                self.expr_var.set(cur[:pos - 1] + cur[pos:])
                self.expr_entry.icursor(pos - 1)
        elif action == "equals":
            self._calculate()
        elif action.startswith("insert:"):
            text = action[7:]
            self._insert_at_cursor(text)
        self.expr_entry.focus_set()

    def _on_science(self, col: int):
        spec = self.SCIENCE_BUTTONS[col]
        if self._inv_mode:
            text_to_insert = spec[3]   # ins_inv
        else:
            text_to_insert = spec[1]   # ins_norm
        self._insert_at_cursor(text_to_insert)
        self.expr_entry.focus_set()

    def _insert_at_cursor(self, text: str):
        pos = self.expr_entry.index(tk.INSERT)
        cur = self.expr_var.get()
        self.expr_var.set(cur[:pos] + text + cur[pos:])
        self.expr_entry.icursor(pos + len(text))

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
        self.expr_entry.focus_set()

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
        self.expr_entry.focus_set()

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

                self._schedule_on_ui_thread(_apply_result, job_id=job_id)
            except (ValueError, ZeroDivisionError, OverflowError,
                    ArithmeticError, TypeError) as exc:
                error_name = type(exc).__name__
                msg = str(exc) if str(exc) else error_name

                def _apply_error():
                    self._last_engine_result = None
                    self.result_display.set_text(f"Error: {msg}")

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
        self.expr_entry.focus_set()

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
            except Exception:
                pass
            finally:
                self._schedule_on_ui_thread(self.result_display.finish_loading_more)

        submitted = self._submit_background(_run)
        if not submitted:
            self.result_display.finish_loading_more()
