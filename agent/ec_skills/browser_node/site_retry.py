"""Run a browser step again, later in the same run, when the site itself failed.

At 04:15 on 2026-11-26 Shopify's admin showed a technical error and then only loading
placeholders; the label step gave up after one reload, the run went on without the day's
label, and the owner had to run it again. A step whose answer says ``"retry_later": true``
(the site did not load, showed an error page or was down; never a refusal or missing data)
is run again after a pause.
"""
import json
import re
from typing import Any, Optional

RETRIES = 2
WAITS = (120, 300)          # seconds before the 1st and 2nd retry


def answer_of(result: Any) -> dict:
    """The step's final answer as a dict ({} when it is not JSON)."""
    final = result.get("final") if isinstance(result, dict) else None
    if isinstance(final, dict):
        return final
    m = re.search(r"\{.*\}", str(final or ""), re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def retry_wait(result: Any, retries_done: int) -> Optional[int]:
    """Seconds to wait before running the step again, or None to keep this result."""
    if retries_done >= RETRIES or answer_of(result).get("retry_later") is not True:
        return None
    return WAITS[min(retries_done, len(WAITS) - 1)]
