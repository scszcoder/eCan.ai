import os
from utils.logger_helper import logger_helper as logger
from browser_use.agent.views import ActionResult
from browser_use import BrowserSession, Controller
from agent.ec_skills.browser_use_extension.extension_tools_views import (
    FileRenameAction,
    FilesPrintAction,
    LabelsReformatAction,
)
from agent.ec_skills.label_utils.print_label import (
    print_labels_async,
    reformat_labels_async,
)

# Create a shared controller with custom actions for browser_use
custom_controller = Controller()


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
    logger.info(f"[Browser Use Extension] Reformatting labels: {params.in_file_names}")
    
    try:
        # Parse in_file_names - could be a single file or comma-separated list
        if isinstance(params.in_file_names, str):
            in_files = [f.strip() for f in params.in_file_names.split(',') if f.strip()]
        else:
            in_files = params.in_file_names
        
        # Parse font size
        font_size = 24
        if params.added_note_font_size:
            try:
                font_size = int(params.added_note_font_size)
            except ValueError:
                font_size = 24
        
        result = await reformat_labels_async(
            in_file_names=in_files,
            out_dir=params.out_file_names if params.out_file_names else None,
            sheet_size=params.sheet_size,
            label_format=params.label_format,
            label_orientation=params.label_orientation,
            label_rows_per_sheet=params.label_rows_per_sheet,
            label_cols_per_sheet=params.label_cols_per_sheet,
            label_rows_pitch=float(params.label_rows_pitch) if params.label_rows_pitch else None,
            label_cols_pitch=float(params.label_cols_pitch) if params.label_cols_pitch else None,
            top_side_margin=float(params.top_side_margin) if params.top_side_margin else None,
            left_side_margin=float(params.left_side_margin) if params.left_side_margin else None,
            add_backup=params.add_backup,
            added_note_text=params.added_note_text,
            added_note_font_size=font_size
        )
        
        if result.success:
            msg = f"Reformatted {result.input_count} labels into {result.output_count} output files"
            if result.backup_files:
                msg += f" with {len(result.backup_files)} backup copies"
            return ActionResult(extracted_content=msg)
        else:
            return ActionResult(error=result.message)
    except Exception as e:
        logger.error(f"[Browser Use Extension] Reformat error: {e}")
        return ActionResult(error=f"Reformat failed: {str(e)}")