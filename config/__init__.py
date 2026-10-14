import sys

from utils.time_util import TimeUtil

# Diagnostics go to stderr (see utils/__init__.py): keeps stdout clean for
# scripts whose stdout is parsed (e.g. the OTA promote resolve step).
print(TimeUtil.formatted_now_with_ms() + " Initializing package config...", file=sys.stderr)
