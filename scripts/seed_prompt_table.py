#!/usr/bin/env python3
"""
Seed the existing Agent_Prompts DynamoDB table with skill-editor system prompts.

Items are stored under  owner_id="system"  agent_id="skill_editor~<name>"
so they are easy to find and edit in the DynamoDB console.

Usage:
    cd ~/repo/eCan.ai
    AWS_PROFILE=maipps8 AWS_REGION=us-east-1 python3 scripts/seed_prompt_table.py
"""

import ast
import datetime
import os
import sys

import boto3

# ---------------------------------------------------------------------------
# Config – mirrors prompt_store.py but with zero internal imports
# ---------------------------------------------------------------------------
TABLE_NAME = os.environ.get("PROMPT_TABLE_NAME", "Agent_Prompts")
REGION = os.environ.get("AWS_REGION", "us-east-1")
OWNER_ID = os.environ.get("PROMPT_OWNER_ID", "system")
PREFIX = "skill_editor~"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Map:  prompt_id  →  (source_file, variable_name)
# ---------------------------------------------------------------------------
PROMPT_SOURCES = {
    "intent_classifier": ("agent/skill_editor/skill_editor_agent.py", "INTENT_CLASSIFIER_SYSTEM_PROMPT"),
    "planner":           ("agent/skill_editor/planner_agent.py",      "PLANNER_SYSTEM_PROMPT"),
    "code_gen":          ("agent/skill_editor/code_agent.py",         "CODE_GENERATION_PROMPT"),
    "edit_flowgram":     ("agent/skill_editor/code_agent.py",         "EDIT_FLOWGRAM_PROMPT"),
    "validator":         ("agent/skill_editor/validator_agent.py",    "VALIDATOR_SYSTEM_PROMPT"),
}


def _extract_string_constant(filepath: str, var_name: str) -> str:
    """Parse a Python file's AST and return the value of a top-level string constant."""
    with open(filepath, "r") as f:
        tree = ast.parse(f.read(), filename=filepath)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == var_name:
                    # ast.literal_eval handles plain strings & concatenations
                    try:
                        return ast.literal_eval(node.value)
                    except Exception:
                        # Fall back to compile + exec for f-strings / complex exprs
                        pass
    raise ValueError(f"Could not find {var_name!r} in {filepath}")


def main():
    session = boto3.Session(region_name=REGION)
    ddb = session.client("dynamodb")

    print(f"Seeding {len(PROMPT_SOURCES)} prompts into {TABLE_NAME} "
          f"(owner_id={OWNER_ID}, agent_id={PREFIX}<name>)...\n")

    ok = 0
    for pid, (relpath, var) in PROMPT_SOURCES.items():
        filepath = os.path.join(PROJECT_ROOT, relpath)
        try:
            text = _extract_string_constant(filepath, var)
        except Exception as e:
            print(f"  {pid}: EXTRACT FAILED – {e}")
            continue

        agent_id = f"{PREFIX}{pid}"
        try:
            ddb.put_item(
                TableName=TABLE_NAME,
                Item={
                    "owner_id":      {"S": OWNER_ID},
                    "agent_id":      {"S": agent_id},
                    "prompt_id":     {"S": pid},
                    "prompt":        {"S": text},
                    "prompt_name":   {"S": f"skill_editor_{pid}"},
                    "suitable_modes": {"S": "all"},
                    "metadata":      {"S": "{}"},
                    "last_mod_date": {"S": datetime.datetime.utcnow().isoformat() + "Z"},
                },
            )
            print(f"  {pid}: {len(text)} chars -> OK")
            ok += 1
        except Exception as e:
            print(f"  {pid}: PUT FAILED – {e}")

    print(f"\nDone: {ok}/{len(PROMPT_SOURCES)} seeded successfully.")
    return 0 if ok == len(PROMPT_SOURCES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
