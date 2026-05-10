"""
Diálogo de configuración de la calculadora científica.

Expone open_settings_dialog(app) para ser invocado desde CalculatorApp.
"""

import tkinter as tk


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
    rd   = app.result_display
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


    # ── Botones ───────────────────────────────────────────────────
    n_rows = 1

    def _apply():
        win.destroy()

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
