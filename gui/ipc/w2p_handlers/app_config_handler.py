"""App configuration IPC handler.

Returns the runtime app config payload. Mirrors web_server.py's
GET /api/config shape so the frontend can use the same normalization in
both modes (desktop → IPC, web deployment → HTTP). See
gui_v2/src/contexts/AppConfigContext.tsx for the consumer.

Public fields only — never include any SECRET_* values.

IPC method: getAppConfig
  params: {} (none)
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_success_response


def _build_app_config() -> Dict[str, Any]:
    """Build the AppConfig payload."""
    from utils.app_env import get_app_id, is_cn as _is_cn

    app_id = get_app_id()
    is_cn_flag = _is_cn()

    cloudbase_env_id = ""
    wechat_app_id = ""
    cognito_domain = ""
    cognito_client_id = ""
    graphql_endpoint = ""
    try:
        from auth.auth_config import AuthConfig
        if is_cn_flag:
            cb = AuthConfig.CLOUDBASE
            cloudbase_env_id = getattr(cb, "ENV_ID", "") or ""
            wx = AuthConfig.WECHAT
            wechat_app_id = getattr(wx, "APP_ID", "") or ""
            app_sync = AuthConfig.APPSYNC
            graphql_endpoint = getattr(app_sync, "GRAPHQL_ENDPOINT", "") or ""
        else:
            cog = AuthConfig.COGNITO
            cognito_domain = getattr(cog, "DOMAIN", "") or ""
            cognito_client_id = getattr(cog, "CLIENT_ID", "") or ""
    except Exception:
        pass

    return {
        "app_id": app_id,
        "is_cn": is_cn_flag,
        "auth_type": "cloudbase" if is_cn_flag else "cognito",
        "auth": {
            "cloudbase_env_id": cloudbase_env_id,
            "wechat_app_id": wechat_app_id,
            "cognito_domain": cognito_domain,
            "cognito_client_id": cognito_client_id,
        },
        "cloud": {
            "graphql_endpoint": graphql_endpoint,
        },
    }


@IPCHandlerRegistry.handler("getAppConfig")
def handle_get_app_config(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Return the runtime app config."""
    return create_success_response(request, _build_app_config())