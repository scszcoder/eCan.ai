# IM Workbench Node Prompt Snippets

## 1) 单会话节点 Prompt

```text
Operate the IM workbench at http://localhost:4173.

Goal:
Handle one urgent customer session from start to finish.

Steps:
1. Open http://localhost:4173
2. Verify [data-testid="im-workbench-page"] exists
3. Click [data-testid="session-tab-urgent"]
4. Click the first [data-testid^="session-item-"]
5. Verify [data-testid="active-session"] exists
6. Read the latest [data-testid^="message-bubble-customer-"]
7. In [data-testid="knowledge-card"], click the first [data-testid^="knowledge-use-"] if available
8. Verify [data-testid="reply-input"] has content; if empty, type: Hello, I checked your request and I’m helping you now.
9. Click [data-testid="send-button"]
10. Confirm a new [data-testid^="message-bubble-agent-"] appears
11. Confirm [data-testid="timeline"] contains a new [data-testid^="timeline-event-"]
12. Return:
   - active session title
   - latest customer message
   - reply sent: yes/no
   - timeline updated: yes/no
   - blocker if any

Rules:
- Prefer data-testid selectors
- Do not modify code
- If the page changes, re-read before continuing
```

## 2) 多会话轮询节点 Prompt

```text
Operate the IM workbench at http://localhost:4173.

Goal:
Process up to 3 sessions in one round, prioritizing urgent sessions.

Steps:
1. Open http://localhost:4173
2. Verify [data-testid="im-workbench-page"] exists
3. Click [data-testid="scenario-option-burst"]
4. Click [data-testid="session-tab-urgent"] and collect up to 3 [data-testid^="session-item-"]
5. If fewer than 3 urgent sessions exist, switch to [data-testid="session-tab-active"] and collect more
6. For each selected session, do:
   a. Click session item
   b. Verify [data-testid="active-session"] changed
   c. Read latest [data-testid^="message-bubble-customer-"]
   d. Read [data-testid^="sla-timer-"]
   e. Click first [data-testid^="knowledge-use-"] if available
   f. Ensure [data-testid="reply-input"] has content, or type: Thanks for your message. I’m reviewing this now.
   g. Click [data-testid="send-button"]
   h. Confirm a new [data-testid^="message-bubble-agent-"] appears
   i. Confirm [data-testid^="timeline-event-"] updated
   j. Record result for this session
7. Return summary:
   - total processed sessions
   - success list
   - failed sessions
   - blocker reasons

Rules:
- Use data-testid selectors first
- Process one session at a time
- Re-check the DOM after each session because burst mode may reorder sessions
- Do not modify code
```
