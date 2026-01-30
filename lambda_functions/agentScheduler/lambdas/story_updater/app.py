import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

ALLOWED_STATUSES = {
    "DRAFT",
    "GENERATING",
    "READY",
    "PLAYING",
    "PAUSED",
    "COMPLETED",
}

_TABLE_NAME = os.environ.get("STORY_TABLE_NAME")
if not _TABLE_NAME:
    raise RuntimeError("STORY_TABLE_NAME environment variable must be set for the story updater Lambda")

dynamodb = boto3.resource("dynamodb")
TABLE = dynamodb.Table(_TABLE_NAME)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_input(event: Dict[str, Any]) -> Dict[str, Any]:
    arguments = (event or {}).get("arguments") or {}
    story_input = arguments.get("input") or {}
    story_id = story_input.get("id")
    acct_site_id = story_input.get("acctSiteID")

    if not story_id:
        raise ValueError("updateStory requires an input.id value")

    if not acct_site_id:
        identity_claims = ((event or {}).get("identity") or {}).get("claims") or {}
        acct_site_id = identity_claims.get("acctSiteID")

    if not acct_site_id:
        raise ValueError("updateStory requires acctSiteID either in the input payload or in the caller identity claims")

    return {**story_input, "id": story_id, "acctSiteID": acct_site_id}


def _build_update_expression(payload: Dict[str, Any]) -> Dict[str, Any]:
    update_fields: Dict[str, Any] = {
        key: value
        for key, value in payload.items()
        if key not in {"id", "acctSiteID"} and value is not None
    }

    update_fields["updated_at"] = _iso_now()

    status = update_fields.get("status")
    if status and status not in ALLOWED_STATUSES:
        raise ValueError(f"Invalid StoryStatus '{status}'. Allowed values: {sorted(ALLOWED_STATUSES)}")

    if not update_fields:
        raise ValueError("No updatable fields were provided in updateStory input")

    expression_parts = []
    expr_attr_names: Dict[str, str] = {}
    expr_attr_values: Dict[str, Any] = {}

    for index, (field_name, field_value) in enumerate(update_fields.items()):
        name_key = f"#f{index}"
        value_key = f":v{index}"
        expression_parts.append(f"{name_key} = {value_key}")
        expr_attr_names[name_key] = field_name
        expr_attr_values[value_key] = field_value

    return {
        "UpdateExpression": "SET " + ", ".join(expression_parts),
        "ExpressionAttributeNames": expr_attr_names,
        "ExpressionAttributeValues": expr_attr_values,
    }


def lambda_handler(event, _context):
    try:
        payload = _extract_input(event)
        key = {"acctSiteID": payload["acctSiteID"], "id": payload["id"]}
        update_context = _build_update_expression(payload)

        response = TABLE.update_item(
            Key=key,
            ReturnValues="ALL_NEW",
            **update_context,
        )

        updated_attributes = response.get("Attributes")
        if not updated_attributes:
            raise RuntimeError("Missing updated attributes in DynamoDB response")

        return updated_attributes

    except (ValueError, ClientError) as exc:
        error_message = getattr(exc, "response", {}).get("Error", {}).get("Message") if isinstance(exc, ClientError) else str(exc)
        raise Exception(json.dumps({"message": error_message})) from exc
