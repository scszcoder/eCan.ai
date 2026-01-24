# Skill Editor Agent - AWS Lambda Deployment Guide

## Overview

This document describes how to package and deploy the `skill_editor_agent` as an AWS Lambda function.

## Dependencies to Bundle

### Internal Modules Required

| Module | Purpose |
|--------|---------|
| `agent/skill_editor/` | All files (the main agent code) |
| `agent/ec_skills/extern_skills/extern_skills.py` | For `scaffold_skill`, `user_skills_root` |
| `agent/ec_skills/llm_utils/llm_utils.py` | LLM utility functions |
| `agent/ec_tasks/appsync_pubsub.py` | For AppSync publishing |
| `utils/logger_helper.py` | Logging utility |
| `utils/env/secure_store.py` | Secure environment store |
| `lambda_functions/skill_editor_lambda/handler.py` | Lambda handler (entry point) |

### External Dependencies (bundled via pip install)

- `langchain-core`
- `langchain-openai`
- `pydantic`
- `httpx`
- `aiohttp`
- `certifi`
- `boto3` (pre-installed in Lambda runtime)

**Note:** The deployment script (`lput_skill_editor.ps1`) automatically installs these from `requirements.txt`.

### Important: Minimal ec_tasks Module

The `agent/ec_tasks/__init__.py` in the Lambda package is a **minimal version** that only imports `appsync_pubsub`. This avoids pulling in `models.py` which has an `a2a-sdk` dependency.

## Directory Structure for Lambda Zip

```
skill_editor_agent/
├── lambda_function.py          # Entry point (handler.py + alias)
├── agent/
│   ├── __init__.py
│   ├── skill_editor/           # Copy entire folder
│   │   ├── __init__.py
│   │   ├── skill_editor_agent.py
│   │   ├── code_agent.py
│   │   ├── planner_agent.py
│   │   ├── node_config_agent.py
│   │   ├── validator_agent.py
│   │   ├── schemas.py
│   │   └── placement.py
│   ├── ec_skills/
│   │   ├── __init__.py
│   │   ├── llm_utils/
│   │   │   ├── __init__.py
│   │   │   └── llm_utils.py
│   │   └── extern_skills/
│   │       ├── __init__.py
│   │       └── extern_skills.py
│   └── ec_tasks/
│       ├── __init__.py          # Minimal version (only imports appsync_pubsub)
│       └── appsync_pubsub.py
└── utils/
    ├── __init__.py              # Minimal version
    ├── logger_helper.py         # Minimal Lambda version (no colorlog/config deps)
    ├── time_util.py
    └── env/
        ├── __init__.py
        └── secure_store.py
```

**Note:** The `utils/logger_helper.py` and `agent/ec_tasks/__init__.py` in the Lambda package are **minimal versions** created by the deployment script to avoid dependencies on `colorlog`, `config.constants`, `config.app_info`, and `a2a-sdk`.

## Deployment Script

The deployment script is located at: `C:\lambda_works\skill_editor_agent\lput_skill_editor.ps1`

### Usage

```powershell
cd C:\lambda_works\skill_editor_agent
.\lput_skill_editor.ps1 -FunctionName "skill_editor_agent"
```

### Script Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `-FunctionName` | `skill_editor_agent` | AWS Lambda function name |
| `-Region` | `us-east-1` | AWS region |
| `-Profile` | `maipps8` | AWS CLI profile |

### What the Script Does

1. **Creates staging directory** with proper module structure
2. **Copies internal modules:**
   - `agent/skill_editor/` (all 8 .py files)
   - `agent/ec_skills/extern_skills/extern_skills.py`
   - `agent/ec_skills/llm_utils/llm_utils.py`
   - `agent/ec_tasks/appsync_pubsub.py`
   - `utils/logger_helper.py` (minimal Lambda version)
   - `utils/time_util.py`
   - `utils/env/secure_store.py`
   - `config/` (constants.py, app_info.py)
   - `my_prompts/` (all prompt files)
   - `app_context.py`
3. **Copies `handler.py`** → `lambda_function.py` and appends `lambda_handler = handler` alias
4. **Installs pip dependencies with Linux platform** (see below)
5. **Creates zip** and deploys via `aws lambda update-function-code`

