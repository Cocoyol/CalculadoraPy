# nuitka-project: --mode=standalone
# nuitka-project: --enable-plugin=tk-inter
# nuitka-project: --python-flag=no_docstrings,isolated
# nuitka-project: --lto=yes
# nuitka-project: --windows-console-mode=disable
# nuitka-project: --include-data-files={MAIN_DIRECTORY}/icon-calculator.ico=icon-calculator.ico
# nuitka-project: --include-data-files={MAIN_DIRECTORY}/icons/*.png=icons/
# nuitka-project: --output-dir={MAIN_DIRECTORY}/dist
# nuitka-project: --output-filename=CalculadoraPy
# nuitka-project: --product-name=CalculadoraPy
# nuitka-project: --file-description=Calculadora cientifica
# nuitka-project: --windows-icon-from-ico={MAIN_DIRECTORY}/icon-calculator.ico
# nuitka-project: --product-version=1.0.0.0
# nuitka-project: --file-version=1.0.0.0
# nuitka-project: --report={MAIN_DIRECTORY}/dist/compilation-report.xml

"""Punto de entrada de la calculadora científica."""

import tkinter as tk

from arbitrary_precision_engine import ArbitraryPrecisionCalculatorEngine
from calculator_config import initialize_config
from calculator_ui import CalculatorApp


AP_INITIAL_DIGITS = 120
AP_PRECISION_STEP = 120


def main():
    initialize_config()
    root = tk.Tk()
    engine = ArbitraryPrecisionCalculatorEngine(
        initial_digits=AP_INITIAL_DIGITS,
        precision_step=AP_PRECISION_STEP,
    )
    CalculatorApp(root, engine=engine)
    root.mainloop()


if __name__ == "__main__":
    main()
