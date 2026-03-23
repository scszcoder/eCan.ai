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


class SendChatAction(BaseModel):
	"""Send a chat message to another agent via A2A (Agent-to-Agent) protocol.
	Use list_chat_agents first to discover available agents and their IDs."""
	sender_agent_id: str = Field(
		description="ID of the agent sending the message."
	)
	recipient_agent_id: Optional[str] = Field(
		default=None,
		description="ID of the recipient agent. Either this or recipient_agent_name is required."
	)
	recipient_agent_name: Optional[str] = Field(
		default=None,
		description="Name of the recipient agent. Either this or recipient_agent_id is required."
	)
	message: str = Field(
		description="The message text to send."
	)
	chat_id: Optional[str] = Field(
		default=None,
		description="Existing chat ID. If not provided, a new chat will be created."
	)
	message_type: Optional[str] = Field(
		default="text",
		description="Type of message: 'text', 'form', or 'notification'. Default: text."
	)
	async_send: Optional[bool] = Field(
		default=True,
		description="If True (default), send asynchronously. If False, wait for delivery confirmation."
	)


class ListChatAgentsAction(BaseModel):
	"""List all available agents that can receive chat messages."""
	exclude_self: Optional[str] = Field(
		default=None,
		description="Agent ID to exclude from the list (typically the calling agent's own ID)."
	)
	filter_name: Optional[str] = Field(
		default=None,
		description="Filter agents by name (partial match, case-insensitive)."
	)


class ReconfigureEventMonitorAction(BaseModel):
	"""Reconfigure the active HTTP polling event monitor with new URL patterns, content filters, or HTTP methods.
	Use this when you need to change what browser events you're listening for without restarting the browser session."""
	label: str = Field(
		default="",
		description="The monitor label to reconfigure. If empty, uses the first active monitor."
	)
	url_patterns: Optional[list[str]] = Field(
		default=None,
		description="New URL patterns to match (e.g., ['/api/poll', '/chat']). Replaces existing patterns."
	)
	content_filters: Optional[list[str]] = Field(
		default=None,
		description="New content filter substrings to match in response body (e.g., ['has_new', 'msg_id']). Replaces existing filters."
	)
	methods: Optional[list[str]] = Field(
		default=None,
		description="New HTTP methods to monitor (e.g., ['GET', 'POST']). Default: ['POST']."
	)
	min_body_length: Optional[int] = Field(
		default=None,
		description="Minimum response body length to trigger event. Default: 10."
	)
	append: bool = Field(
		default=False,
		description="If True, append to existing patterns/filters instead of replacing."
	)


class ListSessionMonitorsAction(BaseModel):
	"""List active or configured session-scoped browser event monitors."""
	include_configs: bool = Field(
		default=True,
		description="Whether to include configured monitor definitions in the response."
	)


class UpsertSessionMonitorAction(BaseModel):
	"""Create or replace a session monitor using the canonical monitor schema."""
	id: str = Field(default="", description="Stable monitor id. If empty, one is generated from label.")
	label: str = Field(description="Semantic event label, e.g. conversation_became_active")
	source_type: str = Field(default="dom_mutation", description="dom_mutation | http_polling | websocket | sse | cdp_raw")
	enabled: bool = Field(default=True, description="Whether this monitor should be active.")
	url_patterns: list[str] = Field(default_factory=list, description="Target page URL patterns.")
	methods: list[str] = Field(default_factory=list, description="HTTP methods for polling monitors.")
	content_filters: list[str] = Field(default_factory=list, description="Substring filters for body/frame matching.")
	min_body_length: int = Field(default=10, description="Minimum body length for HTTP polling.")
	frame_direction: str = Field(default="incoming", description="WebSocket frame direction.")
	sse_event_types: list[str] = Field(default_factory=list, description="SSE event names to watch.")
	dom_selector: str = Field(default="", description="Legacy DOM selector hint.")
	dom_attributes: bool = Field(default=False, description="Observe DOM attribute mutations.")
	dom_child_list: bool = Field(default=True, description="Observe DOM child list mutations.")
	dom_subtree: bool = Field(default=True, description="Observe DOM subtree mutations.")
	dom_check_interval_ms: int = Field(default=250, description="Independent DOM check interval in milliseconds.")
	cdp_domain: str = Field(default="", description="CDP domain for raw CDP monitors.")
	cdp_event_method: str = Field(default="", description="CDP event method for raw CDP monitors.")
	extractor_json: str = Field(default="", description="Advanced extractor JSON payload.")
	auto_start: bool = Field(default=True, description="Whether to restart/apply the monitor immediately.")


