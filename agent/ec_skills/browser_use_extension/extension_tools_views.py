from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


# Action Input Models
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

