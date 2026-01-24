# Minimal logger_helper.py for Lambda deployment
# Replaces the full version which has colorlog/config dependencies that
# try to create directories (read-only in Lambda)
import logging
import sys

# Setup basic logging for Lambda
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Create a simple logger instance that mimics the original API
logger_helper = logging.getLogger('skill_editor_lambda')
logger_helper.setLevel(logging.INFO)

# Add trace level for compatibility
TRACE_LEVEL_NUM = 5
logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")

def trace(self, message, *args, **kws):
    if self.isEnabledFor(TRACE_LEVEL_NUM):
        self._log(TRACE_LEVEL_NUM, message, args, **kws)
logging.Logger.trace = trace
