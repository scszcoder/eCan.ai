"""The send's own retries (mt034, mt038A, newest-turn) must call the unwrapped body.

feige_send_message is a browser-use registry action: its wrapper takes keyword
arguments only, so a positional self-call raises TypeError and the reply is
dropped (KEN 2026-10-29 17:09: "feige_send_message() does not accept positional
arguments" on the mt038A rescue -- the buyer never got an answer).
"""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / (
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/site_tools.py"
)


def _calls_in(func_name: str) -> list[str]:
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == func_name:
            return [
                c.func.id for c in ast.walk(node)
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
            ]
    raise AssertionError(f"{func_name} not found")


def test_the_body_never_calls_the_registry_wrapper():
    assert "feige_send_message" not in _calls_in("_feige_send_message_body")


def test_the_body_retries_itself():
    assert _calls_in("_feige_send_message_body").count("_feige_send_message_body") == 3
