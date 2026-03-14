# eCan.ai Channel Architecture

Connect your eCan.ai agents to external messaging platforms so users can interact with them from Telegram, Slack, Discord, WhatsApp, DingTalk, Facebook Messenger, or X (Twitter) — in addition to the built-in web chat.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration Reference](#configuration-reference)
- [Channel Setup Guides](#channel-setup-guides)
  - [WebChat (built-in)](#webchat-built-in)
  - [Telegram](#telegram)
  - [Slack](#slack)
  - [Discord](#discord)
  - [WhatsApp](#whatsapp)
  - [DingTalk (钉钉)](#dingtalk-钉钉)
  - [Facebook Messenger](#facebook-messenger)
  - [X (Twitter)](#x-twitter)
- [How It Works](#how-it-works)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)

---

## Overview

The channel system lets any eCan.ai agent receive and reply to messages from external platforms. Every channel adapter normalizes inbound messages into a common format, routes them through the standard agent pipeline (skills, LLM, flowgrams), and sends the agent's response back to the originating platform.

**Supported channels:**

| Channel | Protocol | Public Endpoint Required? |
|---------|----------|--------------------------|
| WebChat | Built-in GUI IPC | No |
| Telegram | Bot API long-polling | No |
| Slack | Socket Mode (WebSocket) | No |
| Discord | Gateway bot (WebSocket) | No |
| WhatsApp | Webhook + Cloud API | **Yes** (port 8443) |
| DingTalk | Stream Mode (WebSocket) | No |
| Facebook Messenger | Webhook + Graph API | **Yes** (port 8444) |
| X (Twitter) | Webhook + v2 DM API | **Yes** (port 8445) |

> Channels that require a public endpoint need your machine to be reachable from the internet (e.g. via a reverse proxy or ngrok).

---

## Architecture

The system is organized into three layers:

```
┌─────────────────────────────────────────────────────┐
│  Layer 1: Channel Adapters                          │
│  telegram.py · slack.py · discord.py · whatsapp.py  │
│  dingtalk.py · messenger.py · twitter.py · webchat  │
└──────────────────────┬──────────────────────────────┘
                       │ ChannelMessage
┌──────────────────────▼──────────────────────────────┐
│  Layer 2: Channel Manager                           │
│  Lifecycle control · Thread management · Auto-retry │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  Layer 3: Channel Bridge                            │
│  Inbound:  ChannelMessage → req dict → agent runner │
│  Outbound: agent state → channel_manager.send()     │
└─────────────────────────────────────────────────────┘
```

**Key files:**

| File | Purpose |
|------|---------|
| `agent/channels/base.py` | Core abstractions (`ChannelPlugin`, `ChannelMessage`, etc.) |
| `agent/channels/registry.py` | Auto-discovers adapter modules |
| `agent/channels/channel_manager.py` | Starts/stops channels, auto-restarts on crash |
| `agent/channels/bridge.py` | Converts between channel messages and agent pipeline |
| `agent/channels/adapters/*.py` | One file per platform |
| `agent/agent_files/channels.json` | Configuration for all channels |

---

## Quick Start

### 1. Install dependencies

All dependencies are listed in `requirements-base.txt`. If you haven't installed them yet:

```bash
pip install -r requirements-base.txt
```

Key packages per channel:

| Channel | Package |
|---------|---------|
| Telegram, WhatsApp, Messenger, X | `requests` (already included) |
| Slack | `slack-bolt`, `slack-sdk` |
| Discord | `discord.py` |
| DingTalk | `dingtalk-stream` |
| X (Twitter) | `requests-oauthlib` (already included) |

### 2. Edit the config

Open `agent/agent_files/channels.json` and enable the channels you want:

```json
{
    "channels": {
        "telegram": {
            "enabled": true,
            "bot_token": "******",
            "allowed_chat_ids": [],
            "default_agent_id": ""
        }
    }
}
```

- Set `"enabled": true` for each channel you want to activate.
- Fill in the required credentials (see per-channel guides below).
- `allowed_chat_ids` / `allowed_channels` / `allowed_channel_ids`: leave empty `[]` to accept all, or provide a list to restrict.
- `default_agent_id`: leave empty `""` to route to the first available agent, or set a specific agent ID.

### 3. Restart eCan.ai

The channel manager starts automatically during app initialization. Enabled channels will begin listening immediately after agents are ready.

---

## Configuration Reference

All channel configuration lives in `agent/agent_files/channels.json`. The top-level structure is:

```json
{
    "channels": {
        "<channel_id>": {
            "enabled": false,
            ...channel-specific keys...
        }
    }
}
```

**Common fields (all channels):**

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | `bool` | Whether to start this channel on launch |
| `default_agent_id` | `string` | Route messages to a specific agent (empty = first available) |

---

## Channel Setup Guides

### WebChat (built-in)

The web chat is always active by default — it uses the existing GUI IPC pipeline. No additional setup is needed.

```json
"webchat": {
    "enabled": true,
    "default_agent_id": ""
}
```

---

### Telegram

**How it works:** The adapter connects to the Telegram Bot API using long-polling (`getUpdates`). No public endpoint or webhook is needed — the bot pulls messages from Telegram's servers.

#### Step 1: Create a bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts.
3. Copy the **bot token**.

#### Step 2: Configure

```json
"telegram": {
    "enabled": true,
    "bot_token": "******",
    "allowed_chat_ids": [],
    "default_agent_id": ""
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `bot_token` | Yes | Token from BotFather |
| `allowed_chat_ids` | No | List of chat IDs to accept messages from. Empty = all. |

#### Step 3: Test

1. Start eCan.ai.
2. Open Telegram and send a message to your bot.
3. The agent should respond in the same chat.

#### Finding your chat ID

Send a message to your bot, then open:
```
https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
```
Look for `"chat": {"id": 123456789}` in the response.

---

### Slack

**How it works:** Uses Slack's Socket Mode (WebSocket), so no public endpoint is needed. The bot maintains a persistent connection to Slack's servers.

#### Step 1: Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**.
2. Under **OAuth & Permissions**, add these **Bot Token Scopes**:
   - `chat:write`
   - `channels:history`
   - `groups:history`
   - `im:history`
   - `mpim:history`
3. Install the app to your workspace and copy the **Bot User OAuth Token**.
4. Under **Socket Mode**, enable it and generate an **App-Level Token** with the `connections:write` scope.
5. Under **Event Subscriptions**, enable events and subscribe to:
   - `message.channels`
   - `message.groups`
   - `message.im`
   - `message.mpim`

#### Step 2: Configure

```json
"slack": {
    "enabled": true,
    "bot_token": "******",
    "app_token": "******",
    "allowed_channels": [],
    "default_agent_id": ""
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `bot_token` | Yes | Bot User OAuth Token |
| `app_token` | Yes | App-Level Token for Socket Mode |
| `allowed_channels` | No | List of channel IDs to listen in. Empty = all. |

#### Step 3: Test

1. Start eCan.ai.
2. Invite the bot to a Slack channel: `/invite @YourBotName`.
3. Send a message — the agent responds in the same channel.

---

### Discord

**How it works:** Uses `discord.py`'s Gateway connection (WebSocket). The bot connects to Discord's servers — no public endpoint needed.

#### Step 1: Create a Discord Bot

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications) → **New Application**.
2. Under **Bot**, click **Add Bot**.
3. Enable **Message Content Intent** under Privileged Gateway Intents.
4. Copy the **Bot Token**.
5. Under **OAuth2 → URL Generator**, select scopes `bot` and permissions `Send Messages`, `Read Message History`. Use the generated URL to invite the bot to your server.

#### Step 2: Configure

```json
"discord": {
    "enabled": true,
    "bot_token": "******",
    "allowed_channel_ids": [],
    "default_agent_id": ""
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `bot_token` | Yes | Bot token from Developer Portal |
| `allowed_channel_ids` | No | List of channel IDs (integers) to listen in. Empty = all. |

#### Step 3: Test

1. Start eCan.ai.
2. Send a message in any channel where the bot is present.
3. The agent responds in the same channel.

#### Getting a channel ID

Enable **Developer Mode** in Discord settings → right-click a channel → **Copy Channel ID**.

---

### WhatsApp

**How it works:** Runs a local webhook server to receive inbound messages from the WhatsApp Cloud API. Sends replies via the Graph API. **Requires a public endpoint** (use ngrok or a reverse proxy).

#### Step 1: Set up Meta Developer App

1. Go to [developers.facebook.com](https://developers.facebook.com) → **My Apps** → **Create App** → **Business** type.
2. Add the **WhatsApp** product.
3. Under **WhatsApp → API Setup**, note your:
   - **Phone Number ID**
   - **Temporary Access Token** (or generate a permanent one via System Users)
4. Under **Webhooks**, set the callback URL to `https://<your-domain>:8443/` and the verify token to `whatsapp_verify` (or your custom value).
5. Subscribe to the `messages` webhook field.

#### Step 2: Expose your webhook

```bash
# Using ngrok
ngrok http 8443
# Copy the https URL and set it as your webhook in Meta Developer Console
```

#### Step 3: Configure

```json
"whatsapp": {
    "enabled": true,
    "phone_number_id": "123456789012345",
    "access_token": "******",
    "verify_token": "whatsapp_verify",
    "webhook_port": 8443,
    "default_agent_id": ""
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `phone_number_id` | Yes | From WhatsApp API Setup |
| `access_token` | Yes | Graph API access token |
| `verify_token` | No | Must match what you set in Meta webhook config (default: `whatsapp_verify`) |
| `webhook_port` | No | Local port for the webhook server (default: `8443`) |

---

### DingTalk (钉钉)

**How it works:** Uses the `dingtalk-stream` SDK which maintains a WebSocket connection to DingTalk's servers (similar to Slack Socket Mode). **No public endpoint needed.**

#### Step 1: Create a DingTalk Robot

1. Go to [open-dev.dingtalk.com](https://open-dev.dingtalk.com) → **Application Development** → **Robot**.
2. Create a new robot application.
3. Note the **AppKey** (client_id) and **AppSecret** (client_secret).
4. Under **Robot Configuration**, enable **Stream Mode** (Stream 模式).
5. Deploy the robot to your organization or add it to a group chat.

#### Step 2: Configure

```json
"dingtalk": {
    "enabled": true,
    "client_id": "dingXXXXXXXXXXXXXXXX",
    "client_secret": "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    "default_agent_id": ""
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `client_id` | Yes | AppKey from DingTalk Developer Console |
| `client_secret` | Yes | AppSecret from DingTalk Developer Console |

#### Step 3: Test

1. Start eCan.ai.
2. In DingTalk, @ mention the robot in a group chat or send it a direct message.
3. The agent responds in the same conversation.

> **Note:** For group chats, users must @mention the robot to trigger it. 1:1 chats don't require @mentions.

---

### Facebook Messenger

**How it works:** Runs a local webhook server for inbound messages and uses the Graph API Send endpoint for outbound. **Requires a public endpoint.**

#### Step 1: Set up a Facebook App

1. Go to [developers.facebook.com](https://developers.facebook.com) → **My Apps** → **Create App** → **Business** type.
2. Add the **Messenger** product.
3. Under **Messenger → Settings**:
   - Connect a Facebook Page.
   - Generate a **Page Access Token**.
4. Under **Webhooks**:
   - Set callback URL to `https://<your-domain>:8444/`.
   - Set verify token to `messenger_verify` (or your custom value).
   - Subscribe to `messages` and `messaging_postbacks`.

#### Step 2: Expose your webhook

```bash
ngrok http 8444
```

#### Step 3: Configure

```json
"messenger": {
    "enabled": true,
    "page_access_token": "******",
    "verify_token": "messenger_verify",
    "app_secret": "******",
    "webhook_port": 8444,
    "default_agent_id": ""
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `page_access_token` | Yes | Generated from your Facebook Page |
| `verify_token` | No | Must match webhook config (default: `messenger_verify`) |
| `app_secret` | No | App Secret for HMAC signature verification (recommended) |
| `webhook_port` | No | Local port for the webhook server (default: `8444`) |

---

### X (Twitter)

**How it works:** Uses the Account Activity API to receive DMs via webhook and the v2 DM endpoint to send replies. **Requires a public endpoint** and a developer account with Account Activity API access.

#### Step 1: Set up an X Developer App

1. Go to [developer.x.com](https://developer.x.com) → **Developer Portal** → **Projects & Apps**.
2. Create a new App (or use an existing one).
3. Under **Keys and tokens**, generate:
   - **API Key** and **API Secret**
   - **Access Token** and **Access Token Secret** (with Read and Write + Direct Messages permissions)
4. Under **Products → Premium → Account Activity API**, set up a **Dev environment**.
5. Register your webhook URL:
   ```bash
   # Using the Account Activity API
   curl -X POST \
     "https://api.x.com/1.1/account_activity/all/<env_name>/webhooks.json?url=https://<your-domain>:8445/" \
     -H "Authorization: OAuth ..."
   ```
6. Subscribe to the authenticated user's events:
   ```bash
   curl -X POST \
     "https://api.x.com/1.1/account_activity/all/<env_name>/subscriptions.json" \
     -H "Authorization: OAuth ..."
   ```

#### Step 2: Expose your webhook

```bash
ngrok http 8445
```

#### Step 3: Configure

```json
"twitter": {
    "enabled": true,
    "api_key": "******",
    "api_secret": "******",
    "access_token": "******",
    "access_token_secret": "******",
    "bearer_token": "",
    "env_name": "default",
    "webhook_port": 8445,
    "default_agent_id": ""
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `api_key` | Yes | Consumer API Key |
| `api_secret` | Yes | Consumer API Secret |
| `access_token` | Yes | OAuth 1.0a Access Token |
| `access_token_secret` | Yes | OAuth 1.0a Access Token Secret |
| `bearer_token` | No | Optional Bearer Token (not used for DMs currently) |
| `env_name` | No | Account Activity API environment name (default: `default`) |
| `webhook_port` | No | Local port for the webhook server (default: `8445`) |

---

## How It Works

### Inbound Message Flow

```
User sends message on Platform (e.g. Telegram)
        │
        ▼
Adapter receives message (long-poll / WebSocket / webhook)
        │
        ▼
Adapter normalizes → ChannelMessage dataclass
        │
        ▼
ChannelBridge.dispatch_inbound()
  ├─ Converts ChannelMessage → internal req dict
  ├─ Picks target agent (default_agent_id or first available)
  └─ Calls runner.sync_task_wait_in_line("channel_message", req)
        │
        ▼
Event routing matches "channel_message" → chat task
        │
        ▼
Chat task's pend_event resumes with channel metadata in state
        │
        ▼
LLM processes message and generates response
```

### Outbound Message Flow

```
Agent generates response (via LLM / skill)
        │
        ▼
send_response_back() or build_chat_node()
        │
        ▼
ChannelBridge.route_reply(state, text)
  ├─ Checks state["attributes"]["channel_id"]
  ├─ If "webchat" or absent → falls through to GUI (ChatMessageSender)
  └─ If external channel → ChannelManager.send(channel_id, chat_id, message)
        │
        ▼
Adapter.send() → Platform API → User sees reply
```

### Channel Metadata

When a message arrives from an external channel, these keys are propagated into the agent's running state so the outbound bridge can route replies back:

| State Key | Description |
|-----------|-------------|
| `attributes.channel_id` | Adapter identifier (e.g. `"telegram"`, `"discord"`) |
| `attributes.channel_chat_id` | Platform-specific conversation ID |
| `attributes.channel_sender_id` | Platform-specific sender ID |
| `attributes.channel_message_id` | Platform-specific message ID |
| `attributes.channel_thread_id` | Thread ID (if applicable) |

---

## Examples

### Example 1: Telegram Customer Support Bot

Enable Telegram and point it at your support agent:

```json
{
    "channels": {
        "webchat": { "enabled": true, "default_agent_id": "" },
        "telegram": {
            "enabled": true,
            "bot_token": "******",
            "allowed_chat_ids": [],
            "default_agent_id": "agent-support-001"
        }
    }
}
```

Users message the Telegram bot → the support agent's skill handles it → reply appears in Telegram.

### Example 2: Multi-Channel Setup (Slack + Discord)

Run the same agent on both Slack and Discord simultaneously:

```json
{
    "channels": {
        "webchat": { "enabled": true, "default_agent_id": "" },
        "slack": {
            "enabled": true,
            "bot_token": "******",
            "app_token": "******",
            "allowed_channels": ["C0123456789"],
            "default_agent_id": ""
        },
        "discord": {
            "enabled": true,
            "bot_token": "******",
            "allowed_channel_ids": [1234567890123456789],
            "default_agent_id": ""
        }
    }
}
```

### Example 3: DingTalk for Internal Teams + WhatsApp for External Clients

Route different channels to different agents:

```json
{
    "channels": {
        "dingtalk": {
            "enabled": true,
            "client_id": "******",
            "client_secret": "******",
            "default_agent_id": "agent-internal-ops"
        },
        "whatsapp": {
            "enabled": true,
            "phone_number_id": "123456789",
            "access_token": "******",
            "verify_token": "whatsapp_verify",
            "webhook_port": 8443,
            "default_agent_id": "agent-client-facing"
        }
    }
}
```

---

## Troubleshooting

### Channel shows as "error" status

Check the application logs for `[ChannelManager]` entries. Common causes:
- **Invalid credentials** — double-check tokens/keys in `channels.json`.
- **Network issues** — ensure the machine can reach the platform's API.
- **Missing dependencies** — run `pip install -r requirements-base.txt`.

The channel manager will auto-retry with exponential backoff (up to 5 retries, starting at 2s delay).

### Webhook channels (WhatsApp, Messenger, X) not receiving messages

- Ensure your webhook port is publicly accessible (use ngrok: `ngrok http <port>`).
- Verify the webhook URL is registered correctly in the platform's developer console.
- Check that the `verify_token` in `channels.json` matches what you configured in the platform.

### Bot doesn't respond

1. Check that `"enabled": true` is set in the channel config.
2. Verify there is at least one agent with a running skill that has a chat/pend_event node.
3. Check logs for `[ChannelBridge]` entries — look for "No agent available" or "dispatch_inbound error".

### Messages from the bot are echoed back

Each adapter filters out its own messages. If you see echo loops:
- **Slack:** Ensure the bot doesn't respond to `bot_id` messages (handled automatically).
- **Discord:** The adapter ignores `message.author.bot` and own messages.
- **X/Twitter:** The adapter resolves its own user_id on startup and skips self-sent DMs.

### Restricting which chats/channels the bot listens to

Use the `allowed_*` config fields:
- **Telegram:** `"allowed_chat_ids": ["123456789", "-100123456789"]`
- **Slack:** `"allowed_channels": ["C0123456789"]`
- **Discord:** `"allowed_channel_ids": [1234567890123456789]`

Leave the list empty `[]` to accept messages from all chats/channels.
