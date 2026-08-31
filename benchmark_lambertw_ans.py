"""Prueba de rendimiento de la memoria ANS: W de Lambert por Newton-Raphson.

Calcula W(x) —rama principal— resolviendo `w·e^w = x` con el método de
Newton-Raphson expresado íntegramente como cadena de recetas ANS de la
calculadora:

    semilla:   ln(x) - ln(ln(x))            (Corless et al., x > 1)
    paso n:    A - (A*exp(A) - x)/(exp(A)*(A+1))

Cada paso se evalúa con la API pública del motor (`evaluate`), de modo que
la cadena de dependencias crece un eslabón por iteración y `A` es siempre
el iterante anterior. Después se amplía la precisión con
`request_more_precision()` hasta superar los dígitos solicitados: la
reevaluación repite todas las iteraciones de Newton a la precisión
ampliada, donde la convergencia cuadrática (que duplica los dígitos
correctos en cada paso) sigue avanzando hasta agotar los dígitos internos.

El número de iteraciones se elige para que la repetición a los dígitos
internos finales converja con margen; se verifica contra `mp.lambertw()`
de mpmath a la misma precisión y el script falla si no alcanza los dígitos
pedidos. El rendimiento se compara con ese cálculo directo y con un bucle
de Newton autónomo en mpmath puro. No se impone ningún umbral dependiente
del equipo: solo se informan mediciones.

Recomendado para x >= e (con la semilla indicada converge con seguridad);
para otros valores el script sigue verificando la exactitud final.

Uso:
    python benchmark_lambertw_ans.py --x 1000 --digits 300 --repeats 5
    python benchmark_lambertw_ans.py --x 1000 --digits 300 --iterations 16 --precision-step 90
"""

from __future__ import annotations

import argparse
import math
import statistics
import time

from mpmath import mp

from arbitrary_precision_engine import ArbitraryPrecisionCalculatorEngine

_INITIAL_DIGITS = 18
_DIGITS_PREVIEW = 40


def _seed_expression(x_literal: str) -> str:
    """Semilla inicial calculable en la propia calculadora."""
    return f"ln({x_literal})-ln(ln({x_literal}))"


def _newton_step_expression(x_literal: str) -> str:
    """Paso de Newton-Raphson de w·e^w = x como expresión con `A`."""
    return f"A - (A*exp(A) - {x_literal})/(exp(A)*(A+1))"


def _required_iterations(digits: int) -> int:
    """Iteraciones para que la repetición final converja con margen.

    La convergencia cuadrática duplica los dígitos correctos por paso; con
    los dígitos internos del motor (`2·dígitos + 10`) y una semilla con
    ~1 dígito correcto bastan `ceil(log2(internos)) + 3` pasos.
    """
    internal = 2 * digits + 10
    return max(12, math.ceil(math.log2(internal)) + 3)


def _run_chain_once(
    x_literal: str, iterations: int, digits: int, precision_step: int
) -> tuple:
    """Construye la cadena ANS, la expande al objetivo y mide cada fase."""
    engine = ArbitraryPrecisionCalculatorEngine(
        initial_digits=_INITIAL_DIGITS, precision_step=precision_step
    )

    start_build = time.perf_counter()
    last_text = engine.evaluate(_seed_expression(x_literal))
    step_expression = _newton_step_expression(x_literal)
    for _ in range(iterations):
        last_text = engine.evaluate(step_expression)
    build_seconds = time.perf_counter() - start_build

    working = _INITIAL_DIGITS
    jump_seconds: list[float] = []
    while working < digits and engine.can_expand_precision():
        jump_start = time.perf_counter()
        last_text = engine.request_more_precision()
        jump_seconds.append(time.perf_counter() - jump_start)
        working += precision_step

    depth = engine._answer_recipe.depth
    return build_seconds, jump_seconds, working, last_text, depth


def _correct_digits(last_text: str, x_literal: str, final_working: int) -> float:
    """Dígitos correctos del resultado frente a `mp.lambertw` a igual precisión."""
    internal = 2 * final_working + 10
    with mp.workdps(internal):
        value = mp.mpf(last_text)
        w_true = mp.lambertw(mp.mpf(x_literal))
        relative_error = abs(value - w_true) / abs(w_true)
        if relative_error == 0:
            return float("inf")
        return float(-mp.log10(relative_error))


