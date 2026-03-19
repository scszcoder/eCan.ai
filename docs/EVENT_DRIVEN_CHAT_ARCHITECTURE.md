# Event-Driven Multi-Customer Chat Architecture

## Overview

eCan.ai's event-driven chat orchestration system eliminates polling delays by using browser events and platform-specific detection to achieve near-instant response times.

**Performance:**
- Event-driven platforms: <100ms response time
- Polling-based platforms: 2-3s response time (adaptive)
- Supports 8+ e-commerce platforms out-of-box
- Extensible via custom platform profiles

---

## Architecture Components

### 1. Platform Profiles (`platform_profiles.json`)

Pre-configured detection rules for each e-commerce platform:

```json
{
  "amazon_seller_central": {
    "detection": {
      "url_patterns": ["sellercentral.amazon.com/messaging"],
      "dom_signatures": ["div[data-test-id='message-thread']"]
    },
    "event_strategy": {
      "primary": "websocket",
      "cdp_events": [
        {
          "domain": "Network",
          "method": "Network.webSocketFrameReceived",
          "filter": "url contains '/messaging/ws'",
          "reliability": "high"
        }
      ]
    },
    "chat_id_extraction": [
      {
        "priority": 1,
        "method": "event_payload",
        "path": "params.response.payloadData.conversationId"
      }
    ],
    "polling_config": {
      "enabled": true,
      "interval_ms": 2000
    }
  }
}
```

**Supported Platforms:**
- Amazon Seller Central (WebSocket, <100ms)
- eBay Messages (Polling, ~2s)
- TikTok Shop (WebSocket, <200ms)
- Douyin 抖音 (Polling, ~3s)
- Taobao 淘宝 (Polling, ~2.5s)
- Tmall 天猫 (Polling, ~2.5s)
- JD.com 京东 (Polling, ~2s)
- Etsy Messages (WebSocket, <150ms)

### 2. Platform Detector

Automatically identifies platform from URL and DOM:

```python
from agent.ec_tasks.platform_detector import get_platform_detector

detector = get_platform_detector()
platform_id = detector.detect_platform(url, dom_snapshot)
profile = detector.get_profile(platform_id)
```

### 3. Chat Event Dispatcher

Coordinates CDP events and polling:

```python
from agent.ec_tasks.chat_event_dispatcher import get_chat_event_dispatcher

dispatcher = get_chat_event_dispatcher()

def on_new_message(event):
    chat_id = event['chat_id']
    platform_id = event['platform_id']
    source = event['source']  # 'cdp' or 'polling'
    # Handle new message...

monitor_id = dispatcher.start_monitoring(
    agent_id="orchestrator_123",
    platform_id="amazon_seller_central",
    cdp_client=cdp_client,
    browser_session=browser,
    on_new_message=on_new_message
)
```

**Features:**
- Automatic platform detection
- CDP event subscription (if available)
- Intelligent polling fallback (always active)
- Event deduplication
- Adaptive polling frequency

### 4. Chat ID Extractor

Multi-strategy extraction with priority-based fallback:

```python
from agent.ec_tasks.chat_id_extractor import extract_chat_id_from_event

chat_id = extract_chat_id_from_event(
    event_params=event,
    platform_profile=profile,
    browser_session=browser
)
```

**Extraction Strategies (priority order):**
1. Event payload (fastest, most reliable)
2. DOM attribute (reliable if element present)
3. URL pattern matching (reliable if URL contains ID)
4. DOM text extraction (fallback)

### 5. Polling Service

Adaptive polling with smart frequency adjustment:

```python
from agent.ec_tasks.polling_service import get_polling_service

service = get_polling_service()
poll_id = service.start_polling(
    agent_id="agent_123",
    platform_profile=profile,
    callback=on_change_detected,
    browser_session=browser
)
```

**Features:**
- Adaptive frequency: 2s active → 5s idle → 10s background
- DOM snapshot comparison
- Automatic deduplication with CDP events
- Pause/resume support

---

## Usage Examples

### Example 1: Orchestrator with Event-Driven Detection

```python
# In orchestrator skill (browser automation node)

# 1. Platform is auto-detected from current URL
# 2. Start monitoring for new messages
from agent.ec_tasks.chat_event_dispatcher import get_chat_event_dispatcher

dispatcher = get_chat_event_dispatcher()

def on_new_message(event):
    chat_id = event['chat_id']
    platform_id = event['platform_id']
    
    # Spawn worker agent for this chat
    from agent.ec_tasks.agent_management_mcp_tools import spawn_worker_agent
    
    spawn_worker_agent(
        mainwin=mainwin,
        config={
            "worker_name": f"chat_handler_{chat_id}",
            "orchestrator_agent_id": agent_id,
            "skill_name": "handle_customer_chat",
            "metadata": {
                "chat_id": chat_id,
                "platform_id": platform_id,
                "cdp_client": cdp_client,
                "browser_session": browser_session
            }
        }
    )

monitor_id = dispatcher.start_monitoring(
    agent_id=agent_id,
    cdp_client=cdp_client,
    browser_session=browser_session,
    on_new_message=on_new_message
)
```

