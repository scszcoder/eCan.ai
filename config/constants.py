# APP_NAME is resolved at module load time from apps/{ECAN_APP_ID}/config/app_manifest.json
# via utils.app_config_loader (single source of truth).
# Falls back to 'eCan' (Intl name) when manifest is unavailable.
try:
    import os as _os
    from utils.app_config_loader import AppConfigLoader
    APP_NAME = AppConfigLoader(_os.environ.get('ECAN_APP_ID', 'intl')).app_short_name
except Exception:
    APP_NAME = 'eCan'

RESOURCE = "resource"
FOLDER_DATA = "data"
FOLDER_RUNLOGS = "runlogs"
FOLDER_SETTINGS = "settings"
FOLDER_SKILLS = "skills"
API_DEV_MODE = False

# Timeout settings (in seconds)
# Default timeout for most API calls
DEFAULT_API_TIMEOUT = 60.0
# Extended timeout for slow cloud API calls (e.g., api_ecan_ai_query_components)
EXTENDED_API_TIMEOUT = 120.0