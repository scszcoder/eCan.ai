import os
import shutil
import subprocess
import urllib.request
from typing import Any, Dict, Optional
from utils.logger_helper import logger_helper as logger
from browser_use.agent.views import ActionResult
from browser_use import BrowserSession, Controller
from agent.mcp.server.code_utils.code_tools import run_code, run_shell_script
from agent.ec_skills.browser_use_extension.extension_tools_views import (
    ConvertFileFormatAction,
    DownloadFileAction,
    ExtractDomAction,
    FileRenameAction,
    FilesPrintAction,
    LabelInputFile,
    LabelsReformatAction,
    RagQueryAction,
    RunCodeAction,
    RunShellScriptAction,
)
from agent.ec_skills.label_utils.print_label import (
    print_labels_async,
    reformat_labels_async,
)

from app_context import AppContext

# Create a shared controller with custom actions for browser_use
custom_controller = Controller()

# Global registry to track current agent instance for file path authorization
_current_agent_instance = None

def set_current_agent(agent):
    """Set the current agent instance for file path authorization."""
    global _current_agent_instance
    _current_agent_instance = agent
    logger.debug(f"[ExtensionTools] Set current agent instance: {type(agent).__name__}")

def get_current_agent():
    """Get the current agent instance."""
    return _current_agent_instance


def _authorize_output_files_for_upload(file_paths: list[str]) -> None:
    """Allow converted files to be uploaded by browser-use upload tools."""
    if not file_paths:
        return
    agent = get_current_agent()
    if not agent or not hasattr(agent, "available_file_paths"):
        return
    if agent.available_file_paths is None:
        agent.available_file_paths = []
    for path in file_paths:
        if path not in agent.available_file_paths:
            agent.available_file_paths.append(path)


@custom_controller.action(
    "Download a remote file to a local path. Use for saving images or assets from URLs.",
    param_model=DownloadFileAction,
)
async def download_file(params: DownloadFileAction) -> ActionResult:
    url = (params.url or "").strip()
    path = (params.path or "").strip()
    if not url:
        return ActionResult(error="download_file: url is required")
    if not path:
        return ActionResult(error="download_file: path is required")

    try:
        out_dir = os.path.dirname(path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        # Some sources block requests without UA.
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 eCan-AI downloader"},
        )
        with urllib.request.urlopen(req, timeout=float(params.timeout or 30.0)) as r:
            data = r.read()
        with open(path, "wb") as wf:
            wf.write(data)

        _authorize_output_files_for_upload([path])
        return ActionResult(
            extracted_content=f"Downloaded file successfully: {url} -> {path} ({len(data)} bytes)"
        )
    except Exception as e:
        return ActionResult(error=f"download_file failed: {e}")


def _build_target_path(src: str, target_format: str, output_dir: Optional[str]) -> str:
    base_name = os.path.splitext(os.path.basename(src))[0]
    out_dir = output_dir or os.path.dirname(src)
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"{base_name}_converted.{target_format.lower()}")


def _normalize_ext(ext: str) -> str:
    e = (ext or "").strip().lower().lstrip(".")
    aliases = {
        "jpeg": "jpg",
        "markdown": "md",
    }
    return aliases.get(e, e)


def _collect_source_files(directory: str, source_format: str) -> list[str]:
    src_files: list[str] = []
    sf = _normalize_ext(source_format)
    for root, _, files in os.walk(directory):
        for name in files:
            ext = _normalize_ext(os.path.splitext(name)[1])
            if ext == sf:
                src_files.append(os.path.join(root, name))
    return src_files


def _convert_image_with_pillow(src: str, dst: str, target_format: str, quality: int) -> None:
    from PIL import Image  # type: ignore

    img = Image.open(src)
    fmt = target_format.upper()
    if fmt in ("JPG", "JPEG"):
        # JPEG cannot store alpha channel
        img = img.convert("RGB")
        img.save(dst, "JPEG", quality=quality)
        return
    if fmt == "PNG":
        img.save(dst, "PNG")
        return
    if fmt == "WEBP":
        img.save(dst, "WEBP", quality=quality)
        return
    raise ValueError(f"Unsupported image target format with Pillow: {target_format}")


def _convert_image_with_sips(src: str, dst: str, target_format: str) -> None:
    # macOS fallback converter when Pillow is unavailable.
    # sips supports common image conversions.
    cmd = ["sips", "-s", "format", target_format.lower(), src, "--out", dst]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "sips conversion failed")


