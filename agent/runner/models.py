from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field, model_validator, conlist

# Action Input Models
class SearchGoogleAction(BaseModel):
	query: str


class GoToUrlAction(BaseModel):
	url: str


class WaitForElementAction(BaseModel):
	selector: str
	timeout: Optional[int] = 10000  # Timeout in milliseconds


class ClickElementAction(BaseModel):
	index: int
	xpath: Optional[str] = None


class ClickElementByXpathAction(BaseModel):
	xpath: str


class ClickElementBySelectorAction(BaseModel):
	css_selector: str


class ClickElementByTextAction(BaseModel):
	text: str
	element_type: Optional[str]
	nth: int = 0


class InputTextAction(BaseModel):
	index: int
	text: str
	xpath: Optional[str] = None


class DoneAction(BaseModel):
	text: str
	success: bool


class SwitchTabAction(BaseModel):
	page_id: int


class OpenTabAction(BaseModel):
	url: str


class CloseTabAction(BaseModel):
	page_id: int


class ScrollAction(BaseModel):
	amount: Optional[int] = None  # The number of pixels to scroll. If None, scroll down/up one page


class SendKeysAction(BaseModel):
	keys: str


class GroupTabsAction(BaseModel):
	tab_ids: list[int] = Field(..., description='List of tab IDs to group')
	title: str = Field(..., description='Name for the tab group')
	color: Optional[str] = Field(
		'blue',
		description='Color for the group (grey/blue/red/yellow/green/pink/purple/cyan)',
	)


class UngroupTabsAction(BaseModel):
	tab_ids: list[int] = Field(..., description='List of tab IDs to ungroup')


class ExtractPageContentAction(BaseModel):
	value: str


class NoParamsAction(BaseModel):
	"""
	Accepts absolutely anything in the incoming data
	and discards it, so the final parsed model is empty.
	"""

	model_config = ConfigDict(extra='allow')

	@model_validator(mode='before')
	def ignore_all_inputs(cls, values):
		# No matter what the user sends, discard it and return empty.
		return {}


class Position(BaseModel):
	x: int
	y: int


class DragDropAction(BaseModel):
	# Element-based approach
	element_source: Optional[str] = Field(None, description='CSS selector or XPath of the element to drag from')
	element_target: Optional[str] = Field(None, description='CSS selector or XPath of the element to drop onto')
	element_source_offset: Optional[Position] = Field(
		None, description='Precise position within the source element to start drag (in pixels from top-left corner)'
	)
	element_target_offset: Optional[Position] = Field(
		None, description='Precise position within the target element to drop (in pixels from top-left corner)'
	)

	# Coordinate-based approach (used if selectors not provided)
	coord_source_x: Optional[int] = Field(None, description='Absolute X coordinate on page to start drag from (in pixels)')
	coord_source_y: Optional[int] = Field(None, description='Absolute Y coordinate on page to start drag from (in pixels)')
	coord_target_x: Optional[int] = Field(None, description='Absolute X coordinate on page to drop at (in pixels)')
	coord_target_y: Optional[int] = Field(None, description='Absolute Y coordinate on page to drop at (in pixels)')

	# Common options
	steps: Optional[int] = Field(10, description='Number of intermediate points for smoother movement (5-20 recommended)')
	delay_ms: Optional[int] = Field(5, description='Delay in milliseconds between steps (0 for fastest, 10-20 for more natural)')

class MouseClickAction(BaseModel):
	index: int
	loc: Position
	n: int
	interval: float

class MouseMoveAction(BaseModel):
	index: int
	loc: Position

class MouseDragDropAction(BaseModel):
	index: int
	pick_loc: Position
	drop_loc: Position
	duration: int

class MouseScrollAction(BaseModel):
	index: int
	amount: int
	direction: str

class TextInputAction(BaseModel):
	index: int
	text: str
	interval: float

class KeysAction(BaseModel):
	index: int
	combo: conlist(str)


class OpenAppAction(BaseModel):
	index: int
	app_name: str
	app_exe: str
	app_args: List[str] = []

class CloseAppAction(BaseModel):
	index: int
	app_name: str
	app_exe: str

class SwitchToAppAction(BaseModel):
	index: int
	app_name: str
	win_title: str
	app_exe: str

class CallAPIAction(BaseModel):
	index: int
	api_name: str
	api_endpoint: str
	api_route: str
	api_method: str
	api_parameters: str
	async_call: bool

class WaitAction(BaseModel):
	index: int
	length: float

class RunExternAction(BaseModel):
	index: int
	file: str
	args: List[str] = []

class MakeDirAction(BaseModel):
	index: int
	dir_path: str

class DeleteFileAction(BaseModel):
	index: int
	file: str

class DeleteDirAction(BaseModel):
	index: int
	dir_path: str

class MoveFileAction(BaseModel):
	index: int
	src: str
	dest: str

class CopyFileDirAction(BaseModel):
	index: int
	src: str
	dest: str

class ScreenCaptureAction(BaseModel):
	index: int
	file: str
	win_title_kw: str
	sub_area: List[int]


class ScreenAnalyzeAction(BaseModel):
	index: int
	icons: dict


class SevenZipAction(BaseModel):
	index: int
	file: str
	destination: str


class KillProcessesAction(BaseModel):
	index: int
	pids: List[int]