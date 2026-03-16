"""
Sync rules for cloud API preflight validation and permanent error classification.
"""

from typing import Any, Dict, List, Optional

from agent.cloud_api.constants import DataType, Operation
from utils.env.secure_store import get_current_username


PERMANENT_ERROR_MARKERS = (
    'forbidden',
    'not the owner',
    'unauthorized',
    'unauthenticated',
    'permission denied',
    'access denied',
)


PREFLIGHT_RULES: Dict[DataType, Dict[str, Dict[str, Any]]] = {
    DataType.SKILL: {
        Operation.ADD.value: {
            'required_fields': ('owner',),
            'owner_must_match_current_user': True,
        },
        Operation.UPDATE.value: {
            'required_fields': ('owner',),
            'owner_must_match_current_user': True,
        },
    },
}


def is_permanent_sync_error(error: Any) -> bool:
    err = str(error or '').lower()
    return any(marker in err for marker in PERMANENT_ERROR_MARKERS)


def validate_preflight(data_type: DataType, local_items: List[Dict[str, Any]], operation: str) -> Optional[str]:
    if not local_items:
        return None

    type_rules = PREFLIGHT_RULES.get(data_type, {})
    rule = type_rules.get(operation)
    if not rule:
        return None

    current_username = get_current_username()
    required_fields = tuple(rule.get('required_fields', ()) or ())
    owner_must_match = bool(rule.get('owner_must_match_current_user'))

    for item in local_items:
        item_id = item.get('id') or item.get('agid') or item.get('skid') or item.get('name') or 'UNKNOWN'

        for field in required_fields:
            value = item.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                return f"Preflight rejected {data_type.value}.{operation}: missing {field} for {item_id}"

        if owner_must_match:
            owner = (item.get('owner') or '').strip()
            if current_username and owner != current_username:
                return (
                    f"Preflight rejected {data_type.value}.{operation}: owner mismatch for {item_id} "
                    f"(owner={owner}, current_user={current_username})"
                )

    return None
