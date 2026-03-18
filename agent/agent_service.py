from app_context import AppContext
from typing import TYPE_CHECKING, Optional
from utils.logger_helper import logger_helper as logger, get_traceback

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
    except Exception as e:
        logger.error(f"Failed to get agent by id: {agent_id}")
        logger.error(get_traceback(e))
        return None


def register_agent(agent: 'EC_Agent') -> None:
    """Register an agent with the main window.
    
    Args:
        agent: The agent instance to register
    """
    try:
        main_window = AppContext.get_main_window()
        if not main_window:
            logger.warning(f"Cannot register agent {agent.id}: main window not available")
            return
        
        if not hasattr(main_window, 'agents'):
            main_window.agents = []
        
        # Check if agent already registered
        if any(getattr(getattr(ag, 'card', None), 'id', None) == agent.id for ag in main_window.agents):
            logger.debug(f"Agent {agent.id} already registered")
            return
        
        main_window.agents.append(agent)
        logger.info(f"Registered agent: {agent.id}")
    except Exception as e:
        logger.error(f"Failed to register agent: {agent.id}")
        logger.error(get_traceback(e))


def unregister_agent(agent_id: str) -> None:
    """Unregister an agent from the main window.
    
    Args:
        agent_id: The ID of the agent to unregister
    """
    try:
        main_window = AppContext.get_main_window()
        if not main_window:
            logger.warning(f"Cannot unregister agent {agent_id}: main window not available")
            return
        
        if not hasattr(main_window, 'agents'):
            return
        
        # Remove agent from list
        original_count = len(main_window.agents)
        main_window.agents = [
            ag for ag in main_window.agents 
            if getattr(getattr(ag, 'card', None), 'id', None) != agent_id
        ]
        
        if len(main_window.agents) < original_count:
            logger.info(f"Unregistered agent: {agent_id}")
        else:
            logger.debug(f"Agent {agent_id} was not registered")
    except Exception as e:
        logger.error(f"Failed to unregister agent: {agent_id}")
        logger.error(get_traceback(e))

