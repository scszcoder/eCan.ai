# Multi-Customer Chat Orchestration - Event-Driven Architecture

This document describes eCan.ai's event-driven multi-customer chat orchestration system that uses platform profiles, CDP events, and intelligent polling to achieve near-instant response times (<100ms for event-driven platforms, 2-3s for polling-based platforms).

## Architecture Overview

The system uses a **hybrid detection approach** that combines:
1. **CDP Events** (Chrome DevTools Protocol) - For platforms with WebSocket/API events
2. **Intelligent Polling** - Adaptive fallback with 2-3s intervals
3. **Platform Profiles** - Pre-configured detection rules for 8+ e-commerce platforms
4. **Chat ID Extraction** - Multi-strategy extraction with priority-based fallback
  ├─ Monitors dashboard every 5 seconds
  ├─ Detects new customer messages
  └─ Spawns Worker Agents (1 per customer)

Worker Agents (20+)
  ├─ Each handles 1 customer chat
  ├─ Runs in isolated browser tab
  └─ Completes in <18 seconds
```

---

## 1. Orchestrator Agent Prompt

### Agent Type: Monitoring Orchestrator
### Skill: `monitor_customer_chats_orchestrator.json`
### Node: `check_dashboard` (browser_automation)

**Purpose:** Continuously monitor the customer chat dashboard and extract customers with new unread messages.

**Prompt Template:**

```
Navigate to the customer chat dashboard at https://your-ecommerce-site.com/chat-dashboard.

Extract all customers who have new unread messages. For each customer, get:
1. Customer ID (unique identifier)
2. Customer name
3. Chat URL (direct link to their chat page)
4. Message preview (first 50 chars of their latest message)

Return the data as JSON in this exact format:
{
  "new_customers": [
    {
      "id": "customer_123",
      "name": "John Doe",
      "chat_url": "https://your-ecommerce-site.com/chat/customer_123",
      "message_preview": "Hi, I have a question about my order..."
    }
  ]
}

IMPORTANT: Only include customers with NEW unread messages (highlighted or marked as unread in the UI).
```

**Configuration:**
- `flashMode`: `true` (2-3x speed boost)
- `maxSteps`: `5` (quick extraction only)
- `maxActionsPerStep`: `3` (batch actions)
- `timeout_seconds`: `10` (fast monitoring cycle)
- `browser`: `reuse existing` (share browser session)

**Expected Output:**
```json
{
  "new_customers": [
    {"id": "cust_001", "name": "Alice", "chat_url": "https://...", "message_preview": "Where is my order?"},
    {"id": "cust_002", "name": "Bob", "chat_url": "https://...", "message_preview": "Can I return this item?"}
  ]
}
```

---

## 2. Worker Agent Prompts

### Agent Type: Customer Chat Handler
### Skill: Dynamically generated 1-node skill
### Node: `handle_chat` (browser_automation)

**Purpose:** Handle a single customer's chat message with professional, helpful response.

### 2.1 Default Worker Prompt Template

**Used when:** No custom prompt specified in `WorkerAgentManager.spawn_worker()`

```
Navigate to {chat_url} and handle the customer's latest message.

Read the message, provide an appropriate response, and send it.

Be professional, helpful, and concise.
```

**Variables:**
- `{chat_url}`: Direct URL to customer's chat page (e.g., `https://site.com/chat/customer_123`)

**Configuration:**
- `flashMode`: `true` (maximum speed)
- `maxSteps`: `15` (sufficient for most chats)
- `maxActionsPerStep`: `5` (batch actions)
- `timeout_seconds`: `18` (hard limit for <20s SLA)
- `hard_timeout`: `true` (cancel on timeout)
- `browser`: `reuse existing` (share browser, new tab)

---

### 2.2 E-Commerce Order Inquiry Prompt

**Used when:** Customer asking about order status

```
Navigate to {chat_url}.

The customer has a question about their order. Follow these steps:

1. Read the customer's message carefully
2. Check if they provided an order number
3. If order number is provided:
   - Look up the order status in the system
   - Provide accurate tracking information
   - Estimate delivery date if available
4. If no order number:
   - Politely ask for the order number
   - Explain how they can find it (email confirmation, account page)
5. Send the response

Be empathetic and professional. If you cannot find the order, apologize and offer to escalate to a human agent.
```

**Example Response:**
> "Hi! I see you're asking about order #12345. I've checked our system and your order is currently in transit. Expected delivery: March 20, 2026. You can track it here: [tracking link]. Is there anything else I can help with?"

---

### 2.3 Product Return/Refund Prompt