class RemoveSessionMonitorAction(BaseModel):
	"""Remove one configured session monitor by id or label."""
	id_or_label: str = Field(description="Monitor id or label to remove.")
	auto_restart: bool = Field(default=True, description="Restart active monitor set after removal.")


class GetSessionMonitorSnapshotAction(BaseModel):
	"""Return current capability snapshot and optional latest events."""
	include_configs: bool = Field(default=True, description="Include configured monitor definitions.")
	include_runtime: bool = Field(default=True, description="Include current runtime status and counts.")


class PersistSessionMonitorsToSkillAction(BaseModel):
	"""Persist configured session monitor definitions back into the current node's skill JSON and bundle JSON."""
	monitor_ids_or_labels: list[str] = Field(
		default_factory=list,
		description="Optional subset of monitor ids or labels to persist. Empty means persist all configured monitors."
	)
	stop_after_persist: bool = Field(
		default=False,
		description="If true, stop active monitors after persistence. Monitor definitions remain saved."
	)


class InspectDomRegionsAction(BaseModel):
	"""Inspect visible DOM regions and summarize likely repeated/interactive areas."""
	max_regions: int = Field(default=20, description="Maximum number of region summaries to return.")
	max_text_length: int = Field(default=120, description="Maximum text sample length per region.")
	include_html_hint: bool = Field(default=False, description="Whether to include compact outerHTML snippets.")


class DiscoverChatAdapterAction(BaseModel):
	"""Heuristically discover a customer-support chat adapter from the current page."""
	max_regions: int = Field(default=20, description="Maximum DOM regions to inspect during discovery.")
	prefer_selected_thread: bool = Field(default=True, description="Prefer regions that contain selected/active items.")


class NormalizePageStateAction(BaseModel):
	"""Normalize the current page into a semantic state using a provided adapter JSON."""
	adapter_json: str = Field(description="Adapter JSON produced by discover_chat_adapter or external config.")


class DiffNormalizedStateAction(BaseModel):
	"""Diff two normalized page-state JSON blobs and return semantic changes."""
	previous_state_json: str = Field(description="Previous normalized state JSON.")
	current_state_json: str = Field(description="Current normalized state JSON.")


class RagQueryAction(BaseModel):
	"""Query the local RAG knowledge base for relevant information.
	IMPORTANT: Do NOT override defaults unless explicitly asked. Defaults are tuned for fast, customer-ready answers.
	Just provide the 'query' parameter and leave everything else at defaults.
	"""
	query: str = Field(
		description="The query text to search in the knowledge base (minimum 3 characters)"
	)
	mode: Optional[str] = Field(
		default="naive",
		description="Query mode: 'naive' (vector only, fastest), 'local' (entity-based), 'global' (community-based), 'hybrid' (both), 'mix' (all methods), 'bypass' (no retrieval). Default: naive"
	)
	only_need_context: Optional[bool] = Field(
		default=False,
		description="LEAVE AS FALSE (default). Returns a polished, customer-ready answer. Setting True returns raw context chunks instead (faster but not customer-readable)."
	)
	response_type: Optional[str] = Field(
		default=None,
		description="Response format hint (e.g., 'Multiple Paragraphs', 'Bullet Points', 'Single Sentence'). Only used when only_need_context=False."
	)
	top_k: Optional[int] = Field(
		default=5,
		description="Number of top chunks to retrieve (default: 5)"
	)
	enable_rerank: Optional[bool] = Field(
		default=False,
		description="LEAVE AS FALSE (default). Reranking adds 3-8s latency. Only enable if retrieval quality is poor."
	)
	include_references: Optional[bool] = Field(
		default=True,
		description="Include source references in the response"
	)

