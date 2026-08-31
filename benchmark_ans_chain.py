"""Microbenchmark reproducible del coste de las cadenas de recetas ANS.

Construye una cadena de ANS de profundidad N (`0.1` seguido de `A+1`
repetido), la reevalúa con varios saltos de precisión hasta el objetivo y
compara el resultado con una fórmula independiente equivalente evaluada
directamente por el mismo motor.

El benchmark informa profundidad, precisión y tiempos medidos, pero **no
impone ningún umbral dependiente del equipo**: las cifras sirven para
observar tendencias. En particular, permite verificar que el coste de una
expansión es **lineal en la profundidad** de la cadena (la reevaluación
recorre todos los nodos); mientras no se mida lo contrario, no se impone
ningún límite arbitrario de longitud de cadena ni se añade caché.

Con `--sweep` se ejecuta un barrido sobre varias profundidades y se imprime
el coste por eslabón del último salto, donde la linealidad debe verse como
una columna aproximadamente constante.

Uso:
    python benchmark_ans_chain.py --depth 100 --digits 300 --precision-step 120 --repeats 5
    python benchmark_ans_chain.py --sweep --digits 300 --precision-step 120 --repeats 3
"""

from __future__ import annotations

import argparse
import statistics
import time

from arbitrary_precision_engine import ArbitraryPrecisionCalculatorEngine

# Dígitos de trabajo con los que el benchmark construye cada motor; fijarlos
# de forma explícita mantiene el informe reproducible aunque el motor cambie
# su valor por defecto.
_INITIAL_DIGITS = 18
_DIGITS_PREVIEW = 40
_SWEEP_DEPTHS = (10, 25, 50, 100, 200)


def _independent_expression(depth: int) -> str:
    """Fórmula independiente equivalente a la cadena de profundidad `depth`."""
    return "0.1" + "+1" * (depth - 1)


def _run_chain_once(depth: int, digits: int, precision_step: int):
    """Construye la cadena, la expande al objetivo y devuelve tiempos y textos."""
    engine = ArbitraryPrecisionCalculatorEngine(
        initial_digits=_INITIAL_DIGITS, precision_step=precision_step
    )

    start_build = time.perf_counter()
    final_text = engine.evaluate("0.1")
    for _ in range(depth - 1):
        final_text = engine.evaluate("A+1")
    build_seconds = time.perf_counter() - start_build

    working = _INITIAL_DIGITS
    jump_seconds: list[float] = []
    while working < digits and engine.can_expand_precision():
        jump_start = time.perf_counter()
        final_text = engine.request_more_precision()
        jump_seconds.append(time.perf_counter() - jump_start)
        working += precision_step

    return engine, build_seconds, jump_seconds, working, final_text


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def _format_ms(seconds: float) -> str:
    return f"{seconds * 1000:.3f}"


def _measure_depth(depth: int, digits: int, precision_step: int, repeats: int) -> dict:
    """Repite la medición y devuelve medianas de construcción y expansión."""
    builds: list[float] = []
    total_jumps: list[float] = []
    last_jumps: list[float] = []

    engine = None
    final_text = ""
    working = _INITIAL_DIGITS
    jump_count = 0
    for _ in range(max(1, repeats)):
        engine, build, jumps, working, final_text = _run_chain_once(
            depth, digits, precision_step
        )
        builds.append(build)
        jump_count = len(jumps)
        total_jumps.append(sum(jumps))
        if jumps:
            last_jumps.append(jumps[-1])

    return {
        "depth": depth,
        "initial_digits": _INITIAL_DIGITS,
        "working_digits": working,
        "jump_count": jump_count,
        "build_median": _median(builds),
        "total_jumps_median": _median(total_jumps),
        "last_jump_median": _median(last_jumps),
        "engine": engine,
        "final_text": final_text,
    }


def _verify_equivalence(result: dict, precision_step: int, repeats: int) -> tuple:
    """Evalúa la fórmula independiente al mismo ancho y compara el texto."""
    working = result["working_digits"]
    expression = _independent_expression(result["depth"])

    timings: list[float] = []
    direct_text = ""
    for _ in range(max(1, repeats)):
        direct_engine = ArbitraryPrecisionCalculatorEngine(
            initial_digits=working, precision_step=precision_step
        )
        start = time.perf_counter()
        direct_text = direct_engine.evaluate(expression)
        timings.append(time.perf_counter() - start)

    identical = direct_text == result["final_text"]
    return identical, _median(timings), expression


