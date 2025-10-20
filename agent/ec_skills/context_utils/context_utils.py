# context utility functions
import json
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback


# this function builds context for an llm call.
def context_builder():
    logger.debug("context_builder: placeholder executed")