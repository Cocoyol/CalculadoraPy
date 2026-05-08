"""Microbenchmark reproducible para ResultDisplay._advance_scientific()."""

from __future__ import annotations

import argparse
import statistics
import time

from arbitrary_precision_engine import ArbitraryPrecisionCalculatorEngine
from regression_scroll_checks import _make_display


def _run_once(value: str, steps: int) -> tuple[float, str]:
    display = _make_display(value)
    start = time.perf_counter()
    for _ in range(steps):
        display._advance_scientific(1)
    elapsed = time.perf_counter() - start
    return elapsed, display.get_text()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mide el costo de desplazar ResultDisplay._advance_scientific() sobre resultados largos.",
    )
    parser.add_argument("--expr", default="12.34567^30", help="Expresión a evaluar antes del benchmark.")
    parser.add_argument("--digits", type=int, default=600, help="Dígitos iniciales usados para construir el resultado.")
    parser.add_argument("--precision-step", type=int, default=120, help="Paso de precisión del motor usado para construir el valor.")
    parser.add_argument("--steps", type=int, default=120, help="Cantidad de desplazamientos por repetición.")
    parser.add_argument("--repeats", type=int, default=25, help="Cantidad de repeticiones medidas.")
    parser.add_argument("--warmup", type=int, default=3, help="Cantidad de repeticiones de calentamiento no medidas.")
    args = parser.parse_args()

    engine = ArbitraryPrecisionCalculatorEngine(
        initial_digits=args.digits,
        precision_step=args.precision_step,
    )
    value = engine.evaluate(args.expr)

    for _ in range(max(0, args.warmup)):
        _run_once(value, args.steps)

    timings = []
    final_text = value
    for _ in range(max(1, args.repeats)):
        elapsed, final_text = _run_once(value, args.steps)
        timings.append(elapsed)

    mean_seconds = statistics.mean(timings)
    median_seconds = statistics.median(timings)
    fastest_seconds = min(timings)
    slowest_seconds = max(timings)
    mean_us_per_step = (mean_seconds / max(1, args.steps)) * 1_000_000

    print("Scroll advance benchmark")
    print(f"expr:              {args.expr}")
    print(f"initial digits:    {args.digits}")
    print(f"precision step:    {args.precision_step}")
    print(f"steps per repeat:  {args.steps}")
    print(f"warmup repeats:    {args.warmup}")
    print(f"measured repeats:  {args.repeats}")
    print(f"initial result:    {value}")
    print(f"final text:        {final_text}")
    print(f"mean total ms:     {mean_seconds * 1000:.3f}")
    print(f"median total ms:   {median_seconds * 1000:.3f}")
    print(f"fastest total ms:  {fastest_seconds * 1000:.3f}")
    print(f"slowest total ms:  {slowest_seconds * 1000:.3f}")
    print(f"mean us/step:      {mean_us_per_step:.3f}")


if __name__ == "__main__":
    main()