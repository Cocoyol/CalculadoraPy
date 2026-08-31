"""
Ventana flotante de historial de cálculos.

Muestra las operaciones realizadas y permite recalcular sus expresiones
con doble clic. Es una ventana Toplevel independiente no modal que no
bloquea el funcionamiento de la calculadora.

Las entradas son tuplas simples (expresión, resultado) que nunca retienen
recetas ni valores ocultos (Fase 6 del plan ANS): al recalcular una
expresión con doble clic se captura la respuesta ANS confirmada en ese
instante —o el cero por defecto si aún no existe—, por lo que el resultado
puede diferir del que aparece en la entrada seleccionada.
"""

import tkinter as tk
from tkinter import font as tkfont

# Texto explicativo del pie de ventana: comunica el carácter contextual
# del historial (sección 3.2, decisión 10 y Fase 6 del plan ANS).
_HINT_TEXT = "Doble clic para recalcular; A usa la respuesta actual (0 si aún no existe)"


class HistoryWindow:
    """Ventana flotante no modal con el historial de cálculos.

    El doble clic coloca la expresión de la entrada y lanza su recálculo:
    `on_reuse` coloca la expresión y `on_calculate` la evalúa con la
    respuesta ANS vigente en ese instante (o `0` si aún no existe), nunca
    con el ANS de la época en que se creó la entrada histórica.
    """

    C = {
        "bg":         "#1E1E2E",
        "list_bg":    "#181825",
        "list_fg":    "#CDD6F4",
        "result_fg":  "#A6ADC8",
        "sel_bg":     "#313244",
        "sel_fg":     "#CDD6F4",
        "btn_bg":     "#45475A",
        "btn_fg":     "#CDD6F4",
        "btn_active": "#585B70",
        "hint_fg":    "#585B70",
        "title_fg":   "#BAC2DE",
    }

    _MAX_RESULT_DISPLAY = 40  # caracteres máximos del resultado en la lista
    _LINES_PER_ENTRY = 3      # línea expresión + línea resultado + línea separadora

    def __init__(
        self,
        parent: tk.Misc,
        history: list,
        on_reuse=None,
        on_calculate=None,
    ):
        """
        parent       : ventana raíz de la calculadora.
        history      : lista mutable de tuplas (expresión, resultado).
        on_reuse     : callback(expr: str) invocado al hacer doble clic;
                       coloca la expresión antes de crear la solicitud.
        on_calculate : callback() invocado tras on_reuse para ejecutar el
                       cálculo, que captura el ANS confirmado en ese instante.
        """
        self._history_ref = history
        self._on_reuse = on_reuse
        self._on_calculate = on_calculate
        self._selected_idx: int | None = None
        self._entries: list = []  # (expr, result) en orden de visualización

        self._win = tk.Toplevel(parent)
        self._win.title("Historial")
        self._win.configure(bg=self.C["bg"])
        self._win.resizable(True, True)
        self._win.minsize(360, 320)

        self._init_fonts()
        self._build_ui()
        self.refresh()

    # ── Fuentes ──────────────────────────────────────────────────

    def _init_fonts(self):
        self._f_expr  = tkfont.Font(family="Consolas", size=11, weight="bold")
        self._f_result = tkfont.Font(family="Consolas", size=11)
        self._f_btn   = tkfont.Font(family="Segoe UI", size=11)
        self._f_hint  = tkfont.Font(family="Segoe UI", size=9)
        self._f_title = tkfont.Font(family="Segoe UI", size=10, weight="bold")

    # ── Construcción de UI ────────────────────────────────────────

    def _build_ui(self):
        # ── Barra superior ──
        top = tk.Frame(self._win, bg=self.C["bg"])
        top.pack(fill="x", padx=10, pady=(10, 4))

        tk.Label(
            top, text="Historial de cálculos",
            font=self._f_title, bg=self.C["bg"], fg=self.C["title_fg"],
        ).pack(side="left")

        self._clear_btn = tk.Button(
            top, text="Limpiar", font=self._f_btn,
            bg=self.C["btn_bg"], fg=self.C["btn_fg"],
            activebackground=self.C["btn_active"],
            relief="flat", cursor="hand2",
            command=self._on_clear, padx=8,
        )
        self._clear_btn.pack(side="right")

        # ── Text widget con scrollbar ──
        list_frame = tk.Frame(self._win, bg=self.C["list_bg"], bd=0)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(4, 4))

        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self._text = tk.Text(
            list_frame,
            font=self._f_result,
            bg=self.C["list_bg"],
            fg=self.C["list_fg"],
            # Deshabilitar selección de texto nativa del widget
            selectbackground=self.C["list_bg"],
            selectforeground=self.C["list_fg"],
            inactiveselectbackground=self.C["list_bg"],
            relief="flat",
            bd=4,
            cursor="arrow",
            state="disabled",
            wrap="none",
            yscrollcommand=scrollbar.set,
            width=50,
            height=18,
        )
        self._text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self._text.yview)

        # Tags de formato y selección
        self._text.tag_configure(
            "expr", font=self._f_expr, foreground=self.C["list_fg"])
        self._text.tag_configure(
            "result", font=self._f_result, foreground=self.C["result_fg"])
        self._text.tag_configure(
            "sel_bg", background=self.C["sel_bg"])

        self._text.bind("<Button-1>",        self._on_click)
        self._text.bind("<Double-Button-1>", self._on_double_click)
        self._text.bind("<Control-c>",       self._on_copy)
        self._text.bind("<Control-C>",       self._on_copy)

        # ── Pie de página ──
        # La ayuda explica el recálculo contextual: una expresión con `A`
        # se recalcula con la respuesta actual (o con 0 si aún no existe).
        self._hint_label = tk.Label(
            self._win,
            text=_HINT_TEXT,
            font=self._f_hint,
            bg=self.C["bg"],
            fg=self.C["hint_fg"],
            wraplength=340,
            justify="center",
        )
        self._hint_label.pack(pady=(0, 8))

    # ── Ayudantes de geometría ────────────────────────────────────

    def _idx_from_event(self, event) -> "int | None":
        """Índice de la entrada correspondiente a la posición del evento."""
        idx_str = self._text.index(f"@{event.x},{event.y}")
        line_no = int(idx_str.split(".")[0])          # 1-based
        idx = (line_no - 1) // self._LINES_PER_ENTRY
        return idx if 0 <= idx < len(self._entries) else None

    def _entry_highlight_range(self, idx: int):
        """Rango (start, end) para resaltar expresión + resultado (sin separador)."""
        first = idx * self._LINES_PER_ENTRY + 1
        return f"{first}.0", f"{first + 2}.0"

    # ── Selección visual ──────────────────────────────────────────

    def _select(self, idx: "int | None"):
        self._text.tag_remove("sel_bg", "1.0", tk.END)
        self._selected_idx = idx
        if idx is not None:
            start, end = self._entry_highlight_range(idx)
            self._text.tag_add("sel_bg", start, end)

    # ── Datos ─────────────────────────────────────────────────────

    def refresh(self):
        """Repopula el widget con las entradas del historial (más recientes primero)."""
        self._entries = list(reversed(self._history_ref))
        self._selected_idx = None

        self._text.config(state="normal")
        self._text.delete("1.0", tk.END)

        for expr, result in self._entries:
            display_result = (
                result
                if len(result) <= self._MAX_RESULT_DISPLAY
                else result[: self._MAX_RESULT_DISPLAY - 1] + "\u2026"
            )
            self._text.insert(tk.END, f"  {expr}\n", "expr")
            self._text.insert(tk.END, f"  {display_result}\n", "result")
            self._text.insert(tk.END, "\n")  # separador entre entradas

        self._text.config(state="disabled")

    # ── Eventos ───────────────────────────────────────────────────

    def _on_click(self, event):
        self._select(self._idx_from_event(event))
        self._text.focus_set()
        return "break"

    def _on_double_click(self, event):
        """Recalcula la entrada seleccionada con el ANS vigente.

        Primero coloca la expresión (`on_reuse`) y después lanza el cálculo
        (`on_calculate`); la solicitud se crea tras colocar la expresión, de
        modo que captura la respuesta confirmada en ese instante. El
        resultado puede diferir del guardado en la entrada.
        """
        idx = self._idx_from_event(event)
        if idx is None:
            return "break"
        self._select(idx)
        expr = self._entries[idx][0]
        if self._on_reuse:
            self._on_reuse(expr)
        if self._on_calculate:
            self._on_calculate()
        return "break"

    def _on_copy(self, _event):
        """Copia al portapapeles solo la expresión literal de la entrada.

        Se copia el texto con `A` tal cual, sin sustituirlo por ningún
        número (Fase 6 del plan ANS).
        """
        if self._selected_idx is None:
            return "break"
        expr = self._entries[self._selected_idx][0]
        self._win.clipboard_clear()
        self._win.clipboard_append(expr)
        return "break"

    def _on_clear(self):
        """Vacía el historial compartido; nunca toca la respuesta ANS.

        Solo se eliminan las tuplas (expresión, resultado): la respuesta
        confirmada del motor y el cálculo activo permanecen intactos.
        """
        self._history_ref.clear()
        self._entries = []
        self._selected_idx = None
        self._text.config(state="normal")
        self._text.delete("1.0", tk.END)
        self._text.config(state="disabled")

    # ── Ciclo de vida ─────────────────────────────────────────────

    def is_open(self) -> bool:
        try:
            return bool(self._win.winfo_exists())
        except tk.TclError:
            return False

    def lift(self):
        """Trae la ventana al frente."""
        try:
            self._win.lift()
        except tk.TclError:
            pass

    def destroy(self):
        """Cierra la ventana si sigue abierta."""
        try:
            self._win.destroy()
        except tk.TclError:
            pass
