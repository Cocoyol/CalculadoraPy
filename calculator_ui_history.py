"""
Ventana flotante de historial de cálculos.

Muestra las operaciones realizadas y permite reutilizar expresiones
con doble clic. Es una ventana Toplevel independiente no modal que no
bloquea el funcionamiento de la calculadora.
"""

import tkinter as tk
from tkinter import font as tkfont


class HistoryWindow:
    """Ventana flotante no modal con el historial de cálculos."""

    C = {
        "bg":         "#1E1E2E",
        "list_bg":    "#181825",
        "list_fg":    "#CDD6F4",
        "sel_bg":     "#313244",
        "sel_fg":     "#CDD6F4",
        "btn_bg":     "#45475A",
        "btn_fg":     "#CDD6F4",
        "btn_active": "#585B70",
        "hint_fg":    "#585B70",
        "title_fg":   "#BAC2DE",
    }

    _MAX_RESULT_DISPLAY = 40  # caracteres máximos del resultado en la lista

    def __init__(
        self,
        parent: tk.Misc,
        history: list,
        on_reuse=None,
    ):
        """
        parent   : ventana raíz de la calculadora.
        history  : lista mutable de tuplas (expresión, resultado).
        on_reuse : callback(expr: str) invocado al hacer doble clic.
        """
        self._history_ref = history
        self._on_reuse = on_reuse

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
        self._f_item  = tkfont.Font(family="Consolas", size=11)
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

        # ── Listbox con scrollbar ──
        list_frame = tk.Frame(self._win, bg=self.C["list_bg"], bd=0)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(4, 4))

        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self._listbox = tk.Listbox(
            list_frame,
            font=self._f_item,
            bg=self.C["list_bg"],
            fg=self.C["list_fg"],
            selectbackground=self.C["sel_bg"],
            selectforeground=self.C["sel_fg"],
            activestyle="none",
            relief="flat",
            bd=4,
            yscrollcommand=scrollbar.set,
        )
        self._listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self._listbox.yview)

        self._listbox.bind("<Double-Button-1>", self._on_double_click)

        # ── Pie de página ──
        tk.Label(
            self._win,
            text="Doble clic para reutilizar la expresión",
            font=self._f_hint,
            bg=self.C["bg"],
            fg=self.C["hint_fg"],
        ).pack(pady=(0, 8))

    # ── Datos ─────────────────────────────────────────────────────

    def refresh(self):
        """Repopula el listbox con las entradas del historial (más recientes primero)."""
        self._listbox.delete(0, tk.END)
        for expr, result in reversed(self._history_ref):
            display_result = (
                result
                if len(result) <= self._MAX_RESULT_DISPLAY
                else result[: self._MAX_RESULT_DISPLAY - 1] + "\u2026"
            )
            self._listbox.insert(tk.END, f"  {expr}  =  {display_result}")

    # ── Eventos ───────────────────────────────────────────────────

    def _on_double_click(self, _event):
        if self._on_reuse is None:
            return
        sel = self._listbox.curselection()
        if not sel:
            return
        text = self._listbox.get(sel[0]).strip()
        # Extraer expresión: todo lo anterior a "  =  "
        parts = text.split("  =  ", maxsplit=1)
        if parts:
            self._on_reuse(parts[0].strip())

    def _on_clear(self):
        self._history_ref.clear()
        self._listbox.delete(0, tk.END)

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
