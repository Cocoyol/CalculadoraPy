from arbitrary_precision_engine import ArbitraryPrecisionCalculatorEngine
from calculator_ui import ResultDisplay
from regression_scroll_checks import _make_display, _walk
import re
import sys


VISIBLE_CHARS_UNDER_TEST = 30
ELLIPSIS = "\u2026"


def _visible_len(text: str) -> int:
    return len(text.replace(ELLIPSIS, ""))


def _expect_equal(
    checks: list[tuple[str, bool]],
    expected_actual: list[tuple[str, str, str]],
    label: str,
    expected: str,
    actual: str,
) -> None:
    expected_actual.append((label, expected, actual))
    checks.append((label, expected == actual))


def _expect_no_scroll(
    checks: list[tuple[str, bool]],
    expr: str,
    expected: str,
    *,
    initial_digits: int = 80,
    steps: int = 25,
) -> None:
    _, end_text, states = _walk(expr, steps=steps, initial_digits=initial_digits)
    checks.append((
        f"{expr} stays non-scrollable at width 30",
        end_text == expected and len(states) == 0,
    ))


def _run_width_30_regressions() -> None:
    checks: list[tuple[str, bool]] = []
    expected_actual: list[tuple[str, str, str]] = []
    e = ELLIPSIS

    checks.append((
        "regression script forces VISIBLE_CHARS to 30",
        ResultDisplay.VISIBLE_CHARS == VISIBLE_CHARS_UNDER_TEST,
    ))

    _, end_main, states_main = _walk("12.34567^30", steps=120, initial_digits=420)
    _expect_equal(
        checks,
        expected_actual,
        "12.34567^30 final shifted view at width 30",
        f"{e}3132624440975203227920437e-112",
        end_main,
    )
    checks.append((
        "12.34567^30 keeps middle plain state at width 30",
        any(text == f"{e}1.7483752022212102472623166761" for text in states_main),
    ))
    checks.append((
        "12.34567^30 keeps dot-start state at width 30",
        any(text == f"{e}.74837520222121024726231667618" for text in states_main),
    ))
    checks.append((
        "12.34567^30 exits dot-start directly to shifted exponent state",
        any(
            states_main[i] == f"{e}.74837520222121024726231667618"
            and i + 1 < len(states_main)
            and states_main[i + 1] == f"{e}74837520222121024726231667e-26"
            for i in range(len(states_main))
        ),
    ))

    _, end_short, states_short = _walk("25^25/10^10", steps=120, initial_digits=240)
    _expect_equal(
        checks,
        expected_actual,
        "25^25/10^10 clamps at expected width-30 end",
        f"{e}4197001252323389053.3447265625",
        end_short,
    )
    checks.append((
        "25^25/10^10 avoids over-scroll at width 30",
        len(states_short) == 6 and not any(text.startswith(f"{e}.") for text in states_short),
    ))

    _, end_40_fact, states_40_fact = _walk("40!", steps=220, initial_digits=420)
    _, end_60_fact, states_60_fact = _walk("60!", steps=260, initial_digits=420)
    _expect_equal(
        checks,
        expected_actual,
        "40! clamps to full width-30 tail",
        f"{e}345611269596115894272000000000",
        end_40_fact,
    )
    _expect_equal(
        checks,
        expected_actual,
        "60! clamps to full width-30 tail",
        f"{e}952449277696409600000000000000",
        end_60_fact,
    )
    checks.append(("40! reaches terminal tail in 18 shifted states", len(states_40_fact) == 18))
    checks.append(("60! reaches terminal tail in 52 shifted states", len(states_60_fact) == 52))

    display_one_third = _make_display("0.3333333333333333")
    first_one_third = display_one_third.get_text()
    display_one_third._advance_scientific(1)
    checks.append((
        "short decimal under width 30 remains non-scrollable",
        first_one_third == "0.3333333333333333"
        and display_one_third.get_text() == first_one_third,
    ))

    _, end_complete_dot_start, states_complete_dot_start = _walk(
        "0.333333333333333333333333333+0.00000000000000000000000000045",
        steps=20,
        initial_digits=120,
    )
    _expect_equal(
        checks,
        expected_actual,
        "complete dot-start decimal stops at width 30",
        f"{e}.33333333333333333333333333345",
        end_complete_dot_start,
    )
    checks.append((
        "complete dot-start decimal avoids scientific bridge at width 30",
        states_complete_dot_start == [f"{e}.33333333333333333333333333345"],
    ))

    _expect_no_scroll(checks, "3*10^-30", "3e-30", initial_digits=18)
    _expect_no_scroll(checks, "9^7/10^30", "4.782969e-24", initial_digits=40)
    _expect_no_scroll(checks, "123456789012/10^30", "1.23456789012e-19")
    _expect_no_scroll(checks, "16^14", "72057594037927936")
    _expect_no_scroll(checks, "16^14+1", "72057594037927937")
    _expect_no_scroll(checks, "99999999999999999", "99999999999999999")
    _expect_no_scroll(checks, "10^18", "1000000000000000000")

    engine_initial = ArbitraryPrecisionCalculatorEngine()
    display_22_23 = _make_display(engine_initial.evaluate("22^23"))
    initial_22_23 = display_22_23.get_text()
    display_22_23._advance_scientific(1)
    checks.append((
        "22^23 scientific view fits and stays still at width 30",
        initial_22_23 == "7.51141330201283026e+30"
        and display_22_23.get_text() == initial_22_23,
    ))

    display_37_fact = _make_display(engine_initial.evaluate("37!"))
    _expect_equal(
        checks,
        expected_actual,
        "37! initial scientific view uses the width-30 budget",
        "1.376375309122634504631597e+43",
        display_37_fact.get_text(),
    )
    display_37_fact._advance_scientific(1)
    _expect_equal(
        checks,
        expected_actual,
        "37! first shift uses width-30 shifted budget",
        f"{e}37637530912263450463159795e+17",
        display_37_fact.get_text(),
    )

    for expr, expected in [
        ("15^15", "437893890380859375"),
        ("73.1^31.7", "1.21949731812025232e+59"),
        ("123456789012345678", "123456789012345678"),
        ("1600591090853e+26", "1.600591090853e+38"),
        ("8.6^12.85", "1019307215408.97899"),
        ("12345678901234567890123/10^8", "123456789012345.679"),
        ("12345678901234567890123/10^7", "1234567890123456.79"),
        ("1234567891234567/10", "123456789123456.7"),
        ("12345678912345/10", "1234567891234.5"),
    ]:
        display = _make_display(engine_initial.evaluate(expr))
        initial = display.get_text()
        display._advance_scientific(1)
        checks.append((
            f"{expr} has expected width-30 initial view and no scroll",
            initial == expected and display.get_text() == expected,
        ))

    _, _, states_9_5_20_7 = _walk("9.5^20.7", steps=50, initial_digits=260)
    checks.append((
        "9.5^20.7 shows width-30 decimal window before exponent exit",
        len(states_9_5_20_7) >= 22
        and states_9_5_20_7[20] == f"{e}.67799953461581728867024973859",
    ))
    checks.append((
        "9.5^20.7 width-30 exponent exit keeps first visible decimal digit",
        len(states_9_5_20_7) >= 23
        and states_9_5_20_7[21] == f"{e}67799953461581728867024973e-26",
    ))
    checks.append((
        "9.5^20.7 width-30 next exponent state advances one digit",
        len(states_9_5_20_7) >= 23
        and states_9_5_20_7[22] == f"{e}77999534615817288670249738e-27",
    ))

    _, _, states_5_7 = _walk("5/7", steps=8, initial_digits=240)
    checks.append((
        "5/7 first shifted state is width-30 dot-start",
        len(states_5_7) >= 1 and states_5_7[0] == f"{e}.71428571428571428571428571428",
    ))
    checks.append((
        "5/7 second shifted state uses width-30 standard bridge",
        len(states_5_7) >= 2 and states_5_7[1] == "7.1428571428571428571428571e-1",
    ))
    checks.append((
        "5/7 positive bridge has exactly 30 visible chars",
        len(states_5_7) >= 2 and len(states_5_7[1]) == VISIBLE_CHARS_UNDER_TEST,
    ))

    _, _, states_3_17539 = _walk("3/17539", steps=10, initial_digits=260)
    checks.append((
        "3/17539 first shifted state is width-30 dot-start with leading zeros",
        len(states_3_17539) >= 1
        and states_3_17539[0] == f"{e}.00017104738012429442955698728",
    ))
    checks.append((
        "3/17539 second shifted state uses width-30 standard bridge",
        len(states_3_17539) >= 2
        and states_3_17539[1] == "1.7104738012429442955698728e-4",
    ))
    checks.append((
        "3/17539 third shifted state resumes shifted scientific at width 30",
        len(states_3_17539) >= 3
        and states_3_17539[2] == f"{e}71047380124294429556987285e-30",
    ))

    for expr, first_expected, bridge_expected in [
        (
            "3/1753",
            f"{e}.00171135196805476326297775242",
            "1.7113519680547632629777524e-3",
        ),
        (
            "3/175391",
            f"{e}.00001710464048896465611120296",
            "1.7104640488964656111202969e-5",
        ),
    ]:
        _, _, states = _walk(expr, steps=10, initial_digits=260)
        checks.append((
            f"{expr} first shifted state is width-30 dot-start with leading zeros",
            len(states) >= 1 and states[0] == first_expected,
        ))
        checks.append((
            f"{expr} second shifted state uses width-30 standard bridge",
            len(states) >= 2 and states[1] == bridge_expected,
        ))

    _, _, states_3_over_19_19 = _walk("3/19^19", steps=8, initial_digits=220)
    checks.append((
        "3/19^19 first shifted state advances one place only at width 30",
        len(states_3_over_19_19) >= 1
        and states_3_over_19_19[0] == f"{e}.5163618049471539920405965e-24",
    ))
    checks.append((
        "3/19^19 second shifted state resumes shifted scientific at width 30",
        len(states_3_over_19_19) >= 2
        and states_3_over_19_19[1] == f"{e}51636180494715399204059654e-50",
    ))

    _, _, states_27_23 = _walk("27/23", steps=10, initial_digits=260)
    checks.append((
        "27/23 never produces an e-1 bridge at width 30",
        not any(re.fullmatch(r"[+-]?\d(?:\.\d+)?e-1", text) for text in states_27_23),
    ))

    _, _, states_20_20 = _walk("20^20-sqrt(3)", steps=120, initial_digits=420)
    checks.append((
        "20^20-sqrt(3) never produces an e-1 bridge at width 30",
        not any(re.fullmatch(r"[+-]?\d(?:\.\d+)?e-1", text) for text in states_20_20),
    ))

    engine_wide = ArbitraryPrecisionCalculatorEngine(initial_digits=260, precision_step=120)
    display_neg_dec = _make_display(engine_wide.evaluate("0-23/27"))
    neg_dec_initial = display_neg_dec.get_text()
    _expect_equal(
        checks,
        expected_actual,
        "-23/27 initial display at width 30",
        "-0.851851851851851851851851851",
        neg_dec_initial,
    )
    checks.append((
        "-23/27 initial has 30 chars including sign",
        len(neg_dec_initial) == VISIBLE_CHARS_UNDER_TEST and neg_dec_initial.startswith("-"),
    ))
    display_neg_dec._advance_scientific(1)
    neg_dec_first = display_neg_dec.get_text()
    display_neg_dec._advance_scientific(1)
    neg_dec_bridge = display_neg_dec.get_text()
    _expect_equal(
        checks,
        expected_actual,
        "-23/27 first shifted display at width 30",
        f"-{e}.8518518518518518518518518518",
        neg_dec_first,
    )
    _expect_equal(
        checks,
        expected_actual,
        "-23/27 bridge display at width 30",
        "-8.5185185185185185185185185e-1",
        neg_dec_bridge,
    )
    checks.append((
        "-23/27 shifted views keep 30 visible chars besides ellipsis",
        _visible_len(neg_dec_first) == VISIBLE_CHARS_UNDER_TEST
        and len(neg_dec_bridge) == VISIBLE_CHARS_UNDER_TEST + 1,
    ))
    display_neg_dec._advance_scientific(-1)
    display_neg_dec._advance_scientific(-1)
    checks.append((
        "-23/27 scroll back restores width-30 expanded initial",
        display_neg_dec.get_text() == neg_dec_initial,
    ))

    display_neg_9999_77 = _make_display(engine_wide.evaluate("0-9999/77"))
    neg_9999_77_initial = display_neg_9999_77.get_text()
    display_neg_9999_77._advance_scientific(1)
    neg_9999_77_first = display_neg_9999_77.get_text()
    display_neg_9999_77._advance_scientific(1)
    neg_9999_77_second = display_neg_9999_77.get_text()
    _expect_equal(
        checks,
        expected_actual,
        "-9999/77 initial display at width 30",
        "-129.8571428571428571428571428",
        neg_9999_77_initial,
    )
    checks.append((
        "-9999/77 shifts add one right-side digit at width 30",
        neg_9999_77_first == f"-{e}29.85714285714285714285714285"
        and neg_9999_77_second == f"-{e}9.857142857142857142857142857",
    ))

    display_neg_large_decimal = _make_display(engine_wide.evaluate("0-12345678901234567/1000"))
    neg_large_initial = display_neg_large_decimal.get_text()
    display_neg_large_decimal._advance_scientific(1)
    checks.append((
        "negative large decimal that fit-scrolled at 17 is non-scrollable at width 30",
        neg_large_initial == "-12345678901234.567"
        and display_neg_large_decimal.get_text() == neg_large_initial,
    ))

    display_neg_sci = _make_display(engine_wide.evaluate("0-25^25"))
    neg_sci_initial = display_neg_sci.get_text()
    display_neg_sci._advance_scientific(1)
    _expect_equal(
        checks,
        expected_actual,
        "-25^25 initial display at width 30",
        "-8.881784197001252323389053e+34",
        neg_sci_initial,
    )
    _expect_equal(
        checks,
        expected_actual,
        "-25^25 first shifted display at width 30",
        f"-{e}88178419700125232338905334e+8",
        display_neg_sci.get_text(),
    )

    display_neg_fact = _make_display(engine_wide.evaluate("-90!"))
    neg_fact_initial = display_neg_fact.get_text()
    display_neg_fact._advance_scientific(1)
    _expect_equal(
        checks,
        expected_actual,
        "-90! initial display at width 30",
        "-1.48571596448176149730952e+138",
        neg_fact_initial,
    )
    _expect_equal(
        checks,
        expected_actual,
        "-90! first shifted display at width 30",
        f"-{e}485715964481761497309522e+114",
        display_neg_fact.get_text(),
    )

    display_5_7_1e11 = _make_display(engine_wide.evaluate("(5/7)/10^11"))
    _expect_equal(
        checks,
        expected_actual,
        "(5/7)/10^11 copy from initial width-30 scientific view",
        "7.142857142857142857142857e-12",
        display_5_7_1e11.get_copy_text(),
    )
    _expect_equal(
        checks,
        expected_actual,
        "(5/7)/10^11 shift+copy from initial width-30 scientific view",
        "0.000000000007142857142857142857142857",
        display_5_7_1e11.get_copy_text(plain_decimal=True),
    )
    display_5_7_1e11._advance_scientific(1)
    _expect_equal(
        checks,
        expected_actual,
        "(5/7)/10^11 first bridge copy at width 30",
        "7.1428571428571428571428571e-12",
        display_5_7_1e11.get_copy_text(),
    )
    _expect_equal(
        checks,
        expected_actual,
        "(5/7)/10^11 first bridge shift+copy at width 30",
        "0.0000000000071428571428571428571428571",
        display_5_7_1e11.get_copy_text(plain_decimal=True),
    )
    checks.append((
        "(5/7)/10^11 first bridge copy has no ellipsis at width 30",
        ELLIPSIS not in display_5_7_1e11.get_copy_text(),
    ))

    display_3_17539 = _make_display(engine_wide.evaluate("3/17539"))
    display_3_17539._advance_scientific(1)
    _expect_equal(
        checks,
        expected_actual,
        "3/17539 first shifted copy at width 30",
        "0.00017104738012429442955698728",
        display_3_17539.get_copy_text(),
    )
    _expect_equal(
        checks,
        expected_actual,
        "3/17539 first shifted ctrl+copy at width 30",
        "1.7104738012429442955698728e-4",
        display_3_17539.get_copy_text(standard_scientific=True),
    )

    display_ctrl_pos = _make_display(engine_wide.evaluate("3.57^125"))
    for _ in range(4):
        display_ctrl_pos._advance_scientific(1)
    _expect_equal(
        checks,
        expected_actual,
        "3.57^125 ctrl+copy from shifted width-30 view",
        "1.21206807959710030161516750302e+69",
        display_ctrl_pos.get_copy_text(standard_scientific=True),
    )

    display_ctrl_neg = _make_display(engine_wide.evaluate("3.57^-79"))
    for _ in range(5):
        display_ctrl_neg._advance_scientific(1)
    _expect_equal(
        checks,
        expected_actual,
        "3.57^-79 shift+copy from shifted width-30 view",
        "0.0000000000000000000000000000000000000000000218379027252022387967706093327",
        display_ctrl_neg.get_copy_text(plain_decimal=True),
    )
    _expect_equal(
        checks,
        expected_actual,
        "3.57^-79 ctrl+copy from shifted width-30 view",
        "2.18379027252022387967706093327e-44",
        display_ctrl_neg.get_copy_text(standard_scientific=True),
    )
    checks.append((
        "ctrl+copy takes precedence over shift+copy at width 30",
        display_ctrl_neg.get_copy_text(plain_decimal=True, standard_scientific=True)
        == "2.18379027252022387967706093327e-44",
    ))

    display_ctrl_fact = _make_display(engine_wide.evaluate("121!"))
    _expect_equal(
        checks,
        expected_actual,
        "121! initial display at width 30",
        "8.09429852527344373968162e+200",
        display_ctrl_fact.get_text(),
    )
    for _ in range(5):
        display_ctrl_fact._advance_scientific(1)
    _expect_equal(
        checks,
        expected_actual,
        "121! ctrl+copy from shifted width-30 view",
        "8.09429852527344373968162284544e+200",
        display_ctrl_fact.get_copy_text(standard_scientific=True),
    )

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

    print("\nAll width-30 regression checks passed.")