@custom_controller.action(
    "Convert one or more files to a target format. Use this when user asks things like "
    "'convert webp to jpg', 'turn png into jpg', 'convert all webp in a folder', "
    "or 'change file format'.",
    param_model=ConvertFileFormatAction,
)
async def convert_file_format(params: ConvertFileFormatAction) -> ActionResult:
    target_format = _normalize_ext(params.target_format or "")
    if not target_format:
        return ActionResult(error="target_format is required")

    source_files = list(params.source_files or [])
    if not source_files and params.directory and params.source_format:
        source_files = _collect_source_files(params.directory, params.source_format)
    if not source_files:
        return ActionResult(
            error=(
                "No source files provided. "
                "Pass source_files, or pass both directory and source_format."
            )
        )

    quality = max(1, min(100, int(params.quality or 90)))
    success_rows: list[str] = []
    error_rows: list[str] = []
    produced_files: list[str] = []

    image_exts = {"jpg", "jpeg", "png", "webp", "bmp", "gif", "tiff", "heic"}

    for src in source_files:
        try:
            if not os.path.exists(src):
                error_rows.append(f"{src} -> NOT_FOUND")
                continue

            src_ext = _normalize_ext(os.path.splitext(src)[1])
            dst = _build_target_path(src, target_format, params.output_dir)

            if src_ext in image_exts and target_format in {"jpg", "jpeg", "png", "webp"}:
                try:
                    _convert_image_with_pillow(src, dst, target_format, quality)
                except Exception:
                    # Fallback for environments without Pillow.
                    _convert_image_with_sips(src, dst, target_format)
            elif src_ext in {"txt", "md"} and target_format in {"txt", "md"}:
                # Plain-text conversions (txt<->md) are content-preserving.
                with open(src, "r", encoding="utf-8", errors="ignore") as rf:
                    content = rf.read()
                with open(dst, "w", encoding="utf-8") as wf:
                    wf.write(content)
            else:
                # Generic fallback: copy when same format was requested.
                # Keeps the extension API generic while clearly reporting unsupported transforms.
                if src_ext == target_format:
                    shutil.copy2(src, dst)
                else:
                    raise ValueError(f"Unsupported conversion: {src_ext} -> {target_format}")

            if not params.keep_original and src != dst:
                try:
                    os.remove(src)
                except Exception:
                    pass

            produced_files.append(dst)
            success_rows.append(f"{src} -> {dst}")
        except Exception as e:
            error_rows.append(f"{src} -> ERROR: {e}")

    _authorize_output_files_for_upload(produced_files)

    if success_rows and not error_rows:
        return ActionResult(
            extracted_content="Conversion completed:\n" + "\n".join(success_rows)
        )
    if success_rows and error_rows:
        return ActionResult(
            extracted_content=(
                "Conversion partially completed.\n"
                "Succeeded:\n" + "\n".join(success_rows) + "\n\n"
                "Failed:\n" + "\n".join(error_rows)
            )
        )
    return ActionResult(error="All conversions failed:\n" + "\n".join(error_rows))

@custom_controller.action(
    "Execute Python code in a sandboxed environment. Use 'result' variable to return a value.",
    param_model=RunCodeAction,
)
async def bu_run_code(params: RunCodeAction) -> ActionResult:
    config: Dict[str, Any] = {"code": params.code, "language": "python"}
    if params.args is not None:
        config["args"] = params.args
    if params.timeout is not None:
        config["timeout"] = params.timeout
    if params.allowed_imports is not None:
        config["allowed_imports"] = params.allowed_imports

    login = AppContext.login
    result = run_code(login.main_win, config)

    if result.get("success"):
        parts = [f"Code executed successfully in {result.get('execution_time_ms', 0)}ms"]
        if result.get("stdout"):
            parts.append(f"\nOutput:\n{result['stdout']}")
        if result.get("return_value") is not None:
            parts.append(f"\nReturn value: {result['return_value']}")
        return ActionResult(extracted_content="\n".join(parts))
    else:
        error_msg = f"Code execution failed: {result.get('error', 'Unknown error')}"
        if result.get("stderr"):
            error_msg += f"\nStderr:\n{result['stderr']}"
        return ActionResult(error=error_msg)



