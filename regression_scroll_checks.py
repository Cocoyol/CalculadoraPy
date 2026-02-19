from arbitrary_precision_engine import ArbitraryPrecisionCalculatorEngine
from calculator_ui import ResultDisplay
import re
import sys


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


def inspect_scroll_states(
	expr: str,
	*,
	steps: int = 8,
	initial_digits: int = 260,
	show: int = 3,
) -> None:
	"""Imprime estado inicial y primeros estados cambiantes al desplazar."""
	value, end_text, states = _walk(expr, steps=steps, initial_digits=initial_digits)

	print("Scroll inspection")
	print(f"expr:           {expr}")
	print(f"initial value:  {value}")
	print(f"steps walked:   {steps}")
	print(f"initial digits: {initial_digits}")
	print(f"total states:   {len(states)}")

	if not states:
		print("first states:   (no changes)")
		print(f"final text:     {end_text}")
		return

	limit = max(1, show)
	print("first states:")
	for i, text in enumerate(states[:limit], start=1):
		print(f"  {i}. {text}")

	print(f"final text:     {end_text}")


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
		"dot-start hands off to standard scientific bridge",
		any(
			states_main[i] == "….7483752022212102"
			and i + 1 < len(states_main)
			and re.fullmatch(r"[+-]?\d(?:\.\d+)?e-1", states_main[i + 1]) is not None
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

	_, _, states_5_7 = _walk("5/7", steps=8, initial_digits=240)
	checks.append((
		"5/7 first shifted state is dot-start",
		len(states_5_7) >= 1 and states_5_7[0] == "….7142857142857142",
	))
	checks.append((
		"5/7 second shifted state uses standard scientific bridge",
		len(states_5_7) >= 2 and states_5_7[1] == "7.142857142857e-1",
	))
	checks.append((
		"5/7 third shifted state resumes normal shifted scientific",
		len(states_5_7) >= 3 and states_5_7[2] == "…1428571428571e-14",
	))

	value_5_7_1e11 = ArbitraryPrecisionCalculatorEngine(
		initial_digits=260,
		precision_step=120,
	).evaluate("(5/7)/10^11")
	display_5_7_1e11 = _make_display(value_5_7_1e11)
	expected_actual.append((
		"(5/7)/10^11 shift+copy from initial scientific view",
		"0.00000000000714285714285",
		display_5_7_1e11.get_copy_text(plain_decimal=True),
	))
	checks.append((
		"(5/7)/10^11 copy from initial scientific view keeps scientific text",
		display_5_7_1e11.get_copy_text() == "7.14285714285e-12",
	))
	display_5_7_1e11._advance_scientific(1)
	expected_actual.append((
		"(5/7)/10^11 first bridge copy omits ellipsis",
		"7.142857142857e-12",
		display_5_7_1e11.get_copy_text(),
	))
	expected_actual.append((
		"(5/7)/10^11 first bridge shift+copy keeps real value",
		"0.000000000007142857142857",
		display_5_7_1e11.get_copy_text(plain_decimal=True),
	))
	checks.append((
		"(5/7)/10^11 first bridge copy has no ellipsis",
		"…" not in display_5_7_1e11.get_copy_text(),
	))

	_, _, states_3_17539 = _walk("3/17539", steps=10, initial_digits=260)
	checks.append((
		"3/17539 first shifted state is dot-start with leading zeros",
		len(states_3_17539) >= 1 and states_3_17539[0] == "….0001710473801242",
	))
	display_3_17539 = _make_display(ArbitraryPrecisionCalculatorEngine(
		initial_digits=260,
		precision_step=120,
	).evaluate("3/17539"))
	display_3_17539._advance_scientific(1)
	checks.append((
		"3/17539 first shifted copy omits ellipsis",
		display_3_17539.get_copy_text() == "0.0001710473801242",
	))
	checks.append((
		"3/17539 second shifted state uses standard scientific bridge",
		len(states_3_17539) >= 2 and states_3_17539[1] == "1.710473801242e-4",
	))
	checks.append((
		"3/17539 third shifted state resumes normal shifted scientific",
		len(states_3_17539) >= 3 and states_3_17539[2] == "…7104738012429e-17",
	))
	display_3_17539_back = _make_display(ArbitraryPrecisionCalculatorEngine(
		initial_digits=260,
		precision_step=120,
	).evaluate("3/17539"))
	display_3_17539_back._advance_scientific(1)
	display_3_17539_back._advance_scientific(1)
	display_3_17539_back._advance_scientific(-1)
	checks.append((
		"3/17539 left from standard scientific bridge returns to dot-start",
		display_3_17539_back.get_text() == "….0001710473801242",
	))
	display_3_17539_back._advance_scientific(-1)
	checks.append((
		"3/17539 second left from bridge returns to initial flat decimal",
		display_3_17539_back.get_text() == "0.000171047380124",
	))

	_, _, states_3_1753 = _walk("3/1753", steps=10, initial_digits=260)
	checks.append((
		"3/1753 first shifted state is dot-start with leading zeros",
		len(states_3_1753) >= 1 and states_3_1753[0] == "….0017113519680547",
	))
	checks.append((
		"3/1753 second shifted state uses standard scientific bridge",
		len(states_3_1753) >= 2 and states_3_1753[1] == "1.711351968054e-3",
	))

	_, _, states_3_175391 = _walk("3/175391", steps=10, initial_digits=260)
	checks.append((
		"3/175391 first shifted state is dot-start with leading zeros",
		len(states_3_175391) >= 1 and states_3_175391[0] == "….0000171046404889",
	))
	checks.append((
		"3/175391 second shifted state uses standard scientific bridge",
		len(states_3_175391) >= 2 and states_3_175391[1] == "1.710464048896e-5",
	))

	_, _, states_3_over_19_19 = _walk("3/19^19", steps=8, initial_digits=220)
	checks.append((
		"3/19^19 first shifted state advances one place only",
		len(states_3_over_19_19) >= 1 and states_3_over_19_19[0] == "….516361804947e-24",
	))
	checks.append((
		"3/19^19 second shifted state resumes normal shifted scientific",
		len(states_3_over_19_19) >= 2 and states_3_over_19_19[1] == "…5163618049471e-37",
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
	# Uso rápido:
	#   python regression_scroll_checks.py
	#   python regression_scroll_checks.py --inspect "3/17539"
	#   python regression_scroll_checks.py --inspect "3/17539" --steps 12 --digits 300 --show 5
	if "--inspect" in sys.argv:
		try:
			expr = sys.argv[sys.argv.index("--inspect") + 1]
		except (ValueError, IndexError):
			raise SystemExit("Missing expression after --inspect")

		def _read_int(flag: str, default: int) -> int:
			if flag not in sys.argv:
				return default
			idx = sys.argv.index(flag)
			try:
				return int(sys.argv[idx + 1])
			except (ValueError, IndexError):
				raise SystemExit(f"Invalid value for {flag}")

		inspect_scroll_states(
			expr,
			steps=_read_int("--steps", 8),
			initial_digits=_read_int("--digits", 260),
			show=_read_int("--show", 3),
		)
	else:
		run_regressions()
