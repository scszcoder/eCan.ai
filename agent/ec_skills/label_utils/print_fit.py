"""Print a PDF on a Windows printer, each page scaled to fit the printer's paper.

LibreOffice (``soffice --pt``) printed an A4 label sheet at its own size on a Letter
printer: enlarged and cut off at the bottom, losing the copy's product note (2026-11-18).
This renders each page and draws it through GDI into the printable area the printer
reports, keeping the page's proportions and centring it.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
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


_RUNNER = """import importlib, json, sys
sys.path.insert(0, {root!r})
with open({inp!r}, encoding="utf-8") as f:
    spec = json.load(f)
try:
    res = list(getattr(importlib.import_module(spec["module"]), spec["name"])(*spec["args"]))
except Exception as e:
    res = [False, f"{{type(e).__name__}}: {{e}}"]
with open({out!r}, "w", encoding="utf-8") as f:
    json.dump(res, f)
"""


def run_isolated(fn, *args, timeout: float = 180) -> Tuple[bool, str]:
    """fn(*args) in a fresh process; (False, why) when it fails, crashes or hangs.

    A plain subprocess, not multiprocessing: a spawned child re-imports eCan's main.py, which
    exits at once when it is not the main module, so every print "ended without an answer
    (exit code 0)" after waiting the whole timeout (2026-11-27). The packaged exe cannot run
    a script itself; it runs one named in ECAN_RUN_SCRIPT, as worker_placement does."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    with tempfile.TemporaryDirectory(prefix="ecan_isolated_") as tmp:
        inp, out, runner = (os.path.join(tmp, n) for n in ("in.json", "out.json", "run.py"))
        with open(inp, "w", encoding="utf-8") as f:
            json.dump({"module": fn.__module__, "name": fn.__qualname__, "args": list(args)}, f)
        with open(runner, "w", encoding="utf-8") as f:
            f.write(_RUNNER.format(root=root, inp=inp, out=out))
        env = dict(os.environ)
        if getattr(sys, "frozen", False):
            argv, env["ECAN_RUN_SCRIPT"] = [sys.executable], runner
        else:
            argv = [sys.executable, runner]
        try:
            proc = subprocess.run(argv, env=env, cwd=tmp, timeout=timeout, capture_output=True,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            return False, f"printing did not finish in {timeout:.0f} s"
        if not os.path.exists(out):
            return False, f"the print process ended without an answer (exit code {proc.returncode})"
        with open(out, encoding="utf-8") as f:
            return tuple(json.load(f))


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
