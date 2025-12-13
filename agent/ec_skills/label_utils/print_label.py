"""
Label printing and reformatting utilities.
Cross-platform support for Windows, macOS, and Linux.
"""
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
import asyncio
from enum import Enum
from typing import Optional
import time

from utils.lazy_import import lazy
from PIL import Image, ImageFont, ImageDraw
from concurrent.futures import ThreadPoolExecutor

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
import fitz


# ============================================================================
# Cross-platform print_labels function
# ============================================================================

class PrintStatus(Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class PrintResult:
    status: PrintStatus
    printed_files: list[str]
    failed_files: list[tuple[str, str]]  # (file_path, error_message)
    printer_used: str
    message: str


def get_system_platform() -> str:
    """Returns 'windows', 'darwin' (macOS), or 'linux'."""
    return platform.system().lower()


def get_available_printers() -> list[str]:
    """
    Get list of available printers on the system.
    Cross-platform: Windows, macOS, Linux.
    """
    system = get_system_platform()
    printers = []
    
    try:
        if system == "windows":
            import win32print
            printers = [p[2] for p in win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )]
        elif system in ("darwin", "linux"):
            # Use lpstat to list printers (CUPS)
            result = subprocess.run(
                ["lpstat", "-p"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line.startswith("printer "):
                        # Format: "printer PrinterName is idle..."
                        parts = line.split()
                        if len(parts) >= 2:
                            printers.append(parts[1])
    except Exception as e:
        logger.warning(f"[get_available_printers] Failed to enumerate printers: {e}")
    
    return printers


def get_default_printer() -> Optional[str]:
    """
    Get the system default printer.
    Cross-platform: Windows, macOS, Linux.
    """
    system = get_system_platform()
    
    try:
        if system == "windows":
            import win32print
            return win32print.GetDefaultPrinter()
        elif system in ("darwin", "linux"):
            # Use lpstat to get default printer (CUPS)
            result = subprocess.run(
                ["lpstat", "-d"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0 and ":" in result.stdout:
                # Format: "system default destination: PrinterName"
                return result.stdout.strip().split(":")[-1].strip()
    except Exception as e:
        logger.warning(f"[get_default_printer] Failed to get default printer: {e}")
    
    return None


def is_printer_available(printer_name: str) -> bool:
    """
    Check if a specific printer is available.
    Cross-platform: Windows, macOS, Linux.
    """
    if not printer_name:
        return False
    return printer_name in get_available_printers()


def _print_file_windows(file_path: str, printer_name: str, n_copies: int = 1) -> tuple[bool, str]:
    """
    Print a file on Windows.
    Supports PDF, images, and other printable formats.
    Uses win32api for shell printing or Ghostscript for silent PDF printing.
    """
    try:
        import win32print
        import win32api
        
        # Normalize path
        file_path = os.path.abspath(file_path)
        
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
        
        # Set printer if specified
        if printer_name:
            try:
                win32print.SetDefaultPrinter(printer_name)
            except Exception as e:
                return False, f"Failed to set printer '{printer_name}': {e}"
        
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # For PDFs, try Ghostscript first for silent printing, then fallback to shell
        if file_ext == ".pdf":
            gs_success, gs_msg = _print_pdf_ghostscript_windows(file_path, printer_name, n_copies)
            if gs_success:
                return True, gs_msg
            # Fallback to shell printing
            logger.debug(f"[_print_file_windows] Ghostscript failed, using shell print: {gs_msg}")
        
        # Shell print (opens default app and prints)
        for _ in range(n_copies):
            win32api.ShellExecute(0, "print", file_path, None, ".", 0)
        
        # Brief wait for print job to be queued
        time.sleep(2)
        return True, f"Print job sent for {file_path}"
        
    except ImportError:
        return False, "win32api/win32print not available. Install pywin32."
    except Exception as e:
        return False, f"Windows print error: {e}"


def _print_pdf_ghostscript_windows(file_path: str, printer_name: str, n_copies: int = 1) -> tuple[bool, str]:
    """
    Silent PDF printing using Ghostscript on Windows.
    Uses gswin64c.exe (console version) for silent operation.
    """
    # Find Ghostscript console executable (gswin64c.exe for silent printing)
    # Search common installation paths
    gs_exe = None
    
    # Check Program Files for various GS versions
    gs_base_dirs = [
        r"C:\Program Files\gs",
        r"C:\Program Files (x86)\gs",
    ]
    
    for base_dir in gs_base_dirs:
        if os.path.exists(base_dir):
            # List version directories and find the console executable
            try:
                for version_dir in sorted(os.listdir(base_dir), reverse=True):  # Newest first
                    console_exe = os.path.join(base_dir, version_dir, "bin", "gswin64c.exe")
                    if os.path.exists(console_exe):
                        gs_exe = console_exe
                        break
                    # Try 32-bit version
                    console_exe = os.path.join(base_dir, version_dir, "bin", "gswin32c.exe")
                    if os.path.exists(console_exe):
                        gs_exe = console_exe
                        break
            except OSError:
                pass
        if gs_exe:
            break
    
    # Also check if gswin64c is in PATH
    if not gs_exe:
        gs_exe = shutil.which("gswin64c") or shutil.which("gswin32c")
    
    if not gs_exe:
        return False, "Ghostscript not found"
    
    logger.debug(f"[_print_pdf_ghostscript_windows] Using Ghostscript: {gs_exe}")
    
    try:
        cmd = [
            gs_exe,
            "-dPrinted",
            "-dNoCancel",
            "-dBATCH",
            "-dNOPAUSE",
            "-dNOSAFER",
            "-q",
            "-dFitPage",
            f"-dNumCopies={n_copies}",
            "-sDEVICE=mswinpr2",
        ]
        
        # Add printer output - no extra quotes needed, subprocess handles it
        if printer_name:
            cmd.append(f"-sOutputFile=%printer%{printer_name}")
        
        cmd.append(file_path)
        
        logger.debug(f"[_print_pdf_ghostscript_windows] Command: {cmd}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        
        if result.returncode == 0:
            return True, f"Printed via Ghostscript: {file_path}"
        else:
            return False, f"Ghostscript error (code {result.returncode}): {result.stderr or result.stdout}"
            
    except subprocess.TimeoutExpired:
        return False, "Ghostscript print timeout"
    except Exception as e:
        return False, f"Ghostscript error: {e}"


def _print_file_unix(file_path: str, printer_name: str, n_copies: int = 1) -> tuple[bool, str]:
    """
    Print a file on macOS or Linux using CUPS (lpr command).
    Works with most printers: laser, inkjet, thermal, USB, network, Bluetooth.
    """
    try:
        file_path = os.path.abspath(file_path)
        
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
        
        # Check if lpr is available
        if not shutil.which("lpr"):
            return False, "lpr command not found. Ensure CUPS is installed."
        
        # Build lpr command
        cmd = ["lpr"]
        
        if printer_name:
            cmd.extend(["-P", printer_name])
        
        if n_copies > 1:
            cmd.extend(["-#", str(n_copies)])
        
        # Add options for better compatibility with label printers
        # -o fit-to-page: scale to fit page
        # -o media=Custom: for custom label sizes (optional)
        cmd.extend(["-o", "fit-to-page"])
        
        cmd.append(file_path)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return True, f"Print job sent: {file_path}"
        else:
            return False, f"lpr error: {result.stderr}"
            
    except subprocess.TimeoutExpired:
        return False, "Print command timeout"
    except Exception as e:
        return False, f"Unix print error: {e}"


def print_file(file_path: str, printer_name: Optional[str] = None, n_copies: int = 1) -> tuple[bool, str]:
    """
    Print a single file to the specified printer.
    Cross-platform: Windows, macOS, Linux.
    
    Args:
        file_path: Path to the file to print (PDF, image, etc.)
        printer_name: Target printer name. If None, uses system default.
        n_copies: Number of copies to print.
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    system = get_system_platform()
    
    # Use default printer if not specified
    if not printer_name:
        printer_name = get_default_printer()
        if not printer_name:
            return False, "No printer specified and no default printer found"
        else:
            logger.info(f"[print_file] Using default printer: {printer_name}")
    
    # Verify printer exists
    if not is_printer_available(printer_name):
        available = get_available_printers()
        return False, f"Printer '{printer_name}' not found. Available: {available}"
    
    logger.info(f"[print_file] Printing '{file_path}' to '{printer_name}' (copies: {n_copies})")
    
    if system == "windows":
        return _print_file_windows(file_path, printer_name, n_copies)
    elif system in ("darwin", "linux"):
        return _print_file_unix(file_path, printer_name, n_copies)
    else:
        return False, f"Unsupported platform: {system}"


def print_labels_util(
    files: list[str],
    printer_name: Optional[str] = None,
    n_copies: int = 1,
    stop_on_error: bool = False
) -> PrintResult:
    """
    Print multiple label files to the specified printer.
    Cross-platform: Windows, macOS, Linux.
    Compatible with laser, inkjet, and thermal printers via USB, LAN, or Bluetooth.
    
    Args:
        files: List of file paths to print (PDF, PNG, JPG, etc.)
        printer_name: Target printer name. If None, uses system default.
        n_copies: Number of copies for each file.
        stop_on_error: If True, stop printing on first error.
    
    Returns:
        PrintResult with status, printed files, failed files, and message.
    
    Example:
        result = print_labels_util(
            files=["/path/to/label1.pdf", "/path/to/label2.pdf"],
            printer_name="DYMO_LabelWriter_450",
            n_copies=1
        )
        if result.status == PrintStatus.SUCCESS:
            print(f"All {len(result.printed_files)} labels printed!")
    """
    if not files:
        return PrintResult(
            status=PrintStatus.FAILED,
            printed_files=[],
            failed_files=[],
            printer_used=printer_name or "",
            message="No files provided"
        )
    
    # Resolve printer
    actual_printer = printer_name or get_default_printer()
    if not actual_printer:
        return PrintResult(
            status=PrintStatus.FAILED,
            printed_files=[],
            failed_files=[(f, "No printer available") for f in files],
            printer_used="",
            message="No printer specified and no default printer found"
        )
    
    # Verify printer
    if not is_printer_available(actual_printer):
        available = get_available_printers()
        return PrintResult(
            status=PrintStatus.FAILED,
            printed_files=[],
            failed_files=[(f, f"Printer not found") for f in files],
            printer_used=actual_printer,
            message=f"Printer '{actual_printer}' not found. Available: {available}"
        )
    
    printed_files: list[str] = []
    failed_files: list[tuple[str, str]] = []
    
    logger.info(f"[print_labels] Starting print job: {len(files)} files to '{actual_printer}'")
    
    for file_path in files:
        success, msg = print_file(file_path, actual_printer, n_copies)
        
        if success:
            printed_files.append(file_path)
            logger.debug(f"[print_labels] Printed: {file_path}")
        else:
            failed_files.append((file_path, msg))
            logger.warning(f"[print_labels] Failed: {file_path} - {msg}")
            
            if stop_on_error:
                break
    
    # Determine overall status
    if len(printed_files) == len(files):
        status = PrintStatus.SUCCESS
        message = f"Successfully printed all {len(printed_files)} files"
    elif len(printed_files) > 0:
        status = PrintStatus.PARTIAL
        message = f"Printed {len(printed_files)}/{len(files)} files. {len(failed_files)} failed."
    else:
        status = PrintStatus.FAILED
        message = f"Failed to print any files. {len(failed_files)} errors."
    
    logger.info(f"[print_labels] {message}")
    
    return PrintResult(
        status=status,
        printed_files=printed_files,
        failed_files=failed_files,
        printer_used=actual_printer,
        message=message
    )


async def print_labels_async(
    files: list[str],
    printer_name: Optional[str] = None,
    n_copies: int = 1,
    stop_on_error: bool = False
) -> PrintResult:
    """
    Async version of print_labels_util.
    Runs the synchronous print operation in a thread pool.
    """
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(
            pool,
            lambda: print_labels_util(files, printer_name, n_copies, stop_on_error)
        )
    return result


# ============================================================================
# Label Reformatting Functions
# ============================================================================

# Standard DPI for PDF rendering
DEFAULT_DPI = 150
DEFAULT_MARGIN_INCHES = 0.25  # 1/4 inch default margin


@dataclass
class LabelSheetConfig:
    """Configuration for label sheet layout."""
    sheet_width_inches: float
    sheet_height_inches: float
    label_width_inches: float
    label_height_inches: float
    rows_per_sheet: int
    cols_per_sheet: int
    row_pitch_inches: float  # center-to-center distance between rows
    col_pitch_inches: float  # center-to-center distance between columns
    top_margin_inches: float
    left_margin_inches: float
    orientation: str  # 'landscape' or 'portrait'
    dpi: int = DEFAULT_DPI
    
    @property
    def sheet_width_px(self) -> int:
        return int(self.sheet_width_inches * self.dpi)
    
    @property
    def sheet_height_px(self) -> int:
        return int(self.sheet_height_inches * self.dpi)
    
    @property
    def label_width_px(self) -> int:
        return int(self.label_width_inches * self.dpi)
    
    @property
    def label_height_px(self) -> int:
        return int(self.label_height_inches * self.dpi)
    
    @property
    def top_margin_px(self) -> int:
        return int(self.top_margin_inches * self.dpi)
    
    @property
    def left_margin_px(self) -> int:
        return int(self.left_margin_inches * self.dpi)
    
    @property
    def row_pitch_px(self) -> int:
        return int(self.row_pitch_inches * self.dpi)
    
    @property
    def col_pitch_px(self) -> int:
        return int(self.col_pitch_inches * self.dpi)
    
    @property
    def labels_per_sheet(self) -> int:
        return self.rows_per_sheet * self.cols_per_sheet


def parse_dimension_string(dim_str: str) -> tuple[float, float]:
    """
    Parse dimension string like 'D8.5X5.5' or '8.5x5.5' to (width, height).
    Returns (width_inches, height_inches).
    """
    # Remove leading 'D' if present
    dim_str = dim_str.upper().lstrip('D')
    
    # Split by 'X'
    parts = dim_str.split('X')
    if len(parts) != 2:
        raise ValueError(f"Invalid dimension format: {dim_str}. Expected format: 'D8.5X5.5' or '8.5x5.5'")
    
    try:
        width = float(parts[0])
        height = float(parts[1])
        return width, height
    except ValueError:
        raise ValueError(f"Invalid dimension values in: {dim_str}")


def extract_label_from_pdf_page(
    page,
    target_width_px: int,
    target_height_px: int,
    orientation: str = "landscape",
    dpi: int = DEFAULT_DPI
) -> Optional[Image.Image]:
    """
    Extract the label content from a PDF page and resize to target dimensions.
    
    Args:
        page: fitz page object
        target_width_px: Target width in pixels
        target_height_px: Target height in pixels
        orientation: 'landscape' or 'portrait'
        dpi: Rendering DPI
    
    Returns:
        PIL Image of the extracted and resized label, or None on error.
    """
    import cv2
    
    try:
        # Render page to pixmap at target DPI
        mat = fitz.Matrix(dpi / 72, dpi / 72)  # Scale from 72 DPI to target DPI
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img_array = lazy.np.array(img)
        
        # Find content bounds by detecting non-white pixels
        # Convert to grayscale
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        
        # Threshold to find non-white areas (content)
        # White is ~255, so anything below 250 is considered content
        _, thresh = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)
        
        # Find bounding box of all non-white content
        coords = cv2.findNonZero(thresh)
        
        if coords is not None and len(coords) > 0:
            x, y, w, h = cv2.boundingRect(coords)
            
            # Add padding around content
            padding = 10
            x = max(0, x - padding)
            y = max(0, y - padding)
            w = min(img_array.shape[1] - x, w + 2 * padding)
            h = min(img_array.shape[0] - y, h + 2 * padding)
            
            cropped = img_array[y:y+h, x:x+w]
            logger.debug(f"[extract_label_from_pdf_page] Cropped to content: {w}x{h} from {img_array.shape[1]}x{img_array.shape[0]}")
        else:
            # No content found, use the whole image
            logger.warning("[extract_label_from_pdf_page] No content found, using full page")
            cropped = img_array
        
        # Determine if rotation is needed based on orientation
        crop_h, crop_w = cropped.shape[:2]
        is_landscape = crop_w > crop_h
        want_landscape = orientation.lower() == "landscape"
        
        if is_landscape != want_landscape:
            # Rotate 90 degrees
            cropped = cv2.rotate(cropped, cv2.ROTATE_90_CLOCKWISE)
            logger.debug(f"[extract_label_from_pdf_page] Rotated to match orientation: {orientation}")
        
        # Resize to target dimensions while maintaining aspect ratio
        crop_h, crop_w = cropped.shape[:2]
        
        # Calculate scale to fit within target while maintaining aspect ratio
        scale_w = target_width_px / crop_w
        scale_h = target_height_px / crop_h
        scale = min(scale_w, scale_h)  # Use smaller scale to fit within bounds
        
        new_w = int(crop_w * scale)
        new_h = int(crop_h * scale)
        
        resized = cv2.resize(cropped, (new_w, new_h), interpolation=cv2.INTER_AREA)
        
        # Create white background at target size and center the resized content
        result = lazy.np.full((target_height_px, target_width_px, 3), 255, dtype=lazy.np.uint8)
        
        # Calculate position to center
        x_offset = (target_width_px - new_w) // 2
        y_offset = (target_height_px - new_h) // 2
        
        result[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
        
        logger.debug(f"[extract_label_from_pdf_page] Final size: {target_width_px}x{target_height_px}, content: {new_w}x{new_h}")
        
        return Image.fromarray(result)
        
    except Exception as e:
        logger.error(f"[extract_label_from_pdf_page] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def create_label_sheet(
    labels: list[Image.Image],
    config: LabelSheetConfig,
    background_color: tuple[int, int, int] = (255, 255, 255)
) -> Image.Image:
    """
    Arrange multiple labels on a single sheet.
    
    Args:
        labels: List of PIL Images (labels to place on sheet)
        config: LabelSheetConfig with layout parameters
        background_color: RGB tuple for sheet background
    
    Returns:
        PIL Image of the composed sheet.
    """
    # Create blank sheet
    sheet = Image.new("RGB", (config.sheet_width_px, config.sheet_height_px), background_color)
    
    label_idx = 0
    for row in range(config.rows_per_sheet):
        for col in range(config.cols_per_sheet):
            if label_idx >= len(labels):
                break
            
            label = labels[label_idx]
            
            # Calculate position for this label
            # Using pitch for center-to-center, so we offset by half label size
            if config.rows_per_sheet == 1 and config.cols_per_sheet == 1:
                # Single label per sheet - center it
                x = (config.sheet_width_px - config.label_width_px) // 2
                y = (config.sheet_height_px - config.label_height_px) // 2
            else:
                # Multi-label sheet - use margins and pitch
                x = config.left_margin_px + col * config.col_pitch_px
                y = config.top_margin_px + row * config.row_pitch_px
            
            # Resize label if needed
            if label.size != (config.label_width_px, config.label_height_px):
                label = label.resize((config.label_width_px, config.label_height_px), Image.Resampling.LANCZOS)
            
            # Paste label onto sheet
            sheet.paste(label, (x, y))
            label_idx += 1
    
    return sheet


def find_largest_white_region(img_array, min_area: int = 1000, text_width: int = 100, text_height: int = 20) -> Optional[tuple[int, int, int, int]]:
    """
    Find the largest white rectangular region in an image that can fit the text.
    Uses a scanning approach to find white rectangular areas within the content.
    
    Args:
        img_array: numpy array of the image (RGB or grayscale)
        min_area: Minimum area in pixels for a valid white region
        text_width: Width of text to fit
        text_height: Height of text to fit
    
    Returns:
        Tuple of (x, y, width, height) of the largest white region, or None if not found.
    """
    import cv2
    
    img_h, img_w = img_array.shape[:2]
    
    # Convert to grayscale if needed
    if len(img_array.shape) == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_array
    
    # First, find the content bounding box (non-white area)
    _, content_mask = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)
    content_coords = cv2.findNonZero(content_mask)
    
    if content_coords is None:
        logger.debug("[find_largest_white_region] No content found in image")
        return None
    
    # Get content bounding box
    cx, cy, cw, ch = cv2.boundingRect(content_coords)
    logger.debug(f"[find_largest_white_region] Content bounds: ({cx}, {cy}, {cw}x{ch})")
    
    # Create a binary mask where white pixels are 1
    _, white_mask = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY)
    
    # Apply mild erosion to the INVERSE (content) to shrink thin lines
    # This effectively expands white regions by removing thin content elements
    content_binary = cv2.bitwise_not(white_mask)  # Invert: content=255, white=0
    
    # Mild erosion: 3x3 kernel, 1 iteration (removes ~3 pixel thin lines)
    erosion_kernel = lazy.np.ones((3, 3), lazy.np.uint8)
    eroded_content = cv2.erode(content_binary, erosion_kernel, iterations=1)
    
    # Invert back: white areas are now 255
    white_mask = cv2.bitwise_not(eroded_content)
    
    logger.debug(f"[find_largest_white_region] Applied mild erosion to expand white regions")
    
    white_mask = white_mask // 255  # Convert to 0/1
    
    # Use integral image for fast rectangle sum computation
    integral = cv2.integral(white_mask)
    
    # Scan for white rectangles that can fit the text
    # We need at least text_width x text_height of white space
    min_w = text_width + 20  # Add padding
    min_h = text_height + 10
    
    best_region = None
    best_area = 0
    
    # Scan with a step size for efficiency
    step = 20
    
    # Only scan within the content area (not the outer margins)
    scan_margin = 30  # Pixels inside content bounds
    scan_x1 = cx + scan_margin
    scan_y1 = cy + scan_margin
    scan_x2 = cx + cw - scan_margin
    scan_y2 = cy + ch - scan_margin
    
    for y in range(scan_y1, scan_y2 - min_h, step):
        for x in range(scan_x1, scan_x2 - min_w, step):
            # Try expanding from this point to find largest white rectangle
            for h in range(min_h, min(scan_y2 - y, 200), step):
                for w in range(min_w, min(scan_x2 - x, 400), step):
                    # Calculate sum of white pixels in this rectangle using integral image
                    # integral[y2+1, x2+1] - integral[y1, x2+1] - integral[y2+1, x1] + integral[y1, x1]
                    x1, y1, x2, y2 = x, y, x + w, y + h
                    white_sum = (integral[y2, x2] - integral[y1, x2] - integral[y2, x1] + integral[y1, x1])
                    total_pixels = w * h
                    
                    # Check if at least 95% of pixels are white
                    if white_sum >= total_pixels * 0.95:
                        area = w * h
                        if area > best_area:
                            best_area = area
                            best_region = (x, y, w, h)
    
    if best_region:
        logger.debug(f"[find_largest_white_region] Best white region: {best_region} (area: {best_area})")
    else:
        logger.debug("[find_largest_white_region] No suitable white region found that fits text")
    
    return best_region


def add_note_to_label(
    label_img: Image.Image,
    note_text: str,
    font_size: int = 24,
    font_path: Optional[str] = None,
    position: str = "auto"  # 'auto', 'bottom', 'top', 'center'
) -> Image.Image:
    """
    Add note text to a label image.
    
    Args:
        label_img: PIL Image of the label
        note_text: Text to add
        font_size: Font size in points
        font_path: Path to TTF font file (optional)
        position: Where to place the text:
            - 'auto': Find largest white region and place text there
            - 'bottom': Place at bottom center
            - 'top': Place at top center
            - 'center': Place at image center
    
    Returns:
        PIL Image with text added.
    """
    if not note_text:
        logger.debug("[add_note_to_label] No note text provided, returning original image")
        return label_img
    
    logger.debug(f"[add_note_to_label] Adding note: '{note_text}' at {position}, font_size={font_size}")
    
    img = label_img.copy()
    draw = ImageDraw.Draw(img)
    
    # Load font
    try:
        if font_path and os.path.exists(font_path):
            font = ImageFont.truetype(font_path, font_size)
            logger.debug(f"[add_note_to_label] Using custom font: {font_path}")
        else:
            font = ImageFont.truetype("arial.ttf", font_size)
            logger.debug("[add_note_to_label] Using arial.ttf")
    except Exception as e:
        logger.warning(f"[add_note_to_label] Font loading failed ({e}), using default font")
        font = ImageFont.load_default()
    
    # Get text bounding box
    bbox = draw.textbbox((0, 0), note_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    img_width, img_height = img.size
    
    # Calculate position based on mode
    if position == "auto":
        # Try to find the largest white region that can fit the text
        img_array = lazy.np.array(img)
        white_region = find_largest_white_region(
            img_array, 
            min_area=text_width * text_height,
            text_width=text_width,
            text_height=text_height
        )
        
        if white_region:
            rx, ry, rw, rh = white_region
            # Center text within the white region
            x = rx + (rw - text_width) // 2
            y = ry + (rh - text_height) // 2
            logger.debug(f"[add_note_to_label] Found white region at ({rx}, {ry}, {rw}x{rh}), placing text at ({x}, {y})")
        else:
            # Fallback to bottom if no suitable white region found
            logger.debug("[add_note_to_label] No suitable white region found, falling back to bottom")
            x = (img_width - text_width) // 2
            y = img_height - text_height - 20
    else:
        # Fixed position modes
        x = (img_width - text_width) // 2  # Center horizontally
        
        if position == "bottom":
            y = img_height - text_height - 20
        elif position == "top":
            y = 20
        else:  # center
            y = (img_height - text_height) // 2
    
    logger.debug(f"[add_note_to_label] Text position: ({x}, {y}), size: {text_width}x{text_height}")
    
    # Draw text with slight shadow for visibility
    draw.text((x + 2, y + 2), note_text, font=font, fill=(128, 128, 128))
    draw.text((x, y), note_text, font=font, fill=(0, 0, 0))
    
    return img


@dataclass
class ReformatResult:
    """Result of label reformatting operation."""
    success: bool
    output_files: list[str]
    backup_files: list[str]
    input_count: int
    output_count: int
    message: str


@dataclass
class LabelInputFile:
    """Input file specification with per-file note settings."""
    file_name: str
    added_note_text: str = ""
    added_note_font: Optional[str] = None
    added_note_size: int = 24


def reformat_labels_util(
    in_files: list[dict],
    out_dir: Optional[str] = None,
    sheet_width: float = 8.5,
    sheet_height: float = 11.0,
    label_width: float = 8.5,
    label_height: float = 5.5,
    label_orientation: str = "landscape",
    label_rows_per_sheet: int = 2,
    label_cols_per_sheet: int = 1,
    label_rows_pitch: Optional[float] = None,
    label_cols_pitch: Optional[float] = None,
    top_side_margin: Optional[float] = None,
    left_side_margin: Optional[float] = None,
    add_backup: bool = True,
    dpi: int = DEFAULT_DPI
) -> ReformatResult:
    """
    Reformat label PDFs to fit on multi-label sheets.
    
    This function takes individual label PDFs and arranges them onto sheets
    that may contain multiple labels (e.g., 4 labels per sheet).
    
    Args:
        in_files: List of input file specifications, each a dict with:
            - file_name (str): Path to the PDF file
            - added_note_text (str, optional): Text to add to backup copy
            - added_note_font (str, optional): Path to TTF font file
            - added_note_size (int, optional): Font size for note (default: 24)
        out_dir: Output directory (defaults to same as first input file)
        sheet_width: Sheet width in inches (e.g., 8.5 for letter)
        sheet_height: Sheet height in inches (e.g., 11.0 for letter)
        label_width: Individual label width in inches
        label_height: Individual label height in inches
        label_orientation: 'landscape' or 'portrait'
        label_rows_per_sheet: Number of label rows per sheet
        label_cols_per_sheet: Number of label columns per sheet
        label_rows_pitch: Vertical distance between label centers (inches). Default: auto-calculated
        label_cols_pitch: Horizontal distance between label centers (inches). Default: auto-calculated
        top_side_margin: Top margin in inches. Default: 0.25"
        left_side_margin: Left margin in inches. Default: 0.25"
        add_backup: If True, create backup copies with note text
        dpi: Output DPI
    
    Returns:
        ReformatResult with output file paths and status.
    
    Example:
        # 4 labels per sheet (2x2 layout) with per-file notes
        result = reformat_labels_util(
            in_files=[
                {"file_name": "label1.pdf", "added_note_text": "Order #123"},
                {"file_name": "label2.pdf", "added_note_text": "Order #456"},
            ],
            sheet_width=8.5,
            sheet_height=11.0,
            label_width=4.0,
            label_height=2.5,
            label_rows_per_sheet=2,
            label_cols_per_sheet=2
        )
        # Result: 1 output file with all labels arranged on sheets
    """
    if not in_files:
        return ReformatResult(
            success=False,
            output_files=[],
            backup_files=[],
            input_count=0,
            output_count=0,
            message="No input files provided"
        )
    
    # Use dimensions directly (already floats)
    sheet_w = sheet_width
    sheet_h = sheet_height
    label_w = label_width
    label_h = label_height
    
    # Validate dimensions
    if sheet_w <= 0 or sheet_h <= 0 or label_w <= 0 or label_h <= 0:
        return ReformatResult(
            success=False,
            output_files=[],
            backup_files=[],
            input_count=len(in_files),
            output_count=0,
            message="Invalid dimensions: all dimensions must be positive"
        )
    
    # Apply defaults for margins (1/4 inch)
    if top_side_margin is None or top_side_margin <= 0:
        top_side_margin = DEFAULT_MARGIN_INCHES
    if left_side_margin is None or left_side_margin <= 0:
        left_side_margin = DEFAULT_MARGIN_INCHES
    
    # Auto-calculate pitch if not provided
    labels_per_sheet = label_rows_per_sheet * label_cols_per_sheet
    
    if label_rows_pitch is None or label_rows_pitch <= 0:
        if label_rows_per_sheet > 1:
            # Calculate pitch to evenly distribute labels
            available_height = sheet_h - 2 * top_side_margin
            label_rows_pitch = available_height / label_rows_per_sheet
        else:
            label_rows_pitch = label_h
    
    if label_cols_pitch is None or label_cols_pitch <= 0:
        if label_cols_per_sheet > 1:
            available_width = sheet_w - 2 * left_side_margin
            label_cols_pitch = available_width / label_cols_per_sheet
        else:
            label_cols_pitch = label_w
    
    # Create config
    config = LabelSheetConfig(
        sheet_width_inches=sheet_w,
        sheet_height_inches=sheet_h,
        label_width_inches=label_w,
        label_height_inches=label_h,
        rows_per_sheet=label_rows_per_sheet,
        cols_per_sheet=label_cols_per_sheet,
        row_pitch_inches=label_rows_pitch,
        col_pitch_inches=label_cols_pitch,
        top_margin_inches=top_side_margin,
        left_margin_inches=left_side_margin,
        orientation=label_orientation,
        dpi=dpi
    )
    
    logger.info(f"[reformat_labels] Config: {labels_per_sheet} labels/sheet, "
                f"sheet={sheet_w}x{sheet_h}\", label={label_w}x{label_h}\"")
    
    # Determine output directory
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    else:
        # Get first file path from in_files
        first_file = in_files[0].get("file_name", "") if isinstance(in_files[0], dict) else str(in_files[0])
        out_dir = os.path.dirname(first_file) or "."
    
    # Extract all labels from input PDFs
    all_labels: list[Image.Image] = []
    
    for file_spec in in_files:
        # Parse file specification (dict with file_name, added_note_text, etc.)
        if isinstance(file_spec, dict):
            pdf_path = file_spec.get("file_name", "")
            note_text = file_spec.get("added_note_text", "")
            note_font = file_spec.get("added_note_font")
            note_size = file_spec.get("added_note_size", 24)
        else:
            # Fallback for plain string paths
            pdf_path = str(file_spec)
            note_text = ""
            note_font = None
            note_size = 24
        
        if not pdf_path or not os.path.exists(pdf_path):
            logger.warning(f"[reformat_labels] File not found: {pdf_path}")
            continue
        
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(doc.page_count):
                page = doc.load_page(page_num)
                label_img = extract_label_from_pdf_page(
                    page,
                    config.label_width_px,
                    config.label_height_px,
                    config.orientation,
                    config.dpi
                )
                if label_img:
                    all_labels.append(label_img)
                    logger.debug(f"[reformat_labels] Extracted label {len(all_labels)} from {pdf_path} page {page_num+1}")
                    
                    # If add_backup is True, add a duplicate with per-file note
                    if add_backup:
                        logger.debug(f"[reformat_labels] Adding backup copy with note: '{note_text}'")
                        backup_label = add_note_to_label(
                            label_img,
                            note_text,
                            note_size,
                            note_font
                        )
                        all_labels.append(backup_label)
            doc.close()
        except Exception as e:
            logger.error(f"[reformat_labels] Error processing {pdf_path}: {e}")
    
    if not all_labels:
        return ReformatResult(
            success=False,
            output_files=[],
            backup_files=[],
            input_count=len(in_files),
            output_count=0,
            message="No labels could be extracted from input files"
        )
    
    # Arrange labels onto sheets
    # When add_backup=True, each input label becomes 2 labels (original + backup)
    # so they fill row-by-row on the same sheet
    output_files: list[str] = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Calculate actual labels per input (1 if no backup, 2 if backup)
    labels_per_input = 2 if add_backup else 1
    actual_input_labels = len(all_labels) // labels_per_input
    
    logger.debug(f"[reformat_labels] Total labels to arrange: {len(all_labels)} "
                 f"({actual_input_labels} inputs x {labels_per_input})")
    
    # Process labels into sheets
    for sheet_idx in range(0, len(all_labels), labels_per_sheet):
        sheet_labels = all_labels[sheet_idx:sheet_idx + labels_per_sheet]
        sheet_img = create_label_sheet(sheet_labels, config)
        
        # Save as PDF
        out_filename = f"labels_sheet_{sheet_idx // labels_per_sheet + 1}_{timestamp}.pdf"
        out_path = os.path.join(out_dir, out_filename)
        sheet_img.save(out_path, "PDF", resolution=dpi)
        output_files.append(out_path)
        logger.debug(f"[reformat_labels] Created: {out_path} with {len(sheet_labels)} labels")
    
    message = (f"Reformatted {actual_input_labels} labels from {len(in_files)} files "
               f"into {len(output_files)} sheets ({labels_per_sheet} labels/sheet)")
    if add_backup:
        message += " (with backup copies)"
    
    logger.info(f"[reformat_labels] {message}")
    
    return ReformatResult(
        success=True,
        output_files=output_files,
        backup_files=[],  # Backups are now on same sheet, not separate files
        input_count=len(in_files),
        output_count=len(output_files),
        message=message
    )


async def reformat_labels_async(
    in_files: list[dict],
    out_dir: Optional[str] = None,
    sheet_width: float = 8.5,
    sheet_height: float = 11.0,
    label_width: float = 8.5,
    label_height: float = 5.5,
    label_orientation: str = "landscape",
    label_rows_per_sheet: int = 2,
    label_cols_per_sheet: int = 1,
    label_rows_pitch: Optional[float] = None,
    label_cols_pitch: Optional[float] = None,
    top_side_margin: Optional[float] = None,
    left_side_margin: Optional[float] = None,
    add_backup: bool = True,
    dpi: int = DEFAULT_DPI
) -> ReformatResult:
    """Async version of reformat_labels_util."""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(
            pool,
            lambda: reformat_labels_util(
                in_files=in_files,
                out_dir=out_dir,
                sheet_width=sheet_width,
                sheet_height=sheet_height,
                label_width=label_width,
                label_height=label_height,
                label_orientation=label_orientation,
                label_rows_per_sheet=label_rows_per_sheet,
                label_cols_per_sheet=label_cols_per_sheet,
                label_rows_pitch=label_rows_pitch,
                label_cols_pitch=label_cols_pitch,
                top_side_margin=top_side_margin,
                left_side_margin=left_side_margin,
                add_backup=add_backup,
                dpi=dpi
            )
        )
    return result


# ============================================================================
# MCP Tool Wrappers
# ============================================================================


async def reformat_labels(mainwin, args):  # type: ignore
    """
    MCP tool wrapper for reformat_labels_util.
    Reformats label PDFs to fit on multi-label sheets.
    
    Input args (from LabelsReformatAction):
        - in_files: list of input file specs, each with:
            - file_name: PDF file path
            - added_note_text: note text for backup (optional)
            - added_note_font: font path (optional)
            - added_note_size: font size (optional, default 24)
        - out_dir: output directory (optional)
        - sheet_width: sheet width in inches (default 8.5)
        - sheet_height: sheet height in inches (default 11.0)
        - label_width: label width in inches
        - label_height: label height in inches
        - label_orientation: 'landscape' or 'portrait'
        - label_rows_per_sheet: number of rows
        - label_cols_per_sheet: number of columns
        - label_rows_pitch: row pitch in inches (optional, auto-calculated if <= 0)
        - label_cols_pitch: column pitch in inches (optional, auto-calculated if <= 0)
        - top_side_margin: top margin in inches (optional, default 0.25)
        - left_side_margin: left margin in inches (optional, default 0.25)
        - add_backup: create backup copies with notes
    """
    from mcp.types import TextContent
    
    try:
        input_data = args.get("input", args)
        logger.debug(f"[reformat_labels] Starting with input: {input_data}")
        
        # Extract in_files - list of dicts with file_name and note settings
        in_files = input_data.get("in_files", [])
        if not in_files:
            # Fallback: check for legacy in_file_names parameter
            legacy_files = input_data.get("in_file_names", [])
            if isinstance(legacy_files, str):
                legacy_files = [f.strip() for f in legacy_files.split(",") if f.strip()]
            # Convert to new format
            in_files = [{"file_name": f} for f in legacy_files]
        
        out_dir = input_data.get("out_dir", input_data.get("out_file_names", None))
        if out_dir and os.path.isfile(out_dir):
            out_dir = os.path.dirname(out_dir)
        
        # Get dimensions directly as floats
        sheet_width = float(input_data.get("sheet_width", 8.5))
        sheet_height = float(input_data.get("sheet_height", 11.0))
        label_width = float(input_data.get("label_width", 8.5))
        label_height = float(input_data.get("label_height", 5.5))
        
        label_orientation = input_data.get("label_orientation", "landscape")
        label_rows_per_sheet = int(input_data.get("label_rows_per_sheet", 2))
        label_cols_per_sheet = int(input_data.get("label_cols_per_sheet", 1))
        
        # Optional pitch values (None means auto-calculate)
        label_rows_pitch = input_data.get("label_rows_pitch")
        if label_rows_pitch is not None and label_rows_pitch > 0:
            label_rows_pitch = float(label_rows_pitch)
        else:
            label_rows_pitch = None
            
        label_cols_pitch = input_data.get("label_cols_pitch")
        if label_cols_pitch is not None and label_cols_pitch > 0:
            label_cols_pitch = float(label_cols_pitch)
        else:
            label_cols_pitch = None
        
        # Optional margin values (None means use default 0.25")
        top_side_margin = input_data.get("top_side_margin")
        if top_side_margin is not None and top_side_margin > 0:
            top_side_margin = float(top_side_margin)
        else:
            top_side_margin = None
            
        left_side_margin = input_data.get("left_side_margin")
        if left_side_margin is not None and left_side_margin > 0:
            left_side_margin = float(left_side_margin)
        else:
            left_side_margin = None
        
        add_backup = input_data.get("add_backup", True)
        
        # Call the utility function
        result = reformat_labels_util(
            in_files=in_files,
            out_dir=out_dir,
            sheet_width=sheet_width,
            sheet_height=sheet_height,
            label_width=label_width,
            label_height=label_height,
            label_orientation=label_orientation,
            label_rows_per_sheet=label_rows_per_sheet,
            label_cols_per_sheet=label_cols_per_sheet,
            label_rows_pitch=label_rows_pitch,
            label_cols_pitch=label_cols_pitch,
            top_side_margin=top_side_margin,
            left_side_margin=left_side_margin,
            add_backup=add_backup
        )
        
        msg = result.message
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {
            "success": result.success,
            "output_files": result.output_files,
            "backup_files": result.backup_files,
            "input_count": result.input_count,
            "output_count": result.output_count
        }
        logger.info(f"[reformat_labels] {msg}")
        return [tool_result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorReformatLabels")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def print_labels(mainwin, args):  # type: ignore
    """
    MCP tool wrapper for print_labels_util.
    Prints label files to a specified printer.
    
    Input args (from FilesPrintAction):
        - file_names: list of file paths to print (or comma-separated string)
        - printer: printer name (optional, uses default if not specified)
        - n_copies: number of copies (default 1)
    """
    from mcp.types import TextContent
    
    try:
        input_data = args.get("input", args)
        logger.debug(f"[print_labels] Starting with input: {input_data}")
        
        # Extract parameters from input
        file_names = input_data.get("file_names", [])
        if isinstance(file_names, str):
            # Handle comma-separated string or single file
            file_names = [f.strip() for f in file_names.split(",") if f.strip()]
        
        printer_name = input_data.get("printer", None)
        if printer_name == "":
            printer_name = None
            
        n_copies = int(input_data.get("n_copies", 1))
        
        # Call the utility function
        result = print_labels_util(
            files=file_names,
            printer_name=printer_name,
            n_copies=n_copies,
            stop_on_error=False
        )
        
        msg = result.message
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {
            "status": result.status.value,
            "printed_files": result.printed_files,
            "failed_files": result.failed_files,
            "printer_used": result.printer_used
        }
        logger.info(f"[print_labels] {msg}")
        return [tool_result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorPrintLabels")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


# ============================================================================
# MCP Tool Schema Functions
# ============================================================================

def add_print_labels_tool_schema(tool_schemas):
    """Add print_labels tool schema to the MCP tool schemas list."""
    import mcp.types as types

    tool_schema = types.Tool(
        name="print_labels",
        description="<category>Label</category><sub-category>Print</sub-category>Print label files to a specified printer. Supports PDF, PNG, JPG files. Cross-platform: Windows, macOS, Linux. Compatible with laser, inkjet, and thermal printers via USB, LAN, or Bluetooth.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["file_names"],
                    "properties": {
                        "file_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of file paths to print (PDF, PNG, JPG, etc.)"
                        },
                        "printer": {
                            "type": "string",
                            "description": "Target printer name. If empty or not specified, uses system default printer."
                        },
                        "n_copies": {
                            "type": "integer",
                            "description": "Number of copies for each file. Default is 1.",
                            "default": 1
                        }
                    }
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


def add_reformat_labels_tool_schema(tool_schemas):
    """Add reformat_labels tool schema to the MCP tool schemas list."""
    import mcp.types as types

    tool_schema = types.Tool(
        name="reformat_labels",
        description="<category>Label</category><sub-category>Reformat</sub-category>Reformat label PDFs to fit on multi-label sheets. Supports configurable sheet sizes, label layouts (rows/columns), margins, and optional backup copies with per-file note text.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["in_files"],
                    "properties": {
                        "in_files": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["file_name"],
                                "properties": {
                                    "file_name": {
                                        "type": "string",
                                        "description": "Path to the PDF file"
                                    },
                                    "added_note_text": {
                                        "type": "string",
                                        "description": "Note text to add to backup label (e.g., order number)"
                                    },
                                    "added_note_font": {
                                        "type": "string",
                                        "description": "Path to TTF font file for note text (optional)"
                                    },
                                    "added_note_size": {
                                        "type": "integer",
                                        "description": "Font size for note text. Default: 24",
                                        "default": 24
                                    }
                                }
                            },
                            "description": "List of input file specifications with per-file note settings"
                        },
                        "out_dir": {
                            "type": "string",
                            "description": "Output directory path. If not specified, uses same directory as first input file."
                        },
                        "sheet_width": {
                            "type": "number",
                            "description": "Sheet width in inches (e.g., 8.5 for letter size). Default: 8.5",
                            "default": 8.5
                        },
                        "sheet_height": {
                            "type": "number",
                            "description": "Sheet height in inches (e.g., 11.0 for letter size). Default: 11.0",
                            "default": 11.0
                        },
                        "label_width": {
                            "type": "number",
                            "description": "Label width in inches. Default: 8.5",
                            "default": 8.5
                        },
                        "label_height": {
                            "type": "number",
                            "description": "Label height in inches. Default: 5.5",
                            "default": 5.5
                        },
                        "label_orientation": {
                            "type": "string",
                            "enum": ["landscape", "portrait"],
                            "description": "Label orientation. Default: landscape",
                            "default": "landscape"
                        },
                        "label_rows_per_sheet": {
                            "type": "integer",
                            "description": "Number of label rows per sheet. Default: 2",
                            "default": 2
                        },
                        "label_cols_per_sheet": {
                            "type": "integer",
                            "description": "Number of label columns per sheet. Default: 1",
                            "default": 1
                        },
                        "label_rows_pitch": {
                            "type": "number",
                            "description": "Row pitch in inches. If 0 or not specified, auto-calculated for even distribution."
                        },
                        "label_cols_pitch": {
                            "type": "number",
                            "description": "Column pitch in inches. If 0 or not specified, auto-calculated for even distribution."
                        },
                        "top_side_margin": {
                            "type": "number",
                            "description": "Top margin in inches. Default: 0.25 inches"
                        },
                        "left_side_margin": {
                            "type": "number",
                            "description": "Left margin in inches. Default: 0.25 inches"
                        },
                        "add_backup": {
                            "type": "boolean",
                            "description": "Create backup copies with note text on same sheet. Default: true",
                            "default": True
                        }
                    }
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


# ============================================================================
# Unit Tests
# ============================================================================

def test_print_labels():
    """
    Test the print_labels_util function.
    Run with: python -m agent.ec_skills.label_utils.print_label test_print
    """
    print("\n" + "="*60)
    print("Testing print_labels_util")
    print("="*60)
    
    # Test 1: List available printers
    print("\n[Test 1] Listing available printers...")
    printers = get_available_printers()
    print(f"  Available printers: {printers}")
    
    default_printer = get_default_printer()
    print(f"  Default printer: {default_printer}")
    
    # Test 2: Print with no files (should fail gracefully)
    print("\n[Test 2] Testing with empty file list...")
    result = print_labels_util(files=[])
    print(f"  Status: {result.status.value}")
    print(f"  Message: {result.message}")
    assert result.status == PrintStatus.FAILED, "Should fail with empty file list"
    print("  ✓ Passed")
    
    # Test 3: Print with non-existent file
    print("\n[Test 3] Testing with non-existent file...")
    result = print_labels_util(files=["C:/shopify/orders/JessicaP_WF_1.pdf"])
    print(f"  Status: {result.status.value}")
    print(f"  Message: {result.message}")
    print(f"  Failed files: {result.failed_files}")
    print("  ✓ Passed (expected failure for non-existent file)")
    
    # Test 4: Print with invalid printer
    print("\n[Test 4] Testing with invalid printer name...")
    result = print_labels_util(
        files=["C:/shopify/orders/JessicaP_WF_1.pdf"],
        printer_name="NonExistentPrinter12345"
    )
    print(f"  Status: {result.status.value}")
    print(f"  Message: {result.message}")
    assert result.status == PrintStatus.FAILED, "Should fail with invalid printer"
    print("  ✓ Passed")
    
    print("\n" + "="*60)
    print("All print_labels tests completed!")
    print("="*60)


def test_reformat_labels():
    """
    Test the reformat_labels_util function.
    Run with: python -m agent.ec_skills.label_utils.print_label test_reformat
    """
    import tempfile
    
    print("\n" + "="*60)
    print("Testing reformat_labels_util")
    print("="*60)
    
    # Test 1: Empty file list
    print("\n[Test 1] Testing with empty file list...")
    result = reformat_labels_util(in_files=[])
    print(f"  Success: {result.success}")
    print(f"  Message: {result.message}")
    assert not result.success, "Should fail with empty file list"
    print("  ✓ Passed")
    
    # Test 2: Non-existent file
    print("\n[Test 2] Testing with non-existent file...")
    result = reformat_labels_util(in_files=[{"file_name": "C:/shopify/test/shipping_label9.pdf"}])
    print(f"  Success: {result.success}")
    print(f"  Message: {result.message}")
    print("  ✓ Passed (expected failure for non-existent file)")
    
    # Test 3: Dimension parsing
    print("\n[Test 3] Testing dimension parsing...")
    try:
        w, h = parse_dimension_string("D8.5X11")
        print(f"  Parsed D8.5X11: width={w}, height={h}")
        assert w == 8.5 and h == 11, "Should parse correctly"
        print("  ✓ Passed")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
    
    # Test 4: Various dimension formats
    print("\n[Test 4] Testing various dimension formats...")
    test_dims = ["D4X6", "D8.5X5.5", "D11X8.5", "D2.6X1"]
    for dim in test_dims:
        try:
            w, h = parse_dimension_string(dim)
            print(f"  {dim} -> width={w}, height={h}")
        except Exception as e:
            print(f"  {dim} -> Error: {e}")
    print("  ✓ Passed")
    
    # Test 5: Test with a real PDF if available
    print("\n[Test 5] Looking for test PDF files...")
    test_dirs = [
        # os.path.expanduser("~/Downloads"),
        # os.path.expanduser("~/Documents"),
        "C:/shopify/test",
    ]
    
    test_pdf = None
    test_pdfs = []
    for test_dir in test_dirs:
        if os.path.isdir(test_dir):
            for f in os.listdir(test_dir):
                if f.lower().endswith('.pdf') and 'label' in f.lower():
                    test_pdf = os.path.join(test_dir, f)
                    test_pdfs.append(test_pdf)
        # if test_pdf:
        #     break
    print(f"  Found test PDFs: {test_pdfs}")
    if test_pdfs and os.path.exists(test_pdf):
        print(f"  Found {len(test_pdfs)} test PDFs")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = "C:/shopify/test/output"
            print(f"  Output directory: {tmpdir}")
            
            # Build input files list with per-file notes
            in_files = [
                {
                    "file_name": pdf_path,
                    "added_note_text": f"Note for {os.path.basename(pdf_path)}",
                    "added_note_size": 20
                }
                for pdf_path in test_pdfs
            ]
            
            result = reformat_labels_util(
                in_files=in_files,
                out_dir=tmpdir,
                sheet_width=8.5,
                sheet_height=11.0,
                label_width=3.9,
                label_height=2.9,
                label_rows_per_sheet=3,
                label_cols_per_sheet=2,
                add_backup=True
            )
            print(f"  Success: {result.success}")
            print(f"  Message: {result.message}")
            print(f"  Output files: {result.output_files}")
            print(f"  Backup files: {result.backup_files}")
    else:
        print("  No test PDF found. Skipping real file test.")
        print("  To test with a real file, place a PDF with 'label' in the name in Downloads.")
    
    print("\n" + "="*60)
    print("All reformat_labels tests completed!")
    print("="*60)


def test_all():
    """Run all unit tests."""
    test_print_labels()
    test_reformat_labels()


if __name__ == "__main__":
    import sys

    # test_print_labels()
    test_reformat_labels()

    # if len(sys.argv) > 1:
    #     cmd = sys.argv[1].lower()
    #     if cmd == "test_print":
    #         test_print_labels()
    #     elif cmd == "test_reformat":
    #         test_reformat_labels()
    #     elif cmd == "test" or cmd == "test_all":
    #         test_all()
    #     elif cmd == "printers":
    #         print("Available printers:")
    #         for p in get_available_printers():
    #             print(f"  - {p}")
    #         print(f"\nDefault printer: {get_default_printer()}")
    #     else:
    #         print(f"Unknown command: {cmd}")
    #         print("Usage: python print_label.py [test_print|test_reformat|test_all|printers]")
    # else:
    #     print("Print Label Utility")
    #     print("="*40)
    #     print("Usage: python print_label.py <command>")
    #     print("\nCommands:")
    #     print("  test_print    - Test print_labels_util function")
    #     print("  test_reformat - Test reformat_labels_util function")
    #     print("  test_all      - Run all tests")
    #     print("  printers      - List available printers")
