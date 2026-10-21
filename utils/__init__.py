import sys

from utils.time_util import TimeUtil

# Diagnostics go to stderr: this banner prints on import, and a build/CI
# script whose stdout is parsed as JSON (e.g. set_rollout.py in the OTA
# promote step) breaks if it lands on stdout.
print(TimeUtil.formatted_now_with_ms() + " Initializing package utils...", file=sys.stderr)
