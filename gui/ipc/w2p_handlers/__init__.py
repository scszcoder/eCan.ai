import pkgutil
import importlib

# Dynamically import all modules in current package to ensure all handlers are registered
for loader, name, is_pkg in pkgutil.walk_packages(__path__):
    importlib.import_module('.' + name, __name__)

# Ensure key handlers are explicitly imported (walk_packages may miss new files in some packaging/runtime environments)
try:
    from . import node_state_schema_handler  # noqa: F401
    from . import agent_handler  # noqa: F401 - Ensure agent_handler is imported
    from . import skill_handler  # noqa: F401 - Ensure skill_handler is imported (new_skill/save_skill)
    from . import file_handlers  # noqa: F401 - Ensure file_handlers is imported (read/write/dialog)
except Exception:
    pass