def run_regressions() -> None:
    original_visible_chars = ResultDisplay.VISIBLE_CHARS
    original_decimal_separator = ResultDisplay.DECIMAL_SEPARATOR
    try:
        ResultDisplay.VISIBLE_CHARS = VISIBLE_CHARS_UNDER_TEST
        ResultDisplay.DECIMAL_SEPARATOR = False
        _run_width_30_regressions()
    finally:
        ResultDisplay.VISIBLE_CHARS = original_visible_chars
        ResultDisplay.DECIMAL_SEPARATOR = original_decimal_separator


def inspect_scroll_states(
    expr: str,
    *,
    steps: int = 8,
    initial_digits: int = 260,
    show: int = 3,
) -> None:
    original_visible_chars = ResultDisplay.VISIBLE_CHARS
    try:
        ResultDisplay.VISIBLE_CHARS = VISIBLE_CHARS_UNDER_TEST
        value, end_text, states = _walk(expr, steps=steps, initial_digits=initial_digits)
    finally:
        ResultDisplay.VISIBLE_CHARS = original_visible_chars

    print("Width-30 scroll inspection")
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


if __name__ == "__main__":
    if "--inspect" in sys.argv:
        try:
            expression = sys.argv[sys.argv.index("--inspect") + 1]
        except (ValueError, IndexError):
            raise SystemExit("Missing expression after --inspect")

        def _read_int(flag: str, default: int) -> int:
            if flag not in sys.argv:
                return default
            index = sys.argv.index(flag)
            try:
                return int(sys.argv[index + 1])
            except (ValueError, IndexError):
                raise SystemExit(f"Invalid value for {flag}")

        inspect_scroll_states(
            expression,
            steps=_read_int("--steps", 8),
            initial_digits=_read_int("--digits", 260),
            show=_read_int("--show", 3),
        )
    else:
        run_regressions()