@custom_controller.action(
    "Execute a shell script. Auto-detects OS shell (PowerShell/bash/zsh).",
    param_model=RunShellScriptAction,
)
async def bu_run_shell_script(params: RunShellScriptAction) -> ActionResult:
    config: Dict[str, Any] = {"script": params.script}
    if params.shell is not None:
        config["shell"] = params.shell
    if params.timeout is not None:
        config["timeout"] = params.timeout
    if params.working_dir is not None:
        config["working_dir"] = params.working_dir
    if params.env_vars is not None:
        config["env_vars"] = params.env_vars

    login = AppContext.login
    result = run_shell_script(login.main_win, config)

    if result.get("success"):
        parts = [
            f"Script executed successfully on {result.get('os', 'unknown')} "
            f"using {result.get('shell', 'unknown')} in {result.get('execution_time_ms', 0)}ms"
        ]
        if result.get("stdout"):
            stdout = result['stdout'][:2000]
            if len(result['stdout']) > 2000:
                stdout += "\n... (truncated)"
            parts.append(f"\nOutput:\n{stdout}")
        return ActionResult(extracted_content="\n".join(parts))
    else:
        error_msg = f"Script failed (exit code {result.get('return_code', -1)})"
        if result.get("error"):
            error_msg += f": {result['error']}"
        if result.get("stderr"):
            stderr = result['stderr'][:2000]
            if len(result['stderr']) > 2000:
                stderr += "\n... (truncated)"
            error_msg += f"\nStderr:\n{stderr}"
        return ActionResult(error=error_msg)


@custom_controller.action("List all files in a directory recursively, returning file names and sizes.")
async def list_files(directory: str) -> str:
    results = []
    file_paths = []
    for root, dirs, files in os.walk(directory):
        for f in files:
            path = os.path.join(root, f)
            size = os.path.getsize(path)
            ext = os.path.splitext(f)[1].lower()
            if ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'):
                file_type = "image"
            elif ext in ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'):
                file_type = "document"
            else:
                file_type = "text"
            results.append(f"{path} ({size} bytes, {file_type})")
            file_paths.append(path)
    
    # Auto-authorize all discovered files for upload_file action
    if file_paths:
        agent = get_current_agent()
        if agent and hasattr(agent, 'available_file_paths'):
            if agent.available_file_paths is None:
                agent.available_file_paths = []
            # Add new paths that aren't already in the list
            added_count = 0
            for path in file_paths:
                if path not in agent.available_file_paths:
                    agent.available_file_paths.append(path)
                    added_count += 1
            logger.info(f"[list_files] Auto-authorized {added_count} new file paths (total: {len(agent.available_file_paths)})")
            logger.debug(f"[list_files] Available paths: {agent.available_file_paths}")
        else:
            logger.warning(f"[list_files] Cannot auto-authorize files: agent={agent is not None}, has_attr={hasattr(agent, 'available_file_paths') if agent else False}")
    
    return "\n".join(results)

@custom_controller.action('Rename a downloaded file to a new name', param_model=FileRenameAction)
async def rename_file(params: FileRenameAction, browser_session: BrowserSession):
    logger.info(f"[Browser Use Extension] Renaming file {params.old_path} to {params.new_name}")
    if params.old_path in browser_session.downloaded_files:
        dir_path = os.path.dirname(params.old_path)
        new_path = os.path.join(dir_path, params.new_name)
        os.rename(params.old_path, new_path)
        return ActionResult(extracted_content=f"Renamed {params.old_path} to {new_path}")
    return ActionResult(error=f"File {params.old_path} not found in downloaded files")


@custom_controller.action('Print label files to a specified printer. Supports PDF, PNG, JPG files.', param_model=FilesPrintAction)
async def print_labels(params: FilesPrintAction, browser_session: BrowserSession):
    logger.info(f"[Browser Use Extension] Printing {len(params.file_names)} files to printer: {params.printer or 'default'}")
    
    try:
        result = await print_labels_async(
            files=params.file_names,
            printer_name=params.printer if params.printer else None,
            n_copies=params.n_copies
        )
        
        if result.status.value == "success":
            return ActionResult(
                extracted_content=f"Successfully printed {len(result.printed_files)} files to {result.printer_used}"
            )
        elif result.status.value == "partial":
            return ActionResult(
                extracted_content=f"Partial success: {len(result.printed_files)} printed, {len(result.failed_files)} failed. {result.message}"
            )
        else:
            return ActionResult(error=result.message)
    except Exception as e:
        logger.error(f"[Browser Use Extension] Print error: {e}")
        return ActionResult(error=f"Print failed: {str(e)}")


