from mpmath import mp

from arbitrary_precision_engine import ArbitraryPrecisionCalculatorEngine
from calculator_ui_window import CalculatorApp


class _FakeFuture:
    def __init__(self, *, running: bool = False, done: bool = False):
        self._running = running
        self._done = done
        self.cancelled = False
        self.cancel_calls = 0

    def done(self) -> bool:
        return self._done

    def running(self) -> bool:
        return self._running

    def cancel(self) -> bool:
        self.cancel_calls += 1
        if self._running or self._done:
            return False
        self.cancelled = True
        self._done = True
        return True


class _FakeExecutor:
    def __init__(self, future):
        self._future = future
        self.submit_calls = 0

    def submit(self, _fn):
        self.submit_calls += 1
        return self._future


class _Harness:
    _cancel_pending_background_jobs = CalculatorApp._cancel_pending_background_jobs

    def __init__(self):
        self._background_futures = []
        self._background_job_seq = 0
        self._active_background_job_id = 0
        self._closing = False
        self._background_executor = None


def _assert(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def check_terminal_values_do_not_expand_precision() -> None:
    cases = [
        ("0", "Este resultado no admite más precisión"),
        ("30!", "Este resultado no admite más precisión"),
        ("sqrt(-1)", "Los resultados complejos no expanden precisión"),
        ("ln(0)", "Este resultado no admite más precisión"),
    ]

    for expression, expected_message in cases:
        engine = ArbitraryPrecisionCalculatorEngine(initial_digits=18, precision_step=24)
        engine.evaluate(expression)

        _assert(
            not engine.can_expand_precision(),
            f"{expression!r} no debe expandir precisión",
        )

        try:
            engine.request_more_precision()
        except ValueError as exc:
            _assert(
                str(exc) == expected_message,
                f"{expression!r} produjo mensaje inesperado: {exc!r}",
            )
        else:
            raise AssertionError(f"{expression!r} debio rechazar la expansión")

    engine = ArbitraryPrecisionCalculatorEngine(initial_digits=18, precision_step=24)
    engine.evaluate("1/3")
    _assert(engine.can_expand_precision(), "1/3 debe seguir expandiendo precisión")

    engine._last_expression = "nan"
    engine._last_value = mp.nan
    _assert(not engine.can_expand_precision(), "NaN no debe expandir precisión")


def check_new_job_id_cancels_pending_futures() -> None:
    running = _FakeFuture(running=True)
    pending = _FakeFuture()
    done = _FakeFuture(done=True)

    harness = _Harness()
    harness._background_futures = [running, pending, done]

    job_id = CalculatorApp._next_background_job_id(harness)

    _assert(job_id == 1, f"job_id inesperado: {job_id}")
    _assert(not running.cancelled, "no debe cancelarse un future en ejecución")
    _assert(running.cancel_calls == 0, "no debe intentarse cancelar un future en ejecución")
    _assert(pending.cancelled, "faltó cancelar el future pendiente")
    _assert(pending.cancel_calls == 1, "el future pendiente debe cancelarse una vez")
    _assert(harness._background_futures == [running], "solo debe conservarse el future en ejecución")


def check_submit_background_tracks_latest_future() -> None:
    finished = _FakeFuture(done=True)
    latest = _FakeFuture()

    harness = _Harness()
    harness._background_futures = [finished]
    harness._background_executor = _FakeExecutor(latest)

    submitted = CalculatorApp._submit_background(harness, lambda: None)

    _assert(submitted, "_submit_background debio aceptar el future nuevo")
    _assert(harness._background_executor.submit_calls == 1, "faltó enviar el trabajo al executor")
    _assert(harness._background_futures == [latest], "el seguimiento de futures debe podar los ya finalizados")


def run_regressions() -> None:
    checks = [
        ("terminal values block precision expansion", check_terminal_values_do_not_expand_precision),
        ("new job id cancels queued futures", check_new_job_id_cancels_pending_futures),
        ("submit background tracks latest future", check_submit_background_tracks_latest_future),
    ]

    for label, check in checks:
        check()
        print(f"OK: {label}")

    print("\nAll phase 3 regression checks passed.")


if __name__ == "__main__":
    run_regressions()