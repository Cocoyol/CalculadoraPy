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

    SCROLL_STEPS = 1        # caracteres por evento de rueda
    SCROLL_INTERVAL = 25    # ms entre pasos de animación
    DRAG_THRESHOLD = 8      # píxeles por carácter al arrastrar
    PREFETCH_MARGIN = 15    # solicitar más precisión antes del final
    SCI_FRACTION_WINDOW = 30
    VISIBLE_CHARS = 17       # caracteres visibles en el campo de resultado. +1 auxiliar para el scroll
    SHOW_SHIFTED_SEPARATOR = False  # muestra separador visual en modo desplazado
    PLAIN_TAIL_LAST_EXPONENT = 4

    _SCI_RE = re.compile(
        r"^(?P<sign>[+-]?)(?P<int>\d)(?:\.(?P<frac>\d+))?[eE](?P<exp>[+-]?\d+)$"
    )
    _DEC_RE = re.compile(
        r"^(?P<sign>[+-]?)(?:(?P<int>\d+)(?:\.(?P<frac>\d*))?|\.(?P<only_frac>\d+))$"
    )

    def __init__(self, parent, **kw):
        self._request_more_callback = kw.pop("request_more_callback", None)
        self._var = tk.StringVar(value="0")
        kw.setdefault("width", self.VISIBLE_CHARS + 1)
        self._entry = tk.Entry(parent, textvariable=self._var,
                               state="readonly", **kw)
        self._anim_id = None
        self._last_drag_x = None
        self._loading_more = False
        self._precision_exhausted = False
        self._force_scientific_current_shift = False
        self._sci_mode = False
        self._sci_sign = ""
        self._sci_digits = ""
        self._sci_exponent = 0
        self._sci_shift = 0
        self._sci_initial_text = "0"
        self._sci_source_kind = None
        self._setup_bindings()

    @property
    def widget(self):
        return self._entry

    # ── Texto ────────────────────────────────────────────────────

    def set_text(self, text: str, preserve_view: bool = False):
        if not preserve_view:
            self._precision_exhausted = False
            self._force_scientific_current_shift = False

        scientific = self._parse_scientific(text)
        if scientific is not None:
            sign, digits, exponent = scientific
            self._sci_mode = True
            self._sci_sign = sign
            self._sci_digits = digits
            self._sci_exponent = exponent
            self._sci_source_kind = "scientific"
            if not preserve_view:
                self._sci_shift = 0
            self._sci_initial_text = self._format_initial_scientific()
            self._render_scientific()
            return

        decimal = self._parse_decimal_as_scientific(text)
        if decimal is not None:
            sign, digits, exponent = decimal
            self._sci_mode = True
            self._sci_sign = sign
            self._sci_digits = digits
            self._sci_exponent = exponent
            self._sci_source_kind = "decimal"
            if not preserve_view:
                self._sci_shift = 0
            self._sci_initial_text = text
            self._render_scientific()
            return

        self._sci_mode = False
        self._sci_source_kind = None
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

        self._entry.xview_scroll(direction, "units")
        self._maybe_request_more(direction)
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

    def _maybe_request_more(self, direction: int):
        if direction <= 0:
            return
        if self._precision_exhausted:
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

    def mark_precision_exhausted(self):
        self._precision_exhausted = True

    def reset_precision_exhausted(self):
        self._precision_exhausted = False

    def _scroll_unit(self, direction: int):
        if self._sci_mode:
            self._advance_scientific(direction)
            return

        self._entry.xview_scroll(direction, "units")
        self._maybe_request_more(direction)

    def _advance_scientific(self, direction: int):
        if (
            direction > 0
            and self._sci_shift == 0
            and self._initial_text_fits_visible_window()
        ):
            self._render_scientific()
            return

        if direction > 0:
            if self._is_plain_decimal_dot_start_state():
                scientific_current, _ = self._build_shifted_scientific_text(
                    self._sci_shift,
                    prefer_plain_tail=False,
                )
                if scientific_current != self._var.get():
                    self._force_scientific_current_shift = True
                    self._render_scientific()
                    self._maybe_request_more_scientific(direction)
                    return

            virtual_digits = self._virtual_digits_for_shifting()
            max_shift = max(0, len(virtual_digits) - 1)
            candidate = min(self._sci_shift + 1, max_shift)
            current_text = self._var.get()
            current_plain_right_edge = self._plain_decimal_right_edge(self._sci_shift)
            current_plain_dot_pos = self._plain_decimal_dot_position(self._sci_shift)
            while candidate > 0 and candidate <= max_shift:
                _, is_full_width = self._build_shifted_scientific_text(candidate)
                plain_decimal = self._should_render_plain_decimal_window(candidate)
                allow_underfull = self._allow_underfull_progress(candidate)
                if (
                    is_full_width
                    or plain_decimal
                    or self._should_render_plain_tail(candidate)
                    or allow_underfull
                ):
                    if plain_decimal:
                        candidate_plain_right_edge = self._plain_decimal_right_edge(candidate)
                        candidate_plain_dot_pos = self._plain_decimal_dot_position(candidate)
                        body_width = max(1, self._visible_capacity_chars() - len(self._sci_sign))
                        if (
                            current_plain_right_edge is not None
                            and candidate_plain_right_edge is not None
                            and current_plain_dot_pos is not None
                            and candidate_plain_dot_pos is not None
                            and current_plain_dot_pos < body_width
                            and candidate_plain_dot_pos < body_width
                            and candidate_plain_right_edge <= current_plain_right_edge
                        ):
                            break

                    candidate_text = self._preview_scientific_text(candidate)
                    if candidate_text != current_text:
                        self._sci_shift = candidate
                        self._force_scientific_current_shift = False
                        break
                candidate += 1
        elif direction < 0:
            self._sci_shift = max(0, self._sci_shift - 1)
            self._force_scientific_current_shift = False

        self._render_scientific()
        self._maybe_request_more_scientific(direction)

    def _maybe_request_more_scientific(self, direction: int):
        if direction <= 0:
            return
        if self._precision_exhausted:
            return
        if self._sci_shift == 0 and self._initial_text_fits_visible_window():
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

    def _preview_scientific_text(self, shift: int) -> str:
        if shift <= 0:
            return self._sci_initial_text

        plain_decimal = self._build_plain_decimal_window_text(shift)
        if plain_decimal is not None:
            return plain_decimal[0]

        if self._can_render_plain_tail():
            at_terminal_shift = self._should_render_plain_tail(shift)
        else:
            _, next_is_full_width = self._build_shifted_scientific_text(shift + 1)
            at_terminal_shift = not next_is_full_width

        text, _ = self._build_shifted_scientific_text(
            shift,
            prefer_plain_tail=at_terminal_shift,
        )
        return text

    def _render_scientific(self):
        digits = self._sci_digits
        if not digits:
            self._var.set("0")
            return

        shift = max(0, self._sci_shift)
        if not (
            self._allow_underfull_progress(shift)
            or self._should_render_plain_decimal_window(shift)
        ):
            while shift > 0:
                _, is_full_width = self._build_shifted_scientific_text(shift)
                if is_full_width:
                    break
                shift -= 1

        self._sci_shift = shift
        if shift == 0:
            text = self._initial_visible_text()
        else:
            plain_decimal = self._build_plain_decimal_window_text(shift)
            if plain_decimal is not None and not self._force_scientific_current_shift:
                text = plain_decimal[0]
                self._var.set(text)
                self._entry.after(0, self._scroll_to_start)
                return

            if self._can_render_plain_tail():
                at_terminal_shift = self._should_render_plain_tail(shift)
            else:
                _, next_is_full_width = self._build_shifted_scientific_text(shift + 1)
                at_terminal_shift = not next_is_full_width
            text, _ = self._build_shifted_scientific_text(
                shift,
                prefer_plain_tail=at_terminal_shift,
            )
            self._force_scientific_current_shift = False

        self._var.set(text)
        if shift == 0:
            self._entry.after(0, self._scroll_to_start)
        else:
            self._entry.after(0, self._scroll_to_start)

    def _initial_visible_text(self) -> str:
        text = self._sci_initial_text
        if self._sci_source_kind != "decimal":
            return text

        capacity = self._visible_capacity_chars()
        if len(text) <= capacity:
            return text

        return text[:capacity]

    def _is_plain_decimal_dot_start_state(self) -> bool:
        if not self._should_render_plain_decimal_window(self._sci_shift):
            return False

        dot_pos = self._plain_decimal_dot_position(self._sci_shift)
        return dot_pos == 0

    def _format_initial_scientific(self) -> str:
        exponent = self._sci_exponent
        exp_text = f"e{exponent:+d}"
        budget = max(1, self._visible_capacity_chars() - len(self._sci_sign) - len(exp_text))

        if budget == 1:
            mantissa = self._sci_digits[0]
        elif budget == 2:
            second = self._sci_digits[1:2]
            mantissa = f"{self._sci_digits[0]}{second}" if second else self._sci_digits[0]
        else:
            frac_len = budget - 2
            frac = self._sci_digits[1 : 1 + frac_len]
            mantissa = f"{self._sci_digits[0]}.{frac}" if frac else self._sci_digits[0]

        return f"{self._sci_sign}{mantissa}{exp_text}"

    def _visible_capacity_chars(self) -> int:
        return self.VISIBLE_CHARS

    def _effective_shift(self, shift: int) -> int:
        if self._sci_source_kind == "decimal" and self._sci_exponent < 0:
            return max(0, shift - 1)
        return shift

    def _virtual_digits_for_shifting(self) -> str:
        digits = self._sci_digits
        if not digits:
            return ""

        scale = max(0, self._sci_exponent - (len(digits) - 1))
        if scale <= 0:
            return digits

        if not self._can_render_plain_tail():
            return digits

        return digits + ("0" * scale)

    def _initial_text_fits_visible_window(self) -> bool:
        if self._sci_source_kind != "decimal":
            return False

        text = self._sci_initial_text.strip()
        if not text:
            return True

        return len(text) <= self._visible_capacity_chars()

    @staticmethod
    def _count_trailing_zeros(text: str) -> int:
        count = 0
        for ch in reversed(text):
            if ch != "0":
                break
            count += 1
        return count

    def _integer_trailing_zeros(self) -> int | None:
        digits = self._sci_digits
        if not digits:
            return 0

        trailing_in_digits = self._count_trailing_zeros(digits)
        scale = self._sci_exponent - (len(digits) - 1)

        if scale < 0 and trailing_in_digits < -scale:
            return None

        return max(0, trailing_in_digits + scale)

    def _can_render_plain_tail(self) -> bool:
        trailing_zeros = self._integer_trailing_zeros()
        if trailing_zeros is None:
            return False

        zero_threshold = self._visible_capacity_chars() // 2
        return trailing_zeros <= zero_threshold

    def _minimum_shifted_exponent(self) -> int | None:
        trailing_zeros = self._integer_trailing_zeros()
        if trailing_zeros is None:
            return None
        if self._can_render_plain_tail():
            return None
        return trailing_zeros

    def _has_full_plain_tail_at_shift(self, shift: int) -> bool:
        if shift <= 0:
            return False

        virtual_digits = self._virtual_digits_for_shifting()
        if not virtual_digits:
            return False

        effective_shift = self._effective_shift(shift)
        effective_shift = min(max(0, effective_shift), max(0, len(virtual_digits) - 1))

        sign = self._sci_sign
        core_budget = max(1, self._visible_capacity_chars() - len(sign))
        core_full = virtual_digits[effective_shift:]
        return len(core_full) >= core_budget

    def _shifted_exponent(self, shift: int) -> int | None:
        text, _ = self._build_shifted_scientific_text(shift, prefer_plain_tail=False)
        marker = text.rfind("e")
        if marker < 0:
            return None
        try:
            return int(text[marker + 1 :])
        except ValueError:
            return None

    def _should_render_plain_tail(self, shift: int) -> bool:
        if shift <= 0:
            return False
        if not self._can_render_plain_tail():
            return False

        exponent = self._shifted_exponent(shift)
        if exponent is None:
            return True

        return exponent <= (self.PLAIN_TAIL_LAST_EXPONENT - 1)

    def _should_render_plain_decimal_window(self, shift: int) -> bool:
        if shift <= 0:
            return False

        if self._is_exact_integer_scientific_value():
            return False

        exponent = self._shifted_exponent(shift)
        if exponent is None:
            return False

        if exponent > (self.PLAIN_TAIL_LAST_EXPONENT - 1):
            return False

        effective_shift = self._effective_shift(shift)
        decimal_index = self._sci_exponent + 1
        dot_pos = decimal_index - effective_shift
        return dot_pos >= 0

    def _is_exact_integer_scientific_value(self) -> bool:
        digits = self._sci_digits
        if not digits:
            return False

        return self._sci_exponent >= (len(digits) - 1)

    def _build_plain_decimal_window_text(self, shift: int) -> tuple[str, bool] | None:
        if not self._should_render_plain_decimal_window(shift):
            return None

        digits = self._virtual_digits_for_shifting()
        if not digits:
            return None

        effective_shift = self._effective_shift(shift)
        effective_shift = min(max(0, effective_shift), max(0, len(digits) - 1))

        sign = self._sci_sign
        body_width = max(1, self._visible_capacity_chars() - len(sign))
        decimal_index = self._sci_exponent + 1
        dot_pos = decimal_index - effective_shift

        if dot_pos >= body_width:
            digits_needed = body_width
            chunk = digits[effective_shift : effective_shift + digits_needed]
            if not chunk:
                return None
            core = chunk
        else:
            digits_needed = max(1, body_width - 1)
            chunk = digits[effective_shift : effective_shift + digits_needed]
            if not chunk:
                return None
            insert_at = min(max(0, dot_pos), len(chunk))
            core = f"{chunk[:insert_at]}.{chunk[insert_at:]}"

        text = f"{sign}…{core}"
        return text, len(core) >= body_width

    def _plain_decimal_right_edge(self, shift: int) -> int | None:
        if not self._should_render_plain_decimal_window(shift):
            return None

        digits = self._virtual_digits_for_shifting()
        if not digits:
            return None

        effective_shift = self._effective_shift(shift)
        effective_shift = min(max(0, effective_shift), max(0, len(digits) - 1))

        body_width = max(1, self._visible_capacity_chars() - len(self._sci_sign))
        decimal_index = self._sci_exponent + 1
        dot_pos = decimal_index - effective_shift

        if dot_pos >= body_width:
            digits_needed = body_width
        else:
            digits_needed = max(1, body_width - 1)

        return min(len(digits), effective_shift + digits_needed)

    def _plain_decimal_dot_position(self, shift: int) -> int | None:
        if not self._should_render_plain_decimal_window(shift):
            return None

        effective_shift = self._effective_shift(shift)
        decimal_index = self._sci_exponent + 1
        return decimal_index - effective_shift

    def _allow_underfull_progress(self, shift: int) -> bool:
        return shift > 0 and self._can_render_plain_tail()

    def _build_shifted_scientific_text(self, shift: int, prefer_plain_tail: bool = False) -> tuple[str, bool]:
        digits = self._sci_digits
        if not digits:
            return "0", False

        virtual_digits = self._virtual_digits_for_shifting()

        ellipsis = "…"
        effective_shift = self._effective_shift(shift)
        effective_shift = min(max(0, effective_shift), max(0, len(virtual_digits) - 1))

        sign = self._sci_sign
        core_budget = max(1, self._visible_capacity_chars() - len(sign))

        # Mostrar cola fija sin exponente solo en el último estado alcanzable.
        if prefer_plain_tail and self._can_render_plain_tail():
            core_full = virtual_digits[effective_shift:]
            if len(core_full) < core_budget and effective_shift > 0:
                missing = core_budget - len(core_full)
                effective_shift = max(0, effective_shift - missing)
                core_full = virtual_digits[effective_shift:]
            if len(core_full) >= core_budget:
                core = core_full[-core_budget:]
                is_full_width = True
            else:
                core = core_full
                is_full_width = False
            return f"{sign}{ellipsis}{core}", is_full_width

        use_separator = (
            self.SHOW_SHIFTED_SEPARATOR
            and self._sci_source_kind == "decimal"
        )

        mantissa_budget = core_budget
        if use_separator:
            mantissa_budget = max(1, mantissa_budget - 1)

        mantissa_digits = max(1, mantissa_budget)
        for _ in range(4):
            exponent = self._sci_exponent - (effective_shift + mantissa_digits - 1)
            exp_text = f"e{exponent:+d}"
            new_budget = max(1, core_budget - len(exp_text))
            if use_separator:
                new_budget = max(1, new_budget - 1)
            if new_budget == mantissa_digits:
                break
            mantissa_digits = new_budget

        available_digits = max(1, len(virtual_digits) - effective_shift)
        shown_digits = min(available_digits, mantissa_digits)
        exponent = self._sci_exponent - (effective_shift + shown_digits - 1)
        exp_text = f"e{exponent:+d}"

        max_shown = max(1, core_budget - len(exp_text) - (1 if use_separator else 0))
        shown_digits = min(shown_digits, max_shown)
        exponent = self._sci_exponent - (effective_shift + shown_digits - 1)
        exp_text = f"e{exponent:+d}"

        mantissa = virtual_digits[effective_shift : effective_shift + shown_digits]
        if use_separator and len(mantissa) > 1:
            frac = mantissa[1:].rstrip("0")
            mantissa = f"{mantissa[0]}.{frac}" if frac else mantissa[0]

        core = f"{mantissa}{exp_text}"
        is_full_width = len(core) >= core_budget
        return f"{sign}{ellipsis}{core}", is_full_width

    def _parse_scientific(self, text: str):
        match = self._SCI_RE.fullmatch(text.strip())
        if not match:
            return None

        sign = match.group("sign")
        digits = match.group("int") + (match.group("frac") or "")
        exponent = int(match.group("exp"))
        return sign, digits, exponent

    def _parse_decimal_as_scientific(self, text: str):
        match = self._DEC_RE.fullmatch(text.strip())
        if not match:
            return None

        sign = match.group("sign")
        int_part = match.group("int") if match.group("int") is not None else "0"
        frac_part = match.group("frac")
        if frac_part is None:
            frac_part = match.group("only_frac") or ""

        if set(int_part) == {"0"} and (not frac_part or set(frac_part) == {"0"}):
            return sign, "0", 0

        first_non_zero_int = next((i for i, c in enumerate(int_part) if c != "0"), None)
        if first_non_zero_int is not None:
            exponent = len(int_part) - first_non_zero_int - 1
            digits = int_part[first_non_zero_int:] + frac_part
        else:
            first_non_zero_frac = next((i for i, c in enumerate(frac_part) if c != "0"), None)
            if first_non_zero_frac is None:
                return sign, "0", 0
            exponent = -(first_non_zero_frac + 1)
            digits = frac_part[first_non_zero_frac:]

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
        self._last_engine_result: str | None = None

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

        tk.Button(
            row, text="Copiar", font=self._f_small,
            bg=self.C["func"], fg=self.C["func_fg"],
            activebackground=self.C["special"], relief="flat",
            cursor="hand2", command=self._copy_result, padx=8,
        ).pack(side="right", padx=(6, 0))

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
        self.root.bind("<Escape>", lambda _e: self._on_key("clear"))
        # Permitir escritura libre en el campo de expresión

    # ── Acciones ─────────────────────────────────────────────────

    def _on_key(self, action: str):
        if action == "clear":
            self.expr_var.set("")
            self.result_display.set_text("0")
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

        def _run():
            try:
                result = self.engine.evaluate(expr)
                self._last_engine_result = result
                self.root.after(0, lambda: self.result_display.set_text(result))
            except (ValueError, ZeroDivisionError, OverflowError,
                    ArithmeticError, TypeError) as exc:
                error_name = type(exc).__name__
                msg = str(exc) if str(exc) else error_name
                self._last_engine_result = None
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
                if self._last_engine_result is not None and updated == self._last_engine_result:
                    self.root.after(0, self.result_display.mark_precision_exhausted)
                    return

                self._last_engine_result = updated
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