### Example 2: Worker Agent with Event Monitoring

Worker agents automatically get event monitoring when spawned with `chat_id` and `platform_id` in metadata:

```python
# Spawning automatically starts event monitoring
worker_info = spawn_worker_agent(
    mainwin=mainwin,
    config={
        "worker_name": "chat_worker_001",
        "orchestrator_agent_id": "orch_123",
        "skill_name": "handle_chat",
        "metadata": {
            "chat_id": "customer_abc123",
            "platform_id": "amazon_seller_central",
            "cdp_client": cdp_client,
            "browser_session": browser_session
        }
    }
)

# Worker's pend_event_node will resume when new message arrives
# No polling needed - events are routed directly to worker
```

### Example 3: Custom Platform Configuration

```python
# Via MCP tool (callable by LLM)
result = await async_create_custom_platform_profile(
    mainwin=mainwin,
    arguments={
        "platform_id": "my_custom_store",
        "display_name": "My Custom Store Chat",
        "url_pattern": "mystore.com/messages",
        "chat_container_selector": "div.message-list",
        "chat_id_selector": "div.active-chat",
        "chat_id_attribute": "data-chat-id",
        "polling_interval_ms": 3000
    }
)
```

---

## MCP Tools

### Platform Configuration Tools

**`list_available_platforms`**
- Lists all available platform profiles
- Shows capabilities (event-driven vs polling)

**`get_platform_profile`**
- Get detailed configuration for a platform
- Returns selectors, extraction rules, polling config

**`create_custom_platform_profile`**
- Create custom profile for new platform
- Requires CSS selectors for chat interface

**`test_platform_detection`**
- Test platform detection on current page
- Validates configuration

### Agent Management Tools

**`spawn_worker_agent`**
- Spawns worker agent for customer chat
- Automatically starts event monitoring if `chat_id` + `platform_id` provided

**`stop_worker_agents`**
- Stops worker agents
- Automatically cleans up event monitoring

**`get_worker_agent_status`**
- Get status of worker agents
- Includes event monitoring statistics

**`list_worker_agents`**
- List all active worker agents

---

## Performance Comparison

### Before (Polling Only)

```
Orchestrator polls dashboard every 5 seconds
  ↓
Detects new message (0-5s delay)
  ↓
Spawns worker agent
  ↓
Worker polls for new messages every 5 seconds
  ↓
Total response time: 0-10 seconds
```

### After (Event-Driven)

```
New message arrives in browser
  ↓
CDP event fires (<100ms)
  ↓
Event routed to worker agent
  ↓
Worker resumes immediately
  ↓
Total response time: <100ms
```

**For polling-based platforms:**
```
New message arrives in browser
  ↓
Polling detects change (0-3s)
  ↓
Event routed to worker agent
  ↓
Worker resumes
  ↓
Total response time: 0-3s
```

---

## Troubleshooting

### Platform Not Detected

1. Check URL matches profile patterns:
   ```python
   detector = get_platform_detector()
   platform_id = detector.detect_platform(url)
   ```

2. Add custom profile if needed:
   ```python
   # Use create_custom_platform_profile MCP tool
   ```

### Chat ID Extraction Failing

1. Check extraction rules in profile:
   ```python
   profile = detector.get_profile(platform_id)
   extraction_rules = profile['chat_id_extraction']
   ```

2. Test extraction manually:
   ```python
   from agent.ec_tasks.chat_id_extractor import extract_chat_id_from_browser
   chat_id = extract_chat_id_from_browser(browser_session, profile)
   ```

3. Add custom extraction rule to profile

### Events Not Firing

1. Check CDP client is available
2. Verify event subscriptions:
   ```python
   stats = dispatcher.get_stats(monitor_id)
   # Check cdp_subscriptions count
   ```

3. Polling fallback should still work (check poll_event_count)

### High Duplicate Count

- Normal for platforms with both CDP events and polling
- Deduplication prevents duplicate processing
- Check `duplicate_count` in stats

---

## File Structure

```
agent/ec_tasks/
├── platform_profiles.json          # Platform configurations
├── platform_detector.py            # Auto-detection
├── chat_event_dispatcher.py        # Event coordination
├── chat_id_extractor.py            # ID extraction
├── polling_service.py              # Intelligent polling
├── browser_event_service.py        # CDP event handling
├── agent_management_mcp_tools.py   # Worker spawning (updated)
└── platform_config_mcp_tools.py    # Configuration tools (new)
```

---

## Next Steps

1. **Test on your platforms**: Use `test_platform_detection` to verify
2. **Monitor performance**: Check `get_worker_agent_status` for event stats
3. **Add custom platforms**: Use `create_custom_platform_profile` for unsupported platforms
4. **Optimize polling**: Adjust `polling_interval_ms` in profiles as needed
