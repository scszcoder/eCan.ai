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
    """
    # Common Ghostscript paths
    gs_paths = [
        r"C:\Program Files\gs\gs10.06.0\bin\gswin64.exe",
        r"C:\Program Files\gs\gs10.06.0\bin\gswin64c.exe"
    ]
    
    gs_exe = None
    for path in gs_paths:
        if os.path.exists(path):
            gs_exe = path
            break
    
    # Also check if gswin64c is in PATH
    if not gs_exe:
        gs_exe = shutil.which("gswin64c") or shutil.which("gswin32c")
    
    if not gs_exe:
        return False, "Ghostscript not found"
    
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
            f'-sOutputFile="%printer%{printer_name}"' if printer_name else "",
            file_path
        ]
        # Filter out empty strings
        cmd = [c for c in cmd if c]
        
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
            return False, f"Ghostscript error: {result.stderr}"
            
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
    Extract the label content from a PDF page, crop to content, and resize.
    
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
        # Render page to pixmap
        mat = fitz.Matrix(dpi / 72, dpi / 72)  # Scale from 72 DPI to target DPI
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img_array = lazy.np.array(img)
        
        # Convert to grayscale for contour detection
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        gray = cv2.bilateralFilter(gray, 11, 17, 17)
        
        # Morphological operations to clean up
        kernel = lazy.np.ones((5, 5), lazy.np.uint8)
        erosion = cv2.erode(gray, kernel, iterations=2)
        kernel = lazy.np.ones((4, 4), lazy.np.uint8)
        dilation = cv2.dilate(erosion, kernel, iterations=2)
        
        # Edge detection
        edged = cv2.Canny(dilation, 30, 200)
        
        # Find contours
        contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            # No contours found, use the whole image
            logger.warning("[extract_label_from_pdf_page] No contours found, using full page")
            cropped = img_array
        else:
            # Find the largest contour (main label area)
            largest_contour = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest_contour)
            
            # Add small padding around the detected area
            padding = 5
            x = max(0, x - padding)
            y = max(0, y - padding)
            w = min(img_array.shape[1] - x, w + 2 * padding)
            h = min(img_array.shape[0] - y, h + 2 * padding)
            
            cropped = img_array[y:y+h, x:x+w]
        
        # Determine if rotation is needed based on orientation
        crop_h, crop_w = cropped.shape[:2]
        is_landscape = crop_w > crop_h
        want_landscape = orientation.lower() == "landscape"
        
        if is_landscape != want_landscape:
            # Rotate 90 degrees
            cropped = cv2.rotate(cropped, cv2.ROTATE_90_CLOCKWISE)
        
        # Resize to target dimensions
        resized = cv2.resize(cropped, (target_width_px, target_height_px), interpolation=cv2.INTER_AREA)
        
        return Image.fromarray(resized)
        
    except Exception as e:
        logger.error(f"[extract_label_from_pdf_page] Error: {e}")
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


def add_note_to_label(
    label_img: Image.Image,
    note_text: str,
    font_size: int = 24,
    font_path: Optional[str] = None,
    position: str = "bottom"  # 'bottom', 'top', 'center'
) -> Image.Image:
    """
    Add note text to a label image.
    
    Args:
        label_img: PIL Image of the label
        note_text: Text to add
        font_size: Font size in points
        font_path: Path to TTF font file (optional)
        position: Where to place the text
    
    Returns:
        PIL Image with text added.
    """
    if not note_text:
        return label_img
    
    img = label_img.copy()
    draw = ImageDraw.Draw(img)
    
    # Load font
    try:
        if font_path and os.path.exists(font_path):
            font = ImageFont.truetype(font_path, font_size)
        else:
            font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()
    
    # Get text bounding box
    bbox = draw.textbbox((0, 0), note_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Calculate position
    img_width, img_height = img.size
    x = (img_width - text_width) // 2  # Center horizontally
    
    if position == "bottom":
        y = img_height - text_height - 10
    elif position == "top":
        y = 10
    else:  # center
        y = (img_height - text_height) // 2
    
    # Draw text with slight shadow for visibility
    draw.text((x + 1, y + 1), note_text, font=font, fill=(128, 128, 128))
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


def reformat_labels_util(
    in_file_names: list[str],
    out_dir: Optional[str] = None,
    sheet_size: str = "D8.5X11",
    label_format: str = "D8.5X5.5",
    label_orientation: str = "landscape",
    label_rows_per_sheet: int = 2,
    label_cols_per_sheet: int = 1,
    label_rows_pitch: Optional[float] = None,
    label_cols_pitch: Optional[float] = None,
    top_side_margin: Optional[float] = None,
    left_side_margin: Optional[float] = None,
    add_backup: bool = True,
    added_note_text: str = "",
    added_note_font_size: int = 24,
    font_path: Optional[str] = None,
    dpi: int = DEFAULT_DPI
) -> ReformatResult:
    """
    Reformat label PDFs to fit on multi-label sheets.
    
    This function takes individual label PDFs and arranges them onto sheets
    that may contain multiple labels (e.g., 4 labels per sheet).
    
    Args:
        in_file_names: List of input PDF file paths
        out_dir: Output directory (defaults to same as first input file)
        sheet_size: Sheet dimensions (e.g., 'D8.5X11' for letter size)
        label_format: Individual label dimensions (e.g., 'D4X2.5')
        label_orientation: 'landscape' or 'portrait'
        label_rows_per_sheet: Number of label rows per sheet
        label_cols_per_sheet: Number of label columns per sheet
        label_rows_pitch: Vertical distance between label centers (inches). Default: auto-calculated
        label_cols_pitch: Horizontal distance between label centers (inches). Default: auto-calculated
        top_side_margin: Top margin in inches. Default: 0.25"
        left_side_margin: Left margin in inches. Default: 0.25"
        add_backup: If True, create backup copies with note text
        added_note_text: Text to add to backup copies
        added_note_font_size: Font size for note text
        font_path: Path to TTF font file for notes
        dpi: Output DPI
    
    Returns:
        ReformatResult with output file paths and status.
    
    Example:
        # 4 labels per sheet (2x2 layout)
        result = reformat_labels(
            in_file_names=["label1.pdf", "label2.pdf", "label3.pdf", "label4.pdf"],
            sheet_size="D8.5X11",
            label_format="D4X2.5",
            label_rows_per_sheet=2,
            label_cols_per_sheet=2
        )
        # Result: 1 output file with all 4 labels arranged on one sheet
    """
    if not in_file_names:
        return ReformatResult(
            success=False,
            output_files=[],
            backup_files=[],
            input_count=0,
            output_count=0,
            message="No input files provided"
        )
    
    # Parse dimensions
    try:
        sheet_w, sheet_h = parse_dimension_string(sheet_size)
        label_w, label_h = parse_dimension_string(label_format)
    except ValueError as e:
        return ReformatResult(
            success=False,
            output_files=[],
            backup_files=[],
            input_count=len(in_file_names),
            output_count=0,
            message=str(e)
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
        out_dir = os.path.dirname(in_file_names[0]) or "."
    
    # Extract all labels from input PDFs
    all_labels: list[Image.Image] = []
    all_backup_labels: list[Image.Image] = []
    
    for pdf_path in in_file_names:
        if not os.path.exists(pdf_path):
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
                    
                    # Create backup with note if requested
                    if add_backup:
                        backup_label = add_note_to_label(
                            label_img,
                            added_note_text,
                            added_note_font_size,
                            font_path
                        )
                        all_backup_labels.append(backup_label)
            doc.close()
        except Exception as e:
            logger.error(f"[reformat_labels] Error processing {pdf_path}: {e}")
    
    if not all_labels:
        return ReformatResult(
            success=False,
            output_files=[],
            backup_files=[],
            input_count=len(in_file_names),
            output_count=0,
            message="No labels could be extracted from input files"
        )
    
    # Arrange labels onto sheets
    output_files: list[str] = []
    backup_files: list[str] = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Process main labels
    for sheet_idx in range(0, len(all_labels), labels_per_sheet):
        sheet_labels = all_labels[sheet_idx:sheet_idx + labels_per_sheet]
        sheet_img = create_label_sheet(sheet_labels, config)
        
        # Save as PDF
        out_filename = f"labels_sheet_{sheet_idx // labels_per_sheet + 1}_{timestamp}.pdf"
        out_path = os.path.join(out_dir, out_filename)
        sheet_img.save(out_path, "PDF", resolution=dpi)
        output_files.append(out_path)
        logger.debug(f"[reformat_labels] Created: {out_path}")
    
    # Process backup labels if requested
    if add_backup and all_backup_labels:
        for sheet_idx in range(0, len(all_backup_labels), labels_per_sheet):
            sheet_labels = all_backup_labels[sheet_idx:sheet_idx + labels_per_sheet]
            sheet_img = create_label_sheet(sheet_labels, config)
            
            # Save as PDF
            out_filename = f"labels_backup_{sheet_idx // labels_per_sheet + 1}_{timestamp}.pdf"
            out_path = os.path.join(out_dir, out_filename)
            sheet_img.save(out_path, "PDF", resolution=dpi)
            backup_files.append(out_path)
            logger.debug(f"[reformat_labels] Created backup: {out_path}")
    
    message = (f"Reformatted {len(all_labels)} labels from {len(in_file_names)} files "
               f"into {len(output_files)} sheets ({labels_per_sheet} labels/sheet)")
    if backup_files:
        message += f", plus {len(backup_files)} backup sheets"
    
    logger.info(f"[reformat_labels] {message}")
    
    return ReformatResult(
        success=True,
        output_files=output_files,
        backup_files=backup_files,
        input_count=len(in_file_names),
        output_count=len(output_files),
        message=message
    )


async def reformat_labels_async(
    in_file_names: list[str],
    out_dir: Optional[str] = None,
    sheet_size: str = "D8.5X11",
    label_format: str = "D8.5X5.5",
    label_orientation: str = "landscape",
    label_rows_per_sheet: int = 2,
    label_cols_per_sheet: int = 1,
    label_rows_pitch: Optional[float] = None,
    label_cols_pitch: Optional[float] = None,
    top_side_margin: Optional[float] = None,
    left_side_margin: Optional[float] = None,
    add_backup: bool = True,
    added_note_text: str = "",
    added_note_font_size: int = 24,
    font_path: Optional[str] = None,
    dpi: int = DEFAULT_DPI
) -> ReformatResult:
    """Async version of reformat_labels_util."""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(
            pool,
            lambda: reformat_labels_util(
                in_file_names=in_file_names,
                out_dir=out_dir,
                sheet_size=sheet_size,
                label_format=label_format,
                label_orientation=label_orientation,
                label_rows_per_sheet=label_rows_per_sheet,
                label_cols_per_sheet=label_cols_per_sheet,
                label_rows_pitch=label_rows_pitch,
                label_cols_pitch=label_cols_pitch,
                top_side_margin=top_side_margin,
                left_side_margin=left_side_margin,
                add_backup=add_backup,
                added_note_text=added_note_text,
                added_note_font_size=added_note_font_size,
                font_path=font_path,
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
        - in_file_names: list of input PDF file paths (or comma-separated string)
        - out_file_names: output directory (optional)
        - sheet_size: e.g., 'D8.5X11'
        - label_format: e.g., 'D4X2.5'
        - label_orientation: 'landscape' or 'portrait'
        - label_rows_per_sheet: number of rows
        - label_cols_per_sheet: number of columns
        - label_rows_pitch: row pitch in inches (optional, auto-calculated if <= 0)
        - label_cols_pitch: column pitch in inches (optional, auto-calculated if <= 0)
        - top_side_margin: top margin in inches (optional, default 0.25)
        - left_side_margin: left margin in inches (optional, default 0.25)
        - add_backup: create backup copies with notes
        - added_note_text: text for backup labels
        - added_note_font_size: font size for notes
    """
    from mcp.types import TextContent
    
    try:
        input_data = args.get("input", args)
        logger.debug(f"[reformat_labels] Starting with input: {input_data}")
        
        # Extract parameters from input
        in_file_names = input_data.get("in_file_names", [])
        if isinstance(in_file_names, str):
            # Handle comma-separated string or single file
            in_file_names = [f.strip() for f in in_file_names.split(",") if f.strip()]
        
        out_dir = input_data.get("out_file_names", None)
        if out_dir and os.path.isfile(out_dir):
            out_dir = os.path.dirname(out_dir)
        
        sheet_size = input_data.get("sheet_size", "D8.5X11")
        label_format = input_data.get("label_format", "D8.5X5.5")
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
        added_note_text = input_data.get("added_note_text", "")
        added_note_font_size = input_data.get("added_note_font_size", 24)
        if isinstance(added_note_font_size, str):
            try:
                added_note_font_size = int(added_note_font_size)
            except ValueError:
                added_note_font_size = 24
        
        # Call the utility function
        result = reformat_labels_util(
            in_file_names=in_file_names,
            out_dir=out_dir,
            sheet_size=sheet_size,
            label_format=label_format,
            label_orientation=label_orientation,
            label_rows_per_sheet=label_rows_per_sheet,
            label_cols_per_sheet=label_cols_per_sheet,
            label_rows_pitch=label_rows_pitch,
            label_cols_pitch=label_cols_pitch,
            top_side_margin=top_side_margin,
            left_side_margin=left_side_margin,
            add_backup=add_backup,
            added_note_text=added_note_text,
            added_note_font_size=added_note_font_size
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
        description="<category>Label</category><sub-category>Reformat</sub-category>Reformat label PDFs to fit on multi-label sheets. Supports configurable sheet sizes, label layouts (rows/columns), margins, and optional backup copies with note text.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["in_file_names"],
                    "properties": {
                        "in_file_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of input PDF file paths to reformat"
                        },
                        "out_file_names": {
                            "type": "string",
                            "description": "Output directory path. If not specified, uses same directory as first input file."
                        },
                        "sheet_size": {
                            "type": "string",
                            "description": "Sheet size in format 'DWIDTHxHEIGHT' (e.g., 'D8.5X11' for letter size). Default: D8.5X11",
                            "default": "D8.5X11"
                        },
                        "label_format": {
                            "type": "string",
                            "description": "Label size in format 'DWIDTHxHEIGHT' (e.g., 'D4X2.5'). Default: D8.5X5.5",
                            "default": "D8.5X5.5"
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
                            "description": "Create backup copies with note text for packaging proof. Default: true",
                            "default": True
                        },
                        "added_note_text": {
                            "type": "string",
                            "description": "Note text to add to backup labels (e.g., order number, product info)"
                        },
                        "added_note_font_size": {
                            "type": "integer",
                            "description": "Font size for note text. Default: 24",
                            "default": 24
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
    result = print_labels_util(files=["C:/nonexistent/file.pdf"])
    print(f"  Status: {result.status.value}")
    print(f"  Message: {result.message}")
    print(f"  Failed files: {result.failed_files}")
    print("  ✓ Passed (expected failure for non-existent file)")
    
    # Test 4: Print with invalid printer
    print("\n[Test 4] Testing with invalid printer name...")
    result = print_labels_util(
        files=["C:/test.pdf"],
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
    result = reformat_labels_util(in_file_names=[])
    print(f"  Success: {result.success}")
    print(f"  Message: {result.message}")
    assert not result.success, "Should fail with empty file list"
    print("  ✓ Passed")
    
    # Test 2: Non-existent file
    print("\n[Test 2] Testing with non-existent file...")
    result = reformat_labels_util(in_file_names=["C:/nonexistent/label.pdf"])
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
        os.path.expanduser("~/Downloads"),
        os.path.expanduser("~/Documents"),
        "C:/temp",
    ]
    
    test_pdf = None
    for test_dir in test_dirs:
        if os.path.isdir(test_dir):
            for f in os.listdir(test_dir):
                if f.lower().endswith('.pdf') and 'label' in f.lower():
                    test_pdf = os.path.join(test_dir, f)
                    break
        if test_pdf:
            break
    
    if test_pdf and os.path.exists(test_pdf):
        print(f"  Found test PDF: {test_pdf}")
        with tempfile.TemporaryDirectory() as tmpdir:
            print(f"  Output directory: {tmpdir}")
            result = reformat_labels_util(
                in_file_names=[test_pdf],
                out_dir=tmpdir,
                sheet_size="D8.5X11",
                label_format="D8.5X5.5",
                label_rows_per_sheet=2,
                label_cols_per_sheet=1,
                add_backup=True,
                added_note_text="TEST NOTE"
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
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "test_print":
            test_print_labels()
        elif cmd == "test_reformat":
            test_reformat_labels()
        elif cmd == "test" or cmd == "test_all":
            test_all()
        elif cmd == "printers":
            print("Available printers:")
            for p in get_available_printers():
                print(f"  - {p}")
            print(f"\nDefault printer: {get_default_printer()}")
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: python print_label.py [test_print|test_reformat|test_all|printers]")
    else:
        print("Print Label Utility")
        print("="*40)
        print("Usage: python print_label.py <command>")
        print("\nCommands:")
        print("  test_print    - Test print_labels_util function")
        print("  test_reformat - Test reformat_labels_util function")
        print("  test_all      - Run all tests")
        print("  printers      - List available printers")
