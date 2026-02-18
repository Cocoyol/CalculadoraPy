from arbitrary_precision_engine import ArbitraryPrecisionCalculatorEngine
from calculator_ui import ResultDisplay


class _FakeVar:
	def __init__(self):
		self.v = ""

	def set(self, x):
		self.v = x

	def get(self):
		return self.v


class _FakeEntry:
	def after(self, _ms, fn=None):
		if fn:
			fn()

	def after_cancel(self, _id):
		return None

	def xview_scroll(self, *_):
		return None

	def index(self, _):
		return 0

	def winfo_width(self):
		return 300

	def icursor(self, _):
		return None

	def xview_moveto(self, _):
		return None

	def xview(self, *_):
		return None


class _DummyResultDisplay(ResultDisplay):
	def __init__(self):
		pass


def _make_display(value: str) -> _DummyResultDisplay:
	display = _DummyResultDisplay()
	display._entry = _FakeEntry()
	display._var = _FakeVar()
	display._request_more_callback = lambda: None
	display._anim_id = None
	display._last_drag_x = None
	display._loading_more = False
	display._precision_exhausted = False
	display._force_scientific_current_shift = False
	display._sci_mode = False
	display._sci_sign = ""
	display._sci_digits = ""
	display._sci_exponent = 0
	display._sci_shift = 0
	display._sci_initial_text = "0"
	display._sci_source_kind = None
	display.set_text(value)
	return display


def _walk(expr: str, *, steps: int, initial_digits: int):
	engine = ArbitraryPrecisionCalculatorEngine(
		initial_digits=initial_digits,
		precision_step=120,
	)
	value = engine.evaluate(expr)
	display = _make_display(value)
	states = []

	for _ in range(steps):
		before = display.get_text()
		display._advance_scientific(1)
		after = display.get_text()
		if after != before:
			states.append(after)

	return value, display.get_text(), states


def run_regressions() -> None:
	checks: list[tuple[str, bool]] = []
	expected_actual: list[tuple[str, str, str]] = []

	_, _, states_main = _walk("12.34567^30", steps=100, initial_digits=420)
	checks.append((
		"transition keeps middle plain state",
		any("…1.748375202221210" in text for text in states_main),
	))
	checks.append((
		"transition keeps dot-start state",
		any(text == "….7483752022212102" for text in states_main),
	))
	checks.append((
		"dot-start hands off to e-13",
		any(
			states_main[i] == "….7483752022212102"
			and i + 1 < len(states_main)
			and states_main[i + 1] == "…7483752022212e-13"
			for i in range(len(states_main))
		),
	))

	_, end_short, states_short = _walk("25^25/10^10", steps=120, initial_digits=240)
	expected_actual.append((
		"25^25/10^10",
		"…389053.3447265625",
		end_short,
	))
	checks.append((
		"short-mantissa case clamps at expected end",
		end_short == "…389053.3447265625",
	))
	checks.append((
		"short-mantissa case avoids over-scroll",
		not any(text == "….3447265625" for text in states_short),
	))

	_, end_int_a, _ = _walk("25^25", steps=150, initial_digits=420)
	_, end_int_b, _ = _walk("30!", steps=150, initial_digits=420)
	checks.append(("25^25 never ends with trailing dot", not end_int_a.endswith(".")))
	checks.append(("30! never ends with trailing dot", not end_int_b.endswith(".")))

	_, end_40_fact, _ = _walk("40!", steps=220, initial_digits=420)
	_, end_60_fact, _ = _walk("60!", steps=260, initial_digits=420)
	expected_actual.append((
		"40!",
		"…69596115894272e+9",
		end_40_fact,
	))
	expected_actual.append((
		"60!",
		"…4492776964096e+14",
		end_60_fact,
	))
	checks.append((
		"40! clamps before excessive trailing zeros",
		end_40_fact == "…69596115894272e+9",
	))
	checks.append((
		"60! clamps before excessive trailing zeros",
		end_60_fact == "…4492776964096e+14",
	))

	display = _make_display("0.3333333333333333")
	first = display.get_text()
	display._advance_scientific(1)
	second = display.get_text()
	checks.append(("1/3 initial visible width is 17", len(first) == 17))
	checks.append(("1/3 after first scroll keeps 17 without ellipsis", len(second.replace("…", "")) == 17))

	engine_3e30 = ArbitraryPrecisionCalculatorEngine(initial_digits=18, precision_step=120)
	value_3e30 = engine_3e30.evaluate("3*10^-30")
	_, end_3e30, states_3e30 = _walk("3*10^-30", steps=20, initial_digits=18)
	display_3e30 = _make_display(value_3e30)
	expected_actual.append((
		"3*10^-30",
		"3e-30",
		end_3e30,
	))
	checks.append((
		"3e-30 displays without trailing zeros",
		end_3e30 == "3e-30",
	))
	checks.append((
		"3e-30 produces no scroll states (not scrollable)",
		len(states_3e30) == 0,
	))
	checks.append((
		"3e-30 copy gives clean notation",
		display_3e30.get_copy_text() == "3e-30",
	))
	checks.append((
		"3e-30 shift+copy gives flat decimal",
		display_3e30.get_copy_text(plain_decimal=True) == "0." + "0" * 29 + "3",
	))

	engine_1e20 = ArbitraryPrecisionCalculatorEngine(initial_digits=18, precision_step=120)
	value_1e20 = engine_1e20.evaluate("1/10^20")
	display_1e20 = _make_display(value_1e20)
	checks.append((
		"1/10^20 shift+copy gives flat decimal",
		display_1e20.get_copy_text(plain_decimal=True) == "0." + "0" * 19 + "1",
	))

	failed = [name for name, ok in checks if not ok]
	for name, ok in checks:
		print(f"{name}: {'OK' if ok else 'FAIL'}")

	print("\nExpected vs Actual:")
	for label, expected, actual in expected_actual:
		status = "OK" if expected == actual else "FAIL"
		print(f"- {label}: {status}")
		print(f"  expected: {expected}")
		print(f"  actual:   {actual}")

	if failed:
		print("\nFAILED CHECKS:")
		for name in failed:
			print(f"- {name}")
		raise SystemExit(1)

	print("\nAll regression checks passed.")


if __name__ == "__main__":
	run_regressions()