**Used when:** Customer wants to return or refund

```
Navigate to {chat_url}.

The customer wants to return or refund a product. Follow these steps:

1. Read the customer's message and identify:
   - Product name/SKU
   - Order number
   - Reason for return
2. Check our return policy (within 30 days, unused condition)
3. If eligible:
   - Provide return instructions
   - Generate return label if system allows
   - Explain refund timeline (5-7 business days)
4. If not eligible:
   - Politely explain why (outside window, used condition, etc.)
   - Offer alternatives (exchange, store credit)
5. Send the response

Be understanding and solution-oriented. Customer satisfaction is priority.
```

**Example Response:**
> "I understand you'd like to return the blue sweater from order #12345. Good news - you're within our 30-day return window! I've generated a prepaid return label (check your email). Once we receive the item, your refund will be processed within 5-7 business days. Would you like me to help with anything else?"

---

### 2.4 Technical Support Prompt

**Used when:** Customer has technical issue with product

```
Navigate to {chat_url}.

The customer is experiencing a technical issue. Follow these steps:

1. Read the issue description carefully
2. Ask clarifying questions if needed:
   - What product/model?
   - When did the issue start?
   - What have they tried already?
3. Provide troubleshooting steps:
   - Start with simplest solutions (restart, check connections)
   - Progress to more advanced steps if needed
   - Use clear, non-technical language
4. If issue persists:
   - Offer to escalate to technical team
   - Provide ticket number for tracking
5. Send the response

Be patient and thorough. Avoid jargon. Confirm each step before moving to next.
```

**Example Response:**
> "I'm sorry to hear your wireless headphones aren't connecting. Let's try these steps: 1) Turn off Bluetooth on your phone, 2) Press and hold the power button on headphones for 10 seconds until light flashes, 3) Turn Bluetooth back on and search for devices. Did that work? If not, I can escalate this to our technical team."

---

### 2.5 General Inquiry Prompt

**Used when:** Customer has general question

```
Navigate to {chat_url}.

The customer has a general question. Follow these steps:

1. Read the question carefully
2. Determine the category:
   - Product information → Provide specs, features, pricing
   - Shipping → Explain options, costs, timelines
   - Payment → Explain accepted methods, security
   - Account → Help with login, password, profile
   - Other → Answer directly or escalate
3. Provide accurate, helpful information
4. Offer related help ("Anything else I can assist with?")
5. Send the response

Be friendly and informative. If you don't know the answer, say so and offer to find out.
```

**Example Response:**
> "Great question! Our premium membership includes: free shipping on all orders, early access to sales, and 10% off every purchase. It's $9.99/month or $99/year (save $20!). You can try it free for 30 days. Would you like me to help you sign up?"

---

## 3. Customizing Worker Prompts

### Method 1: Pass Custom Prompt to WorkerAgentManager

```python
# In orchestrator's spawn_workers code node:
custom_prompt = """
Navigate to {chat_url}.

[Your custom instructions here]

Be professional and helpful.
"""

manager.spawn_worker(
    customer_id=customer['id'],
    chat_url=customer['chat_url'],
    custom_prompt=custom_prompt,
)
```

### Method 2: Use Prompt Variables

```python
# Use state["prompt_refs"] for dynamic values
custom_prompt = """
Navigate to {{chat_url}}.

Customer: {{customer_name}}
Previous interactions: {{interaction_count}}

[Your instructions here]
"""

# Set prompt_refs before spawning
state["prompt_refs"]["chat_url"] = customer['chat_url']
state["prompt_refs"]["customer_name"] = customer['name']
state["prompt_refs"]["interaction_count"] = customer['interactions']
```

### Method 3: Category-Based Routing

```python
# In orchestrator's spawn_workers code node:
def get_prompt_for_category(category: str, chat_url: str) -> str:
    prompts = {
        "order_inquiry": f"Navigate to {chat_url}. Handle order status question...",
        "return_refund": f"Navigate to {chat_url}. Process return/refund request...",
        "technical": f"Navigate to {chat_url}. Provide technical support...",
        "general": f"Navigate to {chat_url}. Answer general question...",
    }
    return prompts.get(category, prompts["general"])

# Detect category from message preview
category = detect_category(customer['message_preview'])
custom_prompt = get_prompt_for_category(category, customer['chat_url'])

manager.spawn_worker(
    customer_id=customer['id'],
    chat_url=customer['chat_url'],
    custom_prompt=custom_prompt,
)
```

---

## 4. Performance Optimization Tips

### For <20s Response Time:

