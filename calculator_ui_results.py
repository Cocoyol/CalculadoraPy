"""
Widget de presentación de resultados de la calculadora científica.

Contiene ResultDisplay: campo de solo lectura con scroll horizontal
gradual y lógica de representación científica desplazable.
"""

import tkinter as tk
import re


_CACHE_UNSET = object()


# ═════════════════════════════════════════════════════════════════
#  Widget: campo de resultado con scroll lateral gradual
# ═════════════════════════════════════════════════════════════════

class ResultDisplay:
    """Entry de solo lectura con scroll horizontal gradual."""

    SCROLL_STEPS = 1        # caracteres por evento de rueda
    SCROLL_INTERVAL = 25    # ms entre pasos de animación
    DRAG_PIXELS_PER_STEP = 36  # píxeles horizontales necesarios por dígito al arrastrar
    DRAG_SCROLL_STEPS = 2   # caracteres máximos por tick de arrastre
    DRAG_SCROLL_INTERVAL = 20   # ms entre ticks de arrastre
    DRAG_MAX_PENDING_STEPS = 8  # pasos acumulados máximos para evitar saltos bruscos
    PREFETCH_MARGIN = 30    # solicitar más precisión antes del final
    SCI_FRACTION_WINDOW = 30    # dígitos de precisión que se muestran en modo científico antes de solicitar más
    VISIBLE_CHARS = 17       # caracteres visibles en el campo de resultado. +1 auxiliar para el scroll
    SHOW_SHIFTED_SEPARATOR = False  # muestra separador visual en modo desplazado
    PLAIN_TAIL_LAST_EXPONENT = 4    # último exponente para mostrar cola fija sin exponente en modo desplazado

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
        self._drag_anim_id = None
        self._last_drag_x = None
        self._drag_accum = 0
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
        self._dot_start_transition_active = False
        self._scientific_initial_bridge_active = False
        self._reset_scientific_caches()
        self._setup_bindings()

    @property
    def widget(self):
        return self._entry

    # ── Texto ────────────────────────────────────────────────────

    def _reset_scientific_caches(self):
        self._virtual_digits_cache = None
        self._integer_trailing_zeros_cache = _CACHE_UNSET
        self._can_render_plain_tail_cache = _CACHE_UNSET
        self._shifted_scientific_layout_cache = {}
        self._shifted_scientific_text_cache = {}
        self._should_render_plain_tail_cache = {}
        self._should_render_plain_decimal_window_cache = {}
        self._plain_decimal_window_cache = {}
        self._plain_decimal_right_edge_cache = {}
        self._plain_decimal_dot_position_cache = {}

    def set_text(self, text: str, preserve_view: bool = False):
        self._reset_scientific_caches()
        if not preserve_view:
            self._precision_exhausted = False
            self._force_scientific_current_shift = False
            self._dot_start_transition_active = False
            self._scientific_initial_bridge_active = False

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

    def get_copy_text(
        self,
        plain_decimal: bool = False,
        standard_scientific: bool = False,
    ) -> str:
        """Devuelve el texto a copiar: todos los dígitos desde el primero
        hasta el último visible a la derecha, conservando el exponente.

        Si plain_decimal=True y el número tiene parte fraccionaria, omite
        el exponente e inserta el punto decimal en su posición absoluta.
        Si standard_scientific=True, normaliza el texto copiable actual a
        mantisa estándar x.yyyye±n usando los dígitos visibles.
        Cuando el resultado no está desplazado devuelve el texto visible.
        Cuando está desplazado (hay '…') reconstruye el bloque completo:
        dígitos ocultos a la izquierda + dígitos visibles + exponente.
        """
        if standard_scientific:
            plain_decimal = False

        if not self._sci_mode:
            text = self._var.get()
            return self._to_standard_scientific_copy(text) if standard_scientific else text

        if self._sci_shift == 0:
            visible_copy = self._copy_text_from_unshifted_scientific_view(plain_decimal)
            if visible_copy is not None:
                return self._to_standard_scientific_copy(visible_copy) if standard_scientific else visible_copy
            text = self._var.get()
            return self._to_standard_scientific_copy(text) if standard_scientific else text

        current_text = self._var.get()
        sign = self._sci_sign
        prefix = sign + "\u2026"  # sign + '…'
        if not current_text.startswith(prefix):
            return current_text

        content = current_text[len(prefix):]
        virtual_digits = self._virtual_digits_for_shifting()

        # Caso A: notación científica desplazada con exponente (…XYZe+11)
        m = re.search(r'[eE]([+-]?\d+)$', content)
        if m:
            shown_exponent = int(m.group(1))
            exp_text = m.group(0)          # conserva el formato exacto, ej. "e+11"
            total_digits = self._sci_exponent - shown_exponent + 1
            total_digits = max(1, min(total_digits, len(virtual_digits)))

            if plain_decimal and not self._is_exact_integer_scientific_value():
                # Forma plana decimal: solo si el punto decimal ya apareció a la
                # izquierda, es decir, cae dentro de los dígitos significativos
                # copiados (decimal_pos < total_digits). Si decimal_pos >= total_digits
                # el punto aún no ha aparecido y se conserva el exponente.
                digits = virtual_digits[:total_digits]
                decimal_pos = self._sci_exponent + 1  # cantidad de dígitos enteros
                if decimal_pos < total_digits:
                    if decimal_pos <= 0:
                        text = f"{sign}0.{'0' * abs(decimal_pos)}{digits}"
                        return self._to_standard_scientific_copy(text) if standard_scientific else text
                    text = f"{sign}{digits[:decimal_pos]}.{digits[decimal_pos:]}"
                    return self._to_standard_scientific_copy(text) if standard_scientific else text

            text = f"{sign}{virtual_digits[:total_digits]}{exp_text}"
            return self._to_standard_scientific_copy(text) if standard_scientific else text

        # Caso B: ventana decimal plana (…1234.567, sin exponente)
        if '.' in content:
            right_edge = self._plain_decimal_right_edge(self._sci_shift)
            if right_edge is None:
                # Estado especial de primer desplazamiento: "….xxxxx".
                # En copiado se elimina la elipsis y se conserva el decimal visible.
                if content.startswith('.'):
                    text = f"{sign}0{content}"
                    return self._to_standard_scientific_copy(text) if standard_scientific else text
                return self._to_standard_scientific_copy(current_text) if standard_scientific else current_text
            right_edge = min(right_edge, len(virtual_digits))
            full_digits = virtual_digits[:right_edge]
            decimal_pos = self._sci_exponent + 1  # dígitos antes del punto decimal
            if decimal_pos <= 0:
                text = f"{sign}0.{'0' * abs(decimal_pos)}{full_digits}"
                return self._to_standard_scientific_copy(text) if standard_scientific else text
            if decimal_pos >= len(full_digits):
                text = f"{sign}{full_digits}{'0' * (decimal_pos - len(full_digits))}"
                return self._to_standard_scientific_copy(text) if standard_scientific else text
            text = f"{sign}{full_digits[:decimal_pos]}.{full_digits[decimal_pos:]}"
            return self._to_standard_scientific_copy(text) if standard_scientific else text

        # Caso C: cola fija entera (…12338905, sin exponente ni punto)
        # content son los dígitos visibles; localizar su extremo derecho en
        # virtual_digits para no copiar más allá del último dígito visible.
        visible = content  # dígitos mostrados (sin '…' ni signo)
        right_edge = len(virtual_digits)
        if visible:
            # Buscar la posición más a la derecha donde visible aparece como sufijo
            idx = virtual_digits.rfind(visible)
            if idx >= 0:
                right_edge = idx + len(visible)
        text = f"{sign}{virtual_digits[:right_edge]}"
        return self._to_standard_scientific_copy(text) if standard_scientific else text

    def _copy_text_from_unshifted_scientific_view(self, plain_decimal: bool) -> str | None:
        bridge_copy = self._copy_text_from_initial_scientific_bridge(plain_decimal)
        if bridge_copy is not None:
            return bridge_copy

        parsed = self._parse_visible_scientific_for_copy(self._var.get())
        if parsed is None:
            return None

        sign, digits, exponent = parsed
        if plain_decimal and not self._is_exact_integer_for_digits(digits, exponent):
            return self._to_plain_decimal_text(sign, digits, exponent)

        mantissa = self._format_mantissa_for_copy(digits)
        return f"{sign}{mantissa}e{exponent:+d}"

    def _copy_text_from_initial_scientific_bridge(self, plain_decimal: bool) -> str | None:
        if not self._scientific_initial_bridge_active:
            return None

        text = self._var.get().strip()
        match = re.fullmatch(r"(?P<sign>[+-]?)…\.(?P<frac>\d+)[eE](?P<exp>[+-]?\d+)", text)
        if not match:
            return None

        visible_frac = match.group("frac")
        # En el puente inicial ocultamos solo el primer dígito significativo.
        # Al copiar, conservamos la magnitud real y recortamos a la precisión visible.
        shown_digits = min(len(self._sci_digits), 1 + len(visible_frac))
        digits = (self._sci_digits or "0")[:max(1, shown_digits)]
        exponent = self._sci_exponent
        sign = self._sci_sign

        if plain_decimal and not self._is_exact_integer_for_digits(digits, exponent):
            return self._to_plain_decimal_text(sign, digits, exponent)

        mantissa = self._format_mantissa_for_copy(digits)
        return f"{sign}{mantissa}e{exponent:+d}"

    def _parse_visible_scientific_for_copy(self, text: str):
        stripped = text.strip()
        sci = self._SCI_RE.fullmatch(stripped)
        if sci:
            sign = sci.group("sign")
            digits = sci.group("int") + (sci.group("frac") or "")
            exponent = int(sci.group("exp"))
            return sign, digits, exponent

        # Estado puente inicial: "….<fracción>e±N" (sin dígito entero visible).
        bridge = re.fullmatch(r"(?P<sign>[+-]?)…\.(?P<frac>\d+)[eE](?P<exp>[+-]?\d+)", stripped)
        if not bridge:
            return None

        sign = bridge.group("sign")
        frac = bridge.group("frac")
        exponent = int(bridge.group("exp"))

        non_zero = frac.lstrip("0")
        if not non_zero:
            return sign, "0", 0

        removed_leading = len(frac) - len(non_zero)
        normalized_exponent = exponent - removed_leading - 1
        return sign, non_zero, normalized_exponent

    @staticmethod
    def _is_exact_integer_for_digits(digits: str, exponent: int) -> bool:
        if not digits:
            return False
        return exponent >= (len(digits) - 1)

    @staticmethod
    def _format_mantissa_for_copy(digits: str) -> str:
        if not digits:
            return "0"
        if len(digits) == 1:
            return digits
        return f"{digits[0]}.{digits[1:]}"

    @staticmethod
    def _to_plain_decimal_text(sign: str, digits: str, exponent: int) -> str:
        decimal_pos = exponent + 1
        if decimal_pos <= 0:
            return f"{sign}0.{'0' * abs(decimal_pos)}{digits}"
        if decimal_pos >= len(digits):
            return f"{sign}{digits}{'0' * (decimal_pos - len(digits))}"
        return f"{sign}{digits[:decimal_pos]}.{digits[decimal_pos:]}"

    def _to_standard_scientific_copy(self, text: str) -> str:
        parsed = self._parse_copy_text_as_standard_scientific(text)
        if parsed is None:
            return text

        sign, digits, exponent = parsed
        mantissa = self._format_mantissa_for_copy(digits)
        return f"{sign}{mantissa}e{exponent:+d}"

    def _parse_copy_text_as_standard_scientific(self, text: str):
        stripped = text.strip()
        if not stripped:
            return None

        sci = self._SCI_RE.fullmatch(stripped)
        if sci:
            sign = sci.group("sign")
            digits = sci.group("int") + (sci.group("frac") or "")
            exponent = int(sci.group("exp"))
            return sign, digits, exponent

        compact = re.fullmatch(r"(?P<sign>[+-]?)(?P<digits>\d+)[eE](?P<exp>[+-]?\d+)", stripped)
        if compact:
            sign = compact.group("sign")
            digits = compact.group("digits")
            significant = digits.lstrip("0")
            if not significant:
                return sign, "0", 0
            exponent = int(compact.group("exp")) + len(significant) - 1
            return sign, significant, exponent

        return self._parse_decimal_as_scientific(stripped)

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
        self._cancel_drag_animation()
        return "break"

    def _on_drag(self, event):
        if self._last_drag_x is None:
            return "break"
        dx = event.x - self._last_drag_x
        self._drag_accum += dx
        self._drag_accum = self._clamp_drag_accum(self._drag_accum)
        self._last_drag_x = event.x

        self._schedule_drag_scroll()
        return "break"

    def _on_release(self, _event):
        self._last_drag_x = None
        self._drag_accum = 0
        self._cancel_drag_animation()

    def _clamp_drag_accum(self, value: int) -> int:
        max_accum = self.DRAG_PIXELS_PER_STEP * max(1, self.DRAG_MAX_PENDING_STEPS)
        return max(-max_accum, min(max_accum, value))

    def _schedule_drag_scroll(self):
        if self._drag_anim_id is not None:
            return
        if abs(self._drag_accum) < self.DRAG_PIXELS_PER_STEP:
            return
        self._drag_anim_id = self._entry.after(0, self._drag_scroll_step)

    def _cancel_drag_animation(self):
        if self._drag_anim_id is None:
            return
        self._entry.after_cancel(self._drag_anim_id)
        self._drag_anim_id = None

    def _drag_scroll_step(self):
        self._drag_anim_id = None
        if self._last_drag_x is None:
            self._drag_accum = 0
            return

        steps = 0
        max_steps = max(1, self.DRAG_SCROLL_STEPS)
        while abs(self._drag_accum) >= self.DRAG_PIXELS_PER_STEP and steps < max_steps:
            if self._drag_accum > 0:
                self._scroll_unit(1)
                self._drag_accum -= self.DRAG_PIXELS_PER_STEP
            else:
                self._scroll_unit(-1)
                self._drag_accum += self.DRAG_PIXELS_PER_STEP
            steps += 1

        if abs(self._drag_accum) >= self.DRAG_PIXELS_PER_STEP:
            self._drag_anim_id = self._entry.after(
                self.DRAG_SCROLL_INTERVAL,
                self._drag_scroll_step,
            )

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
        precomputed_shift_text: tuple[int, str] | None = None
        if (
            direction > 0
            and self._sci_shift == 0
            and self._sci_source_kind == "scientific"
            and not self._initial_text_fits_visible_window()
            and len(self._sci_digits) > 1
            and not self._scientific_initial_bridge_active
        ):
            bridge_text = self._build_initial_scientific_bridge_text()
            if bridge_text != self._var.get():
                self._scientific_initial_bridge_active = True
                self._var.set(bridge_text)
                self._entry.after(0, self._scroll_to_start)
                self._maybe_request_more_scientific(direction)
                return

        if (
            direction > 0
            and self._sci_shift == 0
            and self._sci_source_kind == "scientific"
            and self._initial_text_fits_visible_window()
        ):
            self._render_scientific()
            return

        if direction > 0 and self._scientific_initial_bridge_active:
            self._scientific_initial_bridge_active = False

        if direction > 0:
            if self._is_plain_decimal_dot_start_state() and self._sci_exponent < 0:
                transition_text = self._build_dot_start_transition_text()
                if transition_text != self._var.get():
                    self._dot_start_transition_active = True
                    self._var.set(transition_text)
                    self._entry.after(0, self._scroll_to_start)
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

                    candidate_text = self._resolve_shifted_scientific_text(candidate)
                    if candidate_text != current_text:
                        self._sci_shift = candidate
                        self._dot_start_transition_active = False
                        self._force_scientific_current_shift = False
                        precomputed_shift_text = (candidate, candidate_text)
                        break
                candidate += 1
        elif direction < 0:
            if self._dot_start_transition_active:
                # Retroceso desde el puente científico temporal (x.xxxe-y)
                # hacia la vista con punto inicial (….xxxx) sin perder el paso.
                self._dot_start_transition_active = False
                self._force_scientific_current_shift = False
            elif self._scientific_initial_bridge_active:
                self._scientific_initial_bridge_active = False
                self._force_scientific_current_shift = False
            else:
                self._sci_shift = max(0, self._sci_shift - 1)
                self._dot_start_transition_active = False
                self._force_scientific_current_shift = False

        self._render_scientific(precomputed_shift_text=precomputed_shift_text)
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

    def _resolve_shifted_scientific_text(self, shift: int) -> str:
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

    def _render_scientific(self, precomputed_shift_text: tuple[int, str] | None = None):
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
            if self._scientific_initial_bridge_active:
                text = self._build_initial_scientific_bridge_text()
            else:
                text = self._initial_visible_text()
        else:
            if self._dot_start_transition_active:
                text = self._build_dot_start_transition_text()
                self._var.set(text)
                self._entry.after(0, self._scroll_to_start)
                return

            if (
                precomputed_shift_text is not None
                and precomputed_shift_text[0] == shift
                and not self._force_scientific_current_shift
            ):
                text = precomputed_shift_text[1]
            else:
                plain_decimal = self._build_plain_decimal_window_text(shift)
                if plain_decimal is not None and not self._force_scientific_current_shift:
                    text = plain_decimal[0]
                    self._var.set(text)
                    self._entry.after(0, self._scroll_to_start)
                    return

                text = self._resolve_shifted_scientific_text(shift)
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

        capacity = self._initial_visible_capacity_chars()
        if len(text) <= capacity:
            return text

        return text[:capacity]

    def _is_plain_decimal_dot_start_state(self) -> bool:
        if self._sci_shift <= 0:
            return False

        sign = self._sci_sign
        return self._var.get().startswith(f"{sign}….")

    def _build_dot_start_transition_text(self) -> str:
        sign = self._sci_sign
        digits = self._virtual_digits_for_shifting()
        if not digits:
            digits = self._sci_digits or "0"

        effective_shift = self._effective_shift(self._sci_shift)
        effective_shift = min(max(0, effective_shift), max(0, len(digits) - 1))
        mantissa_digits = digits[effective_shift:] or "0"
        exponent = self._sci_exponent - effective_shift
        exp_text = f"e{exponent:+d}"
        budget = max(1, self._initial_visible_capacity_chars() - len(sign) - len(exp_text))

        if budget == 1:
            mantissa = mantissa_digits[0]
        elif budget == 2:
            second = mantissa_digits[1:2]
            mantissa = f"{mantissa_digits[0]}{second}" if second else mantissa_digits[0]
        else:
            frac_len = budget - 2
            frac = mantissa_digits[1 : 1 + frac_len]
            mantissa = f"{mantissa_digits[0]}.{frac}" if frac else mantissa_digits[0]

        return f"{sign}{mantissa}{exp_text}"

    def _build_initial_scientific_bridge_text(self) -> str:
        sign = self._sci_sign
        digits = self._sci_digits or "0"
        exp_text = f"e{self._sci_exponent:+d}"
        budget = max(1, self._visible_capacity_chars() - len(sign) - len(exp_text))
        frac_len = max(1, budget - 1)
        frac = digits[1 : 1 + frac_len]
        if not frac:
            frac = "0"
        return f"{sign}….{frac}{exp_text}"

    def _build_first_shift_dot_start_text(self, shift: int) -> tuple[str, bool] | None:
        if shift != 1:
            return None
        if self._sci_source_kind != "decimal":
            return None
        if self._is_exact_integer_scientific_value():
            return None
        if self._sci_exponent >= 0:
            return None

        digits = self._virtual_digits_for_shifting()
        if not digits:
            return None

        sign = self._sci_sign
        body_width = max(1, self._visible_capacity_chars() - len(sign))
        frac_width = max(1, body_width - 1)
        decimal_index = self._sci_exponent + 1
        leading_zeros = max(0, -decimal_index)
        frac_full = ("0" * leading_zeros) + digits
        chunk = frac_full[:frac_width]
        if not chunk:
            return None

        core = f".{chunk}"
        text = f"{sign}…{core}"
        return text, len(core) >= body_width

    def _format_initial_scientific(self) -> str:
        exponent = self._sci_exponent
        exp_text = f"e{exponent:+d}"
        budget = max(1, self._initial_visible_capacity_chars() - len(self._sci_sign) - len(exp_text))

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

    def _initial_visible_capacity_chars(self) -> int:
        """Capacity for the initial (unshifted) display: +1 for negative sign."""
        if self._sci_sign == "-":
            return self.VISIBLE_CHARS + 1
        return self.VISIBLE_CHARS

    def _initial_scientific_visible_digits(self) -> int:
        exp_text = f"e{self._sci_exponent:+d}"
        budget = max(1, self._initial_visible_capacity_chars() - len(self._sci_sign) - len(exp_text))
        if budget <= 2:
            return budget
        return budget - 1

    def _effective_shift(self, shift: int) -> int:
        if self._sci_source_kind == "decimal" and self._sci_exponent < 0:
            return max(0, shift - 1)
        return shift

    def _virtual_digits_for_shifting(self) -> str:
        if self._virtual_digits_cache is not None:
            return self._virtual_digits_cache

        digits = self._sci_digits
        if not digits:
            self._virtual_digits_cache = ""
            return self._virtual_digits_cache

        scale = max(0, self._sci_exponent - (len(digits) - 1))
        if scale <= 0:
            self._virtual_digits_cache = digits
            return self._virtual_digits_cache

        if not self._can_render_plain_tail():
            self._virtual_digits_cache = digits
            return self._virtual_digits_cache

        self._virtual_digits_cache = digits + ("0" * scale)
        return self._virtual_digits_cache

    def _initial_text_fits_visible_window(self) -> bool:
        text = self._sci_initial_text.strip()
        if not text:
            return True

        capacity = self._initial_visible_capacity_chars()
        if self._sci_source_kind != "scientific":
            return len(text) <= capacity

        if len(text) < capacity:
            return True
        if len(text) > capacity:
            return False

        if len(self._sci_digits) <= self._initial_scientific_visible_digits():
            return True
        return False

    @staticmethod
    def _count_trailing_zeros(text: str) -> int:
        count = 0
        for ch in reversed(text):
            if ch != "0":
                break
            count += 1
        return count

    def _integer_trailing_zeros(self) -> int | None:
        if self._integer_trailing_zeros_cache is not _CACHE_UNSET:
            return self._integer_trailing_zeros_cache

        digits = self._sci_digits
        if not digits:
            self._integer_trailing_zeros_cache = 0
            return self._integer_trailing_zeros_cache

        trailing_in_digits = self._count_trailing_zeros(digits)
        scale = self._sci_exponent - (len(digits) - 1)

        if scale < 0 and trailing_in_digits < -scale:
            self._integer_trailing_zeros_cache = None
            return self._integer_trailing_zeros_cache

        self._integer_trailing_zeros_cache = max(0, trailing_in_digits + scale)
        return self._integer_trailing_zeros_cache

    def _can_render_plain_tail(self) -> bool:
        if self._can_render_plain_tail_cache is not _CACHE_UNSET:
            return self._can_render_plain_tail_cache

        trailing_zeros = self._integer_trailing_zeros()
        if trailing_zeros is None:
            self._can_render_plain_tail_cache = False
            return self._can_render_plain_tail_cache

        zero_threshold = self._visible_capacity_chars() // 2
        self._can_render_plain_tail_cache = trailing_zeros <= zero_threshold
        return self._can_render_plain_tail_cache

    def _shifted_exponent(self, shift: int) -> int | None:
        layout = self._build_shifted_scientific_layout(shift)
        if layout is None:
            return None
        return layout["exponent"]

    def _should_render_plain_tail(self, shift: int) -> bool:
        if shift in self._should_render_plain_tail_cache:
            return self._should_render_plain_tail_cache[shift]

        if shift <= 0:
            self._should_render_plain_tail_cache[shift] = False
            return False
        if not self._can_render_plain_tail():
            self._should_render_plain_tail_cache[shift] = False
            return False

        exponent = self._shifted_exponent(shift)
        if exponent is None:
            self._should_render_plain_tail_cache[shift] = True
            return True

        result = exponent <= (self.PLAIN_TAIL_LAST_EXPONENT - 1)
        self._should_render_plain_tail_cache[shift] = result
        return result

    def _should_render_plain_decimal_window(self, shift: int) -> bool:
        if shift in self._should_render_plain_decimal_window_cache:
            return self._should_render_plain_decimal_window_cache[shift]

        if shift <= 0:
            self._should_render_plain_decimal_window_cache[shift] = False
            return False

        if self._is_exact_integer_scientific_value():
            self._should_render_plain_decimal_window_cache[shift] = False
            return False

        exponent = self._shifted_exponent(shift)
        if exponent is None:
            self._should_render_plain_decimal_window_cache[shift] = False
            return False

        if exponent > (self.PLAIN_TAIL_LAST_EXPONENT - 1):
            self._should_render_plain_decimal_window_cache[shift] = False
            return False

        effective_shift = self._effective_shift(shift)
        decimal_index = self._sci_exponent + 1
        dot_pos = decimal_index - effective_shift
        result = dot_pos >= 0
        self._should_render_plain_decimal_window_cache[shift] = result
        return result

    def _is_exact_integer_scientific_value(self) -> bool:
        digits = self._sci_digits
        if not digits:
            return False

        return self._sci_exponent >= (len(digits) - 1)

    def _build_plain_decimal_window_text(self, shift: int) -> tuple[str, bool] | None:
        if shift in self._plain_decimal_window_cache:
            return self._plain_decimal_window_cache[shift]

        first_shift = self._build_first_shift_dot_start_text(shift)
        if first_shift is not None:
            self._plain_decimal_window_cache[shift] = first_shift
            return first_shift

        if not self._should_render_plain_decimal_window(shift):
            self._plain_decimal_window_cache[shift] = None
            return None

        digits = self._virtual_digits_for_shifting()
        if not digits:
            self._plain_decimal_window_cache[shift] = None
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
                self._plain_decimal_window_cache[shift] = None
                return None
            insert_at = min(max(0, dot_pos), len(chunk))
            core = f"{chunk[:insert_at]}.{chunk[insert_at:]}"

        text = f"{sign}…{core}"
        result = (text, len(core) >= body_width)
        self._plain_decimal_window_cache[shift] = result
        return result

    def _plain_decimal_right_edge(self, shift: int) -> int | None:
        if shift in self._plain_decimal_right_edge_cache:
            return self._plain_decimal_right_edge_cache[shift]

        if not self._should_render_plain_decimal_window(shift):
            self._plain_decimal_right_edge_cache[shift] = None
            return None

        digits = self._virtual_digits_for_shifting()
        if not digits:
            self._plain_decimal_right_edge_cache[shift] = None
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

        result = min(len(digits), effective_shift + digits_needed)
        self._plain_decimal_right_edge_cache[shift] = result
        return result

    def _plain_decimal_dot_position(self, shift: int) -> int | None:
        if shift in self._plain_decimal_dot_position_cache:
            return self._plain_decimal_dot_position_cache[shift]

        if not self._should_render_plain_decimal_window(shift):
            self._plain_decimal_dot_position_cache[shift] = None
            return None

        effective_shift = self._effective_shift(shift)
        decimal_index = self._sci_exponent + 1
        result = decimal_index - effective_shift
        self._plain_decimal_dot_position_cache[shift] = result
        return result

    def _allow_underfull_progress(self, shift: int) -> bool:
        return shift > 0 and self._can_render_plain_tail()

    def _build_shifted_scientific_layout(self, shift: int):
        if shift in self._shifted_scientific_layout_cache:
            return self._shifted_scientific_layout_cache[shift]

        digits = self._sci_digits
        if not digits:
            self._shifted_scientific_layout_cache[shift] = None
            return None

        virtual_digits = self._virtual_digits_for_shifting()
        effective_shift = self._effective_shift(shift)
        effective_shift = min(max(0, effective_shift), max(0, len(virtual_digits) - 1))

        sign = self._sci_sign
        core_budget = max(1, self._visible_capacity_chars() - len(sign))
        use_separator = (
            self.SHOW_SHIFTED_SEPARATOR
            and self._sci_source_kind == "decimal"
        )

        mantissa_digits = max(1, core_budget - (1 if use_separator else 0))
        for _ in range(3):
            exponent = self._sci_exponent - (effective_shift + mantissa_digits - 1)
            exp_text = f"e{exponent:+d}"
            new_budget = max(1, core_budget - len(exp_text) - (1 if use_separator else 0))
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
        result = {
            "sign": sign,
            "core": core,
            "exponent": exponent,
            "is_full_width": len(core) >= core_budget,
        }
        self._shifted_scientific_layout_cache[shift] = result
        return result

    def _build_shifted_scientific_text(self, shift: int, prefer_plain_tail: bool = False) -> tuple[str, bool]:
        cache_key = (shift, prefer_plain_tail)
        if cache_key in self._shifted_scientific_text_cache:
            return self._shifted_scientific_text_cache[cache_key]

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
            result = (f"{sign}{ellipsis}{core}", is_full_width)
            self._shifted_scientific_text_cache[cache_key] = result
            return result

        layout = self._build_shifted_scientific_layout(shift)
        if layout is None:
            return "0", False

        result = (f"{layout['sign']}{ellipsis}{layout['core']}", layout["is_full_width"])
        self._shifted_scientific_text_cache[cache_key] = result
        return result

    def _parse_scientific(self, text: str):
        match = self._SCI_RE.fullmatch(text.strip())
        if not match:
            return None

        sign = match.group("sign")
        digits = match.group("int") + (match.group("frac") or "")
        digits = digits.rstrip("0") or "0"  # los ceros finales no son significativos
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

        digits = digits.rstrip("0") or "0"  # los ceros finales no son significativos
        return sign, digits, exponent