@custom_controller.action('Reformat label PDFs to fit on multi-label sheets with configurable layout and optional backup copies', param_model=LabelsReformatAction)
async def reformat_labels(params: LabelsReformatAction, browser_session: BrowserSession):
    logger.info(f"[Browser Use Extension] Reformatting {len(params.in_files)} label files")
    
    try:
        # Convert LabelInputFile objects to dicts for the utility function
        in_files = [
            {
                "file_name": f.file_name,
                "added_note_text": f.added_note_text,
                "added_note_font": f.added_note_font if f.added_note_font else None,
                "added_note_size": f.added_note_size
            }
            for f in params.in_files
        ]
        
        result = await reformat_labels_async(
            in_files=in_files,
            out_dir=params.out_dir if params.out_dir else None,
            sheet_width=params.sheet_width,
            sheet_height=params.sheet_height,
            label_width=params.label_width,
            label_height=params.label_height,
            label_orientation=params.label_orientation,
            label_rows_per_sheet=params.label_rows_per_sheet,
            label_cols_per_sheet=params.label_cols_per_sheet,
            label_rows_pitch=params.label_rows_pitch if params.label_rows_pitch > 0 else None,
            label_cols_pitch=params.label_cols_pitch if params.label_cols_pitch > 0 else None,
            top_side_margin=params.top_side_margin if params.top_side_margin > 0 else None,
            left_side_margin=params.left_side_margin if params.left_side_margin > 0 else None,
            add_backup=params.add_backup
        )
        
        if result.success:
            msg = f"Reformatted {result.input_count} labels into {result.output_count} output files"
            if params.add_backup:
                msg += " (with backup copies on same sheet)"
            return ActionResult(extracted_content=msg)
        else:
            return ActionResult(error=result.message)
    except Exception as e:
        logger.error(f"[Browser Use Extension] Reformat error: {e}")
        return ActionResult(error=f"Reformat failed: {str(e)}")


@custom_controller.action(
    "Query the local RAG knowledge base for relevant information from ingested documents.",
    param_model=RagQueryAction,
)
async def bu_rag_query(params: RagQueryAction) -> ActionResult:
    """Query the RAG knowledge base using the existing MCP tool.
    
    Defaults optimized for real-time customer support (<12s budget):
    - mode=naive (vector retrieval only, ~1-2s)
    - only_need_context=True (skip LightRAG LLM generation, saves 15-20s)
    - top_k=5, enable_rerank=False
    The calling LLM synthesizes the answer from the returned context chunks.
    """
    import time
    _t0 = time.perf_counter()
    try:
        from agent.ec_skills.rag.local_rag_mcp import rag_query
        
        # Build input dict for MCP tool
        input_data = {
            "query": params.query,
            "mode": params.mode or "naive",
        }
        
        # Add optional parameters
        if params.only_need_context is not None:
            input_data["only_need_context"] = params.only_need_context
        if params.response_type is not None:
            input_data["response_type"] = params.response_type
        if params.top_k is not None:
            input_data["top_k"] = params.top_k
        if params.enable_rerank is not None:
            input_data["enable_rerank"] = params.enable_rerank
        if params.include_references is not None:
            input_data["include_references"] = params.include_references
        
        # Call MCP tool
        login = AppContext.login
        result_list = await rag_query(login.main_win, {"input": input_data})
        
        _elapsed = time.perf_counter() - _t0
        
        # Extract result from TextContent
        if result_list and len(result_list) > 0:
            text_content = result_list[0]
            result_text = text_content.text
            
            # Check if it's an error
            if result_text.startswith("Error:"):
                logger.warning(f"[bu_rag_query] RAG error in {_elapsed:.2f}s: {result_text[:200]}")
                return ActionResult(error=result_text)
            
            # Truncate very long context to keep LLM prompt manageable
            if len(result_text) > 8000:
                result_text = result_text[:8000] + "\n... (context truncated for speed)"
            
            logger.info(f"[bu_rag_query] RAG query completed in {_elapsed:.2f}s (mode={params.mode}, context_only={params.only_need_context}, chars={len(result_text)})")
            return ActionResult(extracted_content=result_text)
        else:
            logger.warning(f"[bu_rag_query] No result in {_elapsed:.2f}s")
            return ActionResult(error="No result returned from RAG query")
            
    except Exception as e:
        _elapsed = time.perf_counter() - _t0
        logger.error(f"[bu_rag_query] RAG query error in {_elapsed:.2f}s: {e}")
        return ActionResult(error=f"RAG query failed: {str(e)}")


