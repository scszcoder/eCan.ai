import os
from utils.logger_helper import logger_helper as logger
from browser_use.agent.views import ActionResult
from browser_use import BrowserSession, Controller
from agent.ec_skills.browser_use_extension.extension_tools_views import (
    FileRenameAction,
    FilesPrintAction,
)
# Create a shared controller with custom actions for browser_use
custom_controller = Controller()


@custom_controller.action('Rename a downloaded file to a new name', param_model=FileRenameAction,)
async def rename_file(params: FileRenameAction, browser_session: BrowserSession):
    logger.info(f"[Browser Use Extension]Renaming file {params.old_path} to {params.new_name}")
    if params.old_path in browser_session.downloaded_files:
        dir_path = os.path.dirname(params.old_path)
        new_path = os.path.join(dir_path, params.new_name)
        os.rename(params.old_path, new_path)
        return ActionResult(extracted_content=f"Renamed {params.old_path} to {params.new_path}")
    return ActionResult(error=f"File {params.old_path} not found in downloaded files")



@custom_controller.action('Rename a downloaded file to a new name', param_model=FileRenameAction,)
async def print_files(params: FileRenameAction, browser_session: BrowserSession):
    logger.info(f"[Browser Use Extension]Renaming file {params.old_path} to {params.new_name}")
    if params.old_path in browser_session.downloaded_files:
        dir_path = os.path.dirname(params.old_path)
        new_path = os.path.join(dir_path, params.new_name)
        os.rename(params.old_path, new_path)
        return ActionResult(extracted_content=f"Renamed {params.old_path} to {params.new_path}")
    return ActionResult(error=f"File {params.old_path} not found in downloaded files")


@custom_controller.action('Rename a downloaded file to a new name', param_model=FileRenameAction,)
async def rename_file(params: FileRenameAction, browser_session: BrowserSession):
    logger.info(f"[Browser Use Extension]Renaming file {params.old_path} to {params.new_name}")
    if params.old_path in browser_session.downloaded_files:
        dir_path = os.path.dirname(params.old_path)
        new_path = os.path.join(dir_path, params.new_name)
        os.rename(params.old_path, new_path)
        return ActionResult(extracted_content=f"Renamed {params.old_path} to {params.new_path}")
    return ActionResult(error=f"File {params.old_path} not found in downloaded files")