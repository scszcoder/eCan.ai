# One set of operations: GUI, CLI and the copilot

Everything the app can do is an **IPC handler**: a method name plus a params dict,
registered in `gui/ipc/w2p_handlers/*` through `IPCHandlerRegistry`. The method
names and params are the contract. Every front end calls the same handlers, so
there is one implementation of each operation:

| Caller | Where it runs | How it calls a handler |
|---|---|---|
| GUI (gui_v2) | the app | the app's local server, `POST /graphql`, login token |
| `ecan` CLI | its own process | the app's local server, `POST /graphql`, the per-start local key (below) |
| **System copilot agent** | **inside the app** | **in-process, by method name: no key, no HTTP** |

## The copilot: call handlers in-process

The copilot runs inside the app, so it calls a handler directly. It does not go
through the CLI or the local server:

```python
from gui.ipc.registry import IPCHandlerRegistry

def call_handler(method: str, params: dict | None = None):
    found = IPCHandlerRegistry.get_handler(method)
    if not found:
        raise LookupError(f"no handler {method}")
    handler, _kind = found          # 'background' handlers block: run them off the event loop
    request = {"id": f"copilot_{method}", "method": method, "params": params or {}, "source": "local_server"}
    resp = handler(request, params or {})
    if resp.get("status") != "success":
        err = resp.get("error") or {}
        raise RuntimeError(f"{err.get('code')}: {err.get('message')}")
    return resp.get("result")
```

`source: "local_server"` marks an in-process call. The registry trusts it
(desktop mode), and `resolve_username` takes the signed-in user from the main
window.

To find out what a CLI command does, look at the handler it calls. Each one
below is also a copilot tool.

## The CLI: the local key

- When its local server is up, the app writes `{pid, port, secret}` to
  `<app data>/local_api/<instance>.json` (`utils/local_api.py`). The secret is
  new on every start, and the file is removed on a clean stop.
- `gui/ipc/registry.py::_validate_token` accepts that secret as well as the
  GUI's login tokens.
- `cli/base/app_client.py` reads the file and posts
  `{"query": "", "variables": params, "extensions": {"method": m}}` with
  `Authorization: Bearer <secret>`. A success reply is `{"data": {m: result}}`;
  an error reply (still HTTP 200) is
  `{"errors": [{"message", "extensions": {"code", "details"}}]}`.
- Security: the server listens on 127.0.0.1 unless `ECAN_ALLOW_REMOTE` is set.
  The file sits in the user's own app data folder, next to the database. Any
  program running as that OS user can drive the app through it.
  `ECAN_LOCAL_API=0` turns this off.

**Edits:** `ecan tasks add/update/remove` and `ecan agents update/remove` go
through the app when it is running and signed in as the CLI's user
(`get_cli_session`). The app saves the change, updates what is running and
syncs to the cloud. Otherwise the CLI writes the database itself and the app
picks the change up when it starts. `ECAN_CLI_DIRECT_DB=1` forces the direct
path.

## Handlers behind the CLI's live commands

| CLI | Method | Params → result |
|---|---|---|
| `ecan agents pool [fd]` | `get_agent_pools` / `get_agent_pool` | `{}` / `{agent_id}` → `{pools: {fd: view}}` / `{pool: view or null}` |
| `ecan agents pool fd --pin N / --unpin` | `set_agent_pool_pin` | `{agent_id, size: N or null}` → `{pool: view}`. Errors: `POOL_NOT_FOUND`, `POOL_SCALING_OFF`. In memory until the app restarts. |
| `ecan agents monitor [id]` | `get_all_agents_runtime_status` / `get_agent_runtime_status` | `{}` / `{agent_id}` |
| `ecan agents stop id` | `set_agent_enabled` | `{agent_id, enabled: false}`: the agent stops now and stays disabled |
| `ecan agents run id -t text` | `send_chat` | `{chatId, role: "user", content, senderId, receiverId: id, …}` |
| `ecan tasks execute task [--input k=v]` | `launch_agent_task` | `{task_id or task_name, agent_id?, task_inputs?}`: one run queued on the task's own loop |
| `ecan tasks state` | `get_task_run_states` | `{}` → `{states: {task_id: {waiting_resource, waiting_after, last_missed}}}` |
| `ecan tasks locks` | `get_resource_locks` | `{}` → `{enabled, held: {key: {holder, count}}, waiting: [...]}` |
| `ecan tasks add/update/remove` | `new_agent_task` / `save_agent_task` / `delete_agent_task` | `{task_info: full record}` / `{task_info: full record with id}` / `{task_id}`. `save_agent_task` replaces every field, so send the whole record. |
| `ecan agents update/remove` | `save_agent` / `delete_agent` | `{username, agent: [{id, …fields}]}` / `{username, agent_id}` |

Run rules and pool size saved through `save_agent_task` reach the running task
at once (`_apply_settings_to_running_tasks`). `save_agent` restarts a running
agent with its new settings (`_swap_agent`), and `delete_agent` and disabling
stop it (`_stop_running_agent`).
