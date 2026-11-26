"""Print a PDF on a Windows printer, each page scaled to fit the printer's paper.

LibreOffice (``soffice --pt``) printed an A4 label sheet at its own size on a Letter
printer: enlarged and cut off at the bottom, losing the copy's product note (2026-11-18).
This renders each page and draws it through GDI into the printable area the printer
reports, keeping the page's proportions and centring it.
"""
import multiprocessing
import os
import queue
import re
from typing import Tuple

DPI = 300


def fit_rect(img_w: int, img_h: int, area_w: int, area_h: int) -> Tuple[int, int, int, int]:
    """(left, top, right, bottom) of an img_w x img_h image scaled to fit area_w x area_h, centred."""
    scale = min(area_w / img_w, area_h / img_h)
    w, h = int(img_w * scale), int(img_h * scale)
    left, top = (area_w - w) // 2, (area_h - h) // 2
    return left, top, left + w, top + h


def local_printer_for(name: str, installed) -> str:
    """The printer on this PC that *name* ("<printer> (redirected N)") is a Remote Desktop copy of, or ""."""
    base = re.sub(r"\s*\(redirected \d+\)$", "", name or "")
    return base if base != name and base in installed else ""


def print_pdf_fit(path: str, printer: str = "", timeout: float = 180) -> Tuple[bool, str]:
    """Print every page of *path* on *printer* (default: the Windows default), fitted to its paper.

    Runs in a child process: a printer driver that crashes takes only the child down. One
    crashed in python311.dll right after a label sheet was made and took eCan with it, before
    the print, the report and the email (2026-11-25)."""
    return run_isolated(_print_here, path, printer, timeout=timeout)


def _child(fn, args, out) -> None:
    try:
        out.put(fn(*args))
    except Exception as e:
        out.put((False, f"{type(e).__name__}: {e}"))


def run_isolated(fn, *args, timeout: float = 180) -> Tuple[bool, str]:
    """fn(*args) in a fresh process; (False, why) when it fails, crashes or hangs."""
    ctx = multiprocessing.get_context("spawn")
    out = ctx.Queue()
    proc = ctx.Process(target=_child, args=(fn, args, out), daemon=True)
    proc.start()
    try:
        return out.get(timeout=timeout)
    except queue.Empty:
        if proc.is_alive():
            proc.terminate()
            return False, f"printing did not finish in {timeout:.0f} s"
        return False, f"the print process ended without an answer (exit code {proc.exitcode})"
    finally:
        proc.join(5)


def _print_here(path: str, printer: str = "") -> Tuple[bool, str]:
    import fitz
    import win32con
    import win32print
    import win32ui
    from PIL import Image, ImageWin

    printer = printer or win32print.GetDefaultPrinter()
    dc = win32ui.CreateDC()
    try:
        dc.CreatePrinterDC(printer)
    except Exception as e:
        # Over Remote Desktop the default is the client's printer, "<name> (redirected N)"; it
        # goes away or is renamed when the session reconnects ("Unable to open printer",
        # 2026-11-22). The same printer installed on this PC is the one to use then.
        local = local_printer_for(printer, [p[2] for p in win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)])
        if not local:
            return False, f"{printer}: {e}"
        printer = local
        dc.CreatePrinterDC(printer)
    try:
        area_w, area_h = dc.GetDeviceCaps(win32con.HORZRES), dc.GetDeviceCaps(win32con.VERTRES)
        with fitz.open(path) as doc:
            dc.StartDoc(os.path.basename(path))
            for page in doc:
                pix = page.get_pixmap(dpi=DPI)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                if (img.width > img.height) != (area_w > area_h):
                    img = img.rotate(90, expand=True)      # a landscape page on portrait paper
                dc.StartPage()
                ImageWin.Dib(img).draw(dc.GetHandleOutput(), fit_rect(img.width, img.height, area_w, area_h))
                dc.EndPage()
            dc.EndDoc()
        return True, f"{printer} (fitted to {area_w}x{area_h} px)"
    except Exception as e:
        try:
            dc.AbortDoc()
        except Exception:
            pass
        return False, f"{printer}: {e}"
    finally:
        dc.DeleteDC()
