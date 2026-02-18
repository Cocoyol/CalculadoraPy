"""Punto de entrada de la calculadora científica."""

import tkinter as tk

from calculator_engine import CalculatorEngine
from calculator_ui import CalculatorApp


USE_ARBITRARY_PRECISION = True
AP_INITIAL_DIGITS = 120
AP_PRECISION_STEP = 120


def main():
    root = tk.Tk()
    root.geometry("420x620")
    root.minsize(380, 580)
    if USE_ARBITRARY_PRECISION:
        from arbitrary_precision_engine import ArbitraryPrecisionCalculatorEngine

        engine = ArbitraryPrecisionCalculatorEngine(
            initial_digits=AP_INITIAL_DIGITS,
            precision_step=AP_PRECISION_STEP,
        )
    else:
        engine = CalculatorEngine()
    CalculatorApp(root, engine=engine)
    root.mainloop()


if __name__ == "__main__":
    main()