1. **Enable Flash Mode** (CRITICAL)
   - `flashMode: true` → 2-3x speed boost
   - Skips evaluation/thinking steps

2. **Limit Steps**
   - `maxSteps: 15` → Prevents runaway agents
   - Most chats complete in 5-10 steps

3. **Batch Actions**
   - `maxActionsPerStep: 5` → Allows parallel actions
   - Example: Read message + compose response + send (3 actions in 1 step)

4. **Hard Timeout**
   - `timeout_seconds: 18` → Hard limit
   - `hard_timeout: true` → Cancel on timeout (don't retry)

5. **Concise Prompts**
   - Shorter prompts = faster LLM processing
   - Be specific, avoid verbose instructions

6. **Reuse Browser**
   - `browser: "reuse existing"` → Share browser session
   - Each worker gets new tab (isolated)

---

## 5. Testing Your Prompts

### Test Single Worker

```python
from agent.ec_tasks.agent_management_mcp_tools import spawn_worker_agent, get_worker_agent_status

# Spawn test worker
result = spawn_worker_agent(
    mainwin=mainwin,
    config={
        "worker_name": "test_worker_001",
        "orchestrator_agent_id": "test_orch",
        "skill_name": "handle_customer_chat",
        "timeout": 18,
        "metadata": {
            "customer_id": "test_001",
            "chat_url": "https://your-site.com/chat/test_001"
        }
    }
)

# Check status
import time
time.sleep(20)
status = get_worker_agent_status(
    mainwin=mainwin,
    config={"worker_id": result["worker_id"]}
)
print(f"Status: {status}")
```

### Benchmark Performance

```python
import time

start = time.time()

# Spawn 5 workers
for i in range(5):
    manager.spawn_worker(
        customer_id=f"test_{i}",
        chat_url=f"https://your-site.com/chat/test_{i}",
    )

# Wait for completion
while manager.get_active_count() > 0:
    time.sleep(1)
    manager.cleanup_completed_workers()

elapsed = time.time() - start
print(f"5 workers completed in {elapsed:.1f}s")
# Target: <20s for all 5
```

---

## 6. Troubleshooting

### Worker Takes >20s

**Possible causes:**
- Prompt too complex → Simplify instructions
- Too many steps → Reduce `maxSteps`
- Flash mode disabled → Enable `flashMode: true`
- Slow website → Optimize page load or use faster selectors

**Solution:**
```python
# Ultra-fast configuration
manager.spawn_worker(
    customer_id=customer_id,
    chat_url=chat_url,
    timeout=15,  # Even stricter
    flash_mode=True,
    max_steps=10,  # Fewer steps
    max_actions_per_step=10,  # More batch actions
)
```

### Worker Fails to Find Message

**Possible causes:**
- Chat UI changed → Update selectors in prompt
- Message not loaded → Add wait instruction
- Wrong tab focused → Check browser session

**Solution:**
```
Navigate to {chat_url}.

Wait for the chat interface to fully load (look for message input box).

Scroll to the bottom of the chat to see the latest message.

Read the customer's most recent message (it should be highlighted or at the bottom).

[Rest of instructions...]
```

### Multiple Workers Interfere

**Possible causes:**
- Sharing same tab → Each should get new tab
- Browser session conflict → Check `_cached_browser_session`

**Solution:** Workers automatically get isolated tabs via browser-use CDP protocol. No action needed.

---

## 7. Advanced: Multi-Language Support

```python
# Detect language from message preview
def detect_language(message: str) -> str:
    # Simple heuristic or use language detection library
    if any(ord(c) > 0x4e00 for c in message):
        return "zh"  # Chinese
    return "en"  # English

# Language-specific prompts
prompts = {
    "en": "Navigate to {chat_url}. Read and respond to the customer's message professionally.",
    "zh": "导航到 {chat_url}。阅读并专业地回复客户的消息。",
}

lang = detect_language(customer['message_preview'])
custom_prompt = prompts.get(lang, prompts["en"]).format(chat_url=customer['chat_url'])

manager.spawn_worker(
    customer_id=customer['id'],
    chat_url=customer['chat_url'],
    custom_prompt=custom_prompt,
)
```

---

## Summary

**Orchestrator Prompt:** Extract new customers from dashboard → Return JSON
**Worker Prompt:** Navigate to chat → Read message → Respond professionally

**Key Settings for <20s:**
- `flashMode: true`
- `maxSteps: 15`
- `maxActionsPerStep: 5`
- `timeout_seconds: 18`

**Customization:** Pass `custom_prompt` to `spawn_worker()` for specialized handling.
