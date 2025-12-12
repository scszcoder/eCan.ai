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


class LabelsReformatAction(BaseModel):
	in_file_names: str = Field(
		default="", description="to-be-reformated label pdf file's full path name"
	)
	out_file_names: str = Field(
		default="", description="after reformat label file's full path name"
	)
	sheet_size: str = Field(
		default="D11X8.5", description="width x height of sheet in inches, choices: D6X4, D8.5X5.5, D5X4, D4X3, D3X2, D2.6X1"
	)
	add_backup: bool = Field(
		default=True, description="create a duplicate copy of the label for note text and proof of packaging."
	)
	label_format: str = Field(
		default="D8.5X5.5", description="width x height of label in inches, choices: D6X4, D8.5X5.5, D5X4, D4X3, D3X2, D2.6X1"
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
	label_rows_pitch: int = Field(
		default=2, description="number of inches of label rows pitch"
	)
	label_cols_pitch: int = Field(
		default=1, description="number of inches of label columns pitch"
	)
	top_side_margin: int = Field(
		default=2, description="number of inches of top side margin"
	)
	left_side_margin: int = Field(
		default=1, description="number of inches of left side margin"
	)
	added_note_text: str = Field(
		default="", description="note text to be added to 2nd copy of the label, if add_backup is true"
	)
	added_note_font_size: str = Field(
		default="", description="font size of note text"
	)

