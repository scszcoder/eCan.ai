"""A label sheet is scaled to fit the printer's paper, never enlarged past it
(agent/ec_skills/label_utils/print_fit.py; 2026-11-18: an A4 sheet printed on Letter was cut off)."""
from agent.ec_skills.label_utils.print_fit import fit_rect

LETTER_300DPI = (2480, 3230)        # printable area the Epson reported


def test_an_a4_sheet_fits_inside_letter_paper_whole():
    a4 = (2481, 3507)                   # A4 rendered at 300 dpi
    left, top, right, bottom = fit_rect(*a4, *LETTER_300DPI)
    assert left >= 0 and top >= 0 and right <= LETTER_300DPI[0] and bottom <= LETTER_300DPI[1]
    assert bottom - top == LETTER_300DPI[1]                     # height is the limit
    assert abs((right - left) / (bottom - top) - a4[0] / a4[1]) < 0.002   # proportions kept


def test_a_small_page_is_scaled_up_and_centred():
    left, top, right, bottom = fit_rect(1200, 1800, *LETTER_300DPI)
    assert (left + right) // 2 == LETTER_300DPI[0] // 2 or abs((left + right) / 2 - LETTER_300DPI[0] / 2) <= 1
    assert right - left <= LETTER_300DPI[0] and bottom - top <= LETTER_300DPI[1]


def test_a_remote_desktop_printer_falls_back_to_the_same_printer_on_this_pc():
    from agent.ec_skills.label_utils.print_fit import local_printer_for
    installed = ["Microsoft Print to PDF", "EPSON ET-3750 Series"]
    assert local_printer_for("EPSON ET-3750 Series (redirected 2)", installed) == "EPSON ET-3750 Series"
    assert local_printer_for("Brother HL (redirected 2)", installed) == ""
    assert local_printer_for("EPSON ET-3750 Series", installed) == ""


def test_a_print_that_crashes_or_hangs_fails_without_taking_ecan_down():
    # 2026-11-25: a crash in python311.dll while printing a label sheet closed eCan.
    import os
    import time
    from agent.ec_skills.label_utils.print_fit import run_isolated
    ok, why = run_isolated(os._exit, 3, timeout=60)
    assert not ok and "exit code 3" in why
    ok, why = run_isolated(time.sleep, 30, timeout=3)
    assert not ok and "did not finish" in why
    assert run_isolated(divmod, 7, 2, timeout=60) == (3, 1)


def test_an_isolated_print_works_from_an_app_whose_main_module_exits_when_reimported(tmp_path):
    # 2026-11-27: eCan's main.py exits when imported as anything but __main__, so a
    # multiprocessing child (which re-imports it) ended at once and no label printed.
    import os
    import subprocess
    import sys
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    app = tmp_path / "app_main.py"
    app.write_text(
        "import sys\n"
        "if __name__ != '__main__':\n"
        "    sys.exit(0)\n"
        f"sys.path.insert(0, {root!r})\n"
        "from agent.ec_skills.label_utils.print_fit import run_isolated\n"
        "print(run_isolated(divmod, 7, 2, timeout=60))\n", encoding="utf-8")
    done = subprocess.run([sys.executable, str(app)], capture_output=True, text=True, timeout=120)
    assert done.stdout.strip().endswith("(3, 1)"), done.stdout + done.stderr