def _print_depth_report(result: dict, direct_median: float, expression: str) -> None:
    depth = result["depth"]
    per_link_ms = (result["last_jump_median"] * 1000) / depth
    overhead = (
        result["last_jump_median"] / direct_median if direct_median > 0 else 0.0
    )

    print(f"\nProfundidad de la cadena:       {depth}")
    print(f"Precisión inicial:              {result['initial_digits']} dígitos")
    print(f"Precisión final:                {result['working_digits']} dígitos")
    print(f"Saltos de precisión:            {result['jump_count']}")
    print(f"Construcción (mediana):         {_format_ms(result['build_median'])} ms")
    print(
        f"Expansión total (mediana):      "
        f"{_format_ms(result['total_jumps_median'])} ms"
    )
    print(
        f"Último salto (mediana):         "
        f"{_format_ms(result['last_jump_median'])} ms "
        f"({per_link_ms:.4f} ms/eslabón)"
    )
    shown = expression[:48]
    print(f"Fórmula independiente:          {shown}{'…' if len(expression) > 48 else ''}")
    print(f"  evaluación directa (mediana): {_format_ms(direct_median)} ms")
    if overhead:
        print(f"  sobrecoste del último salto:  ×{overhead:.2f}")


def run_single(depth: int, digits: int, precision_step: int, repeats: int) -> None:
    result = _measure_depth(depth, digits, precision_step, repeats)
    identical, direct_median, expression = _verify_equivalence(
        result, precision_step, repeats
    )
    _print_depth_report(result, direct_median, expression)

    preview = result["final_text"][:_DIGITS_PREVIEW]
    print(f"Valor final (primeros {_DIGITS_PREVIEW}): {preview}…")
    print(f"Equivalencia con el directo:    {'idéntica' if identical else '¡DIFIERE!'}")
    if not identical:
        raise SystemExit(
            "ERROR: la reevaluación de la cadena y la fórmula independiente "
            "produjeron textos distintos."
        )


def run_sweep(digits: int, precision_step: int, repeats: int) -> None:
    print(f"Barrido de profundidades (objetivo {digits} dígitos, paso {precision_step})")
    print(f"{'profundidad':>12} {'último salto ms':>17} {'ms/eslabón':>12} {'saltos':>7}")
    for depth in _SWEEP_DEPTHS:
        result = _measure_depth(depth, digits, precision_step, repeats)
        per_link_ms = (result["last_jump_median"] * 1000) / depth
        print(
            f"{depth:>12} "
            f"{_format_ms(result['last_jump_median']):>17} "
            f"{per_link_ms:>12.4f} "
            f"{result['jump_count']:>7}"
        )
    print(
        "\nSi el coste del último salto crece linealmente con la profundidad, "
        "la columna «ms/eslabón» permanece aproximadamente constante."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Mide el coste de construir y reevaluar cadenas de recetas ANS "
            "y lo compara con la fórmula independiente equivalente."
        ),
    )
    parser.add_argument(
        "--depth", type=int, default=100, help="Profundidad de la cadena ANS (>= 1)."
    )
    parser.add_argument(
        "--digits", type=int, default=300, help="Dígitos de trabajo objetivo."
    )
    parser.add_argument(
        "--precision-step",
        type=int,
        default=120,
        help="Dígitos añadidos por cada salto de precisión.",
    )
    parser.add_argument(
        "--repeats", type=int, default=5, help="Repeticiones medidas por sección."
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Barrido sobre varias profundidades para observar el coste lineal.",
    )
    args = parser.parse_args()

    if args.depth < 1:
        raise SystemExit("ERROR: --depth debe ser >= 1")
    if args.precision_step < 1:
        raise SystemExit("ERROR: --precision-step debe ser >= 1")

    if args.sweep:
        run_sweep(args.digits, args.precision_step, args.repeats)
    else:
        run_single(args.depth, args.digits, args.precision_step, args.repeats)


if __name__ == "__main__":
    main()
