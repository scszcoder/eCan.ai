from app_context import AppContext
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from agent.ec_agent import EC_Agent

def get_agent_by_id(agent_id) -> Optional['EC_Agent']:
    """Safely fetch agent by id from the current main window.
    Returns None if main window or agents are not yet initialized.
    """
    try:
        main_window = AppContext.get_main_window()
        if not main_window:
            return None
        agents = main_window.agents
        return next((ag for ag in agents if getattr(getattr(ag, 'card', None), 'id', None) == agent_id), None)
    except Exception:
        return None