@custom_controller.action(
    'Extract raw DOM/markdown content from the current page. Returns webpage content for cloud-side analysis without requiring local LLM.',
    param_model=ExtractDomAction
)
async def extract_dom(params: ExtractDomAction, browser_session: BrowserSession):
    """Extract raw markdown content from the current page without LLM analysis.
    
    This action is used in passive mode where the cloud agent will analyze the content.
    It extracts the same content that browser-use's extract action would feed to an LLM,
    but returns it raw for the cloud to process.
    """
    MAX_CHAR_LIMIT = 30000
    query = params.query or ""
    extract_links = params.extract_links
    start_from_char = params.start_from_char or 0

    try:
        from browser_use.dom.markdown_extractor import extract_clean_markdown
        content, content_stats = await extract_clean_markdown(
            browser_session=browser_session, extract_links=extract_links
        )
    except Exception as e:
        logger.error(f"[extract_dom] Failed to extract markdown: {e}", exc_info=True)
        return ActionResult(error=f"Could not extract clean markdown: {type(e).__name__}: {e}")

    final_filtered_length = content_stats.get("final_filtered_chars", len(content))

    if start_from_char > 0:
        if start_from_char >= len(content):
            return ActionResult(
                error=f"start_from_char ({start_from_char}) exceeds content length {final_filtered_length} characters."
            )
        content = content[start_from_char:]
        content_stats["started_from_char"] = start_from_char

    # Smart truncation with context preservation
    truncated = False
    if len(content) > MAX_CHAR_LIMIT:
        truncate_at = MAX_CHAR_LIMIT
        # Look for paragraph break within last 500 chars of limit
        paragraph_break = content.rfind("\n\n", MAX_CHAR_LIMIT - 500, MAX_CHAR_LIMIT)
        if paragraph_break > 0:
            truncate_at = paragraph_break
        else:
            # Look for sentence break within last 200 chars of limit
            sentence_break = content.rfind(".", MAX_CHAR_LIMIT - 200, MAX_CHAR_LIMIT)
            if sentence_break > 0:
                truncate_at = sentence_break + 1
        content = content[:truncate_at]
        truncated = True
        next_start = (start_from_char or 0) + truncate_at
        content_stats["truncated_at_char"] = truncate_at
        content_stats["next_start_char"] = next_start

    # Build stats summary (same format as browser-use)
    original_html_length = content_stats.get("original_html_chars", 0)
    initial_markdown_length = content_stats.get("initial_markdown_chars", 0)
    chars_filtered = content_stats.get("filtered_chars_removed", 0)

    stats_summary = f"Content processed: {original_html_length:,} HTML chars → {initial_markdown_length:,} initial markdown → {final_filtered_length:,} filtered markdown"
    if start_from_char > 0:
        stats_summary += f" (started from char {start_from_char:,})"
    if truncated:
        stats_summary += f" → {len(content):,} final chars (truncated, use start_from_char={content_stats['next_start_char']} to continue)"
    elif chars_filtered > 0:
        stats_summary += f" (filtered {chars_filtered:,} chars of noise)"

    try:
        current_url = await browser_session.get_current_page_url()
    except Exception:
        current_url = "unknown"

    # Return raw content in same format as browser-use's extract action LLM input
    extracted_content = (
        f"<url>\n{current_url}\n</url>\n"
        f"<query>\n{query}\n</query>\n"
        f"<content_stats>\n{stats_summary}\n</content_stats>\n"
        f"<webpage_content>\n{content}\n</webpage_content>"
    )

    logger.info(f"[extract_dom] Extracted {len(content):,} chars from {current_url}")

    return ActionResult(
        extracted_content=extracted_content,
        include_in_memory=True,
        long_term_memory=f"Extracted raw markdown for query: {query}",
    )


# Log registered custom actions at module load time for debugging
try:
    # Access the actions dict from registry.registry.actions (current browser-use API)
    action_registry = custom_controller.registry.registry.actions
    action_names = list(action_registry.keys())
    logger.info(f"[Browser-Use Extension] Registered {len(action_registry)} custom actions: {action_names}")

    # Startup self-check: ensure critical actions are loaded in current process.
    required_actions = ["download_file", "convert_file_format"]
    missing_actions = [a for a in required_actions if a not in action_names]
    if missing_actions:
        logger.error(
            "[Browser-Use Extension] Startup self-check FAILED. "
            f"Missing actions: {missing_actions}. "
            "Please restart main.py to load latest extension actions."
        )
    else:
        logger.info(
            "[Browser-Use Extension] Startup self-check OK. "
            f"Critical actions loaded: {required_actions}"
        )
except AttributeError:
    logger.warning("[Browser-Use Extension] Could not access registry actions - API may have changed")
