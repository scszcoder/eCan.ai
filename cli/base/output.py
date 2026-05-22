#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI Output - Provides consistent output formatting across all commands.
"""

import json
import sys
from enum import Enum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


class OutputFormat(Enum):
    """Output format types."""
    AUTO = "auto"
    SIMPLE = "simple"
    TABLE = "table"
    JSON = "json"
    YAML = "yaml"


class OutputLevel(Enum):
    """Output verbosity levels."""
    QUIET = "quiet"
    NORMAL = "normal"
    VERBOSE = "verbose"


@dataclass
class OutputStyle:
    """ANSI color and style codes."""

    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    RESET = "\033[0m"

    @classmethod
    def success(cls, text: str) -> str:
        """Format success message."""
        return f"{cls.GREEN}✓{cls.RESET} {text}"

    @classmethod
    def error(cls, text: str) -> str:
        """Format error message."""
        return f"{cls.RED}✗{cls.RESET} {text}"

    @classmethod
    def warning(cls, text: str) -> str:
        """Format warning message."""
        return f"{cls.YELLOW}⚠{cls.RESET} {text}"

    @classmethod
    def info(cls, text: str) -> str:
        """Format info message."""
        return f"{cls.CYAN}ℹ{cls.RESET} {text}"

    @classmethod
    def title(cls, text: str) -> str:
        """Format title/header."""
        return f"{cls.BOLD}{cls.CYAN}{text}{cls.RESET}"


class CLIOutput:
    """
    Centralized output handler for CLI commands.

    Features:
    - Colorized output with ANSI codes
    - Multiple output formats (table, json, yaml)
    - Progress indicators
    - Pagination support
    - Error formatting
    """

    def __init__(
        self,
        format: OutputFormat = OutputFormat.AUTO,
        level: OutputLevel = OutputLevel.NORMAL,
        no_color: bool = False,
        file=None
    ):
        self.format = format
        self.level = level
        self.no_color = no_color or not sys.stdout.isatty()
        self.file = file or sys.stdout
        self._style = OutputStyle()

    def _color(self, code: str, text: str) -> str:
        """Apply color code to text."""
        if self.no_color:
            return text
        return f"{code}{text}{self._style.RESET}"

    def print(self, *args, **kwargs):
        """Print to output."""
        if self.level != OutputLevel.QUIET:
            print(*args, file=self.file, **kwargs)

    def print_error(self, *args, **kwargs):
        """Print error to stderr."""
        print(*args, file=sys.stderr, **kwargs)

    def success(self, message: str):
        """Print success message."""
        self.print(self._style.success(message))

    def error(self, message: str):
        """Print error message."""
        self.print_error(self._style.error(message))

    def warning(self, message: str):
        """Print warning message."""
        self.print(self._style.warning(message))

    def info(self, message: str):
        """Print info message."""
        self.print(self._style.info(message))

    def title(self, message: str):
        """Print title."""
        self.print(self._style.title(message))

    def header(self, message: str, char: str = "─", width: int = 60):
        """Print section header."""
        line = char * width
        self.print()
        self.print(self._color(self._style.BOLD, line))
        self.print(self._color(self._style.BOLD + self._style.CYAN, message))
        self.print(self._color(self._style.BOLD, line))

    def json(self, data: Any, indent: int = 2):
        """Print JSON output."""
        if self.no_color:
            print(json.dumps(data, indent=indent, default=str), file=self.file)
        else:
            json_str = json.dumps(data, indent=indent, default=str)
            lines = json_str.split('\n')
            for line in lines:
                line = line.rstrip()
                if ':' in line:
                    key, _, value = line.partition(':')
                    self.print(f"{self._color(self._style.CYAN, key)}:{value}")
                else:
                    self.print(line)

    def table(
        self,
        title: str,
        columns: List[str],
        rows: List[List[Any]],
        truncate: bool = True,
        max_col_width: int = 50
    ):
        """Print formatted table."""
        if not rows:
            self.warning(f"No {title.lower()} found")
            return

        col_widths = [len(c) for c in columns]
        for row in rows:
            for i, cell in enumerate(row):
                cell_str = str(cell)
                if truncate and len(cell_str) > max_col_width:
                    cell_str = cell_str[:max_col_width-3] + "..."
                col_widths[i] = max(col_widths[i], len(cell_str))

        self.title(title)

        # Calculate widths based on content
        col_widths = [len(c) for c in columns]
        for row in rows:
            for i, cell in enumerate(row):
                cell_str = str(cell)
                if truncate and len(cell_str) > max_col_width:
                    cell_str = cell_str[:max_col_width-3] + "..."
                col_widths[i] = max(col_widths[i], len(cell_str))

        # Build table parts
        # Each cell: [space][content padded][space]
        sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
        header = "|" + "|".join(f" {col.ljust(w)} " for col, w in zip(columns, col_widths)) + "|"

        if not self.no_color:
            header = self._color(self._style.BOLD + self._style.CYAN, header)
            sep = self._color(self._style.DIM, sep.replace("+", "+").replace("-", "-"))

        self.print(sep)
        self.print(header)
        self.print(sep.replace("-", "="))

        for row in rows:
            cells = []
            for cell, width in zip(row, col_widths):
                cell_str = str(cell)
                if truncate and len(cell_str) > width:
                    cell_str = cell_str[:width-3] + "..."
                cells.append(f" {cell_str.ljust(width)} ")
            self.print("|" + "|".join(cells) + "|")

        self.print(sep)
        self.print(f"\n{self._color(self._style.DIM, f'Total: {len(rows)} items')}")

    def key_value(
        self,
        data: Dict[str, Any],
        title: str = None,
        indent: int = 0,
        color_keys: bool = True
    ):
        """Print key-value pairs."""
        if title:
            self.title(title)

        prefix = " " * indent
        for key, value in data.items():
            if color_keys:
                key_str = self._color(self._style.CYAN, key)
            else:
                key_str = key
            self.print(f"{prefix}{key_str}: {value}")

    def progress_start(self, message: str):
        """Start progress indication."""
        self.info(f"{message}... ", end="", flush=True)

    def progress_done(self, success: bool = True):
        """Complete progress indication."""
        if success:
            self.print("done")
        else:
            self.print("failed")

    def confirm(self, message: str, default: bool = False) -> bool:
        """Ask for confirmation."""
        suffix = " [Y/n]" if default else " [y/N]"
        suffix_colored = f" {self._color(self._style.DIM, suffix)}"

        while True:
            response = input(f"{message}{suffix_colored}: ").strip().lower()
            if not response:
                return default
            if response in ('y', 'yes'):
                return True
            if response in ('n', 'no'):
                return False
            self.warning("Please enter 'y' or 'n'")


_global_output: Optional[CLIOutput] = None


def get_output(**kwargs) -> CLIOutput:
    """Get or create global output handler."""
    global _global_output
    if _global_output is None or kwargs:
        _global_output = CLIOutput(**kwargs)
    return _global_output


def set_output(output: CLIOutput):
    """Set global output handler."""
    global _global_output
    _global_output = output
