"""
Diálogo de configuración de la calculadora científica.

Expone open_settings_dialog(app) para ser invocado desde CalculatorApp.
"""

import tkinter as tk

from calculator_config import update_config_value
from calculator_config_normalizations import clamp_int, get_decimal_separator_enabled, get_visible_chars


def open_settings_dialog(app) -> None:
    """Abre el diálogo de configuración centrado sobre la ventana de *app*.

    Si ya existe una instancia visible la trae al frente en lugar de
    crear una segunda ventana.

    Parameters
    ----------
    app:
        Instancia de ``CalculatorApp``.  Se accede a sus atributos
        ``root``, ``result_display``, ``C`` (paleta) y las fuentes
        ``_f_small``, ``_f_func``.
    """
    # Reutilizar ventana existente
    existing = getattr(app, "_settings_win", None)
    if existing is not None and existing.winfo_exists():
        existing.lift()
        return

    root = app.root
    C    = app.C

    win = tk.Toplevel(root)
    win.title("Configuración")
    win.configure(bg=C["bg"])
    win.resizable(False, False)
    win.transient(root)
    win.grab_set()
    app._settings_win = win

    pad = {"padx": 12, "pady": 6}

    # ── Título ────────────────────────────────────────────────────
    tk.Label(
        win, text="Configuración",
        font=app._f_small, bg=C["bg"], fg=C["expr_fg"],
    ).grid(row=0, column=0, columnspan=3, **pad, sticky="w")

    # ── Controles ───────────────────────────────────────
    visible_chars_var = tk.StringVar(value=str(get_visible_chars()))
    decimal_separator_var = tk.IntVar(value=1 if get_decimal_separator_enabled() else 0)

    tk.Label(
        win, text="Caracteres visibles",
        font=app._f_small, bg=C["bg"], fg=C["expr_fg"],
    ).grid(row=1, column=0, **pad, sticky="w")

    tk.Spinbox(
        win, from_=17, to=32, increment=1,
        textvariable=visible_chars_var, width=6,
        font=app._f_small, justify="center",
        bg=C["display_bg"], fg=C["result_fg"],
        buttonbackground=C["func"], relief="flat",
    ).grid(row=1, column=1, columnspan=2, **pad, sticky="e")

    tk.Checkbutton(
        win, text="Separador de miles",
        variable=decimal_separator_var,
        font=app._f_small, bg=C["bg"], fg=C["expr_fg"],
        activebackground=C["bg"], activeforeground=C["expr_fg"],
        selectcolor=C["display_bg"], relief="flat",
    ).grid(row=2, column=0, columnspan=3, **pad, sticky="w")

    legend_font = app._f_small.copy()
    legend_font.configure(slant="italic")
    tk.Label(
        win, text="Al aplicar se reiniciará la calculadora.",
        font=legend_font, bg=C["bg"], fg=C["expr_fg"],
    ).grid(row=3, column=0, columnspan=3, padx=12, pady=(8, 2), sticky="w")

    # ── Botones ───────────────────────────────────────────────────
    n_rows = 4

    def _apply():
        visible_chars = clamp_int(visible_chars_var.get(), 17, 32)
        decimal_separator = 1 if decimal_separator_var.get() else 0
        update_config_value("VISIBLE_CHARS", visible_chars)
        update_config_value("DECIMAL_SEPARATOR", decimal_separator)
        win.destroy()
        root.after(0, app.restart_ui_after_config_change)

    def _cancel():
        win.destroy()

    btn_frame = tk.Frame(win, bg=C["bg"])
    btn_frame.grid(row=n_rows, column=0, columnspan=3,
                   padx=12, pady=(4, 10), sticky="e")

    tk.Button(
        btn_frame, text="Cancelar", font=app._f_small,
        bg=C["func"], fg=C["func_fg"],
        activebackground=C["special"], relief="flat",
        padx=10, command=_cancel,
    ).pack(side="right", padx=(6, 0))

    tk.Button(
        btn_frame, text="Aplicar", font=app._f_small,
        bg=C["equals"], fg=C["equals_fg"],
        activebackground=C["special"], relief="flat",
        padx=10, command=_apply,
    ).pack(side="right")

    win.bind("<Return>", lambda _e: _apply())
    win.bind("<Escape>", lambda _e: _cancel())

    # Centrar sobre la ventana principal
    win.update_idletasks()
    rx = root.winfo_rootx() + (root.winfo_width()  - win.winfo_width())  // 2
    ry = root.winfo_rooty() + (root.winfo_height() - win.winfo_height()) // 2
    win.geometry(f"+{rx}+{ry}")