### CRITICAL: Linux-Compatible Packages

The script uses `--platform manylinux2014_x86_64` when installing pip packages to ensure Linux-compatible binaries are downloaded instead of Windows `.pyd` files:

```powershell
pip install -r requirements.txt -t "$StagingDir" `
    --platform manylinux2014_x86_64 `
    --implementation cp `
    --python-version 3.12 `
    --only-binary=:all: `
    --upgrade
```

**Why this matters:** Packages like `pydantic_core` contain compiled C extensions. Running `pip install` on Windows downloads Windows binaries (`.pyd`), which fail on AWS Lambda (Linux). The `--platform` flag forces pip to download Linux wheels (`.so` files).

## Linux Build Script (Recommended)

For building on Linux (e.g., Ubuntu server), use the provided shell script:

```bash
cd /path/to/eCan.ai/lambda_functions/skill_editor_lambda
chmod +x build_lambda.sh
./build_lambda.sh
```

This script:
1. Copies source modules from the repo
2. **Applies Lambda overrides** from `lambda_overrides/` directory
3. Creates a zip file at `/tmp/skill_editor_agent.zip`

### Lambda Overrides

The `lambda_overrides/` directory contains minimal versions of files that have Lambda-incompatible code:

| File | Why Override |
|------|--------------|
| `agent/ec_tasks/__init__.py` | Full version imports `scheduler.py` which imports `logger_helper.py` which imports `app_info.py` which tries to create directories |
| `utils/__init__.py` | Minimal version |
| `utils/logger_helper.py` | Full version imports `config.app_info` which calls `os.makedirs()` on read-only filesystem |

**CRITICAL:** When deploying from Linux, you MUST apply these overrides. The Lambda filesystem is read-only except for `/tmp`.

## Lambda Configuration

### Handler Setting

```
lambda_function.lambda_handler
```

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `S3_BUCKET` | S3 bucket for session/history storage |
| `S3_KEY_ROOT` | S3 key prefix (optional) |
| `APPSYNC_API_URL` | AppSync API endpoint URL |
| `APPSYNC_API_KEY` | AppSync API key |
| `OPENAI_API_KEY` | OpenAI API key for LLM calls |

### Recommended Settings

- **Timeout:** 60-120 seconds (LLM calls can take time)
- **Memory:** 512MB - 1024MB
- **Runtime:** Python 3.11+

## Potential Issues

### AppContext Import

The `code_agent.py` and `planner_agent.py` files contain `AppContext` imports inside `_load_llm_from_settings()`:

```python
try:
    from app_context import AppContext
    from agent.ec_skills.llm_utils.llm_utils import pick_llm
    
    mainwin = AppContext.get_main_window()
    # ... desktop GUI logic
except Exception as e:
    # Fallback for Lambda environment
    from langchain_openai import ChatOpenAI
    import os
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        return ChatOpenAI(model="gpt-4o", api_key=api_key, max_tokens=16384)
```

**The fallback to `os.environ.get("OPENAI_API_KEY")` should work**, but if `app_context.py` itself imports GUI libraries at module level, you may encounter import errors.

**Solution if import errors occur:**
1. Ensure `app_context.py` is NOT included in the Lambda package
2. The try/except block will catch the `ImportError` and use the fallback

### Testing

After deployment, test with a simple GraphQL event:

```json
{
  "info": {
    "fieldName": "getSkillEditorChatSessions"
  },
  "arguments": {
    "input": {
      "userId": "test-user"
    }
  }
}
```

## GraphQL Operations Supported

| Operation | Description |
|-----------|-------------|
| `createSkillEditorChatSession` | Create a new chat session |
| `getSkillEditorChatSessions` | List all sessions for a user |
| `loadSkillEditorContexts` | Load skill contexts (per user, per skill from S3) |
| `getSkillEditorChatHistory` | Get chat history for a session |
| `sendSkillEditorChatMessage` | Send a message and get AI response |
| `cancelSkillEditorChatGeneration` | Cancel ongoing generation |
| `deleteSkillEditorChatSession` | Delete a chat session |
