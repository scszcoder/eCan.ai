import os
import json
import time
from typing import Any, Dict, List, Optional

import requests

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback


def _resolve_base_url() -> str:
    """Resolve LightRAG server base URL from environment or defaults."""
    host = os.environ.get("HOST", "127.0.0.1")
    port = os.environ.get("PORT", "9621")
    scheme = "http"
    return f"{scheme}://{host}:{port}"


class LightragClient:
    """Backend adapter to proxy LightRAG WebGUI API calls from frontend IPC.

    NOTE: This is a skeleton. Fill in implementations to call the real LightRAG
    endpoints and translate responses as needed.
    """

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, token: Optional[str] = None):
        self.base_url = base_url or _resolve_base_url()
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
        })
        if api_key:
            self.session.headers["X-API-Key"] = api_key
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        logger.info(f"[LightragClient] base_url={self.base_url}")

    # ---- Health/Auth ----
    def health(self) -> Dict[str, Any]:
        try:
            r = self.session.get(f"{self.base_url}/health", timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            err = get_traceback(e, "LightragClient.health")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    # ---- Documents ingestion ----
    def ingest_files(self, paths: List[str], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Request to vectorize and store files into the vector DB.
        Placeholder: implement upload/batch endpoints mapping.
        """
        try:
            return {"status": "not_implemented", "message": "ingest_files pending", "paths": paths}
        except Exception as e:
            err = get_traceback(e, "LightragClient.ingest_files")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    def ingest_directory(self, dir_path: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            return {"status": "not_implemented", "message": "ingest_directory pending", "dir_path": dir_path}
        except Exception as e:
            err = get_traceback(e, "LightragClient.ingest_directory")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    # ---- Query ----
    def query(self, text: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            payload = {"query": text}
            if options:
                payload.update(options)
            r = self.session.post(f"{self.base_url}/query", data=json.dumps(payload), timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            err = get_traceback(e, "LightragClient.query")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    # ---- Status / Abort ----
    def status(self, job_id: str) -> Dict[str, Any]:
        try:
            return {"status": "not_implemented", "message": "status pending", "job_id": job_id}
        except Exception as e:
            err = get_traceback(e, "LightragClient.status")
            logger.error(err)
            return {"status": "error", "message": str(e)}

    def abort(self, job_id: str) -> Dict[str, Any]:
        try:
            return {"status": "not_implemented", "message": "abort pending", "job_id": job_id}
        except Exception as e:
            err = get_traceback(e, "LightragClient.abort")
            logger.error(err)
            return {"status": "error", "message": str(e)}


# Convenience factory
def get_client(api_key: Optional[str] = None, token: Optional[str] = None) -> LightragClient:
    return LightragClient(api_key=api_key, token=token)