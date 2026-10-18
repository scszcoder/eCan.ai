"""The URL fragment that marks eCan's own background detection tabs.

The EventMonitor opens a separate tab per live-chat site for its 新消息 poll and
stamps it with this fragment, so a later app session reusing the same browser
can recognize -- and close -- leftover detection tabs. A real store URL must
never carry it: a customer's store URL saved as ``…/workspace#ecan_det`` (copied
from a detection tab's address bar) made the agent's own main tab look like a
leftover detection tab, and the sweep closed it -- the browser exited with its
last tab (2026-10-18, two 抖店 stores: store B's Chrome dead for 8 h).
"""

DETECTION_TAB_MARKER = "#ecan_det"


def strip_detection_marker(url):
    """``url`` without a trailing detection-tab marker (anything else unchanged)."""
    if isinstance(url, str) and url.endswith(DETECTION_TAB_MARKER):
        return url[: -len(DETECTION_TAB_MARKER)]
    return url
