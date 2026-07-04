# nuitka-project: --mode=standalone
# nuitka-project: --follow-imports
# nuitka-project: --enable-plugin=tk-inter
# nuitka-project: --python-flag=no_docstrings,no_asserts,isolated
# nuitka-project: --lto=yes
# nuitka-project: --jobs=4
# nuitka-project: --windows-console-mode=disable
# nuitka-project: --include-data-files=calculator_config.json=calculator_config.json
# nuitka-project: --include-data-files=icon-calculator.ico=icon-calculator.ico
# nuitka-project: --include-data-dir=icons=icons
# nuitka-project: --output-dir=dist
# nuitka-project: --output-filename=CalculadoraPy
# nuitka-project: --product-name=CalculadoraPy
# nuitka-project: --windows-icon-from-ico=icon-calculator.ico
# nuitka-project: --product-version=1.0.0.0
# nuitka-project: --file-version=1.0.0.0
# nuitka-project: --nofollow-import-to=regression_phase1_checks
# nuitka-project: --nofollow-import-to=regression_phase3_checks
# nuitka-project: --nofollow-import-to=regression_scroll_checks
# nuitka-project: --nofollow-import-to=regression_scroll_30_checks
# nuitka-project: --nofollow-import-to=benchmark_scroll_advance
# nuitka-project: --nofollow-import-to=generate_icons
# nuitka-project: --prefer-source-code

"""Punto de entrada de la calculadora científica."""

import tkinter as tk

from arbitrary_precision_engine import ArbitraryPrecisionCalculatorEngine
from calculator_ui import CalculatorApp


AP_INITIAL_DIGITS = 120
AP_PRECISION_STEP = 120


def main():
    root = tk.Tk()
    engine = ArbitraryPrecisionCalculatorEngine(
        initial_digits=AP_INITIAL_DIGITS,
        precision_step=AP_PRECISION_STEP,
    )
    CalculatorApp(root, engine=engine)
    root.mainloop()


if __name__ == "__main__":
    main()
