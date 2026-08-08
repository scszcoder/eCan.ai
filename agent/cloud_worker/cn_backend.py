"""CN (Tencent CloudBase) backend client for the headless cloud worker.

Speaks the cloudbase-graphql API (AppSync-compatible schema served by the TCB
SCF function) with TCB Auth JWT bearer authentication. The server enforces
owner scoping from the JWT, so the token must belong to the task owner.

Auth sources, in order:
  1. ECAN_TCB_ACCESS_TOKEN  — a ready access token (tests / short jobs)
  2. ECAN_TCB_REFRESH_TOKEN — exchanged via TCB Auth /auth/v1/token; also
     used to re-auth once when a call fails with an auth error mid-run

Endpoint: ECAN_CN_GRAPHQL_ENDPOINT env override, else CloudEndpointConfig
(apps/cn/config/auth_config.yml — requires ECAN_APP_ID=cn).
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from utils.logger_helper import logger_helper as logger

_TASK_FIELDS = (
    "id owner name description status taskType triggerType action "
    "objectives result schedule metadata"
)
_SKILL_FIELDS = "id owner name description category config diagram source path"


class CNBackendError(RuntimeError):
    pass


def _looks_like_auth_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "unauthenticated" in text or "401" in text or "jwt" in text or "token" in text


class CNBackendClient:
    def __init__(self, endpoint: str, access_token: str, refresh_token: str = ""):
        if not endpoint:
            raise CNBackendError("CN GraphQL endpoint is not configured")
        if not access_token and not refresh_token:
            raise CNBackendError(
                "No CN credentials: set ECAN_TCB_ACCESS_TOKEN or ECAN_TCB_REFRESH_TOKEN"
            )
        self.endpoint = endpoint
        self.access_token = access_token
        self._refresh_token = refresh_token
        if not self.access_token:
            self._refresh_access_token()

    @classmethod
    def from_env(cls) -> "CNBackendClient":
        endpoint = (os.getenv("ECAN_CN_GRAPHQL_ENDPOINT") or "").strip()
        if not endpoint:
            from agent.cloud_api.endpoints import get_endpoint_config

            endpoint = get_endpoint_config().graphql_endpoint
        return cls(
            endpoint=endpoint,
            access_token=(os.getenv("ECAN_TCB_ACCESS_TOKEN") or "").strip(),
            refresh_token=(os.getenv("ECAN_TCB_REFRESH_TOKEN") or "").strip(),
        )

    # ------------------------------------------------------------- auth

    def _refresh_access_token(self) -> None:
        if not self._refresh_token:
            raise CNBackendError("Access token expired and no ECAN_TCB_REFRESH_TOKEN set")
        from auth.tencent.cloudbase_auth import CloudBaseAuthService

        result = CloudBaseAuthService().refresh_token(self._refresh_token)
        data = getattr(result, "data", None) or {}
        if not getattr(result, "success", False):
            raise CNBackendError(f"TCB token refresh failed: {getattr(result, 'error', result)}")
        token = data.get("access_token") or data.get("AccessToken")
        if not token:
            raise CNBackendError(f"TCB token refresh returned no access_token: {list(data)}")
        # TCB rotates refresh tokens on use; keep the newest one for the next refresh.
        self._refresh_token = data.get("refresh_token") or self._refresh_token
        self.access_token = token
        logger.info("[cn_backend] refreshed TCB access token")

    # ---------------------------------------------------------- graphql

    async def graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            return await self._graphql_once(query, variables)
        except Exception as exc:
            if self._refresh_token and _looks_like_auth_error(exc):
                logger.warning(f"[cn_backend] auth error, refreshing token and retrying: {exc}")
                self._refresh_access_token()
                return await self._graphql_once(query, variables)
            raise

    async def _graphql_once(self, query: str, variables: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.endpoint,
                json={"query": query, "variables": variables or {}},
                headers=headers,
                timeout=60.0,
            )
            resp.raise_for_status()
            payload = resp.json()
        if isinstance(payload, dict) and payload.get("errors"):
            raise CNBackendError(json.dumps(payload["errors"], ensure_ascii=False))
        return payload.get("data") or {}

    # ------------------------------------------------------ task / skill

    async def get_task(self, task_id: str) -> Dict[str, Any]:
        data = await self.graphql(
            "query GetTask($input: TaskQueryInput) {"
            f" getAgentTasks(input: $input) {{ {_TASK_FIELDS} }} }}",
            {"input": {"id": task_id}},
        )
        tasks = data.get("getAgentTasks") or []
        if not tasks:
            raise CNBackendError(f"Task not found (or not owned by token identity): {task_id}")
        return tasks[0]

    async def get_task_skills(self, task_id: str) -> List[Dict[str, Any]]:
        """Ordered skills for a task via agent_task_skill_rels (executionOrder asc)."""
        data = await self.graphql(
            "query QTSR($qb: String) { queryTaskSkillRelations(qb: $qb) }",
            {"qb": json.dumps({"task_id": task_id})},
        )
        rels = json.loads(data.get("queryTaskSkillRelations") or "[]")
        rels.sort(key=lambda r: (r.get("executionOrder") or 0))
        skills: List[Dict[str, Any]] = []
        for rel in rels:
            skill_id = rel.get("skill_id") or rel.get("skillId")
            if not skill_id:
                continue
            sdata = await self.graphql(
                "query GetSkill($input: SkillQueryInput) {"
                f" getAgentSkills(input: $input) {{ {_SKILL_FIELDS} }} }}",
                {"input": {"id": skill_id}},
            )
            found = sdata.get("getAgentSkills") or []
            if found:
                skill = dict(found[0])
                skill["_rel"] = rel
                skills.append(skill)
        return skills

    # ----------------------------------------------------------- files

    async def file_ops(self, ops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """reqFileOp; each op: {op, names, options[, contentType, expiresIn]}.

        Returns the parsed result list: upload/download -> {op,key,url,method,
        headers}; list -> {op,prefix,objects:[{key,size,...}]}.
        """
        data = await self.graphql(
            "query FileOps($fo: [FileOp!]) { reqFileOp(fo: $fo) }",
            {"fo": ops},
        )
        return json.loads(data.get("reqFileOp") or "[]")

    async def download_prefix_to_dir(self, options: str, name: str, dest: Path) -> int:
        """Download every COS object under the prefix built from (options, name)
        into dest, preserving the relative layout. Returns file count.

        The server namespaces keys as users/{hash(owner)}/{marker path}/{name}.
        """
        listing = (await self.file_ops([{"op": "list", "names": name, "options": options}]))[0]
        prefix = listing.get("prefix", "")
        objects = listing.get("objects") or []
        count = 0
        async with httpx.AsyncClient() as client:
            for obj in objects:
                key = obj.get("key") or ""
                if not key.startswith(prefix):
                    continue
                rel = key[len(prefix):].lstrip("/")
                if not rel or rel.endswith("/"):
                    continue
                # Re-derive (options, name) for the download op from the full key:
                # everything after users/{hash}/ is marker path + filename.
                marker_path = key.split("/", 2)[2] if key.count("/") >= 2 else rel
                dl_dir, _, dl_name = marker_path.rpartition("/")
                grant = (await self.file_ops(
                    [{"op": "download", "names": dl_name, "options": dl_dir + "/"}]
                ))[0]
                resp = await client.get(grant["url"], timeout=120.0)
                resp.raise_for_status()
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(resp.content)
                count += 1
        logger.info(f"[cn_backend] downloaded {count} objects for prefix {prefix}")
        return count

    async def upload_json(self, options: str, name: str, payload: Dict[str, Any]) -> None:
        grant = (await self.file_ops([
            {"op": "upload", "names": name, "options": options, "contentType": "application/json"}
        ]))[0]
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = dict(grant.get("headers") or {})
        headers.setdefault("Content-Type", "application/json")
        async with httpx.AsyncClient() as client:
            resp = await client.put(grant["url"], content=body, headers=headers, timeout=60.0)
            resp.raise_for_status()
