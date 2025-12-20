"""
Skill Build Template - Standard Interface for Dynamic Skill Loading
====================================================================

This module provides a standard `build_skill()` template for code-based skills.

## When is build_skill() used?

Currently, `build_skill()` is NOT actively used because:
1. Core skills are loaded via `build_agent_skills_parallel()` which directly calls
   async functions like `create_my_twin_chatter_skill(mainwin)`
2. This is faster and more efficient for built-in skills

## When WOULD build_skill() be used?

The `build_skill()` interface would be used if:
1. A skill is placed in `ec_skills/` directory as an external/plugin skill
2. The skill is NOT hardcoded in `build_agent_skills_parallel()`
3. The system uses `build_agent_skills_from_files()` to dynamically scan and load it

## Dynamic Loading Flow (when build_skill() IS used):

```
build_agent_skills_from_files()
    ↓
load_from_code(skill_root, code_dir)
    ↓
build_fn = getattr(mod, "build_skill")  # ← Looks for build_skill()
    ↓
built = build_fn(mainwin=mainwin)  # ← Calls it synchronously
```

## Why keep build_skill()?

1. **Future extensibility**: When we want to support user-defined skills
2. **Plugin architecture**: External skills can be dropped into ec_skills/ directory
3. **Backward compatibility**: Existing skill files won't break
4. **Standard interface**: Consistent API for all code-based skills

## Usage Example:

```python
# In your skill file (e.g., my_custom_skill.py):

async def create_my_custom_skill(mainwin):
    '''Actual skill creation logic'''
    skill = EC_Skill(name="My Custom Skill")
    # ... setup workflow, nodes, etc.
    return skill

def build_skill(run_context: dict | None = None, mainwin=None) -> EC_Skill:
    '''Standard entry point for dynamic loading'''
    return sync_to_async_bridge(create_my_custom_skill, mainwin)
```

Author: eCan.ai Team
Last Updated: 2025-10-30
"""

import asyncio
import concurrent.futures
from typing import Optional, Callable, Any
from app_context import AppContext
from agent.ec_skill import EC_Skill
from utils.logger_helper import logger_helper as logger


def sync_to_async_bridge(
    async_creator_func: Callable,
    mainwin: Any = None,
    run_context: Optional[dict] = None
) -> EC_Skill:
    """
    Bridge function to call async skill creation from sync context.
    
    This handles the complexity of running async functions in potentially
    nested event loop scenarios.
    
    Args:
        async_creator_func: The async function that creates the skill
        mainwin: MainWindow instance (will get from AppContext if None)
        run_context: Optional runtime context dictionary
        
    Returns:
        EC_Skill: The created skill instance
        
    Raises:
        Exception: If skill creation fails
        
    Example:
        >>> def build_skill(mainwin=None):
        >>>     return sync_to_async_bridge(create_my_skill, mainwin)
    """
    if mainwin is None:
        mainwin = AppContext.get_main_window()
    
    try:
        # Check if we're already in an event loop
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, but build_skill is sync
            # Create a new thread to run the async function
            logger.debug("[skill_build_template] Running in new thread (event loop detected)")
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, async_creator_func(mainwin))
                return future.result()
        except RuntimeError:
            # No event loop running, safe to use asyncio.run
            logger.debug("[skill_build_template] Running with asyncio.run (no event loop)")
            return asyncio.run(async_creator_func(mainwin))
    except Exception as e:
        logger.error(f"[skill_build_template] Failed to build skill: {e}")
        raise


def create_build_skill_function(async_creator_func: Callable) -> Callable:
    """
    Factory function to create a standard build_skill() function.
    
    This is a convenience wrapper that returns a properly configured
    build_skill function for your skill.
    
    Args:
        async_creator_func: Your async skill creation function
        
    Returns:
        Callable: A build_skill function ready to use
        
    Example:
        >>> # In your skill file:
        >>> async def create_my_skill(mainwin):
        >>>     # ... skill creation logic
        >>>     return skill
        >>> 
        >>> # Create the standard build_skill function:
        >>> build_skill = create_build_skill_function(create_my_skill)
    """
    def build_skill(run_context: dict | None = None, mainwin=None) -> EC_Skill:
        """
        Standard entry point for skill building system.
        This function is called by the skill loader to build the skill.
        
        NOTE: Currently not actively used for built-in skills.
        See module docstring for details.
        """
        return sync_to_async_bridge(async_creator_func, mainwin, run_context)
    
    return build_skill


# Example usage (for documentation):
if __name__ == "__main__":
    """
    Example: How to use this template in your skill file
    """
    
    # Step 1: Define your async skill creation function
    async def create_example_skill(mainwin):
        from langgraph.graph import StateGraph
        from langgraph.constants import END
        
        skill = EC_Skill(
            name="Example Skill",
            description="This is an example skill"
        )
        
        # Define your workflow
        workflow = StateGraph(dict)
        workflow.add_node("process", lambda state: state)
        workflow.set_entry_point("process")
        workflow.add_edge("process", END)
        
        skill.set_work_flow(workflow)
        return skill
    
    # Step 2: Create the standard build_skill function
    build_skill = create_build_skill_function(create_example_skill)
    
    # Step 3: The skill loader can now call build_skill()
    # (This would happen automatically during dynamic loading)
    print("Example template ready!")
