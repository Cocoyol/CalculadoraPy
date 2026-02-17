"""
Interfaz gráfica de la calculadora científica.

Usa tkinter. El procesamiento se ejecuta en un hilo aparte
para no bloquear la interfaz.
"""

import threading
import tkinter as tk
import re
from tkinter import font as tkfont

from calculator_engine import CalculatorEngine


# ═════════════════════════════════════════════════════════════════
#  Widget: campo de resultado con scroll lateral gradual
# ═════════════════════════════════════════════════════════════════

class ResultDisplay:
    """Entry de solo lectura con scroll horizontal gradual."""

    SCROLL_STEPS = 3        # caracteres por evento de rueda
    SCROLL_INTERVAL = 25    # ms entre pasos de animación
    DRAG_THRESHOLD = 8      # píxeles por carácter al arrastrar
    PREFETCH_MARGIN = 15    # solicitar más precisión antes del final
    SCI_FRACTION_WINDOW = 30

    _SCI_RE = re.compile(
        r"^(?P<sign>[+-]?)(?P<int>\d)(?:\.(?P<frac>\d+))?[eE](?P<exp>[+-]?\d+)$"
    )

    def __init__(self, parent, **kw):
        self._request_more_callback = kw.pop("request_more_callback", None)
        self._var = tk.StringVar(value="0")
        self._entry = tk.Entry(parent, textvariable=self._var,
                               state="readonly", **kw)
        self._anim_id = None
        self._last_drag_x = None
        self._loading_more = False
        self._sci_mode = False
        self._sci_sign = ""
        self._sci_digits = ""
        self._sci_exponent = 0
        self._sci_shift = 0
        self._setup_bindings()

    @property
    def widget(self):
        return self._entry

    # ── Texto ────────────────────────────────────────────────────

    def set_text(self, text: str, preserve_view: bool = False):
        scientific = self._parse_scientific(text)
        if scientific is not None:
            sign, digits, exponent = scientific
            self._sci_mode = True
            self._sci_sign = sign
            self._sci_digits = digits
            self._sci_exponent = exponent
            if not preserve_view:
                self._sci_shift = self._compute_initial_sci_shift()
            self._render_scientific()
            return

        self._sci_mode = False
        left_index = self._entry.index("@0")
        self._var.set(text)
        if preserve_view:
            self._entry.after(10, lambda: self._restore_view(left_index))
        else:
            self._entry.after(10, self._scroll_to_start)

    def get_text(self) -> str:
        return self._var.get()

    def _scroll_to_start(self):
        self._entry.icursor(0)
        self._entry.xview_moveto(0.0)

    def _scroll_to_end(self):
        self._entry.icursor(len(self._var.get()))
        self._entry.xview_moveto(1.0)

    def _restore_view(self, left_index: int):
        length = len(self._var.get())
        safe_index = min(max(0, left_index), max(0, length - 1))
        self._entry.icursor(safe_index)
        self._entry.xview(safe_index)

    # ── Bindings ─────────────────────────────────────────────────

    def _setup_bindings(self):
        e = self._entry

        # Bloquear saltos instantáneos
        for key in ("<Home>", "<End>", "<Control-Home>", "<Control-End>",
                     "<Prior>", "<Next>", "<Control-Left>", "<Control-Right>",
                     "<Control-a>"):
            e.bind(key, lambda _ev: "break")

        # Rueda del ratón → scroll gradual
        e.bind("<MouseWheel>", self._on_mousewheel)
        e.bind("<Shift-MouseWheel>", self._on_mousewheel)

        # Arrastre con el ratón → scroll limitado en velocidad
        e.bind("<Button-1>", self._on_press)
        e.bind("<B1-Motion>", self._on_drag)
        e.bind("<ButtonRelease-1>", self._on_release)

    # ── Rueda del ratón ──────────────────────────────────────────

    def _on_mousewheel(self, event):
        direction = -1 if event.delta > 0 else 1
        self._animate_scroll(direction, self.SCROLL_STEPS)
        return "break"

    def _animate_scroll(self, direction, steps):
        if self._anim_id:
            self._entry.after_cancel(self._anim_id)
            self._anim_id = None
        self._scroll_step(direction, steps)

    def _scroll_step(self, direction, remaining):
        if remaining <= 0:
            self._anim_id = None
            return
        if self._sci_mode:
            self._advance_scientific(direction)
            self._anim_id = self._entry.after(
                self.SCROLL_INTERVAL,
                lambda: self._scroll_step(direction, remaining - 1),
            )
            return

        before = self._entry.xview()
        self._entry.xview_scroll(direction, "units")
        after = self._entry.xview()
        self._maybe_request_more(direction, before, after)
        self._anim_id = self._entry.after(
            self.SCROLL_INTERVAL,
            lambda: self._scroll_step(direction, remaining - 1),
        )

    # ── Arrastre ─────────────────────────────────────────────────

    def _on_press(self, event):
        self._last_drag_x = event.x
        self._drag_accum = 0
        return "break"

    def _on_drag(self, event):
        if self._last_drag_x is None:
            return "break"
        dx = event.x - self._last_drag_x
        self._drag_accum += dx
        self._last_drag_x = event.x

        while abs(self._drag_accum) >= self.DRAG_THRESHOLD:
            if self._drag_accum > 0:
                self._scroll_unit(1)
                self._drag_accum -= self.DRAG_THRESHOLD
            else:
                self._scroll_unit(-1)
                self._drag_accum += self.DRAG_THRESHOLD
        return "break"

    def _on_release(self, _event):
        self._last_drag_x = None

    def _maybe_request_more(self, direction: int, before: tuple, after: tuple):
        if direction <= 0:
            return
        if self._request_more_callback is None:
            return
        if self._loading_more:
            return

        right_visible = self._entry.index(f"@{self._entry.winfo_width()}")
        text_length = len(self._var.get())
        remaining = max(0, text_length - right_visible)
        if remaining > self.PREFETCH_MARGIN:
            return

        self._loading_more = True
        self._entry.after(0, self._request_more_callback)

    def finish_loading_more(self):
        self._loading_more = False

    def _scroll_unit(self, direction: int):
        if self._sci_mode:
            self._advance_scientific(direction)
            return

        before = self._entry.xview()
        self._entry.xview_scroll(direction, "units")
        after = self._entry.xview()
        self._maybe_request_more(direction, before, after)

    def _advance_scientific(self, direction: int):
        if direction > 0:
            self._sci_shift += 1
        elif direction < 0:
            self._sci_shift = max(0, self._sci_shift - 1)

        self._render_scientific()
        self._maybe_request_more_scientific(direction)

    def _maybe_request_more_scientific(self, direction: int):
        if direction <= 0:
            return
        if self._request_more_callback is None:
            return
        if self._loading_more:
            return

        needed_index = self._sci_shift + self.SCI_FRACTION_WINDOW
        remaining = len(self._sci_digits) - 1 - needed_index
        if remaining > self.PREFETCH_MARGIN:
            return

        self._loading_more = True
        self._entry.after(0, self._request_more_callback)

    def _render_scientific(self):
        digits = self._sci_digits
        if not digits:
            self._var.set("0")
            return

        shift = max(0, self._sci_shift)
        if shift < len(digits):
            int_part = digits[: shift + 1]
            frac_part = digits[shift + 1 : shift + 1 + self.SCI_FRACTION_WINDOW]
        else:
            int_part = digits + ("0" * (shift - len(digits) + 1))
            frac_part = "0" * self.SCI_FRACTION_WINDOW

        exponent = self._sci_exponent - shift
        text = f"{self._sci_sign}{int_part}"
        if exponent < 0:
            visible_fraction = min(self.SCI_FRACTION_WINDOW, max(1, -exponent))
            frac_part = frac_part[:visible_fraction]
            if len(frac_part) < visible_fraction:
                frac_part += "0" * (visible_fraction - len(frac_part))
            text += f".{frac_part}"
        text += f"e{exponent:+d}"
        self._var.set(text)
        self._entry.after(0, self._scroll_to_end)

    def _compute_initial_sci_shift(self) -> int:
        max_shift = max(0, len(self._sci_digits) - 1)
        target_chars = self._visible_capacity_chars()

        best_shift = 0
        for shift in range(max_shift + 1):
            if self._rendered_sci_length_for_shift(shift) <= target_chars:
                best_shift = shift
            else:
                break

        return best_shift

    def _visible_capacity_chars(self) -> int:
        self._entry.update_idletasks()
        width_px = max(1, self._entry.winfo_width() - 8)
        font_value = self._entry.cget("font")
        font_obj = tkfont.nametofont(font_value)
        char_px = max(1, font_obj.measure("0"))
        return max(8, width_px // char_px)

    def _rendered_sci_length_for_shift(self, shift: int) -> int:
        exponent = self._sci_exponent - shift
        int_len = shift + 1
        base_len = len(self._sci_sign) + int_len + len(f"e{exponent:+d}")
        if exponent < 0:
            visible_fraction = min(self.SCI_FRACTION_WINDOW, max(1, -exponent))
            return base_len + 1 + visible_fraction
        return base_len

    def _parse_scientific(self, text: str):
        match = self._SCI_RE.fullmatch(text.strip())
        if not match:
            return None

        sign = match.group("sign")
        digits = match.group("int") + (match.group("frac") or "")
        exponent = int(match.group("exp"))
        return sign, digits, exponent


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
        self.root.resizable(False, False)

        self.engine = engine if engine is not None else CalculatorEngine()
        self._inv_mode = False

        self._init_fonts()
        self._create_display()
        self._create_toggle_bar()
        self._create_science_panel()
        self._create_keypad()
        self._bind_keyboard()

        # Foco inicial en el campo de expresión
        self.expr_entry.focus_set()

    # ── Fuentes ──────────────────────────────────────────────────

    def _init_fonts(self):
        self._f_expr   = tkfont.Font(family="Consolas", size=16)
        self._f_result = tkfont.Font(family="Consolas", size=22, weight="bold")
        self._f_btn    = tkfont.Font(family="Segoe UI", size=15)
        self._f_func   = tkfont.Font(family="Segoe UI", size=12)
        self._f_small  = tkfont.Font(family="Segoe UI", size=11)

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
        self.result_display.widget.pack(side="left", fill="x", expand=True)

        tk.Button(
            row, text="Copiar", font=self._f_small,
            bg=self.C["func"], fg=self.C["func_fg"],
            activebackground=self.C["special"], relief="flat",
            cursor="hand2", command=self._copy_result, padx=8,
        ).pack(side="right", padx=(6, 0))

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

        # Determinar el ancho máximo de las filas
        max_cols = max(len(row) for row in self.KEYPAD)
        for c in range(max_cols):
            frame.columnconfigure(c, weight=1, uniform="key")

        for r, row_def in enumerate(self.KEYPAD):
            cols_in_row = len(row_def)
            # Repartir columnas con colspan para filas cortas
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
        # Permitir escritura libre en el campo de expresión

    # ── Acciones ─────────────────────────────────────────────────

    def _on_key(self, action: str):
        if action == "clear":
            self.expr_var.set("")
            self.result_display.set_text("0")
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

        def _run():
            try:
                result = self.engine.evaluate(expr)
                self.root.after(0, lambda: self.result_display.set_text(result))
            except (ValueError, ZeroDivisionError, OverflowError,
                    ArithmeticError, TypeError) as exc:
                error_name = type(exc).__name__
                msg = str(exc) if str(exc) else error_name
                self.root.after(0, lambda: self.result_display.set_text(
                    f"Error: {msg}"))

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    # ── Copiar resultado ─────────────────────────────────────────

    def _copy_result(self):
        text = self.result_display.get_text()
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.expr_entry.focus_set()

    def _request_more_precision(self):
        if not hasattr(self.engine, "request_more_precision"):
            self.result_display.finish_loading_more()
            return

        def _run():
            try:
                updated = self.engine.request_more_precision()
                self.root.after(0, lambda: self.result_display.set_text(
                    updated,
                    preserve_view=True,
                ))
            except Exception:
                pass
            finally:
                self.root.after(0, self.result_display.finish_loading_more)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