def _time_direct(
    x_literal: str, internal: int, iterations: int, repeats: int
) -> tuple[float, float]:
    """Medianas de `mp.lambertw` y de un bucle Newton puro a igual precisión."""
    lambert_times: list[float] = []
    newton_times: list[float] = []
    for _ in range(max(1, repeats)):
        with mp.workdps(internal):
            x = mp.mpf(x_literal)

            start = time.perf_counter()
            mp.lambertw(x)
            lambert_times.append(time.perf_counter() - start)

            start = time.perf_counter()
            w = mp.log(x) - mp.log(mp.log(x))
            for _step in range(iterations):
                w = w - (w * mp.e**w - x) / (mp.e**w * (w + 1))
            newton_times.append(time.perf_counter() - start)

    return statistics.median(lambert_times), statistics.median(newton_times)


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def _format_ms(seconds: float) -> str:
    return f"{seconds * 1000:.3f}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Calcula W(x) por Newton-Raphson como cadena de recetas ANS con "
            "al menos los dígitos pedidos y mide el rendimiento."
        ),
    )
    parser.add_argument(
        "--x", default="1000", help="Argumento de W (literal decimal, se usa tal cual)."
    )
    parser.add_argument(
        "--digits", type=int, default=300, help="Dígitos de trabajo objetivo (>= 300)."
    )
    parser.add_argument(
        "--precision-step",
        type=int,
        default=120,
        help="Dígitos añadidos por cada salto de precisión.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Iteraciones de Newton (por defecto, las suficientes con margen).",
    )
    parser.add_argument(
        "--repeats", type=int, default=5, help="Repeticiones medidas por sección."
    )
    args = parser.parse_args()

    x_literal = args.x.strip()
    try:
        if mp.mpf(x_literal) <= 1:
            raise SystemExit("ERROR: --x debe ser mayor que 1 (rama principal).")
    except SystemExit:
        raise
    except Exception:
        raise SystemExit(f"ERROR: --x no es un literal decimal válido: {x_literal!r}")
    if args.digits < 1 or args.precision_step < 1:
        raise SystemExit("ERROR: --digits y --precision-step deben ser >= 1")

    iterations = args.iterations or _required_iterations(args.digits)
    if iterations < 1:
        raise SystemExit("ERROR: --iterations debe ser >= 1")

    builds: list[float] = []
    total_jumps: list[float] = []
    last_text = ""
    final_working = _INITIAL_DIGITS
    jump_count = 0
    depth = 0
    for _ in range(max(1, args.repeats)):
        build, jumps, final_working, last_text, depth = _run_chain_once(
            x_literal, iterations, args.digits, args.precision_step
        )
        builds.append(build)
        jump_count = len(jumps)
        total_jumps.append(sum(jumps))

    build_median = _median(builds)
    jumps_median = _median(total_jumps)
    total_ans = build_median + jumps_median

    internal = 2 * final_working + 10
    lambert_median, newton_median = _time_direct(
        x_literal, internal, iterations, args.repeats
    )
    correct = _correct_digits(last_text, x_literal, final_working)

    print("Benchmark W de Lambert vía ANS (Newton-Raphson)")
    print(f"x:                          {x_literal}")
    print(f"Iteraciones de Newton:      {iterations}")
    print(f"Profundidad de la cadena:   {depth} (semilla + {iterations} pasos)")
    print(
        f"Precisión:                  objetivo {args.digits} dígitos "
        f"(internos {internal})"
    )
    print(
        f"Saltos de precisión:        {jump_count} "
        f"({_INITIAL_DIGITS} → {final_working} dígitos, paso {args.precision_step})"
    )
    print(f"Semilla:                    {_seed_expression(x_literal)}")
    print(f"Paso de Newton:             {_newton_step_expression(x_literal)}")
    print()
    print(f"Tiempos (mediana de {max(1, args.repeats)} repeticiones)")
    print(f"  construir cadena (semilla + {iterations} iteraciones): "
          f"{_format_ms(build_median)} ms")
    print(f"  expansiones de precisión:               "
          f"{_format_ms(jumps_median)} ms "
          f"({_format_ms(jumps_median / jump_count) if jump_count else 'n/d'} ms/salto)")
    print(f"  total motor ANS:                        {_format_ms(total_ans)} ms")
    print(f"  mp.lambertw directo ({internal} dps):        "
          f"{_format_ms(lambert_median)} ms")
    print(f"  bucle Newton mpmath puro ({internal} dps):   "
          f"{_format_ms(newton_median)} ms")
    print()
    print(f"Exactitud")
    print(f"  dígitos correctos vs mp.lambertw: {correct:.1f} "
          f"(objetivo >= {args.digits})")
    print(f"  W({x_literal}) ≈ {last_text[:_DIGITS_PREVIEW]}…")

    if correct < args.digits - 1:
        raise SystemExit(
            f"ERROR: la cadena ANS solo alcanzó {correct:.1f} dígitos correctos; "
            f"prueba con más iteraciones (--iterations)."
        )
    if depth != iterations + 1:
        raise SystemExit(
            f"ERROR: la profundidad de la cadena ({depth}) no coincide con "
            f"la esperada ({iterations + 1})."
        )


if __name__ == "__main__":
    main()
