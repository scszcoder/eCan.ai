import os
from utils.logger_helper import logger_helper as logger
from browser_use.agent.views import ActionResult
from browser_use import BrowserSession, Controller
from agent.ec_skills.browser_use_extension.extension_tools_views import (
    ExtractDomAction,
    FileRenameAction,
    FilesPrintAction,
    LabelInputFile,
    LabelsReformatAction,
)
from agent.ec_skills.label_utils.print_label import (
    print_labels_async,
    reformat_labels_async,
)

# Create a shared controller with custom actions for browser_use
custom_controller = Controller()


@custom_controller.action("List all files in a directory recursively, returning file names and sizes.")
def list_files(directory: str) -> str:
    results = []
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
