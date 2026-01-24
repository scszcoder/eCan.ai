import json
import os
import uuid
import urllib.request
import boto3

S3_BUCKET = os.environ.get("S3_BUCKET")
APPSYNC_API_URL = os.environ.get("APPSYNC_API_URL")
APPSYNC_API_KEY = os.environ.get("APPSYNC_API_KEY")
DEFAULT_OWNER = os.environ.get("NOTIFY_OWNER")
DEFAULT_EXPIRES = int(os.environ.get("PRESIGNED_EXPIRES", "900"))

MUTATION = """
mutation PublishAccountNotification($input: AccountNotificationInput!) {
  publishAccountNotification(input: $input) {
    id
    owner
    type
    title
    message
    payload
    created_at
  }
}
"""


def _require_env(value: str, name: str) -> str:
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _appsync_request(url: str, api_key: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as resp:
        data = resp.read().decode("utf-8")
    return json.loads(data)


def lambda_handler(event, context):
    bucket = _require_env(S3_BUCKET, "S3_BUCKET")
    appsync_url = _require_env(APPSYNC_API_URL, "APPSYNC_API_URL")
    appsync_key = _require_env(APPSYNC_API_KEY, "APPSYNC_API_KEY")

    owner = event.get("owner") or DEFAULT_OWNER
    if not owner:
        raise RuntimeError("Missing owner in event or NOTIFY_OWNER env var")

    key = event.get("key") or f"presigned-tests/{uuid.uuid4().hex}.txt"
    content_type = event.get("contentType") or event.get("content_type") or "text/plain"
    expires_in = int(event.get("expiresIn") or event.get("expires_in") or DEFAULT_EXPIRES)

    s3 = boto3.client("s3")
    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_in,
    )
    download_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )

    payload = {
        "type": "presigned_test",
        "bucket": bucket,
        "key": key,
        "contentType": content_type,
        "upload": {
            "url": upload_url,
            "method": "PUT",
            "headers": {"Content-Type": content_type},
        },
        "download": {
            "url": download_url,
            "method": "GET",
        },
    }

    variables = {
        "input": {
            "owner": owner,
            "type": "PRESIGNED_TEST",
            "title": event.get("title") or "Presigned URL Test",
            "message": event.get("message") or "Presigned upload/download links",
            "payload": json.dumps(payload),
        }
    }

    response = _appsync_request(
        appsync_url,
        appsync_key,
        {"query": MUTATION, "variables": variables, "operationName": "PublishAccountNotification"},
    )

    return {
        "statusCode": 200,
        "payload": payload,
        "appsyncResponse": response,
    }
