import os
from utils.logger_helper import logger_helper as logger
from browser_use.agent.views import ActionResult
from browser_use import BrowserSession, Controller

# Create a shared controller with custom actions for browser_use
custom_controller = Controller()


@custom_controller.action('Rename a downloaded file to a new name')
async def rename_file(old_path: str, new_name: str, browser_session: BrowserSession):
    logger.info(f"[Browser Use Extension]Renaming file {old_path} to {new_name}")
    if old_path in browser_session.downloaded_files:
        dir_path = os.path.dirname(old_path)
        new_path = os.path.join(dir_path, new_name)
        os.rename(old_path, new_path)
        return ActionResult(extracted_content=f"Renamed {old_path} to {new_path}")
    return ActionResult(error=f"File {old_path} not found in downloaded files")