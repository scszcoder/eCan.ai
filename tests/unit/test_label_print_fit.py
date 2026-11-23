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
