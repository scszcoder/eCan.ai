import os
from utils.logger_helper import logger_helper as logger
from browser_use.agent.views import ActionResult
from browser_use import BrowserSession, Controller
from agent.ec_skills.browser_use_extension.extension_tools_views import (
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
