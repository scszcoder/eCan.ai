from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field


# Action Input Models
class RunCodeAction(BaseModel):
	"""Execute Python code in a sandboxed environment with access to common safe modules.
	Use the 'result' variable to return a value from the code."""
	code: str = Field(
		description="Python code to execute. Use 'result' variable to return a value. "
		"Has access to: os, json, math, re, datetime, collections, itertools, functools, random, string, uuid, hashlib, base64."
	)
	args: Optional[dict[str, Any]] = Field(
		default=None,
		description="Input arguments dict accessible as 'args' and as individual variables in the code."
	)
	timeout: Optional[float] = Field(
		default=None,
		description="Maximum execution time in seconds. Default: 30."
	)
	allowed_imports: Optional[list[str]] = Field(
		default=None,
		description="Additional module names to allow importing beyond the safe defaults."
	)


class RunShellScriptAction(BaseModel):
	"""Execute a shell script. Auto-detects OS and uses appropriate shell
	(PowerShell on Windows, bash on Linux, zsh on macOS)."""
	script: str = Field(
		description="Shell script to execute."
	)
	shell: Optional[str] = Field(
		default=None,
		description="Shell to use: powershell, pwsh, bash, zsh, sh, cmd. Auto-detected from OS if not specified."
	)
	timeout: Optional[float] = Field(
		default=None,
		description="Maximum execution time in seconds. Default: 60."
	)
	working_dir: Optional[str] = Field(
		default=None,
		description="Working directory for script execution."
	)
	env_vars: Optional[dict[str, str]] = Field(
		default=None,
		description="Additional environment variables as key-value pairs."
	)


class FileRenameAction(BaseModel):
	old_path: str = Field(
		default="", description="current file's full path name"
	)
	new_name: str = Field(
		default="", description="new file's full path name after renaming"
	)

class FilesPrintAction(BaseModel):
	printer: str = Field(
		default="", description="networked printer name"
	)
	file_names: list[str] = Field(
		default="", description="list of to-be-printed files' full path names"
	)
	n_copies: int = Field(
		default=1, description="number of copies to be printed"
	)


class LabelInputFile(BaseModel):
	"""Input file specification with per-file note settings."""
	file_name: str = Field(
		default="", description="path to the PDF file"
	)
	added_note_text: str = Field(
		default="", description="note text to add to backup label (e.g., order number)"
	)
	added_note_font: str = Field(
		default="", description="path to TTF font file for note text (optional)"
	)
	added_note_size: int = Field(
		default=24, description="font size for note text"
	)


class ExtractDomAction(BaseModel):
	"""Extract raw DOM/markdown content from the current page without LLM analysis.
	Used in passive mode where cloud agent will analyze the content."""
	query: str = Field(
		default="", description="The extraction query describing what to look for"
	)
	extract_links: bool = Field(
		default=False, description="Whether to include links in the extracted content"
	)
	start_from_char: int = Field(
		default=0, description="Character position to start extraction from (for pagination)"
	)


class LabelsReformatAction(BaseModel):
	in_files: list[LabelInputFile] = Field(
		default_factory=list, description="list of input file specifications with per-file note settings"
	)
	out_dir: str = Field(
		default="", description="output directory path. If not specified, uses same directory as first input file."
	)
	sheet_width: float = Field(
		default=8.5, description="sheet width in inches (e.g., 8.5 for letter size)"
	)
	sheet_height: float = Field(
		default=11.0, description="sheet height in inches (e.g., 11.0 for letter size)"
	)
	label_width: float = Field(
		default=8.5, description="label width in inches"
	)
	label_height: float = Field(
		default=5.5, description="label height in inches"
	)
	label_orientation: str = Field(
		default="landscape", description="label orientation, choices: landscape, portrait"
	)
	label_rows_per_sheet: int = Field(
		default=2, description="number of label rows placed per sheet"
	)
	label_cols_per_sheet: int = Field(
		default=1, description="number of label columns placed per sheet"
	)
	label_rows_pitch: float = Field(
		default=0, description="row pitch in inches. If 0, auto-calculated for even distribution."
	)
	label_cols_pitch: float = Field(
		default=0, description="column pitch in inches. If 0, auto-calculated for even distribution."
	)
	top_side_margin: float = Field(
		default=0.25, description="top margin in inches"
	)
	left_side_margin: float = Field(
		default=0.25, description="left margin in inches"
	)
	add_backup: bool = Field(
		default=True, description="create backup copies with note text on same sheet"
	)

